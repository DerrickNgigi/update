from meter_gsm import gsmInitialization, gsmCheckStatus
from meter_mqtts import mqttInitialize, mqtt, mqttPublish
from meter import (
    read_cumulative_flow, read_instantaneous_flow, read_cell_voltage,
    open_valve, close_valve, monitor_target, read_meter_parameters, valve_test, read_meter_parameters_upload
)
from meter_storage import *
from ota_update import *
from machine import UART
from utime import sleep, time
import _thread
import globals
import machine
import json
import gc

# ============ UART CONFIGURATION ============ #
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# ============ MODBUS Slave Addresses ============ #
SLAVE_ADDRESSES = globals.SLAVE_ADDRESSES

# ============ MQTT CONFIGURATION ============ #
MQTT_PUB_TOPIC = globals.MQTT_PUB_TOPIC
MQTT_SUB_TOPICS = globals.MQTT_SUB_TOPICS

# ============ Device CONFIGURATION ============ #

# ============ MONITOR THREAD ============ #

def print_sleep_duration(timer_value):
    # Convert seconds to minutes and seconds
    minutes = timer_value // 60
    seconds = timer_value % 60

    if minutes > 0:
        duration_text = "%d minute%s" % (minutes, "s" if minutes > 1 else "")
        if seconds:
            duration_text += " and %d second%s" % (seconds, "s" if seconds > 1 else "")
    else:
        duration_text = "%d second%s" % (seconds, "s" if seconds > 1 else "")

    print("✅ Monitoring complete. Sleeping for %s.\n" % duration_text)

def monitor_loop():
    # Initialize watchdog (30 minutes = 1800 seconds)
    gc.collect()
    print("Free mem:", gc.mem_free())

    while True:
        print("\n🕒 Running periodic meter monitoring...")

        # Garbage collect to free up memory
        gc.collect()
        print("Free mem:", gc.mem_free())

        # Check GSM status before continuing
        if gsmCheckStatus() != 1:
            print("⚠ GSM not connected. Restarting system...")
            sleep(3)
            machine.reset()
        else:
            print("📶 GSM connected.")

        # Read meter data and publish
        meter_data = read_meter_parameters_upload(uart, SLAVE_ADDRESSES)
        if meter_data:
            try:
                mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps(meter_data))
                print("📤 Meter data published successfully.")
            except Exception as e:
                print("❌ MQTT publish failed:", e)
        else:
            print("⚠ No data received from meters.")

        # Monitor target (non-returning side effect)
        try:
            monitor_target(uart, SLAVE_ADDRESSES)
        except Exception as e:
            print("⚠ Error during monitor_target:", e)

        print_sleep_duration(globals.timer)

        # Sleep for 30 minutes
        for _ in range(globals.timer):  # 30 minutes = 1800 seconds
            sleep(1)


# ============ MAIN EXECUTION ============ #
def main():
    print("🚀 Machine booting...")
    
    sleep(8)

    # Initial Valve Test
    print("🔧 Testing valves...")
    valve_test(uart, SLAVE_ADDRESSES)
    sleep(1)
    
    # Initial meter parameter read
    print("📊 Reading initial meter parameters...")
    read_meter_parameters(uart, SLAVE_ADDRESSES)
    sleep(1)    
    
    # Initial target monitoring
    print("📊 Monitering Units...")
    monitor_target(uart, SLAVE_ADDRESSES)
    
    # Garbage collect to free up memory
    gc.collect()
    print("Free mem:", gc.mem_free())

    # Initialize GSM Module
    print("📡 Initializing GSM module...")
    sleep(4)
    gsmInitialization()

    # Wait for GSM signal before continuing
    while gsmCheckStatus() != 1:
        print("📶 Waiting for GSM connection...")
        sleep(1)
    print("✅ GSM connected.")
    
    gc.collect()
    print("Free mem:", gc.mem_free())
    
    # Check on global variable updates
    update_global_file(globals.MQTT_CLIENT_ID, retries=3)
    gc.collect()
    print("Free mem:", gc.mem_free())    
    
    # Check on files updates
    run_ota()
    gc.collect()
    print("Free mem:", gc.mem_free())
    
    sleep(3)
    
    
    

    # Start MQTT listener thread
    print("🔌 Starting MQTT listener thread...")
    _thread.start_new_thread("MqttListener", mqttInitialize, (mqtt, MQTT_SUB_TOPICS,))

    sleep(10)
    
    # Start periodic monitoring thread
    print("🧵 Starting periodic meter monitor thread...")
    _thread.start_new_thread("MeterMonitor", monitor_loop, ())

    print("✅ System initialization complete. Now running...")

# ============ ENTRY POINT ============ #
if __name__ == "__main__":
    main()



