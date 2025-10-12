from machine import UART

# ============ MODBUS SLAVE ADDRESSES ============ #
SLAVE_ADDRESSES = [12, 13, 14, 15]

# ============ MQTT CONFIGURATION ============ #
MQTT_BROKER_HOST = "152.42.139.67"
MQTT_BROKER_PORT = 18100
MQTT_CLIENT_ID = "FQX_SM_10006"
MQTT_CLIENT_USERNAME = "FQX_SM_10006"
MQTT_CLIENT_PASSWORD = "FQX_SM@10006"

MQTT_PUB_TOPIC = 'smartmeter/FQX_SM_10006/pub/controlcomm/message'

# ============ GSM CONFIGURATION ============ #
GSM_APN = 'safaricom'  # Your APN
GSM_USER = 'saf'  # Your User
GSM_PASS = 'data'  # Your Pass

MQTT_SUB_TOPICS = [
    "smartmeter/FQX_SM_10006-12/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-13/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-14/sub/controlcomm/message",
    "smartmeter/FQX_SM_10006-15/sub/controlcomm/message"
]

timer = 1800

