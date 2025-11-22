from machine import UART

# ============ DEVICE CONFIGURATION ============ #
GLOBAL_VERSION = "1.0.2"

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
VERSION_FILE = "/flash/version.txt"

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [1]#, 2, 3, 4, 5, 6]

# ============ MQTT CONFIGURATION ============ #
MQTT_BROKER_HOST = "152.42.139.67"
MQTT_BROKER_PORT = 18100
MQTT_CLIENT_ID = "FQX_SM_10008"
MQTT_CLIENT_USERNAME = "FQX_SM_10008"
MQTT_CLIENT_PASSWORD = "FQX_SM@10008"

MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10008/pub/controlcomm/message'

# ============ GSM CONFIGURATION ============ #
GSM_APN = 'safaricomiot'  # Your APN
GSM_USER = ''  # Your User
GSM_PASS = ''  # Your Pass

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10008-1/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-2/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-3/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-4/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-5/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-6/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-7/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-8/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-9/sub/controlcomm/message",
    "smartmeter/FQX_SM_10008-10/sub/controlcomm/message"
]

timer = 180
