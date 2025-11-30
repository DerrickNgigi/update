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

def smart_sleep(seconds):
    """
    Sleeps for 'seconds' while keeping the Watchdog alive.
    Feeds the dog every 10 seconds.
    """
    # Loop in 10-second chunks
    for _ in range(seconds // 10):
        if wdt: wdt.feed()
        sleep(10)
    
    # Sleep remaining seconds (if any)
    remaining = seconds % 10
    if remaining > 0:
        sleep(remaining)
        
    if wdt: wdt.feed() # Feed one last time on wake up

# ============ MONITOR THREAD (SIMPLIFIED) ============ #
def monitor_loop():
    global wdt
    
    # 1. SETUP WATCHDOG - 300 Seconds (5 Minutes)
    try:
        wdt = WDT(timeout=300000) 
        sys_log("Watchdog Enabled (300s limit)", "INFO")
    except Exception:
        sys_log("Could not start WDT", "ERROR")

    safe_gc()
    
    # --- RESTORED VARIABLES ---
    mqtt_fail_count = 0
    MAX_MQTT_RETRIES = 10  # Set to 10 as requested

    while True:
        try:
            # --- START OF CYCLE ---
            if wdt: wdt.feed()
            safe_gc()
            
            # 1. Midnight Check
            check_scheduled_restart()

            # 2. GSM Check
            if gsmCheckStatus() != 1:
                sys_log("GSM disconnected in Loop. Resetting.", "ERROR")
                sleep(3)
                machine.reset()

            # 3. MQTT Health Check
            can_upload = False
            try:
                if mqtt:
                    mqtt.ping()
                    can_upload = True
                    mqtt_fail_count = 0 # Success, reset counter
                else:
                    raise Exception("No MQTT Object")
            except:
                mqtt_fail_count += 1
                print("MQTT Ping Failed ({}/{})".format(mqtt_fail_count, MAX_MQTT_RETRIES))
                
                # Check against MAX_MQTT_RETRIES (10)
                if mqtt_fail_count >= MAX_MQTT_RETRIES:
                    sys_log("MQTT Dead. Rebooting.", "ERROR")
                    sleep(2)
                    machine.reset()

            # 4. UPLOAD (Only if check passed)
            if can_upload:
                try:
                    read_meter_parameters_upload(uart, SLAVE_ADDRESSES, mqttPublish, mqtt, MQTT_PUB_TOPIC)
                except Exception as e:
                    sys_log("Read/Upload Fail: {}".format(e), "ERROR")
            
            # 5. Local Monitor
            try:
                monitor_target(uart, SLAVE_ADDRESSES)
            except Exception:
                pass 

            # 6. SLEEP
            # Use smart_sleep to handle the timer and watchdog automatically
            smart_sleep(globals.timer)

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
        read_meter_parameters(uart, SLAVE_ADDRESSES)

        # Initialize GSM (BLOCKING WAIT)
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

        # OTA Updates
        gc.collect()
        try:
            update_global_file(globals.MQTT_CLIENT_ID, retries=3)
            gc.collect()
            run_ota()
            gc.collect()
        except Exception as e:
            sys_log("OTA Fail: {}".format(e), "ERROR")

        # Start Threads
        _thread.start_new_thread("MqttListener", mqttInitialize, (mqtt, MQTT_SUB_TOPICS,))
        
        sleep(5) 
        _thread.start_new_thread("MeterMonitor", monitor_loop, ())

        sys_log("System Running", "INFO")
        
        # Keep Main Alive
        while True:
            sleep(10)

    except Exception as e:
        sys_log("Main Crash: {}".format(e), "ERROR")
        sleep(5)
        machine.reset()

if __name__ == "__main__":
    main()