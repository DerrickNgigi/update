import network
import utime
import globals
import json
import machine
import _thread

# Global Variables
MQTT_BROKER_HOST = globals.MQTT_BROKER_HOST
MQTT_BROKER_PORT = globals.MQTT_BROKER_PORT
MQTT_CLIENT_USERNAME = globals.MQTT_CLIENT_USERNAME
MQTT_CLIENT_PASSWORD = globals.MQTT_CLIENT_PASSWORD
MQTT_CLIENT_ID = globals.MQTT_CLIENT_ID
MQTT_PUB_TOPIC = globals.MQTT_PUB_TOPIC
MQTT_SUB_TOPICS = globals.MQTT_SUB_TOPICS

def get_device_Hex(deviceID):
    if '-' in deviceID:
        try:
            return int(deviceID.split('-')[-1], 10)
        except ValueError:
            return None
    return None

# ---------------- MQTT CALLBACKS ---------------- #

def conncb(task):
    print("[{}] Connected".format(task))

def disconncb(task):
    print("[{}] Disconnected".format(task))

def subscb(task):
    print("[{}] Subscribed".format(task))

def pubcb(pub):
    print("[{}] Published: {}".format(pub[0], pub[1]))

def datacb(msg):
    # This runs in the MQTT Thread. 
    # WE MUST NOT TOUCH UART HERE.
    print("[Data] Topic: {}, Msg: {}".format(msg[1], msg[2]))

    try:
        payload = json.loads(msg[2])
        cmd = payload.get('message') # The command string
        dev_id = payload.get('deviceID')
        litres = payload.get('litres', 0)
        
        # 1. Handle System Commands (No specific address needed)
        if cmd == "check_update" or cmd == "check_status":
            _thread.lock()
            globals.CMD_QUEUE.append({
                "cmd": cmd,
                "addr": None,
                "dev_id": dev_id,
                "litres": 0
            })
            _thread.unlock()
            print("Queued System Command: {}".format(cmd))
            return

        # 2. Handle Device-Specific Commands
        addr = get_device_Hex(dev_id)
        
        if not addr:
            print("Invalid Device ID")
            return

        # Pass raw data to queue for Main Thread to process
        cmd_data = {
            "cmd": cmd,
            "addr": addr,
            "dev_id": dev_id,
            "litres": litres,
            "mode": payload.get('mode')
        }

        _thread.lock()
        globals.CMD_QUEUE.append(cmd_data)
        _thread.unlock()
        
        print("Queued Device Command: {}".format(cmd))

    except Exception as e:
        print("MQTT Parse Error: {}".format(e))

# ---------------- MQTT INITIALIZATION ---------------- #

mqtt = network.mqtt(
    MQTT_CLIENT_ID, MQTT_BROKER_HOST, user=MQTT_CLIENT_USERNAME, password=MQTT_CLIENT_PASSWORD,
    port=MQTT_BROKER_PORT, autoreconnect=True, clientid=MQTT_CLIENT_ID,
    connected_cb=conncb, disconnected_cb=disconncb, subscribed_cb=subscb,
    published_cb=pubcb, data_cb=datacb
)

# QoS 1 (at-least-once), matching the backend's publish/subscribe QoS - kept
# the same on both ends deliberately, since MQTT only guarantees min(sender
# QoS, receiver QoS) anyway, so a mismatch here would silently cap delivery
# at the lower side. Not QoS 2: the broker/client four-way handshake adds
# latency this old REPL's serial link doesn't need, and the backend already
# tolerates the occasional duplicate QoS 1 can produce. Not verified against
# the binding's own help() text (that query hung repeatedly against this old
# REPL over a live serial session) - so every call site tries qos=1 first
# and transparently falls back to the no-qos default if the native binding
# doesn't accept the keyword, rather than assuming and risking a crash.
MQTT_QOS = getattr(globals, 'MQTT_QOS', 1)

def _subscribe(mqtt, topic):
    try:
        mqtt.subscribe(topic, qos=MQTT_QOS)
    except TypeError:
        mqtt.subscribe(topic)

def _publish(mqtt, topic, message):
    try:
        mqtt.publish(topic, message, qos=MQTT_QOS)
    except TypeError:
        mqtt.publish(topic, message)

def mqttInitialize(mqtt, topic_list):
    loopCount = 10
    mqtt.start()
    utime.sleep(2)

    while mqtt.status()[0] != 2 and loopCount > 0:
        print("MQTT Connecting...")
        utime.sleep(1)
        loopCount -= 1

    if mqtt.status()[0] != 2:
        print("MQTT Failed")
        return None

    print("MQTT Connected")
    for topic in topic_list:
        _subscribe(mqtt, topic)
    return mqtt

def mqttPublish(mqtt, topic, message):
    try:
        _publish(mqtt, topic, message)
    except Exception as e:
        print("Publish Error:", e)

def publish(topic, message):
    """
    Bound to this module's single `mqtt` client - matches the (topic,
    message) signature every direct-publish call site in main.py used, and
    the publish_func(topic, message) signature meter.py's
    read_meter_parameters_upload()/monitor_target() call. Always goes
    through the QoS-aware _publish() above, unlike calling
    meter_mqtts.mqtt.publish() directly (what main.py did everywhere
    before this), which has no QoS applied at all.
    """
    _publish(mqtt, topic, message)