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


# ============ MEMORY HELPERS ============ #
def safe_gc(tag=""):
    """Force garbage collection and check memory threshold."""
    gc.collect()
    free = gc.mem_free()
    print("🧠 GC run after %s | Free mem: %d" % (tag, free))
    if free < 10240:  # Less than ~10 KB
        print("🚨 Memory critically low (%d). Rebooting..." % free)
        sleep(3)
        machine.reset()


# ============ MONITOR THREAD ============ #
def print_sleep_duration(timer_value):
    """Human-readable sleep time logging."""
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
    """Periodic monitoring of meter data with aggressive GC."""
    safe_gc("monitor_loop_start")

    while True:
        try:
            print("\n🕒 Running periodic meter monitoring...")
            safe_gc("loop_start")

            # GSM Check
            if gsmCheckStatus() != 1:
                print("⚠ GSM not connected. Restarting system...")
                sleep(3)
                machine.reset()
            else:
                print("📶 GSM connected.")

            # Read and publish meter data
            meter_data = None
            try:
                meter_data = read_meter_parameters_upload(uart, SLAVE_ADDRESSES)
                safe_gc("read_meter_parameters_upload")
            except Exception as e:
                print("⚠ Error reading meter data:", e)
                safe_gc("read_meter_exception")

            if meter_data:
                try:
                    mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps(meter_data))
                    print("📤 Meter data published successfully.")
                except Exception as e:
                    print("❌ MQTT publish failed:", e)
                safe_gc("mqtt_publish")
            else:
                print("⚠ No data received from meters.")

            # Monitor target
            try:
                monitor_target(uart, SLAVE_ADDRESSES)
            except Exception as e:
                print("⚠ Error during monitor_target:", e)
            safe_gc("monitor_target")

            # Log sleep
            print_sleep_duration(globals.timer)

            # Sleep with periodic GC
            for i in range(globals.timer):  # 30 minutes = 1800 seconds
                if i % 30 == 0:
                    safe_gc("sleep_cycle_%d" % i)
                sleep(1)

        except Exception as e:
            print("💥 Monitor loop error:", e)
            safe_gc("monitor_loop_exception")
            sleep(5)
            machine.reset()


# ============ MAIN EXECUTION ============ #
def main():
    print("🚀 Machine booting...")
    sleep(5)
    safe_gc("boot_start")

    try:
        # Valve Test
        print("🔧 Testing valves...")
        valve_test(uart, SLAVE_ADDRESSES)
        safe_gc("valve_test")
        sleep(1)

        # Initial parameter read
        print("📊 Reading initial meter parameters...")
        read_meter_parameters(uart, SLAVE_ADDRESSES)
        safe_gc("read_meter_parameters")
        sleep(1)

        # Initial monitoring
        print("📊 Monitoring Units...")
        monitor_target(uart, SLAVE_ADDRESSES)
        safe_gc("monitor_target_init")

        # Initialize GSM
        print("📡 Initializing GSM module...")
        sleep(4)
        gsmInitialization()
        safe_gc("gsm_init")

        while gsmCheckStatus() != 1:
            print("📶 Waiting for GSM connection...")
            sleep(1)
        print("✅ GSM connected.")
        safe_gc("gsm_connected")

        # Global file OTA
        update_global_file(globals.MQTT_CLIENT_ID, retries=3)
        safe_gc("update_global_file")

        # Firmware OTA
        run_ota()
        safe_gc("run_ota")

        # Start MQTT listener
        print("🔌 Starting MQTT listener thread...")
        _thread.start_new_thread("MqttListener", mqttInitialize, (mqtt, MQTT_SUB_TOPICS,))

        sleep(10)

        # Start periodic monitoring thread
        print("🧵 Starting periodic meter monitor thread...")
        _thread.start_new_thread("MeterMonitor", monitor_loop, ())

        print("✅ System initialization complete. Now running...")

    except Exception as e:
        print("💥 Fatal error in main():", e)
        safe_gc("main_exception")
        sleep(5)
        machine.reset()


# ============ ENTRY POINT ============ #
if __name__ == "__main__":
    main()
