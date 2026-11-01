# Building Phillips Hue - MQTT Adapter
After building the Adapter, my smart home system will be able to do that following: 
1. Discover Philips Hue lights automatically.
2. Publish their information and current state to Mosquitto.
3. Receive MQTT commands to turn lights on/off or adjust brightness.
4. Detect changes made through the Hue app and synchronize them with MQTT.
5. Report whether the adapter is online or offline.

The adapter is a translator between two different systems:

| Phillips Hue | MQTT |
|---|---|
|Hue Light resource ID|`hue-id`|
|`on.on`|`state.on`|
|`diming.brightness`(0-100)|`state.brightness`(0-100)|
|Hue API PUT request|MQTT `/set` command|
|Hue Event Stream|MQTT `/state` updates|

## Publishing Hue Lights to MQTT
We will use two topics for every Hue Light. 

`home/device/<id>/info` - Device identify and capabilities
`home/device/<id>/state` - Current on/off and brightness values

For example, the `info` payload: 
```json
{
  "id": "hue-2c9a4f8e",
  "name": "Living Room Lamp",
  "manufacturer": "Philips Hue",
  "type": "light",
  "capabilities": ["on", "brightness"]
}
```

And the `state` payload: 
```json
{
  "on": true,
  "brightness": 75.0
}
```
**Why Retained Messages?**
A retained MQTT message is stored by the broker as the latest retained value for its topic. 

When the smart display connects later, it can immediately receive the latest published light states without waiting for the adapter to publish them again. 

Retained does not mean continuously updated. 

## Subscribing to MQTT Broker to Control Hue Lights
This will now add bidirectional communication. Instead of only reading information from the Hue Bridge, the adapter will listen for MQTT commands and translate them into HTTP PUT requests that control the lights. 

For example, an MQTT command like this will be published: 
```json
{
  "on": true,
  "brightness": 75
}
```
To a topic like `home/device/hue-<uuid>/set`. The adapter will translate that into a Hue API request: 
```http
PUT https://<bridge-ip>/clip/v2/resource/light/<light-uuid>
```
With this JSON body: 
```json
{
  "on": {
    "on": true
  },
  "dimming": {
    "brightness": 75
  }
}
```
| Topic | Direction | Retained? |
|---|---|---|
| `home/device/<id>/info` | Adapter -> MQTT | Yes | 
| `home/device/<id>/state` | Adapter -> MQTT | Yes |
| `home/device/<id>/set` |  MQTT -> Adapter | No |

Never retain `/set` commands. Retained commands could be replayed when the adapater reconnects, causing an old instruction to execute unexpectedly. 

Use Quality of Service Level 1 for commands and validate the payload before senind anything to the Hue Bridge.

## Live Philips Hue State Synchronization
Next step is to make the adapter react to changes in real time 
- Toggling a light in the Hue App updates MQTT explorer automatically
- Sending an MQTT `/set` command updates the physical light and then its MQTT `/state`
- Changing brightness updates MQTT without restarting the adapter
- The MQTT command listener and Hue Event listener run concurrently
- Partial Hue events are merged into the current state instead of overwriting unrelated fields

### Event Stream
Philips Hue API v2 provides a SSE endpoint (server-sent events):
```http
GET /eventstream/clip/v2
Accept: text/event-stream
hue-application-key: YOUR_APP_KEY
```
Unlike a normal GET request, the connection stays open. 

Whenever a Hue resource changes, the bridge can send an event over that connection. 

A simplified example: `data: [{"type":"update","data":[{"id":"abc-123","type":"light","on":{"on":true}}]}]`

An important detail: **Hue events often contain only changed fields**, not a complete light object

### The Synchronization Process
Example - Hue App Turns a light on
1. Hue Bridge emits an SSE event
2. Python identifies the light by its resource ID
3. Python converts Hue fields into our MQTT state format
4. Python merges the partial update into the cached state
5. Python publishes the complete updated state with `retain=True`

## MQTT Device Lifecycle and Availability
1. Last Will and Testament (LWT): Mosquitto automatically publishes `offline` if the adapter unexpectedly loses its MQTT conenction
2. Birth Message: The adapter publishes `online` after connecting successfully
3. Graceful CTRL+C Shutdown: The adapter publishes `offline` before disconnecting normally
4. Lifecycle verification: Confirm all three behaviors in MQTT explorer 

