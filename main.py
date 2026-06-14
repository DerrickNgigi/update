from meter_gsm import gsmInitialization, gsmCheckStatus
import meter_mqtts 
from meter import (
    read_meter_parameters_upload, monitor_target, 
    valve_test, get_valid_volume,
    open_valve, close_valve, 
    save_target_reading, load_target_reading,
    uart, get_valid_valve_status
)
from ota_update import *
from machine import UART, Pin
from utime import sleep, time, localtime
import _thread
import globals
import machine
import gc
import json
import os

# ============ CONFIGURATION ============ #
SLAVE_ADDRESSES = globals.SLAVE_ADDRESSES
MQTT_PUB_TOPIC = globals.MQTT_PUB_TOPIC
MQTT_SUB_TOPICS = globals.MQTT_SUB_TOPICS
LOG_FILE = "system_error.log"

# Status LED (Pin 13)
led = Pin(13, Pin.OUT)

# Global tick to track system health
last_alive_tick = time() 

# ============ UTILITIES ============ #
def sys_log(msg, level="INFO"):
    """Logs messages to console and file. Limits file to ~50KB to prevent storage overflow."""
    try:
        t = localtime()
        timestamp = "{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[1], t[2], t[3], t[4], t[5])
        formatted_msg = "[{}] [{}] {}".format(timestamp, level, msg)
        print(formatted_msg)

        if level == "ERROR" or level == "BOOT":
            write_mode = 'a'
            
            try:
                if os.stat(LOG_FILE)[6] > 31200:
                    write_mode = 'w'
                    formatted_msg = "[{}] [SYSTEM] Log file exceeded 50KB. Wiped and restarted.\n".format(timestamp) + formatted_msg
            except OSError:
                pass

            with open(LOG_FILE, write_mode) as f:
                f.write(formatted_msg + "\n")
    except:
        pass

def safe_gc():
    sys_log("Cleaning Memory...", "DEBUG")
    gc.collect()

def supervisor_thread():
    """Independent thread to check if monitor_loop is alive."""
    global last_alive_tick
    WDT_TIMEOUT = 600 # 10 minutes
    
    while True:
        if (time() - last_alive_tick) > WDT_TIMEOUT:
            sys_log("Monitor Loop Frozen! Rebooting...", "ERROR")
            machine.reset()
        sleep(30)
        
def check_scheduled_restart():
    """Checks for OTA updates at Midnight instead of rebooting."""
    t = localtime()
    # If year > 2024 (time synced) and it is Midnight (00:0X)
    if t[0] > 2024 and t[3] == 0 and 0 <= t[4] < 2: 
        try:
            run_ota()
        except:
            pass
        sleep(60) # Avoid repeating in same minute

def check_for_update_on_start():
    try:
        sys_log("Checking for OTA Updates...", "INFO")
        update_global_file(globals.MQTT_CLIENT_ID, retries=3)
        run_ota()
    except Exception as e:
        sys_log("OTA Error: {}".format(e), "ERROR")

def check_for_initConnection():
    """
    Runs on boot. Optimized for Memory Efficiency.
    1. Checks if a target file exists.
    2. If MISSING: Reads meter and initializes file (Syncs Target = Current).
    """
    # 1. Clear memory before starting heavy IO operations
    gc.collect()
    sys_log("Checking Init States...", "INFO")

    for addr in SLAVE_ADDRESSES:
        try:
            # Load from file (IO Operation)
            saved_target = load_target_reading(addr)
            
            # --- CASE 1: STATE EXISTS (Fast Path) ---
            if saved_target is not None:
                # Log minimal info to save string memory
                # sys_log("Addr {} OK.".format(addr), "DEBUG") 
                saved_target = None # Clear ref
                continue # Skip to next meter immediately

            # --- CASE 2: STATE MISSING (Recovery Path) ---
            sys_log("Addr {} State Missing. Reading...".format(addr), "WARNING")
            
            # Read Hardware
            current_vol = get_valid_volume(uart, addr)
            
            if current_vol is not None:
                # Save to file
                save_target_reading(addr, current_vol)
                sys_log("Init Addr {}: {} L".format(addr, current_vol), "INFO")
            else:
                sys_log("Init Failed Addr {}".format(addr), "ERROR")

        except Exception as e:
            sys_log("Init Err {}: {}".format(addr, e), "ERROR")
        
        # 2. CRITICAL: Clear loop variables to prevent heap fragmentation
        saved_target = None
        current_vol = None
        
    # 3. Final Cleanup: Compacting memory before Main Loop starts
    gc.collect()

# ============ MONITORING CORE ============ #

def monitor_loop():
    """
    Highly Optimized Main Logic Loop.
    - Zero Memory Leak Design: Explicit GC after uploads.
    - High Responsiveness: Checks Queue every 1s.
    - Robust Error Handling: Catches all exceptions to keep loop alive.
    """
    global last_alive_tick
    sys_log("Monitor Loop Started", "INFO")
    
    # --- CONSTANTS (Use consts to save lookup time) ---
    CHECK_INTERVAL = globals.CHECK_INTERVAL   # 3 Minutes
    UPLOAD_INTERVAL = globals.UPLOAD_INTERVAL  # 1 Hour
    RESPONSIVE_SLEEP = globals.RESPONSIVE_SLEEP  # Sleep cycle duration
    
    # Initialize Timers
    # Set upload time to NOW to force an initial upload (or set to time() + 3600 to wait)
    # We set it to time() to prevent immediate upload race condition at boot
    last_upload_time = time() 
    last_check_time = time()
    
    # Pre-allocate reuseable variables to avoid fragmentation
    current_time = 0
    cmd_item = None
    
    # Force initial cleanup
    gc.collect()

    while True:
        try:
            current_time = time()
            last_alive_tick = current_time # Feed Supervisor

            # =================================================
            # 1. IMMEDIATE COMMAND PROCESSING
            # =================================================
            if globals.CMD_QUEUE:
                sys_log("Processing Queue...", "DEBUG")
                
                # Process only 1 command per loop to prevent blocking
                # (or process all if critical, but 1 per loop is safer for RAM)
                while globals.CMD_QUEUE:
                    # --- THREAD LOCK: Safely read/remove from the shared resource ---
                    _thread.lock()
                    cmd_item = globals.CMD_QUEUE.pop(0)
                    _thread.unlock()
                    # ----------------------------------------------------------------
                    
                    # Extract safely
                    cmd = cmd_item.get('cmd')
                    addr = cmd_item.get('addr')
                    dev_id = cmd_item.get('dev_id')
                    
                    sys_log("CMD: {} -> {}".format(cmd, dev_id), "INFO")

                    # --- Command Logic ---
                    if cmd == "check_update":
                        sys_log("Manual OTA...", "INFO")
                        check_for_update_on_start()
                    
                    elif cmd == "check_status":
                        sys_log("Manual Status...", "INFO")
                        read_meter_parameters_upload(
                            uart, SLAVE_ADDRESSES, 
                            meter_mqtts.mqtt.publish, meter_mqtts.mqtt, MQTT_PUB_TOPIC
                        )

                    elif cmd == "success" and addr:
                        litres = cmd_item.get('litres', 0)
                        if litres > 0:
                            # 1. Update Target
                            curr = load_target_reading(addr)
                            if curr is None: curr = 0
                            new_target = curr + litres
                            save_target_reading(addr, new_target)
                            
                            # 2. Publish Confirmation
                            meter_mqtts.mqtt.publish(MQTT_PUB_TOPIC, json.dumps({
                                "type": "device_report", "device": dev_id, 
                                "status": "load_success", "new_target": new_target
                            }))

                            # 3. Enforce Valve (5 Arguments Required)
                            monitor_target(
                                uart, [addr], 
                                meter_mqtts.mqtt.publish, meter_mqtts.mqtt, MQTT_PUB_TOPIC
                            )

                    elif cmd == "valve_open" and addr:
                        open_valve(uart, addr)
                        meter_mqtts.mqtt.publish(MQTT_PUB_TOPIC, json.dumps({
                            "type": "device_report", "device": dev_id, "status": "valve_open"
                        }))
                    
                    elif cmd == "valve_close" and addr:
                        close_valve(uart, addr)
                        meter_mqtts.mqtt.publish(MQTT_PUB_TOPIC, json.dumps({
                            "type": "device_report", "device": dev_id, "status": "valve_closed"
                        }))
                    
                    cmd_item = None
                    last_alive_tick = time() # Feed watchdog after cmd processing

            # =================================================
            # 2. SCHEDULED LOCAL CHECK (Every 3 Mins)
            # =================================================
            if (current_time - last_check_time) >= CHECK_INTERVAL:
                # sys_log("3-Min Check", "DEBUG")
                monitor_target(
                    uart, SLAVE_ADDRESSES, 
                    meter_mqtts.mqtt.publish, meter_mqtts.mqtt, MQTT_PUB_TOPIC
                )
                last_check_time = current_time
                # Clean RAM after check
                gc.collect()

            # =================================================
            # 3. SCHEDULED SERVER UPLOAD (Every 1 Hour)
            # =================================================
            if (current_time - last_upload_time) >= UPLOAD_INTERVAL:
                sys_log("1-Hour Upload...", "INFO")
                read_meter_parameters_upload(
                    uart, SLAVE_ADDRESSES, 
                    meter_mqtts.mqtt.publish, meter_mqtts.mqtt, MQTT_PUB_TOPIC
                )
                last_upload_time = current_time
                
                # CRITICAL: Reclaim memory after heavy upload JSON building
                gc.collect() 

        except Exception as e:
            sys_log("Loop Error: {}".format(e), "ERROR")
            # If error occurred, wait slightly longer to let system stabilize
            sleep(2)
            gc.collect()

        # =================================================
        # 4. RESPONSIVE WAIT (Feed Watchdog)
        # =================================================
        # We break the 5s sleep into 1s chunks to keep the loop responsive
        # AND to feed the watchdog variable frequently.
        for _ in range(RESPONSIVE_SLEEP):
            last_alive_tick = time() # Feed Supervisor every second
            if globals.CMD_QUEUE:
                break # Wake up immediately
            sleep(1)

# ============ MAIN EXECUTION ============ #
def main():
    gc.enable()
    sys_log("Booting...", "BOOT")
    led.value(1)
    sleep(2)
    led.value(0)
    
    # 1. Clear RAM before starting
    safe_gc()

    try:
        sys_log("Initializing GSM...", "INFO")
        gsmInitialization()
        
        wait = 0
        while gsmCheckStatus() != 1:
            print("Waiting for GSM...")
            led.value(not led.value())
            sleep(1)
            wait += 1
            if wait > 120: 
                 sys_log("GSM Timeout. Rebooting.", "ERROR")
                 machine.reset()
        
        sys_log("GSM Connected.", "INFO")
        led.value(1)
        
#         # 2. Run OTA Check
#         check_for_update_on_start()
        
        # 3. Initialize Memory/State
        check_for_initConnection()

        # 4. Start Helper Threads (These are light and fine as threads)
        try:
            _thread.start_new_thread(meter_mqtts.mqttInitialize, (meter_mqtts.mqtt, MQTT_SUB_TOPICS,))
        except TypeError:
             _thread.start_new_thread("MqttListener", meter_mqtts.mqttInitialize, (meter_mqtts.mqtt, MQTT_SUB_TOPICS,))
        
        try:
            _thread.start_new_thread(supervisor_thread, ())
        except TypeError:
            _thread.start_new_thread("Supervisor", supervisor_thread, ())

        # 5. RUN MONITOR LOOP IN MAIN THREAD (Fixes Stack Overflow)
        sys_log("System Running - Entering Monitor Loop", "INFO")
        sleep(5) 
        
        # Call the function directly instead of _thread.start_new_thread
        monitor_loop()

    except Exception as e:
        sys_log("Critical System Failure: {}".format(e), "ERROR")
        sleep(10)
        machine.reset()

if __name__ == "__main__":
    main()

