from machine import UART
import time

# ========== UART CONFIG ==========
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# MODBUS Slave Addresses
SLAVE_ADDRESS_1 = 13  # Meter1 MODBUS Slave address
SLAVE_ADDRESS_2 = 14  # Meter2 MODBUS Slave address
SLAVE_ADDRESS_3 = 15
SLAVE_ADDRESS_4 = 12

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
    if write_single_register(uart, device_address, 0x0060, 0x0001):
        print("Valve opened for device address", device_address)
    else:
        print("Failed to open valve for device address", device_address)

def close_valve(uart, device_address):
    if write_single_register(uart, device_address, 0x0060, 0x0002):
        print("Valve closed for device address", device_address)
    else:
        print("Failed to close valve for device address", device_address)

def print_value(label, value, unit, fmt="%.2f"):
    if value is not None:
        print("%s: %s %s" % (label, fmt % value, unit))
    else:
        print("Failed to read %s" % label)

# ========== MAIN LOOP ==========

def main():
    while True:
        print("---- Reading from water meters ----")

        cumulative1 = read_cumulative_flow(uart, SLAVE_ADDRESS_1)
        cumulative2 = read_cumulative_flow(uart, SLAVE_ADDRESS_2)
        cumulative3 = read_cumulative_flow(uart, SLAVE_ADDRESS_3)
        cumulative4 = read_cumulative_flow(uart, SLAVE_ADDRESS_4)
            
        
        # Print values
        print_value("Cumulative Flow 1", cumulative1, "L", "%.1f")
        print_value("Cumulative Flow 2", cumulative2, "L", "%.1f")
        
        print_value("Cumulative Flow 3", cumulative3, "L", "%.1f")
        print_value("Cumulative Flow 4", cumulative4, "L", "%.1f")
        
#         open_valve(uart, SLAVE_ADDRESS_1)
#         time.sleep(5)
# 
#         close_valve(uart, SLAVE_ADDRESS_1)
#         time.sleep(5)
        
        

        print("---- Done ----\n")
        time.sleep(2)

# Run main loop
main()
