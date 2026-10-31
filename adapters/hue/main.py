import asyncio                      # run async code using an event loop
import os                           # access to environment variables

import httpx                        # HTTP client used to connect with Hue Bridge API
from dotenv import load_dotenv      # loads environment variables from a .env, required as our Hue IP and Key are stored there

import aiomqtt                      #
import json                         #

from datetime import datetime 

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# MILESTONE 1 - GET HUE LLIGHTS INFO - JSON RESPONSE --------------------------------------------------------------------------------------------------------------------------
async def get_hue_lights(bridge_ip, app_key):
    
    url = f"https://{bridge_ip}/clip/v2/resource/light"         # construct the URL for the Hue API v2 light endpoints
                                                                # this endpoint returns information about all lights connected to the bridge
    
    # HTTP headers contain additional information sent with the request
    # Hue Bridge requires the application key to authenticate API requests
    headers = {
        "hue-application-key": app_key
    }
    
    # Create an async HTTP client to communicate with the Hue Bridge
    async with httpx.AsyncClient(       # opens HTTP client and closes it automatically when done
        verify=False,                   # disables SSL certificate verification ebcause the Hue Bridge uses a certificate that is not trusted by default
        timeout=10.0,                   # times out after 10 seconds,  prevents the request from wiating indefinitely if the bridge does not respond
        trust_env=False                 # prevents system environment settings from interfering 
    ) as client:
        response = await client.get(url,headers=headers)        # pauses this coroutine until the HTTP request completes without blocking the entire asyncio event loop
                                                                # headers include app key 

        response.raise_for_status()         # check if HTTP request was successful

        lights = response.json().get("data",[])             # convert JSON object to Python Dictionary
                                                            # returns JSON object containing the data field that holds a list of light objects

        log(f'[INFO] Found {len(lights)} Hue Lights')   # print num of lights found

        for light in lights:        # iterate through lights list 

            light_id = light["id"]      # get ID assigned to this light , can be used to identify light in MQTT

            on = light.get("on",{}).get("on")   # retrieve the light's current power state (TRUE / FALSE)
                                                # Hue API stores - "on": {"on":true}
                                                # .get() safetly handles missing fields

            brightness=light.get("dimming",{}).get("brightness")    # retrieve the light's current brightness level
                                                                    # Hue API stores - "dimming": {"brightness": 75.0}
                                                                    # Brightness is represented as a percentage
                                                                    # Returns None, if not supported

            log(f"[DEBUG] Device Found: [light_id: \"{light_id}\", on: \"{on}\", brightness: \"{brightness}\"]")  # print data in the form of a debug log


    return lights

# MILESTONE 2 - PUBLISH LIGHTS TO MQTT ----------------------------------------------------------------------------------------------------------------------------------------
def build_device_messages(light):

    # Convert Hue API Light resource into two standardized MQTT messages
    #   1. info -> Device and capabilities
    #   2. state -> Describes the device's currect values
    # This allows our smart home system to communicate with different manufacturers using the same data structure 

    light_id = light["id"]                  # get unique identifier assigned to the light from Hue Bridge
    device_id = f"hue-{light_id}"           # Add hue- to distinguish Hue devices

    metadata = light.get("metadata",{})     # get metadata, includes info such as user-assigned name. Empty Dictionary if empty
    name = metadata.get("name",device_id)   # get name from metadata, use device-id if none
    
    capabilities = []       # create empty list that will contain all the light capabilities

    hue_capabilities = ["on", "dimming", "color", "color_temperature"]       # default hue capabilities 

    for h in hue_capabilities:          # iterate through default capabilities
        if h in light:                  # if light has this capability
            capabilities.append(h)      # append to light capability list

    # build device information payload
    info = {
        "id":device_id,
        "name":name,
        "manufacturer":"Philips Hue",
        "type":"light",
        "capabilities":capabilities
    }

    state = {}          # create a dictionary with light's current state
                        # unlike info, this contains values that can change while smart home is running

    if "on" in light:                                                           # get current light on/off state
        state["on"] = light["on"]["on"]                                         # True -> On , False -> Off

    if "dimming" in light:                                                      # get current brightness %
        state["brightness"] = light["dimming"]["brightness"]                    # preserved value from hue from a scale of 0-100%

    if "color" in light:                                                        # get current light color
        state["color"] = light["color"].get("xy")                               # Hue uses the CIE XY Color Space rather than RGB, this is preserved and converted later

    if "color_temperature" in light:                                            # get current color temperature
        state["color_temperature"] = light["color_temperature"].get("mirek")    # Hue uses "mirek" (micro reciprocal kelvin)
                                                                                # lower mirek = cooler white, higher mirek = warmer white
                                                                                # converted later, original mirek is perserved

    return device_id, info, state 

async def publish_lights(mqtt_host, mqtt_port,lights):
    # Connect to Mosquitto and publish two retained MQTT messages for every Hue Light:
    #
    # home/device/<device_id>/info
    # home/device/<device_id>/state
    #
    # Both messages use QoS 1 and retain=True

    # Establish an async connection to the MQTT broker
    async with aiomqtt.Client(  # "async with" automatically manages the conection
        hostname=mqtt_host,         # mqtt_host -> IP address of Mosquitto
        port=mqtt_port              # mqtt_port -> MQTT listening port 
    ) as mqtt:

        log(f"[INFO] Connected to MQTT Broker \n\tHOST: {mqtt_host}\n\tPORT: {mqtt_port}")

        for light in lights:

            device_id, info, state = build_device_messages(light)           # convert the Hue API response into the standardized 
                                                                            # device ID, information payload, and state payload
                                                                            # this seprates Hue-specific data from the MQTT logic
            
            base_topic = f"home/device/{device_id}"         # construct base MQTT topic for the device

            await mqtt.publish(                 # publish device information
                f"{base_topic}/info",           # topic 
                payload=json.dumps(info),       # converts python dict into a JSON string
                qos=1,                          # quality of service level 1, Delivery is "at least once", so duplicates are possible
                retain=True                     # tells mosquitto to store the latest message for this exact topic 
            )

            await mqtt.publish(                 # publish device state
                f"{base_topic}/state",          # topic
                payload=json.dumps(state),       # converts python dict into a JSON string
                qos=1,                          # quality of service level 1, Delivery is "at least once", so duplicates are possible
                retain=True                     # tells mosquitto to store the latest message for this exact topic 
            )

            log(f"[DEBUG] Published: {device_id}\n\t{info}\n\t{state}")

        log("[INFO] All Hue Lights published successfully")

# MAIN FUNCTION ---------------------------------------------------------------------------------------------------------------------------------------------------------------
async def main():
    
    load_dotenv()           # loads variables from .env files into this environment
                            # this allows us to keep sensitive information safe and out of our source code
    
    BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")          # load Hue Bridge IP Address environment variable
    APP_KEY = os.getenv("HUE_APP_KEY")              # load Hue Application Key environment variable
    
    if not BRIDGE_IP or not APP_KEY:
        raise ValueError("Mising Hue Configuration in .env")    # throws an error if either Hue IP or Key are missing

    # MILESTONE 1 - GET HUE LLIGHTS INFO - JSON RESPONSE ----------------------------------------------------------------------------------------------------------------------
    hue_lights = await get_hue_lights(BRIDGE_IP,APP_KEY) 

    # MILESTONE 2 - PUBLISH LIGHTS TO MQTT ------------------------------------------------------------------------------------------------------------------------------------
    MQTT_HOST = os.getenv("MQTT_HOST","127.0.0.1")                  # load MQTT Broker Host IP address environment variable
                                                                    # defaults to 127.0.0.1 if not specified
    MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))                  # load MQTT Port environment variable
                                                                    # defaults to 1883 if not specified
                                                                    # environment variables are strings, so int() converts it into an integer that is expected by aiomqtt
    
    await publish_lights(MQTT_HOST,MQTT_PORT,hue_lights)            # publish each discovered lisght information and current state to mosquitto 


if __name__ == "__main__":
    asyncio.run(main())     # Start the asyncio event loop and execute the main() coroutine
                            # the event manages asynchronous operations such as HTTP requests 
