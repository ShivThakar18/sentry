import asyncio
import logging
import aiomqtt

from . import config

log = logging.getLogger(__name__)

async def mqtt_loop(app) -> None:               # will run forever, conenct, subscribe, handle messages and reconnect on failure

    while True:
        try:
            async with aiomqtt.Client(
                hostname=config.MQTT_HOST,
                port=config.MQTT_PORT,
                identifier="smart-home-core"
            ) as client:
                app.state.mqtt = client         # expose the client so HTTP handlers can publish 

                await client.subscribe("home/adapter/+/status",qos=1)       # subscribe to see adapter status
                await client.subscribe("home/device/+/info",qos=1)          # subscribe for device information 
                await client.subscribe("home/device/+/state",qos=1)         # subscribe for state updates
                await client.subscribe("home/device/+/event",qos=1)         # subscribe for event notifications

                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload                   # payload in bytes
                    log.info("%s %r", topic, payload[:80])

        except aiomqtt.MqttError as e:
            app.state.mqtt = None
            log.warning("MQTT Lost (%s): retrying in 3 seconds", e)
            await asyncio.sleep(3)