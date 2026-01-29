from machine import UART

# ============ DEVICE CONFIGURATION ============ #
GLOBAL_VERSION = "1.0.7"

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
VERSION_FILE = "/flash/version.txt"

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [13, 14, 10, 35]#, 2, 3, 4, 5, 6]

# ============ MQTT CONFIGURATION ============ #
MQTT_BROKER_HOST = "152.42.139.67"
MQTT_BROKER_PORT = 18100
MQTT_CLIENT_ID = "FQX_SM_10006"
MQTT_CLIENT_USERNAME = "FQX_SM_10006"
MQTT_CLIENT_PASSWORD = "FQX_SM@10006"

MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10006/pub/controlcomm/message'

# ============ GSM CONFIGURATION ============ #
GSM_APN = 'safaricomiot'  # Your APN
GSM_USER = ''  # Your User
GSM_PASS = ''  # Your Pass

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10006-13/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-14/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-10/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-35/sub/controlcomm/message"
]

timer = 180

# ============ COMMAND QUEUE (THREAD SAFE) ============ #
# MQTT thread puts commands here. Main thread executes them.
CMD_QUEUE = []