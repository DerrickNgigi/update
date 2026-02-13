from machine import UART
import time
from meter_storage import *
import json

# ========== UART CONFIG ==========
# Configure UART for Modbus communication (9600 baud, 8N1)
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
    response = smart_read_modbus(uart, 8)
    return response and verify_crc(response)

# ========== STATUS & DIAGNOSTIC FUNCTIONS ==========

def read_valve_status(uart, address):
    """
    Performs a single Modbus read of the equipment control register (0x0060).
    """
    clear_uart_buffer(uart)
    request = build_modbus_request(address, 0x03, 0x0060, 0x01)
    uart.write(request)
    response = smart_read_modbus(uart, 7)
    
    if response and len(response) == 7 and verify_crc(response):
        status_bits = response[4] & 0x03 # D1:D0
        if status_bits == 0x01: return "Open"
        if status_bits == 0x02: return "Closed"
    return None

def get_valid_valve_status(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        status = read_valve_status(uart, address)
        if status: return status
        time.sleep(delay)
    return "Unknown"

def read_general_status(uart, address):
    """
    Reads the General Status Register (ST) at 0x0001 for hardware health.
    """
    clear_uart_buffer(uart)
    request = build_modbus_request(address, 0x03, 0x0001, 0x01)
    uart.write(request)
    response = smart_read_modbus(uart, 7)
    
    if response and len(response) == 7 and verify_crc(response):
        st_val = (response[3] << 8) | response[4]
        return {
            "battery": "Low" if (st_val & 0x0001) else "Good",
            "pipe_empty": "EMPTY (No Water)" if (st_val & 0x0002) else "Full (Normal)",
            "sensor_error": bool(st_val & 0x0010)
        }
    return None

def get_valid_health_data(uart, address, retries=3, delay=0.5):
    for _ in range(retries):
        data = read_general_status(uart, address)
        if data: return data
        time.sleep(delay)
    return {"battery": "Unknown", "pipe_empty": "Unknown", "sensor_error": False}

# ========== FLOW & VALVE CONTROL ==========

def read_cumulative_flow(uart, address):
    clear_uart_buffer(uart)
    request = build_modbus_request(address, 0x03, 0x000E, 0x02)
    uart.write(request)
    response = smart_read_modbus(uart, 9)
    if response and len(response) == 9 and verify_crc(response):
        return (response[3] << 8) | response[4]
    return None

def get_valid_volume(uart, address, retries=5, delay=1):
    for attempt in range(retries):
        volume_value = read_cumulative_flow(uart, address)
        if volume_value is not None:
            return volume_value
        time.sleep(delay)
    return None

def open_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0001)
    time.sleep(0.5)

def close_valve(uart, device_address):
    write_single_register(uart, device_address, 0x0060, 0x0002)
    time.sleep(0.5)

# ========== MONITORING FUNCTIONS ==========

def monitor_target(uart, addresses, publish_func, mqtt_client, mqtt_topic):
    """
    Standard monitoring with integrated ALERTING.
    Direct logic execution: No extra flags.
    """
    for address in addresses:
        current_volume = get_valid_volume(uart, address)
        
        # --- ALERT LOGIC: Connection Failure ---
        if current_volume is None:
            try:
                payload = json.dumps({
                    "type": "device_report", 
                    "device": address, 
                    "cumulative_flow_L": None,
                    "target_flow_L": None,
                    "alert": "No meter connection"
                })
                publish_func(mqtt_topic, payload)
            except:
                pass
            continue 

        # --- NORMAL LOGIC ---
        target_volume_liters = load_target_reading(address)
        
        if target_volume_liters is None:
            save_target_reading(address, current_volume)
            target_volume_liters = current_volume

        # Enforce Logic & Direct Upload
        if current_volume >= target_volume_liters:
            close_valve(uart, address)
            try:
                read_meter_parameters_upload(uart, [address], publish_func, mqtt_client, mqtt_topic)
            except:
                pass
        else:
            open_valve(uart, address)


def read_meter_parameters(uart, addresses):
    """
    Reads parameters for local display/logging without MQTT.
    """
    for address in addresses:
        current_volume = get_valid_volume(uart, address)
        if current_volume is None: 
            continue 
        health = get_valid_health_data(uart, address)
        valve_state = get_valid_valve_status(uart, address)

def read_meter_parameters_upload(uart, addresses, publish_func, mqtt_client, mqtt_topic):
    """
    Reads meter, enforces valve logic locally, and uploads detailed report to MQTT.
    """
    for address in addresses:
        # 1. Read Flow Data
        cumulative = get_valid_volume(uart, address)
        
        # FIX 1: Check 'cumulative', not 'current_volume'
        if cumulative is None:
            try:
                payload = json.dumps({
                    "type": "device_report", 
                    "device": address, 
                    "cumulative_flow_L": None,
                    "target_flow_L": None,
                    "alert": "No meter connection"
                })
                # FIX 2: Ensure publish_func is called correctly (usually takes topic, msg)
                # Some libraries use client.publish(topic, msg), others just publish(topic, msg)
                # Based on your main.py: meter_mqtts.mqtt.publish(MQTT_PUB_TOPIC, payload)
                publish_func(mqtt_topic, payload)
            except:
                pass
            continue 
        
        # 2. Check and Enforce Target
        target_volume = load_target_reading(address)
        if target_volume is None:
            save_target_reading(address, cumulative)
            target_volume = cumulative
        
        # FIX 3: Use consistent variable names ('cumulative' vs 'target_volume')
        if cumulative >= target_volume:
            close_valve(uart, address)
            # Note: We are ALREADY inside the upload function. 
            # Recursively calling read_meter_parameters_upload here is dangerous (infinite loop risk).
            # Instead, just let the flow continue to step 4 to upload the status "Closed".
        else:
            open_valve(uart, address)

        # 3. Read Health Variations
        valve_state = get_valid_valve_status(uart, address)
        health = get_valid_health_data(uart, address)
        
        # 4. Upload Comprehensive Payload
        payload = json.dumps({
            "type": "device_report",
            "device": address,
            "cumulative_flow_L": cumulative,
            "target_flow_L": target_volume,
            "valve_status": valve_state,
            "pipe_status": health["pipe_empty"],
            "battery_status": health["battery"]
        })

        try:
            publish_func(mqtt_topic, payload)
        except Exception as e:
            print("Publish Error:", e)

def valve_test(uart, addresses):
    for address in addresses:
        close_valve(uart, address)
    time.sleep(2)
    for address in addresses:
        open_valve(uart, address)
    time.sleep(2)