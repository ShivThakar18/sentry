import asyncio                      # run async code using an event loop
import os                           # access to environment variables

import httpx                        # HTTP client used to connect with Hue Bridge API
from dotenv import load_dotenv      # loads environment variables from a .env, required as our Hue IP and Key are stored there

import aiomqtt                      #
import json                         #

from datetime import datetime 

# HUE -> CAPABILITY DICTIONARY -----------------------------------------------------------------------------------------------------------------------------------------------
HUE_TO_CAPABILITY = {
    "on": "on_off",
    "dimming": "brightness",
    "color": "color_xy",
    "color_temperature": "color_temp_k"
}

AVAILABLE_STATUSES = {"connected"}
# LOG HELPER FUNCTION --------------------------------------------------------------------------------------------------------------------------------------------------------
def getTimestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message):
    print(f"{getTimestamp()} hue-adapter{message}",flush=True)

# CONVERSION HELPERS ---------------------------------------------------------------------------------------------------------------------------------------------------------
def kelvin_to_mirek(kelvin):
    return round(1_000_000 / kelvin)

def mirek_to_kelvin(mirek):
    return round(1_000_000 / mirek)

def color_temp_to_kelvin(color_temperature):
    mirek = color_temperature.get("mirek")
    if not color_temperature.get("mirek_valid",True) or not mirek:
        return None
    return mirek_to_kelvin(mirek)

# HUE ADAPTERS FUNCTION ------------------------------------------------------------------------------------------------------------------------------------------------------
async def get_hue_connectivity(bridge_ip, app_key):

    func_log = f".get_hue_connectivity"

    url = f"https://{bridge_ip}/clip/v2/resource/zigbee_connectivity"
    headers = {
        "hue-application-key": app_key
    }

    async with httpx.AsyncClient(verify=False, timeout=10.0, trust_env=False) as client:
        response = await client.get(url,headers=headers)
        response.raise_for_status()

        connectivity = {}

        for zc in response.json().get("data",[]):
            owner_rid = zc.get("owner",{}).get("rid")
            status = zc.get("status")
            if owner_rid and status:
                connectivity[owner_rid] = status

    log(f"{func_log} [INFO] found {len(connectivity)} zigbee connectivity entries")

    return connectivity

async def get_hue_rooms(bridge_ip, app_key):

    func_log = f".get_hue_rooms"

    url = f"https://{bridge_ip}/clip/v2/resource/room"
    headers = {
        "hue-application-key":app_key
    }

    async with httpx.AsyncClient(verify=False,timeout=10.0,trust_env=False) as client:
        response = await client.get(url,headers=headers)
        response.raise_for_status()

    rooms = {}

    for room in response.json().get("data",[]):
        room_name = room.get("metadata",{}).get("name")

        for child in room.get("children",[]):
            if child.get("rtype") == "device" and child.get("rid"):
                rooms[child["rid"]] = room_name

    log(f"{func_log} [INFO] found {len(rooms)} devices assigned to rooms")

    return rooms

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

def build_device_messages(light, room=None):            # Convert Hue API Light resource into two standardized MQTT messages
                                                        #   1. info -> Device and capabilities
                                                        #   2. state -> Describes the device's currect values
                                                        # This allows our smart home system to communicate with different manufacturers using the same data structure 
    func_log = f".build_device_messages"
    light_id = light["id"]                  # get unique identifier assigned to the light from Hue Bridge
    device_id = f"hue-{light_id}"           # Add hue- to distinguish Hue devices

    metadata = light.get("metadata",{})     # get metadata, includes info such as user-assigned name. Empty Dictionary if empty
    name = metadata.get("name",device_id)   # get name from metadata, use device-id if none
    
    capabilities = [cap for hue_key, cap in HUE_TO_CAPABILITY.items() if hue_key in light]
    limits = {}

    state = {}          # create a dictionary with light's current state
                        # unlike info, this contains values that can change while smart home is running

    if "on" in light:                                                           # get current light on/off state
        state["on"] = light["on"]["on"]                                         # True -> On , False -> Off

    if "dimming" in light:                                                      # get current brightness %
        state["brightness"] = light["dimming"]["brightness"]                    # preserved value from hue from a scale of 0-100%

    if "color" in light:                                                        # get current light color
        state["color_xy"] = light["color"].get("xy")                            # Hue uses the CIE XY Color Space rather than RGB, this is preserved and converted later

    if "color_temperature" in light:                                                # get current color temperature
        mirek = light["color_temperature"].get("mirek")                             # Hue uses "mirek" (micro reciprocal kelvin)
        state["color_temp_k"] = color_temp_to_kelvin(light["color_temperature"])    # lower mirek = cooler white, higher mirek = warmer white                                                         
        schema = light["color_temperature"].get("mirek_schema",{})
        mirek_min = schema.get("mirek_minimum",153)
        mirek_max = schema.get("mirek_maximum",500)
        limits["color_temp_k_range"] = [mirek_to_kelvin(mirek_max),mirek_to_kelvin(mirek_min)]

    # build device information payload
    info = {
        "id":device_id,
        "name":name,
        "manufacturer":"Philips Hue",
        "adapter":"hue",
        "type":"light",
        "room":room,
        "capabilities":capabilities,
        **limits
    }

    return device_id, info, state 

async def publish_device(mqtt, light, connectivity, rooms, known_devices):

    func_log = f".publish_device"

    owner_rid = light.get("owner",{}).get("rid")

    device_id, info, state = build_device_messages(light,rooms.get(owner_rid))      # convert the Hue API response into the standardized 
                                                                                    # device ID, information payload, and state payload
                                                                                    # this seprates Hue-specific data from the MQTT logic

    state["available"] = connectivity.get(owner_rid) in AVAILABLE_STATUSES

    known_devices[device_id] = {
        "light_id": light["id"],
        "owner_rid": owner_rid,
        "capabilities": info["capabilities"],
        "color_temp_k_range": info.get("color_temp_k_range"),
        "state": state.copy()
    }

    base_topic = f"home/device/{device_id}"        # construct base MQTT topic for the device

    await mqtt.publish(f"{base_topic}/info",payload=json.dumps(info),qos=1,retain=True)         # publish device information
                                                                                                # topic 
                                                                                                # converts python dict into a JSON string
                                                                                                # quality of service level 1, Delivery is "at least once", so duplicates are possible
                                                                                                # tells mosquitto to store the latest message for this exact topic 
    await mqtt.publish(f"{base_topic}/state",payload=json.dumps(state),qos=1,retain=True)       # publish device state
                                                                                                # topic
                                                                                                # converts python dict into a JSON string
                                                                                                # quality of service level 1, Delivery is "at least once", so duplicates are possible
                                                                                                # tells mosquitto to store the latest message for this exact topic

    log(f"{func_log} [DEBUG] published: {device_id}\n\t{info}\n\t{state}")

async def remove_device(mqtt,device_id,known_devices):          # clear a deleted light's retained topics so it doesn't stay behind as a ghost

    func_log = f".remove_device"

    base_topic = f"home/device/{device_id}"

    await mqtt.publish(f"{base_topic}/state",payload=None,qos=1,retain=True)        # an empty retained payload deleted the retained message
    await mqtt.publish(f"{base_topic}/info",payload=None,qos=1,retain=True)         # state first then info, signals the core of the device is gone
        
    known_devices.pop(device_id,None)

    log(f"{func_log} [INFO] removed: {device_id}")

async def find_retained_devices(mqtt, window=1.0):
    func_log = f".find_retained_devices"

    topic = "home/device/+/info"
    found = set()

    await mqtt.subscribe(topic,qos=1)       # retained info messages are delivered right after subscribing

    try:
        async with asyncio.timeout(window):
            async for message in mqtt.messages:
                if not message.payload:
                    continue

                try:
                    info = json.loads(message.payload.decode("utf-8"))
                except ValueError:
                    log(f"{func_log} [WARN] bad retained info on {message.topic}")
                    continue

                if not isinstance(info,dict) or info.get("adapter") != "hue":
                    continue

                found.add(str(message.topic).split("/")[2])
    except TimeoutError:
        pass
    finally:
        await mqtt.unsubscribe(topic)

    log(f"{func_log} [INFO] found {len(found)} retained hue devices")

    return found

async def publish_lights(mqtt,lights, connectivity, rooms):        # Connect to Mosquitto and publish two retained MQTT messages for every Hue Light:
                                                            #
                                                            # home/device/<device_id>/info
                                                            # home/device/<device_id>/state
                                                            #
                                                            # Both messages use QoS 1 and retain=True
    func_log = f".publish_lights"
    known_devices = {}

    # Establish an async connection to the MQTT broker
    for light in lights:
        await publish_device(mqtt,light,connectivity,rooms, known_devices)

    log(f"{func_log} [INFO] all hue lights published successfully")

    return known_devices

def build_hue_commands(command,device):                                       # Convert an MQTT command into a Hue API v2 payload. 

    func_log = f".build_hue_commands"
    
    if not isinstance(command,dict):        # MQTT commands must be JSON objects
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] command must be a json object")

    if not command:                         # MQTT commands cannot be empty
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] command cannot be empty")


    capabilities = device["capabilities"]
    allowed_fields = {"on","brightness","color_xy","color_temp_k"}        # only accepts fields the adapter understands
    unknown = set(command) - allowed_fields                               # finds fields in the command that are not allowed

    if unknown:     # reject commands containing unsupported fields 
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] unsupported fields: {unknown}")

    if "color_xy" in command and "color_temp_k" in command: 
        raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] send color_xy or color_temp_k, not both")

    hue_payload = {}            # create an empty dict for the Hue API payload 

    if "on" in command:         # translate the on/off control 

        if "on_off" not in capabilities:            # check if the light supports on/off support 
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light does not supprot on/off support") 
        
        if not isinstance(command["on"], bool):     # make sure the value is true or false, not string/int
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] \'on\' must be true or false")

        hue_payload["on"]={         # convert {"on": True} -> {"on", {"on":True}}
            "on": command["on"]
        }

    if "brightness" in command:          # translate the brightness control 

        if "brightness" not in capabilities:        # check if brightness control is in capabilities
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light does not support brightness control") 

        brightness = command["brightness"]          # extract the brightness value from the command

        if type(brightness) not in (int,float):     # check if brightness is a int or float
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] brightness must be a number") 

        if not 0 < brightness <= 100:     # check if brightness is within range 
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] brightness command given is outside of range. acceptable range 0-100%.") 

        hue_payload["dimming"] = {       # convert brightness into the Hue API dimming format 
            "brightness": brightness
        }

    if "color_temp_k" in command:
        if "color_temp_k" not in capabilities:
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light does not support color temperature")

        kelvin = command["color_temp_k"]
        if type(kelvin) not in (int, float):
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] color_temp_k must be a number")

        k_range = device.get("color_temp_k_range")
        if not k_range:
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] no color temperature range known for this light")

        k_min, k_max = k_range

        if not k_min <= kelvin <= k_max:
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] color temperature (color_temp_k) not in range")

        hue_payload["color_temperature"] = {
            "mirek": kelvin_to_mirek(kelvin)
        }

    if "color_xy" in command:
        if "color_xy" not in capabilities:
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] light doesn't support color")
        xy = command["color_xy"]

        if not isinstance(xy,dict) or set(xy) != {"x","y"}:
            raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] color_xy must be x: .. y: ..")
        for axis in ("x", "y"):
            if type(xy[axis]) not in (int,float) or not 0 <= xy[axis] <= 1:
                raise ValueError(f"{getTimestamp()} hue-adapter{func_log} [ERROR] color_xy.{axis} must be a number 0-1")
        hue_payload["color"] = {
            "xy": {
                "x":xy["x"],
                "y":xy["y"]
                }
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

            if len(topic_parts) != 4 or topic_parts[3] != "set":           # skip message if topic_parts does not = 4 
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

            command = None

            try:
                payload_text = message.payload.decode("utf-8")                                  # MQTT arrives in bytes, decode them into UTF-8 string
                command = json.loads(payload_text)                                              # parse the JSON string into a Python object

                hue_payload = build_hue_commands(command,device)                       # validate the command and convert it into the formated expected by Hue API v2
                log(f"{func_log} [DEBUG] command received for {device_id}\n\t{command}")                   

                await send_hue_command(http_client,bridge_ip,app_key,light_id,hue_payload)      # send an HTTP PUT request to the Hue Bridge

                log(f"{func_log} [DEBUG] command accepted: {device_id}")       
            except(
                ValueError,
                UnicodeDecodeError,
                httpx.HTTPError
            ) as error:
                log(f"{func_log} [ERROR] command failed for {device_id} with \n\t{error}\n\t{message.payload!r}")  

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

        if xy is not None and current_state.get("color_xy") != xy:      # verify xy is not empty / None; compare the new value with the current MQTT state; only update if the values are different
            current_state["color_xy"] = xy                              # if true, set current_state to update
            changed = True                                              # and update changed flag to True
            log(f"{func_log} [DEBUG] xy value changed to: {xy}")

    if "color_temperature" in hue_update:                       # check if color_temperature is changed in hue update

        kelvin = color_temp_to_kelvin(hue_update["color_temperature"])

        if current_state.get("color_temp_k") != kelvin:                                 # compare the new value with the current MQTT state; only update if the values are different
            current_state["color_temp_k"] = kelvin                                      # # if true, set current_state to update
            changed = True                                                              # and update changed flag to True
            log(f"{func_log} [DEBUG] color temperature value changed to: {kelvin}")
                                                                      
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

async def handle_light_update(mqtt,resource,known_devices):
    func_log = f".handle_light_update"
    
    light_id = resource.get("id")
    if not light_id:
        return

    device_id = f"hue-{light_id}"
    if device_id not in known_devices:
        log(f"{func_log} [WARN] unknown hue light: {light_id}")
        return

    current_state = known_devices[device_id]["state"]
    
    changed = merge_light_state(current_state, resource)    # merge the new Hue update into the existing state. 
                                                            # returns true if the state changed 
    
    if not changed:      # no values changed; there is no need to publish
        return            # skip resource

    topic = f"home/device/{device_id}/state"        # build MQTT topic where the light's state is published

    await mqtt.publish(topic,payload=json.dumps(current_state),qos=1,retain=True)       # publish the complete updated state to MQTT

    log(f"{func_log} [DEBUG] live state updated: {device_id}\n\t{current_state}")

async def handle_light_add(mqtt,resource,known_devices,bridge_ip,app_key):

    func_log = f".handle_light_add"

    light_id = resource.get("id")
    if not light_id or f"hue-{light_id}" in known_devices:
        return

    rooms = await get_hue_rooms(bridge_ip,app_key)
    connectivity = await get_hue_connectivity(bridge_ip,app_key)

    await publish_device(mqtt,resource,connectivity,rooms,known_devices)

    log(f"{func_log} [INFO] new hue light added: {light_id}")

async def handle_light_delete(mqtt,resource,known_devices):
    light_id = resource.get("id")
    device_id = f"hue-{light_id}"

    if device_id in known_devices:
        await remove_device(mqtt,device_id,known_devices)

async def handle_connectivity_update(mqtt,resource,known_devices):

    func_log = f".handle_connectivity_update"

    owner_rid = resource.get("owner",{}).get("rid")
    status = resource.get("status")
    
    if not owner_rid or status is None:
        return

    available = status in AVAILABLE_STATUSES

    for device_id, device in known_devices.items():
        if device["owner_rid"] != owner_rid:
            continue
        
        current_state = device["state"]
        if current_state.get("available") == available:
            continue

        current_state["available"] = available

        topic = f"home/device/{device_id}/state"        # build MQTT topic where the light's state is published
        
        await mqtt.publish(topic,payload=json.dumps(current_state),qos=1,retain=True)       # publish the complete updated state to MQTT
        
        log(f"{func_log} [DEBUG] {device_id} available={available} (zigbee status: {status})")

async def process_hue_events(mqtt,events,known_devices,bridge_ip,app_key):    # process Hue event batches and publish updated MQTT states whe values change

    func_log = f".process_hue_events"

    if not isinstance(events,list):         # ignore the data if it is not a list. Hue sends events as a list of dictionaries 
        return

    for event in events:                            # iterate through events received from the hue bridge

        event_type = event.get("type")

        for resource in event.get("data",[]):
            resource_type = resource.get("type")

            if resource_type == "light":
                if event_type == "update":
                    await handle_light_update(mqtt,resource,known_devices)
                elif event_type == "add":
                    await handle_light_add(mqtt,resource,known_devices,bridge_ip,app_key)
                elif event_type == "delete":
                    await handle_light_delete(mqtt,resource,known_devices)
            elif resource_type == "zigbee_connectivity" and event_type == "update":
                await handle_connectivity_update(mqtt,resource,known_devices)

async def refresh_light_states(mqtt, bridge_ip, app_key, known_devices):    # fetch current Hue light states and reconcile them with the adapter's cached states

    func_log = f".refresh_light_states"

    lights = await get_hue_lights(bridge_ip,app_key)            # request the latest light information from the Hue bridge
                                                                # await waits for the HTTP request without blocking other tasks
    connectivity = await get_hue_connectivity(bridge_ip,app_key)
    rooms = await get_hue_rooms(bridge_ip,app_key)

    bridge_ids = {f"hue-{light["id"]}" for light in lights}

    for device_id in list(known_devices):
        if device_id not in bridge_ids:
            await remove_device(mqtt,device_id,known_devices)


    for light in lights:                                    # loop thorugh lights

        device_id = f"hue-{light["id"]}"                    # extract light id and create MQTT id 
        if device_id not in known_devices:                  # ignore if unknown device
            await publish_device(mqtt,light,connectivity,rooms,known_devices)
            continue

        _,_,new_state = build_device_messages(light)        # _ ignores return values. convert Hue light data into our MQTT format. 
        owner_rid = known_devices[device_id]["owner_rid"]
        new_state["available"] = connectivity.get(owner_rid) in AVAILABLE_STATUSES

        if known_devices[device_id]["state"] == new_state:  # replace current state to new state
            continue

        known_devices[device_id]["state"] = new_state

        await mqtt.publish(f"home/device/{device_id}/state",payload=json.dumps(new_state),qos=1,retain=True)    # publish the updated state to the light's MQTT topic

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
                        await process_hue_events(mqtt,events,known_devices,bridge_ip,app_key)     # pass the received events to our MQTT processing function

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

    MQTT_HOST = os.getenv("MQTT_HOST","localhost")                  # load MQTT Broker Host IP address environment variable
                                                                        # defaults to 127.0.0.1 if not specified
    MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))                  # load MQTT Port environment variable
                                                                    # defaults to 1883 if not specified
                                                                    # environment variables are strings, so int() converts it into an integer that is expected by aiomqtt
    
    MQTT_AVAILABILITY_TOPIC = "home/adapter/hue/status"
    MQTT_ONLINE = "online"
    MQTT_OFFLINE = "offline"
    
    if not BRIDGE_IP or not APP_KEY:
        raise ValueError("Mising Hue Configuration in .env")    # throws an error if either Hue IP or Key are missing

    # define the message mosquitto should publish if the adapter unexpectedly loses its MQTT connection
    last_will = aiomqtt.Will(topic=MQTT_AVAILABILITY_TOPIC, payload=MQTT_OFFLINE, qos=1, retain=True)

    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST,port=MQTT_PORT,will=last_will,keepalive=10) as mqtt:
                log(f"{func_log} [INFO] connected to mqtt broker: \n\thost: {MQTT_HOST}\n\tport: {MQTT_PORT}")

                hue_lights = await get_hue_lights(BRIDGE_IP,APP_KEY)
                connectivity = await get_hue_connectivity(BRIDGE_IP,APP_KEY)
                rooms = await get_hue_rooms(BRIDGE_IP,APP_KEY)

                retained_ids = await find_retained_devices(mqtt)
                bridge_ids = {f"hue-{light["id"]}" for light in hue_lights}

                known_devices = await publish_lights(mqtt,hue_lights,connectivity,rooms)

                for device_id in retained_ids - bridge_ids: 
                    await remove_device(mqtt,device_id,known_devices)
            
                await mqtt.publish(MQTT_AVAILABILITY_TOPIC,payload=MQTT_ONLINE,qos=1,retain=True)

                log(f"{func_log} [INFO] hue adapter is online...")

                try:
                    
                    async with asyncio.TaskGroup() as tasks:                            # TaskGroup ensure that if either fails, the other is cancelled and awaited as well
                        tasks.create_task(              # keep listening for commands
                            listen_for_commands(mqtt,BRIDGE_IP,APP_KEY,known_devices) 
                        )

                        tasks.create_task(              # keep listening for hue events
                            listen_for_hue_events(mqtt,BRIDGE_IP,APP_KEY,known_devices)    
                        )

                except BaseException:
                    try:                                    # CTRL+C causes asyncio.run() to cancel the main task, publish offlie while the client is still conencted
                        await mqtt.publish(MQTT_AVAILABILITY_TOPIC,payload=MQTT_OFFLINE,qos=1,retain=True)
                        print("\n")
                        log(f"{func_log} [INFO] hue adapter is offline...")
                    except aiomqtt.MqttError:
                        log(f"{func_log} [ERROR] could not publish offline: mqtt connection unavailable")

                    raise       # preserve cancellation so hte application actually shuts down. 

        except* (aiomqtt.MqttError, httpx.HTTPError) as errors:
            log(f"{func_log} [ERROR] mqtt or hue bridge connection failed \n\t{errors}\n\tMQTT: {MQTT_HOST}:{MQTT_PORT}")

        log(f"{func_log} [INFO] retrying mqtt connection in 5 seconds...")
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())     # Start the asyncio event loop and execute the main() coroutine
                                # the event manages asynchronous operations such as HTTP requests 
    except KeyboardInterrupt:
        print("\n")
        log(f".__name__ [INFO] Adapter stopped by user")