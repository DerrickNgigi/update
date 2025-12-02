from machine import UART
import time
from meter_storage import *
import json

# ========== UART CONFIG ==========
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)

# ========== HELPER: CLEAR BUFFER ==========
def clear_uart_buffer(uart):
    """
    Reads all pending data to ensure the line is silent before we speak.
    """
    try:
        while uart.any():
            uart.read()
            time.sleep(0.01) # Yield to CPU
    except:
        pass
    time.sleep(0.05) 

# ========== HELPER: SMART READ ==========
def smart_read_modbus(uart, expected_bytes, timeout_attempts=15):
    """
    Waits for 'expected_bytes' to arrive in the buffer.
    """
    for _ in range(timeout_attempts):
        if uart.any() >= expected_bytes:
            break
        time.sleep(0.1) 
    
    try:
        return uart.read(expected_bytes)
    except:
        return None

# ========== CRC Utils ==========
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
    if not frame or len(frame) < 3:
        return False
    received_crc = frame[-2] | (frame[-1] << 8)
    return calculate_crc(frame[:-2]) == received_crc

# ========== MODBUS FUNCTIONS ==========
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
    clear_uart_buffer(uart)
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
    # Wait for response (8 bytes for Write command)
    response = smart_read_modbus(uart, 8)
    return response and verify_crc(response)

def read_cumulative_flow(uart, address):
    clear_uart_buffer(uart)
    request = build_modbus_request(address, 0x03, 0x000E, 0x02)
    uart.write(request)
    response = smart_read_modbus(uart, 9)
    
    if response and len(response) == 9 and verify_crc(response):
        if response[0] == address:
            return (response[3] << 8) | response[4]
    return None

def open_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0001)
    time.sleep(0.5)

def close_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0002)
    time.sleep(0.5)

def get_valid_volume(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        volume_value = read_cumulative_flow(uart, address)
        if volume_value is not None:
            return volume_value
        time.sleep(delay)
    return None

def monitor_target(uart, addresses):
    """
    Standard monitoring function (kept for reference or standalone use).
    """
    for address in addresses:
        current_volume = get_valid_volume(uart, address)
        time.sleep(0.2)
        target_volume_liters = load_target_reading(address)
        
        if target_volume_liters is None:
            if current_volume is not None:
                save_target_reading(address, current_volume)
                target_volume_liters = current_volume
            else:
                continue

        if current_volume is None: continue 

        print("Mon Addr: %d | Targ: %s | Curr: %s" % (address, target_volume_liters, current_volume))

        if current_volume >= target_volume_liters:
            close_valve(uart, address)
        else:
            open_valve(uart, address)

def read_meter_parameters_upload(uart, addresses, publish_func, mqtt_client, mqtt_topic):
    """
    Reads meter, enforces valve target logic locally, THEN uploads to MQTT.
    """
    for address in addresses:
        # 1. Read Meter
        cumulative = get_valid_volume(uart, address)
        if cumulative is None: continue
        
        # 2. Check Target
        target_volume_liters = load_target_reading(address)
        if target_volume_liters is None:
            save_target_reading(address, cumulative)
            target_volume_liters = cumulative
        
        print("Read OK: Curr %s L | Targ %s L" % (cumulative, target_volume_liters))

        # 3. ENFORCE MONITOR TARGET (Valve Control)
        # We do this immediately to prevent network latency (crushing) from delaying the valve close
        if cumulative >= target_volume_liters:
            close_valve(uart, address)
        else:
            open_valve(uart, address)

        # 4. Prepare Payload
        payload = '{"type": "device_report", "device": %d, "cumulative_flow_L": %s, "target_flow": %s}' % (
            address, cumulative, target_volume_liters
        )

        # 5. Upload
        try:
            publish_func(mqtt_client, mqtt_topic, payload)
        except:
            pass

def valve_test(uart, addresses):
    for address in addresses:
        open_valve(uart, address)
    time.sleep(2)
    for address in addresses:
        close_valve(uart, address)
    time.sleep(2)