from meter_gsm import gsmInitialization, gsmCheckStatus
from meter_mqtts import mqttInitialize, mqtt, mqttPublish
from meter import (
    read_cumulative_flow, open_valve, close_valve, monitor_target,
    read_meter_parameters, valve_test, read_meter_parameters_upload
)
from meter_storage import *
from ota_update import *
from machine import UART
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
                # Check file size (Delete if > 10KB)
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
    safe_gc()
    mqtt_fail_count = 0
    MAX_MQTT_RETRIES = 10
    
    # Give the system 60 seconds of "Grace Period" where we don't reboot on MQTT failure
    # This allows the slow GSM/MQTT connection to establish on boot.
    boot_grace_period = 60 
    start_time = time()

    while True:
        try:
            safe_gc()
            
            # 1. Midnight Check
            check_scheduled_restart()

            # 2. GSM Check (Strict)
            # We assume GSM was initialized in Main. If it drops here, we must reset.
            if gsmCheckStatus() != 1:
                sys_log("GSM disconnected in Loop. Resetting.", "ERROR")
                sleep(3)
                machine.reset()

            # 3. MQTT Check with STARTUP PROTECTION
            mqtt_connected = False
            
            # Check if we are still in the boot-up grace period
            is_booting = (time() - start_time) < boot_grace_period

            if mqtt is None:
                # MQTT thread hasn't finished initializing the object yet. 
                # Do NOT increment failure count. Just wait.
                if not is_booting:
                    print("Waiting for MQTT Object initialization...")
            else:
                # MQTT Object exists, let's try to Ping
                try:
                    mqtt.ping()
                    mqtt_connected = True
                    mqtt_fail_count = 0 # Reset counter on success
                except:
                    # Ping failed.
                    if is_booting:
                        print("MQTT Ping failed (Booting...) - Ignoring")
                    else:
                        mqtt_fail_count += 1
                        print("MQTT Ping Failed {}/{}".format(mqtt_fail_count, MAX_MQTT_RETRIES))
                        
                        if mqtt_fail_count >= MAX_MQTT_RETRIES:
                            sys_log("MQTT Dead after retries. Resetting.", "ERROR")
                            sleep(2)
                            machine.reset()
            
            # 4. Read & Upload (Only if Connected)
            if mqtt_connected:
                try:
                    read_meter_parameters_upload(uart, SLAVE_ADDRESSES, mqttPublish, mqtt, MQTT_PUB_TOPIC)
                except Exception as e:
                    sys_log("Read/Upload Fail: {}".format(e), "ERROR")
            
            # 5. Monitor Target
            try:
                monitor_target(uart, SLAVE_ADDRESSES)
            except Exception:
                pass 

            # Sleep
            for _ in range(globals.timer):
                sleep(1)

        except Exception as e:
            sys_log("Loop Crash: {}".format(e), "ERROR")
            sleep(5)
            machine.reset()

# ============ MAIN EXECUTION ============ #
def main():
    sys_log("Booting...", "BOOT")
    sleep(2)
    safe_gc()

    try:
        # 1. Hardware Tests (Local only, no GSM needed)
        valve_test(uart, SLAVE_ADDRESSES)
        read_meter_parameters(uart, SLAVE_ADDRESSES)
        monitor_target(uart, SLAVE_ADDRESSES)

        # 2. Initialize GSM (CRITICAL STEP)
        sys_log("Initializing GSM...", "INFO")
        gsmInitialization()
        
        # Block and wait until GSM is actually ready
        wait_cycles = 0
        while gsmCheckStatus() != 1:
            print("Waiting for GSM Signal...")
            sleep(1)
            wait_cycles += 1
            if wait_cycles > 60: # If no GSM after 60s, reboot
                 sys_log("GSM Init Timeout. Rebooting.", "ERROR")
                 machine.reset()
        
        sys_log("GSM Connected.", "INFO")

        # 3. OTA Updates (Requires GSM)
        gc.collect()
        try:
            update_global_file(globals.MQTT_CLIENT_ID, retries=3)
            gc.collect()
            run_ota()
            gc.collect()
        except Exception as e:
            sys_log("OTA Fail: {}".format(e), "ERROR")

        # 4. Start MQTT Thread (Now that GSM is ready)
        _thread.start_new_thread("MqttListener", mqttInitialize, (mqtt, MQTT_SUB_TOPICS,))
        
        # 5. Start Monitor Thread
        # We give MQTT thread a slight head start, but the loop has a "grace period" logic now.
        sleep(5) 
        _thread.start_new_thread("MeterMonitor", monitor_loop, ())

        sys_log("System Running", "INFO")

    except Exception as e:
        sys_log("Main Crash: {}".format(e), "ERROR")
        sleep(5)
        machine.reset()

if __name__ == "__main__":
    main()