import os

MQTT_HOST = os.environ.get("MQTT_HOST","localhost")     # env variables with default values, configured same as my CLI
MQTT_PORT = int(os.environ.get("MQTT_PORT","1883")) 