import network
import utime
import globals
import json
MAX_RETRIES = 5
from meter import *
from machine import UART
import machine

# Global Variables
MQTT_BROKER_HOST = globals.MQTT_BROKER_HOST
MQTT_BROKER_PORT = globals.MQTT_BROKER_PORT
MQTT_CLIENT_USERNAME = globals.MQTT_CLIENT_USERNAME
MQTT_CLIENT_PASSWORD = globals.MQTT_CLIENT_PASSWORD
MQTT_CLIENT_ID = globals.MQTT_CLIENT_ID
MQTT_PUB_TOPIC = globals.MQTT_PUB_TOPIC


# UART CONFIGURATION
uart = UART(2, baudrate=9600, bits=8, parity=1, stop=1, tx=19, rx=18)  # UART2 on ESP32

# List of topics to subscribe to
MQTT_SUB_TOPICS = globals.MQTT_SUB_TOPICS


def get_device_Hex(deviceID):
    if '-' in deviceID:
        suffix = deviceID.split('-')[-1]
        try:
            return int(suffix, 10)
        except ValueError:
            return None
    return None

# ---------------- MQTT CALLBACKS ---------------- #

def conncb(task):
    print("[{}] Connected".format(task))

def disconncb(task):
    print("[{}] Disconnected".format(task))
    mqttInitialize(mqtt, MQTT_SUB_TOPICS)

def subscb(task):
    print("[{}] Subscribed".format(task))

def pubcb(pub):
    print("[{}] Published: {}".format(pub[0], pub[1]))

def datacb(msg):
    print("[{}] Data arrived from topic: {}, Message:\n{}".format(msg[0], msg[1], msg[2]))
    global uart

    utime.sleep(1)

    try:
        payload = json.loads(msg[2])
        message = payload.get('message')
        litres = payload.get('litres')
        deviceID = payload.get('deviceID')

        print("message: {}".format(message))
        print("litres: {}".format(litres))
        print("deviceID: {}".format(deviceID))

        hex_address = get_device_Hex(deviceID)
        print("Device HEX address: {}".format(hex_address))

        # Handle different message types
        if message == "success":
            if litres is None or litres == 0:
                print("Ignoring message due to empty or zero litres.")
                return
            retries = 0
            while retries < 5:
                try:
                    current_target_reading = load_target_reading(hex_address)
                    print("Current reading: {}".format(current_target_reading))

                    target_reading = current_target_reading + litres
                    print("Target reading: {}".format(target_reading))

                    save_target_reading(hex_address, target_reading)
                    print("Target reading saved successfully.")

                    monitor_target(uart, [hex_address])
                    
                    mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps({
                        "type": "device_report",
                        "device": deviceID,
                        "status": "load_success"
                    }))
                    break  # Success
                except Exception as e:
                    retries += 1
                    print("Retry {}/5 failed: {}".format(retries, e))
                    if retries == 5:
                        print("Max retries reached. Could not complete reading or writing.")
                    mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps({
                        "type": "device_report",
                        "device": deviceID,
                        "status": "load_failure"
                    }))

        elif message == "valve_open":
            print("🔓 Opening valve for device:", hex_address)
            open_valve(uart, hex_address)
            mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps({
                "type": "device_report",
                "device": deviceID,
                "status": "valve_open"
            }))

        elif message == "valve_close":
            print("🔒 Closing valve for device:", hex_address)
            close_valve(uart, hex_address)
            mqttPublish(mqtt, MQTT_PUB_TOPIC, json.dumps({
                "type": "device_report",
                "device": deviceID,
                "status": "valve_closed"
            }))

        else:
            print("⚠ Unknown message type:", message)

    except Exception as e:
        print("Error while parsing data: {}".format(e))


        


# ---------------- MQTT INITIALIZATION ---------------- #

# Create MQTT client
mqtt = network.mqtt(
    MQTT_CLIENT_ID,
    MQTT_BROKER_HOST,
    user=MQTT_CLIENT_USERNAME,
    password=MQTT_CLIENT_PASSWORD,
    port=MQTT_BROKER_PORT,
    autoreconnect=True,
    clientid=MQTT_CLIENT_ID,
    connected_cb=conncb,
    disconnected_cb=disconncb,
    subscribed_cb=subscb,
    published_cb=pubcb,
    data_cb=datacb
)

# Initialize and subscribe to multiple topics
def mqttInitialize(mqtt, topic_list):
    loopCount = 10

    def mqttConnect():
        mqtt.start()
        utime.sleep(2)
        return mqtt.status()

    status = mqttConnect()

    while status[0] != 2 and loopCount > 0:
        print("MQTT Not Connected")
        status = mqttConnect()
        utime.sleep(1)
        loopCount -= 1
        if loopCount == 0:
            print("MQTT Connection Failed")
            machine.reset()
            return None  # Return None if connection fails
    else:
        print("MQTT Connected")

        # Subscribe to each topic individually
        for topic in topic_list:
            if isinstance(topic, str):
                if mqtt.subscribe(topic):
                    print("Subscribed to topic:", topic)
                else:
                    print("Failed to subscribe to topic:", topic)
            else:
                print("Invalid topic format, expected string but got:", type(topic))
        
        return mqtt


# ---------------- PUBLISH & CHECK ---------------- #

def mqttPublish(mqtt, topic, message):
    mqtt.publish(topic, message)
    print("MQTT Published to Topic:", topic, "Message:", message)
    return True

def mqttCheckStatus(mqtt):
    status = mqtt.status()[0]
    if status != 2:
        print("MQTT not connected")
    else:
        print("MQTT connected")
    return status