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