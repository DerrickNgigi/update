from machine import UART

# ============ DEVICE CONFIGURATION ============ #
GLOBAL_VERSION = "1.0.3"

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
VERSION_FILE = "/flash/version.txt"

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [1]#, 2, 3, 4, 5, 6]

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
    "smartmeter/FQX_SM_10006-1/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-2/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-3/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-4/sub/controlcomm/message"
]

timer = 180

# ============ COMMAND QUEUE (THREAD SAFE) ============ #
# MQTT thread puts commands here. Main thread executes them.
CMD_QUEUE = []