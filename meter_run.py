from machine import UART
import time
from meter import *

# ========== UART CONFIG ==========
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# MODBUS Slave Addresses
SLAVE_ADDRESSES = [12, 13, 14, 15]   

# ========== MAIN LOOP ==========

def main():
        print("---- Test Starting ----")

        read_meter_parameters(uart, SLAVE_ADDRESSES)
        time.sleep(3)
        valve_test(uart, SLAVE_ADDRESSES)
        time.sleep(3)
        set_init_target_reading(uart, SLAVE_ADDRESSES)
        time.sleep(3)
        monitor_target(uart, SLAVE_ADDRESSES)
        
        print("---- Test Complete Done ----\n")
        time.sleep(2)

# Run main loop
main()

