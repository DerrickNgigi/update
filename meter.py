from machine import UART
import time
from meter_storage import *
import time
import json

# ========== UART CONFIG ==========
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# ========== CRC + Frame Utilities ==========
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

def write_single_register(uart, address, register_address, value):
    frame = bytearray(9)
    frame[0] = address
    frame[1] = 0x10  # Write Multiple Registers
    frame[2] = (register_address >> 8) & 0xFF
    frame[3] = register_address & 0xFF
    frame[4] = 0x00  # Number of registers high byte
    frame[5] = 0x01  # Number of registers low byte
    frame[6] = 0x02  # Byte count
    frame[7] = (value >> 8) & 0xFF
    frame[8] = value & 0xFF
    crc = calculate_crc(frame)
    frame += bytearray([crc & 0xFF, (crc >> 8) & 0xFF])
    uart.write(frame)
    time.sleep(0.1)
    response = uart.read(8)
    return response and verify_crc(response)

# ========== FUNCTION DEFINITIONS ==========

def read_cumulative_flow(uart, address):
    request = build_modbus_request(address, 0x03, 0x000E, 0x02)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(9)
    if response and verify_crc(response):
        value = (response[3] << 8) | response[4]
        return value 
    return None

def read_instantaneous_flow(uart, address):
    request = build_modbus_request(address, 0x03, 0x0014, 0x02)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(9)
    if response and verify_crc(response):
        value = (response[3] << 8) | response[4]
        return value 
    return None

def bcd_to_decimal(bcd):
    """Converts a BCD byte (or pair) to decimal."""
    high = (bcd >> 4) & 0x0F
    low = bcd & 0x0F
    return high * 10 + low

def read_cell_voltage(uart, address):
    request = build_modbus_request(address, 0x03, 0x0016, 0x01)
    uart.write(request)
    time.sleep(0.1)
    response = uart.read(7)
    if response and verify_crc(response):
        msb = response[3]
        lsb = response[4]

        # Convert both bytes from BCD to decimal
        voltage_bcd = bcd_to_decimal(msb) * 100 + bcd_to_decimal(lsb)
        voltage = voltage_bcd * 0.01  # Scale to volts

        return voltage
    return None

def open_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0001)
        
def close_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0002)
                
def get_valid_flow(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        flow_value = read_instantaneous_flow(uart, address)
        time.sleep(1)
        if flow_value is not None:
            return flow_value
        time.sleep(delay)
    print("Failed to read valid flow after retries.")
    uart.flush()
    return None


def get_valid_volume(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        volume_value = read_cumulative_flow(uart, address)
        time.sleep(1)
        if volume_value is not None:
            return volume_value
        time.sleep(delay)
    print("Failed to read valid volume after retries.")
    uart.flush()
    return None


# ========== MAJOR OPERATIONS ==========     

def monitor_target(uart, addresses):
    for address in addresses:
        target_volume_liters = load_target_reading(address)
        time.sleep(1)
        if target_volume_liters is None:
            print("Target volume is None. Skipping address:", address)
            close_valve(uart, address)
            time.sleep(1)            
            continue
        else:
            print("Monitoring started for address", address, ". Target:", target_volume_liters, "L")

        current_volume = get_valid_volume(uart, address)
        time.sleep(1)

        if current_volume is not None:
            print("Current volume:", current_volume)
        else:
            print("Volume is None. Sending close command and continuing...")
            close_valve(uart, address)
            time.sleep(1) 
            continue  # Skip to next address

        print("Current:", current_volume, "L")

        if current_volume >= target_volume_liters:
            close_valve(uart, address)
            time.sleep(1)
            print("Target volume reached. Valve closed.")
        else:
            open_valve(uart, address)


def read_meter_parameters(uart, addresses):
    for address in addresses:
        print("\n Reading meter parameters for device %s" % hex(address))
        
        cumulative = get_valid_volume(uart, address)
        time.sleep(1)
        if cumulative is None:
            continue

        # Final print after successful reads
        print("Device %s Read Successful:" % hex(address))
        print("  Cumulative Flow: %s L" % cumulative)

def read_meter_parameters_upload(uart, addresses, publish_func, mqtt_client, mqtt_topic):
    """
    Reads meter parameters and publishes one message PER device.
    publish_func: The function used to send data (passed from main)
    """

    for address in addresses:
        print("\nReading meter parameters for device %s" % address)
     
        cumulative = get_valid_volume(uart, address)
        time.sleep(1)
        
        if cumulative is None:
            continue
        
        target_volume_liters = load_target_reading(address)
        time.sleep(1)
        
        if target_volume_liters is None:
            continue
        
        print("Device %s Read Successful:" % address)
        print("  Cumulative Flow: %s L" % cumulative)
        print("  Target Flow: %s L" % target_volume_liters)

        payload = '{"type": "device_report", "device": %d, "cumulative_flow_L": %s, "target_flow": %s}' % (
            address,
            cumulative,
            target_volume_liters
        )

        try:
            # USE THE PASSED FUNCTION ARGUMENT HERE
            publish_func(mqtt_client, mqtt_topic, payload)
            print("Meter data published for device %s." % address)
        except Exception as e:
            print("MQTT publish failed for device %s: %s" % (address, e))
      

def valve_test(uart, addresses):
    # Open all valves
    for address in addresses:
        open_valve(uart, address)
    time.sleep(3)
    
    # Close all valves first
    for address in addresses:
        close_valve(uart, address)
    time.sleep(3)
    
    
def set_init_target_reading(uart, addresses):
    for address in addresses:
        target_volume_liters = load_target_reading(address)
        time.sleep(1)

        if target_volume_liters is None:
            print("Target volume is None. Setting target for:", address)

            new_target_volume_liters = get_valid_volume(uart, address)
            time.sleep(1)

            if new_target_volume_liters is None:
                print("Failed to set target volume for:", address)
            else:
                save_target_reading(address, new_target_volume_liters)
                time.sleep(1)
                print("Target volume set successfully for:", address)