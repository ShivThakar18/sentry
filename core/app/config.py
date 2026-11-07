import os
import socket 

MQTT_HOST = os.environ.get("MQTT_HOST","localhost")                                     # env variables with default values, configured same as my CLI
MQTT_PORT = int(os.environ.get("MQTT_PORT","1883"))

MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", f"sentry-{socket.gethostname()}")     # every MQTT client needs a UNIQUE id. If two clients connect with the same ID
                                                                                        # the broker kcicks the first one off
                                                                                        # With a core on the PC and one on the PI, they'd kick each other off forever
                                                                                        # Adding the hostname makes each machine's id different by default

MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", "10"))                            # seconds between pings when nothing else is sent. the broker decides the core
                                                                                        # is gone after about 1.5 x MQTT_KEEPALIVE                      

MQTT_RECONNECT_SECONDS = float(os.environ.get("MQTT_RECONNECT_SECONDS","3"))            # how long to wait before trying to reconnect after the broker disappears

