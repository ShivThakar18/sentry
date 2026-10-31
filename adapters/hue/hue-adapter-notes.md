# Building Phillips Hue - MQTT Adapter
After building the Adapter, my smart home system will be able to do that following: 
1. Discover your Philips Hue lights automatically.
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
```
{
  "id": "hue-2c9a4f8e",
  "name": "Living Room Lamp",
  "manufacturer": "Philips Hue",
  "type": "light",
  "capabilities": ["on", "brightness"]
}
```

And the `state` payload: 
```
{
  "on": true,
  "brightness": 75.0
}
```
**Why Retained Messages?**
A retained MQTT message is stored by the broker as the latest retained value for its topic. 

When the smart display connects later, it can immediately receive the latest published light states without waiting for your adapter to publish them again. 

Retained does not mean continuously updated. 