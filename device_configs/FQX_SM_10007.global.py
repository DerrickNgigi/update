from machine import UART

# ============ DEVICE CONFIGURATION ============ #
GLOBAL_VERSION = "1.0.1"

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
VERSION_FILE = "/flash/version.txt"

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [12, 13, 14, 15]

# ============ MQTT CONFIGURATION ============ #
MQTT_BROKER_HOST = "152.42.139.67"
MQTT_BROKER_PORT = 18100
MQTT_CLIENT_ID = "FQX_SM_10007"
MQTT_CLIENT_USERNAME = "FQX_SM_10007"
MQTT_CLIENT_PASSWORD = "FQX_SM@10007"

MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10007/pub/controlcomm/message'

# ============ GSM CONFIGURATION ============ #
GSM_APN = 'safaricom'  # Your APN
GSM_USER = 'saf'  # Your User
GSM_PASS = 'data'  # Your Pass

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10007-12/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-13/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-14/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-15/sub/controlcomm/message"
]

timer = 180


