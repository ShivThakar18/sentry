from __future__ import annotations

import asyncio
import logging
import aiomqtt

from . import config

log = logging.getLogger(__name__)


SUBSCRIPTIONS = {
    ("home/adapter/+/status",1),        # subscribe to see adapter status
    ("home/device/+/info",1),           # subscribe for device information
    ("home/device/+/state",1),          # subscribe for state updates
    ("home/device/+/event",1)           # subscribe for event notifications
}

def _to_bytes(payload) -> bytes:
    if payload is None:
        return b""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    
    return str(payload).encode()


async def mqtt_loop(app) -> None:               # will run forever, conenct, subscribe, handle messages and reconnect on failure

    registry = app.state.registry

    while True:
        try:
            async with aiomqtt.Client(
                hostname=config.MQTT_HOST,
                port=config.MQTT_PORT,
                identifier=config.MQTT_CLIENT_ID,
                keepalive=config.MQTT_KEEPALIVE
            ) as client:

                log.info(f"MQTT connected to {config.MQTT_HOST}:{config.MQTT_PORT} as {config.MQTT_CLIENT_ID}")

                for topic, qos in SUBSCRIPTIONS: 
                    await client.subscribe(topic,qos=qos)

                app.state.mqtt = client         # expose the client so HTTP handlers can publish 

                async for message in client.messages:
                    topic = str(message.topic)

                    try:
                        registry.handle(topic, _to_bytes(message.payload))
                    except Exception:
                        log.exception(f"registry failed on {topic}")

        except aiomqtt.MqttError as e:
            app.state.mqtt = None
            log.warning(f"MQTT Lost {e}: retrying in {config.MQTT_RECONNECT_SECONDS} seconds")
        
        except asyncio.CancelledError:
            log.info("MQTT loop started")
            raise

        except Exception:
            log.exception(f"unexpected error in MQTT loop: retrying in {config.MQTT_RECONNECT_SECONDS} seconds")

        finally:
            app.state.mqtt = None

        await asyncio.sleep(config.MQTT_RECONNECT_SECONDS)