import asyncio                      # run async code using an event loop
import os                           # access to environment variables

import httpx                        # HTTP client used to connect with Hue Bridge API
from dotenv import load_dotenv      # loads environment variables from a .env, required as our Hue IP and Key are stored there

import aiomqtt                      #
import json                         #

from datetime import datetime 

# LOG HELPER FUNCTION --------------------------------------------------------------------------------------------------------------------------------------------------------
def getTimestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message):
    print(f"{getTimestamp()} hue-adapter{message}")

async def get_hue_lights(bridge_ip, app_key):

    func_log = f".get_hue_lights"
    
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

        log(f"{func_log} [INFO] found {len(lights)} hue lights")   # print num of lights found

        for light in lights:        # iterate through lights list 

            light_id = light["id"]      # get ID assigned to this light , can be used to identify light in MQTT

            on = light.get("on",{}).get("on")   # retrieve the light's current power state (TRUE / FALSE)
                                                # Hue API stores - "on": {"on":true}
                                                # .get() safetly handles missing fields

            brightness=light.get("dimming",{}).get("brightness")    # retrieve the light's current brightness level
                                                                    # Hue API stores - "dimming": {"brightness": 75.0}
                                                                    # Brightness is represented as a percentage
                                                                    # Returns None, if not supported

            log(f"{func_log} [DEBUG] Device Found: [light_id: \"{light_id}\", on: \"{on}\", brightness: \"{brightness}\"]")  # print data in the form of a debug log

    return lights

def build_device_messages(light):           # Convert Hue API Light resource into two standardized MQTT messages
                                            #   1. info -> Device and capabilities
                                            #   2. state -> Describes the device's currect values
                                            # This allows our smart home system to communicate with different manufacturers using the same data structure 
    func_log = f".build_device_messages"
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

async def publish_lights(mqtt,lights):      # Connect to Mosquitto and publish two retained MQTT messages for every Hue Light:
                                            #
                                            # home/device/<device_id>/info
                                            # home/device/<device_id>/state
                                            #
                                            # Both messages use QoS 1 and retain=True
    func_log = f".publish_lights"
    known_devices = {}

    # Establish an async connection to the MQTT broker
    for light in lights:

        device_id, info, state = build_device_messages(light)           # convert the Hue API response into the standardized 
                                                                        # device ID, information payload, and state payload
                                                                        # this seprates Hue-specific data from the MQTT logic
            
        base_topic = f"home/device/{device_id}"         # construct base MQTT topic for the device

        known_devices[device_id] = {
            "light_id": light["id"],
            "capabilities": info["capabilities"],
            "state": state.copy()
        }

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

        log(f"{func_log} [DEBUG] published: {device_id}\n\t{info}\n\t{state}")

    log(f"{func_log} [INFO] all hue lights published successfully")

    return known_devices

def build_hue_commands(command,capabilities):                                       # Convert an MQTT command into a Hue API v2 payload. 

    func_log = f".build_hue_commands"
    
    if not isinstance(command,dict):        # MQTT commands must be JSON objects
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] command must be a json object")

    if not command:                         # MQTT commands cannot be empty
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] command cannot be empty")

    hue_payload = {}            # create an empty dict for the Hue API payload 

    allowed_fields = {"on","brightness"}        # only accepts fields the adapter understands
    unknown = set(command) - allowed_fields     # finds fields in the command that are not allowed

    if unknown:     # reject commands containing unsupported fields 
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] unsupported fields: {unknown}")

    if "on" in command:         # translate the on/off control 

        if "on" not in capabilities:            # check if the light supports on/off support 
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light does not supprot on/off support") 
        
        if not isinstance(command["on"], bool):     # make sure the value is true or false, not string/int
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] \'on\' must be true or false")

        hue_payload["on"]={         # convert {"on": True} -> {"on", {"on":True}}
            "on": command["on"]
        }

    if "brightness" in command:          # translate the brightness control 

        if "dimming" not in capabilities:        # check if brightness control is in capabilities
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light does not support brightness control") 

        brightness = command["brightness"]          # extract the brightness value from the command

        if type(brightness) not in (int,float):     # check if brightness is a int or float
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] brightness must be a number") 

        if brightness <=0 or brightness > 100:     # check if brightness is within range 
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] brightness command given is outside of range. acceptable range 0-100%.") 

        hue_payload["dimming"] = {       # convert brightness into the Hue API dimming format 
            "brightness": brightness
        }

    return hue_payload

async def send_hue_command(client, bridge_ip, app_key, light_id, hue_payload):      # send a command to a specific Hue Light using the Hue API v2

    func_log = f".send_hue_command"
    
    # construct the API endpoint for this light
    url = (
        f"https://{bridge_ip}"
        f"/clip/v2/resource/light/{light_id}"
    )

    headers = {
        "hue-application-key": app_key      # auth with our Hue Application Key
    }

    log(f"{func_log} [DEBUG] hue PUT payload: {hue_payload}")

    response = await client.put(        # PUT sends the requested light changes 
        url,
        headers=headers,
        json=hue_payload
    )
    log(f"{func_log} [DEBUG] hue PUT response: {response.status_code}, {response.text}")

    response.raise_for_status()         # Raise an exception for HTTP error responses
    result = response.json()            # Hue API responses may contain application-level errors

    if result.get("errors"):
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] hue api errors: {result['errors']}")

    return result

async def listen_for_commands(mqtt, bridge_ip, app_key, known_devices):             # Listen for MQTT /set commands and forware valid commands to the Hue Bridge

    func_log = f".listen_for_commands"

    topic = "home/device/+/set"             # subscribe to commands for all device IDs. + wildcard matches exactly one topic level
    await mqtt.subscribe(topic,qos=1)       # subscribe to the topic with QoS 1

    log(f"{func_log} [DEBUG] subscribed to {topic}")   # confirm that the subscription was successful

    async with httpx.AsyncClient(           # create an async HTTP client for sending commands
        verify=False,                       # disables SSL certificate verification
        timeout=10.0,                       
        trust_env=False                     # ignores proxy settings from the environment
    ) as http_client:   

        async for message in mqtt.messages:     # continuously listen for incoming MQTT messages
                                                # async for waits without blocking other async tasks

            topic_parts = str(message.topic).split("/")        # split the MQTT topic

            if len(topic_parts) != 4:           # skip message if topic_parts does not = 4 
                continue

            device_id = topic_parts[2]          # extract device_id

            if message.retain:                  # reject retained MQTT commands to avoid replaying old commands
                log(f"{func_log} [DEBUG] ignoring retained command")
                continue

            if device_id not in known_devices:  # reject device_id if not a known device
                log(f"{func_log} [WARN] unknown device was found: \n\t{device_id}")
                continue

            device = known_devices[device_id]       # retreive stored information for the device. known_devices maps MQTT device IDs to Hue device details
            light_id = device["light_id"]           # get the actual Hue resource ID used by the Hue API
            capabilities = device["capabilities"]   # get the support features

            try:
                payload_text = message.payload.decode("utf-8")                                  # MQTT arrives in bytes, decode them into UTF-8 string
                command = json.loads(payload_text)                                              # parse the JSON string into a Python object

                hue_payload = build_hue_commands(command,capabilities)                       # validate the command and convert it into the formated expected by Hue API v2
                log(f"{func_log} [DEBUG] command received for {device_id}\n\t{command}")                   

                await send_hue_command(http_client,bridge_ip,app_key,light_id,hue_payload)      # send an HTTP PUT request to the Hue Bridge

                log(f"{func_log} [DEBUG] command accepted: {device_id}")       
            except(
                ValueError,
                UnicodeDecodeError,
                httpx.HTTPError
            ) as error:
                command = "no command was set" 
                log(f"{func_log} [ERROR] command failed for {device_id} with \n\t{error}\n\t{command}")  

def merge_light_state(current_state,hue_update):            # merge partial Hue light update

    func_log = f".merge_light_state"

    changed = False

    if "on" in hue_update:                                      # check if on is part of this hue update
        on_value = hue_update["on"].get("on")                   # extract the on/off value from Hue's nested dictionary

        if(isinstance(on_value,bool)):                          # verify on_value is type bool
            if(current_state.get("on") != on_value):            # compare the new value with the current MQTT state; only update if the values are different
                current_state["on"] = on_value                  # if true, set current_state to update
                changed = True                                  # and update changed flag to True
                log(f"{func_log} [DEBUG] on state changed to: {on_value}")

    if "dimming" in hue_update:                                 # check if dimming is part of hue update
        brightness = hue_update["dimming"].get("brightness")    # extract brightness value from hue_update

        if(isinstance(brightness,(int,float))):                 # check if brightness is a type int or float 
            if current_state.get("brightness") != brightness:   # compare the new value with the current MQTT state; only update if the values are different
                current_state["brightness"] = brightness        # if true, set current_state to update
                changed = True                                  # and update changed flag to True
                log(f"{func_log} [DEBUG] brightness value changed to: {brightness}")

    if "color" in hue_update:                                   # check if color is changed in hue update  
        xy = hue_update["color"].get("xy")                      # extract the xy color characteristics from the hue update

        if xy is not None:                                      # verify xy is not empty / None
            if current_state.get("color") != xy:                # compare the new value with the current MQTT state; only update if the values are different
                current_state["color"] = xy                     # if true, set current_state to update
                changed = True                                  # and update changed flag to True
                log(f"{func_log} [DEBUG] xy value changed to: {xy}")

    if "color_temperature" in hue_update:                       # check if color_temperature is changed in hue update
        mirek = hue_update["color_temperature"].get("mirek")    # extract the mirek color temp characteristics from the hue update

        if mirek is not None:                                   # verify mirek is not None or empty
            if current_state.get("color_temperature") != mirek: # compare the new value with the current MQTT state; only update if the values are different
                current_state["color_temperature"] = mirek      # if true, set current_state to update
                changed = True                                  # and update changed flag to True
                log(f"{func_log} [DEBUG] color temperature value changed to: {mirek}")
    
    return changed

async def read_sse_events(response):                        # read SSE events from an HTTP streaming response
                                                            # yield parsed JSON event batches whenever a complete SSE message is received
    
    func_log = f".read_sse_events"

    data_lines = []         # create an empty list to store data liens from an SSE event

    async for line in response.aiter_lines():       # asynchronously read each line from the HTTP resposne stream
                                                    # aiter_lines returns lines as they arrive from the Hue Bridge

        if line == "":          # blank line marks the end of an SSE event

            if data_lines:                              # only process the event if data lines were collected 
                data_text = "\n".join(data_lines)       # combine all collected data lines into one string 
                data_lines.clear()                      # clear the list for next SSE event

                try:                                            # attempt to convert the SSE data into JSON
                    yield json.loads(data_text)                 # parse the JSON string into a python object
                                                                # yield returns the data while keeping the generator running

                except json.JSONDecodeError as error:           # catch errors if SSE data is not valid JSON
                    log(f"{func_log} [ERROR] invalid sse json: {error}")

            continue

        if line.startswith(":"):                        # ignore SSE comments and keep-alive lines
            continue                                    # lines starting with ":" do not contain event data

        if line == "data":                              # check for a data field with no value
            data_lines.append("")                       # marks the end of data stream, add an empty string to the end of data_lines
        elif line.startswith("data:"):                  # check if line begins with "data:" field
            data_lines.append(line[5:].lstrip(" "))     # these lines contain the actual event information
                                                        # remove the first 5 chars ("data:")
                                                        # lstrip(" ") removes any leading spaces from the value
                                                        # apepend the extracted data to our list 

async def process_hue_events(mqtt,events,known_devices):    # process Hue event batches and publish updated MQTT states whe values change

    func_log = f".process_hue_events"

    # log(f"{func_log} [DEBUG] raw hue event:\n\t{json.dumps(events,indent=2)}")

    if not isinstance(events,list):         # ignore the data if it is not a list. Hue sends events as a list of dictionaries 
        return

    for event in events:                            # iterate through events received from the hue bridge
        if event.get("type") != "update":           # only process events that report a resource update
            continue        

        for resource in event.get("data",[]):       # each event can contain updates for multiple resources
                                                    # .get("data",[]) returns an empty list if "data" is missing
            if resource.get("type") != "light":     # skip all resources that aren't type light
                continue

            light_id = resource.get("id")           # extract resource id 
            if not light_id:                        # ignore light if there isn't a valid id 
                continue

            device_id = f"hue-{light_id}"           #  convert the Hue resource ID into the MQTT device ID
            if device_id not in known_devices:      # ignore device if unknown
                log(f"{func_log} [WARN] unknown hue light: {light_id}")
                continue

            current_state = known_devices[device_id]["state"]       # retrieve the light's previously stored state 

            changed = merge_light_state(current_state, resource)    # merge the new Hue update into the existing state. 
                                                                    # returns true if the state changed 
            
            if not changed:         # no values changed; there is no need to publish
                continue            # skip resource

            topic = f"home/device/{device_id}/state"        # build MQTT topic where the light's state is published

            await mqtt.publish(                             # publish the complete updated state to MQTT
                topic,                                  
                payload=json.dumps(current_state),
                qos=1,                                      # Quality of Service level 1, at least once delivery
                retain=True                                 # retained messages; stores the latest state for new subscribers
            )

            log(f"{func_log} [DEBUG] live state updated: {device_id}\n\t{current_state}")

async def refresh_light_states(mqtt, bridge_ip, app_key, known_devices):    # fetch current Hue light states and reconcile them with the adapter's cached states

    func_log = f".refresh_light_states"

    lights = await get_hue_lights(bridge_ip,app_key)            # request the latest light information from the Hue bridge
                                                                # await waits for the HTTP request without blocking other tasks

    for light in lights:                                    # loop thorugh lights

        device_id = f"hue-{light["id"]}"                    # extract light id and create MQTT id 
        if device_id not in known_devices:                  # ignore if unknown device
            continue

        _,_,new_state = build_device_messages(light)        # _ ignores return values. convert Hue light data into our MQTT format. 
        current_state = known_devices[device_id]["state"]   # retrieve the previously cahced state for this light

        if current_state == new_state:                      # compare the cached state with the latest hue state
            continue                                        # skip if identical state

        known_devices[device_id]["state"] = new_state       # replace current state to new state

        await mqtt.publish(                                 # publish the updated state to the light's MQTT topic
            f"home/device/{device_id}/state",               # topic
            payload=json.dumps(new_state),                  
            qos=1,                                          # quality of service level 1
            retain=True                                     # retained enabled
        ) 

        log(f"{func_log} [DEBUG] state refreshed: {device_id}")

    return 

async def listen_for_hue_events(mqtt, bridge_ip, app_key, known_devices):   # continously listen to Hue's SSE events, reconnect if stream closes or temporary network error

    func_log = f"listen_for_hue_events"

    url = f"https://{bridge_ip}/eventstream/clip/v2"            # build the Hue Bridge URL for receiving live SSE

    headers = {                                                 # set HTTP headers required by the Hue Bridge
        "hue-application-key": app_key,
        "Accept": "text/event-stream"
    }

    timeout = httpx.Timeout(        # configure timeout for HTTP connection
        connect=10.0,
        read=None,
        write=10.0,
        pool=10.0
    )

    async with httpx.AsyncClient(   # create in async HTTP client for the Hue Bridge
        verify=False,
        timeout=timeout,
        trust_env=False
    ) as client:
        while True:                                                             # keep lisenting forever, reconnect if necessary
            try:                                                                # establish and maintain the SSE connection
                log(f"{func_log} [DEBUG] connecting to hue event stream...")               

                async with client.stream(                                       # open a streaming HTTP GET connection to the Hue Bridge
                    "GET",                                                      # streaming lets us receive events without closing ther request
                    url=url,
                    headers=headers
                ) as response:
                    response.raise_for_status()                                 # raise an exception if the HTTP response is an error
                    log(f"{func_log} [DEBUG] connected to hue event stream")               

                    await refresh_light_states(mqtt,bridge_ip,app_key,known_devices)    # reconcile states after re-connecting

                    async for events in read_sse_events(response):              # read each complete SSE event from the stream
                        await process_hue_events(mqtt,events,known_devices)     # pass the received events to our MQTT processing function

                log(f"{func_log} [DEBUG] hue event stream closed")
            except httpx.HTTPError as error:                                    # catch HTTP erros such as connection failures or bad responses
                log(f"{func_log} [ERROR] hue event stream error: {error}")

            log(f"{func_log} [DEBUG] reconnecting in 5 seconds...")
            await asyncio.sleep(5)                                              # wait 5 seconds before attempting to reconnect

# MAIN FUNCTION ---------------------------------------------------------------------------------------------------------------------------------------------------------------
async def main():

    func_log = f".main"

    load_dotenv()           # loads variables from .env files into this environment
                            # this allows us to keep sensitive information safe and out of our source code
    
    BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")          # load Hue Bridge IP Address environment variable
    APP_KEY = os.getenv("HUE_APP_KEY")              # load Hue Application Key environment variable

    MQTT_HOST = os.getenv("MQTT_HOST","127.0.0.1")                  # load MQTT Broker Host IP address environment variable
                                                                        # defaults to 127.0.0.1 if not specified
    MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))                  # load MQTT Port environment variable
                                                                    # defaults to 1883 if not specified
                                                                    # environment variables are strings, so int() converts it into an integer that is expected by aiomqtt
    
    MQTT_AVAILABILITY_TOPIC = "home/adapter/hue/availability"
    MQTT_ONLINE = "online"
    MQTT_OFFLINE = "offline"
    
    if not BRIDGE_IP or not APP_KEY:
        raise ValueError("Mising Hue Configuration in .env")    # throws an error if either Hue IP or Key are missing
    
    last_will = aiomqtt.Will(                   # define the message mosquitto should publish if the adapter unexpectedly loses its MQTT connection
        topic=MQTT_AVAILABILITY_TOPIC,
        payload=MQTT_OFFLINE,
        qos=1,
        retain=True
    )

    while True:
        try:

            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                will=last_will,
                keepalive=10
            ) as mqtt:

                log(f"{func_log} [INFO] connected to mqtt broker: \n\thost: {MQTT_HOST}\n\tport: {MQTT_PORT}")

                hue_lights = await get_hue_lights(BRIDGE_IP,APP_KEY)
                known_devices = await publish_lights(mqtt,hue_lights)               # publish each discovered light information and current state to mosquitto

                await mqtt.publish(
                    MQTT_AVAILABILITY_TOPIC,
                    payload=MQTT_ONLINE,
                    qos=1,
                    retain=True
                )

                log(f"{func_log} [INFO] hue adapter is online...")

                try:
                    
                    async with asyncio.TaskGroup() as tasks:                            # TaskGroup ensure that if either fails, the other is cancelled and awaited as well
                        tasks.create_task(              # keep listening for commands
                            listen_for_commands(        
                                mqtt,
                                BRIDGE_IP,
                                APP_KEY,
                                known_devices
                                ),    
                        )

                        tasks.create_task(              # keep listening for hue events
                            listen_for_hue_events(
                                mqtt,
                                BRIDGE_IP,
                                APP_KEY,
                                known_devices
                                )    
                        )

                except asyncio.CancelledError:
                    try:                                    # CTRL+C causes asyncio.run() to cancel the main task, publish offlie while the client is still conencted
                        await mqtt.publish(
                            MQTT_AVAILABILITY_TOPIC,
                            payload=MQTT_OFFLINE,
                            qos=1,
                            retain=True
                        )
                        print("\n")
                        log(f"{func_log} [INFO] hue adapter is offline...")
                    except:
                        log(f"{func_log} [ERROR] could not publish offline: mqtt connection unavailable")

                    raise       # preserve cancellation so hte application actually shuts down. 

        except* (aiomqtt.MqttError, httpx.HTTPError) as errors:
            log(f"{func_log} [ERROR] mqtt or hue bridge connection failed \n\t{errors}")

        log(f"{func_log} [INFO] retrying mqtt connection in 5 seconds...")
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())     # Start the asyncio event loop and execute the main() coroutine
                                # the event manages asynchronous operations such as HTTP requests 
    except KeyboardInterrupt:
        print("\n")
        log(f".__name__ [INFO] Adapter stopped by user")