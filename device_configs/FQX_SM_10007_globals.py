from machine import UART

# ============ DEVICE CONFIGURATION ============ #
GLOBAL_VERSION = "1.0.3"

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
VERSION_FILE = "/flash/version.txt"

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [01, 02, 03, 04, 05, 06]

# ============ MQTT CONFIGURATION ============ #
MQTT_BROKER_HOST = "152.42.139.67"
MQTT_BROKER_PORT = 18100
MQTT_CLIENT_ID = "FQX_SM_10007"
MQTT_CLIENT_USERNAME = "FQX_SM_10007"
MQTT_CLIENT_PASSWORD = "FQX_SM@10007"

MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10007/pub/controlcomm/message'

# ============ GSM CONFIGURATION ============ #
GSM_APN = 'safaricomiot'  # Your APN
GSM_USER = ''  # Your User
GSM_PASS = ''  # Your Pass

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10007-1/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-2/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-3/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-4/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-5/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-6/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-7/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-8/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-9/sub/controlcomm/message",
    "smartmeter/FQX_SM_10007-10/sub/controlcomm/message"
]

timer = 1800
