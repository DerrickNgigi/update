from meter_gsm import gsmInitialization, gsmCheckStatus
from meter_mqtts import mqttInitialize, mqtt, mqttPublish
from meter import (
    read_cumulative_flow, read_instantaneous_flow, read_cell_voltage,
    open_valve, close_valve, monitor_target, read_meter_parameters, valve_test, read_meter_parameters_upload
)
from meter_storage import *
from lobo_wifi import wifiInitialize
from machine import UART
from utime import sleep, time
import _thread
import globals
import machine
import json
from machine import WDT, reset
import gc


# ============ UART CONFIGURATION ============ #
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# ============ MODBUS Slave Addresses ============ #
SLAVE_ADDRESSES = [12, 13, 14, 15]

# ============ MQTT CONFIGURATION ============ #
MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10006/pub/controlcomm/message'

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10006-12/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-13/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-14/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-15/sub/controlcomm/message"
]


# ============ MONITOR THREAD ============ #
def monitor_loop():
    # Initialize watchdog (30 minutes = 1800 seconds)

    while True:
        print("\n🕒 Running periodic meter monitoring...")

        # Garbage collect to free up memory
        gc.collect()

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

        print("✅ Monitoring complete. Sleeping for 30 minutes.\n")

        # Sleep for 30 minutes
        for _ in range(1800):  # 30 minutes = 1800 seconds
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

    # Initialize GSM Module
    print("📡 Initializing GSM module...")
    sleep(4)
    gsmInitialization()

    # Wait for GSM signal before continuing
    while gsmCheckStatus() != 1:
        print("📶 Waiting for GSM connection...")
        sleep(1)
    print("✅ GSM connected.")

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


