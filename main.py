from meter_gsm import gsmInitialization, gsmCheckStatus
from meter_mqtts import mqttInitialize, mqtt, mqttPublish
from meter import (
    read_cumulative_flow, open_valve, close_valve, monitor_target,
    read_meter_parameters, valve_test, read_meter_parameters_upload
)
from meter_storage import *
from ota_update import *
from machine import UART, WDT
from utime import sleep, time, localtime
import _thread
import globals
import machine
import json
import gc
import os

# ============ UART CONFIGURATION ============ #
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)

# ============ CONFIGURATION ============ #
SLAVE_ADDRESSES = globals.SLAVE_ADDRESSES
MQTT_PUB_TOPIC = globals.MQTT_PUB_TOPIC
MQTT_SUB_TOPICS = globals.MQTT_SUB_TOPICS
LOG_FILE = "system_error.log"

# ============ GLOBAL WATCHDOG ============ #
wdt = None 

# ============ LOGGER & MEMORY HELPERS ============ #
def sys_log(msg, level="INFO"):
    """
    INFO: Print to console only.
    ERROR: Print to console AND write to file.
    """
    try:
        t = localtime()
        timestamp = "{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[1], t[2], t[3], t[4], t[5])
        formatted_msg = "[{}] [{}] {}".format(timestamp, level, msg)
        
        print(formatted_msg)

        if level == "ERROR" or level == "BOOT":
            try:
                try:
                    if os.stat(LOG_FILE)[6] > 10240:
                        os.remove(LOG_FILE)
                except OSError:
                    pass 

                with open(LOG_FILE, 'a') as f:
                    f.write(formatted_msg + '\n')
            except Exception:
                pass 
    except Exception:
        print(msg) 

def safe_gc():
    """Silent GC."""
    gc.collect()
    free = gc.mem_free()
    if free < 10240:
        sys_log("Low RAM: {}b. Rebooting.".format(free), "ERROR")
        sleep(2)
        machine.reset()

# ============ TIME HELPER ============ #
def check_scheduled_restart():
    """Midnight (00:00) Restart."""
    t = localtime()
    if t[3] == 0 and 0 <= t[4] < 2: 
        sys_log("Midnight Maintenance Restart", "BOOT")
        sleep(1)
        machine.reset()

# ============ MONITOR THREAD ============ #
def monitor_loop():
    global wdt
    
    # 1. SETUP WATCHDOG - 300 Seconds (5 Minutes)
    # This is the maximum hardware limit. We cannot set it to 30 mins.
    try:
        wdt = WDT(timeout=300000) 
        sys_log("Watchdog Enabled (300s limit)", "INFO")
    except Exception:
        sys_log("Could not start WDT", "ERROR")

    safe_gc()
    mqtt_fail_count = 0
    MAX_MQTT_RETRIES = 10
    
    boot_grace_period = 60 
    start_time = time()

    while True:
        try:
            # Feed WDT at start of active cycle
            if wdt: wdt.feed()

            safe_gc()
            
            # --- ACTIVE TASKS (Takes ~10-30 seconds) ---
            check_scheduled_restart()

            if gsmCheckStatus() != 1:
                sys_log("GSM disconnected in Loop. Resetting.", "ERROR")
                sleep(3)
                machine.reset()

            mqtt_connected = False
            is_booting = (time() - start_time) < boot_grace_period

            if mqtt is None:
                pass 
            else:
                try:
                    mqtt.ping()
                    mqtt_connected = True
                    mqtt_fail_count = 0 
                except:
                    if not is_booting:
                        mqtt_fail_count += 1
                        print("MQTT Ping Failed {}/{}".format(mqtt_fail_count, MAX_MQTT_RETRIES))
                        if mqtt_fail_count >= MAX_MQTT_RETRIES:
                            sys_log("MQTT Dead. Resetting.", "ERROR")
                            sleep(2)
                            machine.reset()
            
            if mqtt_connected:
                try:
                    read_meter_parameters_upload(uart, SLAVE_ADDRESSES, mqttPublish, mqtt, MQTT_PUB_TOPIC)
                except Exception as e:
                    sys_log("Read/Upload Fail: {}".format(e), "ERROR")
            
            try:
                monitor_target(uart, SLAVE_ADDRESSES)
            except Exception:
                pass 

            # --- LONG SLEEP (e.g., 30 Minutes) ---
            # We must prevent the 5-minute watchdog from killing us,
            # but we will only touch it occasionally.
            
            # This feed happens right before sleep starts
            if wdt: wdt.feed() 
            
            for i in range(globals.timer):
                # We calculate when to feed. 
                # 120 seconds = 2 minutes.
                # If we are sleeping for 30 minutes, we will only feed ~15 times total.
                # This minimizes interference significantly.
                if i > 0 and i % 120 == 0:
                     if wdt: wdt.feed()
                
                sleep(1)

        except Exception as e:
            sys_log("Loop Crash: {}".format(e), "ERROR")
            sleep(5)
            machine.reset()

# ============ MAIN EXECUTION ============ #
def main():
    gc.enable()
    gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

    sys_log("Booting...", "BOOT")
    sleep(2)
    safe_gc()

    try:
        valve_test(uart, SLAVE_ADDRESSES)
        read_meter_parameters(uart, SLAVE_ADDRESSES)
        monitor_target(uart, SLAVE_ADDRESSES)

        sys_log("Initializing GSM...", "INFO")
        gsmInitialization()
        
        wait_cycles = 0
        while gsmCheckStatus() != 1:
            print("Waiting for GSM Signal...")
            sleep(1)
            wait_cycles += 1
            if wait_cycles > 120: 
                 sys_log("GSM Init Timeout. Rebooting.", "ERROR")
                 machine.reset()
        
        sys_log("GSM Connected.", "INFO")

        gc.collect()
        try:
            update_global_file(globals.MQTT_CLIENT_ID, retries=3)
            gc.collect()
            run_ota()
            gc.collect()
        except Exception as e:
            sys_log("OTA Fail: {}".format(e), "ERROR")

        _thread.start_new_thread("MqttListener", mqttInitialize, (mqtt, MQTT_SUB_TOPICS,))
        
        sleep(5) 
        _thread.start_new_thread("MeterMonitor", monitor_loop, ())

        sys_log("System Running", "INFO")
        
        while True:
            sleep(10)

    except Exception as e:
        sys_log("Main Crash: {}".format(e), "ERROR")
        sleep(5)
        machine.reset()

if __name__ == "__main__":
    main()