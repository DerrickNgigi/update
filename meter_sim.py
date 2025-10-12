from machine import UART
import time
import json
from meter_storage import *

# ==========================================
# CONFIGURATION
# ==========================================
SIMULATION_MODE = True   # Set to False when meters are connected

uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# ==========================================
# CRC + FRAME UTILITIES
# ==========================================
def calculate_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

def verify_crc(frame):
    if len(frame) < 3:
        return False
    received_crc = frame[-2] | (frame[-1] << 8)
    return calculate_crc(frame[:-2]) == received_crc


def build_modbus_request(address, function_code, register_address, register_count):
    frame = bytearray(6)
    frame[0] = address
    frame[1] = function_code
    frame[2] = (register_address >> 8) & 0xFF
    frame[3] = register_address & 0xFF
    frame[4] = (register_count >> 8) & 0xFF
    frame[5] = register_count & 0xFF
    crc = calculate_crc(frame)
    frame += bytearray([crc & 0xFF, (crc >> 8) & 0xFF])
    return frame

# ==========================================
# SIMULATED RESPONSES
# ==========================================
def simulated_cumulative_flow(address):
    return 1000 + (address * 50)

def simulated_flow(address):
    return 2.5 + (address * 0.1)

def simulated_voltage(address):
    return 3.7 + (address * 0.02)


# ==========================================
# WRITE SINGLE REGISTER
# ==========================================
def write_single_register(uart, address, register_address, value):
    if SIMULATION_MODE:
        print("💡 Simulating write register %s = %s for device %s" %
              (hex(register_address), value, address))
        time.sleep(0.1)
        return True

    frame = bytearray(9)
    frame[0] = address
    frame[1] = 0x10
    frame[2] = (register_address >> 8) & 0xFF
    frame[3] = register_address & 0xFF
    frame[4] = 0x00
    frame[5] = 0x01
    frame[6] = 0x02
    frame[7] = (value >> 8) & 0xFF
    frame[8] = value & 0xFF
    crc = calculate_crc(frame)
    frame += bytearray([crc & 0xFF, (crc >> 8) & 0xFF])
    uart.write(frame)
    time.sleep(0.1)
    response = uart.read(8)
    return response and verify_crc(response)


# ==========================================
# READ METER PARAMETERS
# ==========================================
def read_cumulative_flow(uart, address):
    if SIMULATION_MODE:
        val = simulated_cumulative_flow(address)
        print("📈 Simulated cumulative flow for device %s: %s L" % (address, val))
        return val

    request = build_modbus_request(address, 0x03, 0x000E, 0x02)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(9)
    if response and verify_crc(response):
        return (response[3] << 8) | response[4]
    return None


def read_instantaneous_flow(uart, address):
    if SIMULATION_MODE:
        val = simulated_flow(address)
        print("💧 Simulated instantaneous flow for device %s: %.2f L/s" % (address, val))
        return val

    request = build_modbus_request(address, 0x03, 0x0014, 0x02)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(9)
    if response and verify_crc(response):
        return (response[3] << 8) | response[4]
    return None


def read_cell_voltage(uart, address):
    if SIMULATION_MODE:
        val = simulated_voltage(address)
        print("🔋 Simulated voltage for device %s: %.2f V" % (address, val))
        return val

    request = build_modbus_request(address, 0x03, 0x0016, 0x01)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(7)
    if response and verify_crc(response):
        msb = response[3]
        lsb = response[4]
        voltage = ((msb >> 4) * 10 + (msb & 0x0F)) * 100 + ((lsb >> 4) * 10 + (lsb & 0x0F))
        return voltage * 0.01
    return None


# ==========================================
# VALVE CONTROL
# ==========================================
def open_valve(uart, device_address):
    if SIMULATION_MODE:
        print("🟢 Simulating valve open for device %s" % device_address)
        return True
    return write_single_register(uart, device_address, 0x0060, 0x0001)


def close_valve(uart, device_address):
    if SIMULATION_MODE:
        print("🔴 Simulating valve close for device %s" % device_address)
        return True
    return write_single_register(uart, device_address, 0x0060, 0x0002)


# ==========================================
# RETRY HANDLERS
# ==========================================
def get_valid_flow(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        flow_value = read_instantaneous_flow(uart, address)
        if flow_value is not None:
            return flow_value
        print("⚠ Attempt %d failed. Retrying..." % (attempt + 1))
        time.sleep(delay)
    print("❌ Failed to read valid flow after retries.")
    return None


def get_valid_volume(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        volume_value = read_cumulative_flow(uart, address)
        if volume_value is not None:
            return volume_value
        print("⚠ Attempt %d failed. Retrying..." % (attempt + 1))
        time.sleep(delay)
    print("❌ Failed to read valid volume after retries.")
    return None


# ==========================================
# MAIN OPERATIONS
# ==========================================
def monitor_target(uart, addresses):
    for address in addresses:
        target_volume_liters = load_target_reading(address)
        time.sleep(0.5)

        if target_volume_liters is None:
            print("⚠ Target volume missing for device %s" % address)
            close_valve(uart, address)
            continue

        print("Monitoring device %s, Target: %s L" % (address, target_volume_liters))

        current_volume = get_valid_volume(uart, address)
        if current_volume is None:
            print("⚠ Volume read failed. Closing valve.")
            close_valve(uart, address)
            continue

        print("Current Volume: %s L" % current_volume)

        if current_volume >= target_volume_liters:
            close_valve(uart, address)
            print("✅ Target reached for device %s. Valve closed." % address)
        else:
            open_valve(uart, address)


def read_meter_parameters(uart, addresses):
    for address in addresses:
        print("\n📟 Reading parameters for device %s" % address)
        cumulative = get_valid_volume(uart, address)
        voltage = read_cell_voltage(uart, address)
        flow = get_valid_flow(uart, address)

        print("✅ Device %s Read Successful:" % address)
        print("  Cumulative Flow: %s L" % cumulative)
        print("  Instant Flow: %.2f L/s" % flow)
        print("  Voltage: %.2f V" % voltage)


def read_meter_parameters_upload(uart, addresses):
    results = {}
    for address in addresses:
        cumulative = get_valid_volume(uart, address)
        target = load_target_reading(address)
        voltage = read_cell_voltage(uart, address)

        results[address] = {
            "type": "device_report",
            "device": address,
            "cumulative_flow_L": cumulative,
            "target_flow": target,
            "voltage": voltage
        }

    print(json.dumps(results))
    return json.dumps(results)


def valve_test(uart, addresses):
    print("\n🔄 Valve test start...")
    for address in addresses:
        open_valve(uart, address)
    time.sleep(2)
    for address in addresses:
        close_valve(uart, address)
    print("✅ Valve test complete.")


def set_init_target_reading(uart, addresses):
    for address in addresses:
        current_volume = get_valid_volume(uart, address)
        if current_volume is not None:
            save_target_reading(address, current_volume)
            print("💾 Set initial target volume for %s = %s L" %
                  (address, current_volume))
        else:
            print("❌ Failed to set initial target for %s" % address)

