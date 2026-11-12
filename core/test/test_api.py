"""API tests: no broker, no uvicorn.

TestClient calls the app in-process. We build a tiny app with just the router,
put a real Registry and a FAKE MQTT client on app.state, and check responses.
"""
import json

import aiomqtt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.registry import Registry

INFO = json.dumps({
    "id": "hue-1", "name": "Kitchen Lamp", "adapter": "hue", "manufacturer": "Philips Hue",
    "type": "light", "room": "Kitchen",
    "capabilities": ["on_off", "brightness", "color_temp_k"],   # white ambiance: no color_xy
    "color_temp_k_range": [2000, 6536],
}).encode()
STATE = b'{"on": true, "brightness": 80, "color_temp_k": 2700, "available": true}'


class FakeMqtt:
    """Records publishes instead of sending them."""
    def __init__(self, fail=False):
        self.published = []
        self.fail = fail

    async def publish(self, topic, payload, qos=0, retain=False):
        if self.fail:
            raise aiomqtt.MqttError("connection lost")
        self.published.append((topic, json.loads(payload), qos, retain))


@pytest.fixture
def env():
    reg = Registry()
    reg.handle("home/adapter/hue/status", b"online")
    reg.handle("home/device/hue-1/info", INFO)
    reg.handle("home/device/hue-1/state", STATE)
    app = FastAPI()
    app.include_router(router)
    app.state.registry = reg
    app.state.mqtt = FakeMqtt()
    return TestClient(app), app, reg


def test_list_and_get(env):
    client, _, _ = env
    r = client.get("/devices")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "Kitchen Lamp"
    assert client.get("/devices/hue-1").json()["usable"] is True
    assert client.get("/devices/nope").status_code == 404
    assert client.get("/devices/hue-1").json()["manufacturer"] == "Philips Hue"

def test_set_publishes_partial_payload(env):
    client, app, _ = env
    r = client.post("/devices/hue-1/set", json={"brightness": 40})
    assert r.status_code == 202
    assert app.state.mqtt.published == [("home/device/hue-1/set", {"brightness": 40}, 1, False)]


@pytest.mark.parametrize("body", [
    {},                                                   # empty
    {"brightness": 0},                                    # 0 not allowed
    {"brightness": 101},
    {"temperature_c": 5},                                 # not settable → extra=forbid
    {"on": "true"},                                       # strict: string isn't a bool
    {"on": 1},                                            # strict: int isn't a bool
    {"brightness": None},                                 # explicit null
    {"color_xy": {"x": 0.5, "y": 0.4}, "color_temp_k": 2700},  # both colour modes
    {"color_xy": {"x": 0.5, "y": 0.4}},                   # bulb has no color_xy
    {"color_temp_k": 9000},                               # outside this bulb's range
    {"mode": "heat"},                                     # not a thermostat
])
def test_bad_commands_are_422_and_not_published(env, body):
    client, app, _ = env
    r = client.post("/devices/hue-1/set", json=body)
    assert r.status_code == 422, r.json()
    assert app.state.mqtt.published == []


def test_valid_nested_xy_passes_model(env):
    # Proves strict mode still accepts a JSON object for the nested XY model.
    # Rejected only by the capability check (422 with our message, not Pydantic's).
    client, _, _ = env
    r = client.post("/devices/hue-1/set", json={"color_xy": {"x": 0.5, "y": 0.4}})
    assert "doesn't support" in r.json()["detail"]


def test_unknown_device_404(env):
    client, _, _ = env
    assert client.post("/devices/nope/set", json={"on": True}).status_code == 404


def test_adapter_offline_409(env):
    client, app, reg = env
    reg.handle("home/adapter/hue/status", b"offline")
    assert client.post("/devices/hue-1/set", json={"on": False}).status_code == 409
    assert app.state.mqtt.published == []


def test_broker_down_503(env):
    client, app, _ = env
    app.state.mqtt = None
    assert client.post("/devices/hue-1/set", json={"on": False}).status_code == 503


def test_publish_fails_mid_request_503(env):
    client, app, _ = env
    app.state.mqtt = FakeMqtt(fail=True)
    assert client.post("/devices/hue-1/set", json={"on": False}).status_code == 503
