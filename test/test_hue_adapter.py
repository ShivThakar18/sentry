"""Offline tests for the Hue adapter: no bridge, no broker.

Run:  HUE_ADAPTER_PATH=/path/to/main.py pytest -v tests/test_hue_adapter.py
(defaults to adapters/hue/main.py relative to the repo root)
"""

import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest

# LOAD THE ADAPTER ------------------------------------------------------------------------------------------------------------------------------------------------------------
ADAPTER_PATH = Path(os.getenv("HUE_ADAPTER_PATH", Path(__file__).parent.parent / "adapters/hue/main.py"))
spec = importlib.util.spec_from_file_location("hue_main", ADAPTER_PATH)
hue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hue)

# FAKES -----------------------------------------------------------------------------------------------------------------------------------------------------------------------
class FakeMqtt:                                 # records publishes instead of sending them
    def __init__(self, messages=()):
        self.published = []
        self._messages = list(messages)

    async def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))

    async def subscribe(self, topic, qos=0):
        pass

    async def unsubscribe(self, topic):
        pass

    @property
    def messages(self):
        async def gen():
            for m in self._messages:
                yield m
        return gen()

class FakeMessage:
    def __init__(self, topic, payload, retain=False):
        self.topic = topic
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.retain = retain

class FakeResponse:                             # stands in for an httpx streaming response
    def __init__(self, lines):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

def run(coro):
    return asyncio.run(coro)

# SAMPLE HUE DATA -------------------------------------------------------------------------------------------------------------------------------------------------------------
def color_light(light_id="abc", owner="dev-1"):
    return {
        "id": light_id,
        "owner": {"rid": owner, "rtype": "device"},
        "metadata": {"name": "Desk Lamp"},
        "on": {"on": True},
        "dimming": {"brightness": 75.0},
        "color": {"xy": {"x": 0.3, "y": 0.3}},
        "color_temperature": {"mirek": 370, "mirek_valid": True,
                              "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500}},
    }

def white_light(light_id="wht", owner="dev-2"):         # dimmable white only: no colour, no colour temp
    return {
        "id": light_id,
        "owner": {"rid": owner, "rtype": "device"},
        "metadata": {"name": "Hall"},
        "on": {"on": False},
        "dimming": {"brightness": 10.0},
    }

COLOR_DEVICE = {"capabilities": ["on_off", "brightness", "color_xy", "color_temp_k"], "color_temp_k_range": [2000, 6536]}
WHITE_DEVICE = {"capabilities": ["on_off", "brightness"], "color_temp_k_range": None}

# CONVERSIONS -----------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_kelvin_mirek_round_trip():
    assert hue.kelvin_to_mirek(2000) == 500
    assert hue.mirek_to_kelvin(153) == 6536
    assert hue.mirek_to_kelvin(hue.kelvin_to_mirek(2700)) == pytest.approx(2700, abs=10)

def test_color_temp_invalid_mirek_is_none():
    assert hue.color_temp_to_kelvin({"mirek": 370, "mirek_valid": False}) is None
    assert hue.color_temp_to_kelvin({"mirek": None}) is None
    assert hue.color_temp_to_kelvin({"mirek": 370}) == 2703

# BUILD_DEVICE_MESSAGES (info + state shape, spec §3.1/§3.2) ------------------------------------------------------------------------------------------------------------------
def test_color_light_messages():
    device_id, info, state = hue.build_device_messages(color_light(), room="Office")
    assert device_id == "hue-abc"
    assert info["id"] == device_id
    assert info["name"] == "Desk Lamp"
    assert info["adapter"] == "hue"
    assert info["room"] == "Office"
    assert set(info["capabilities"]) == {"on_off", "brightness", "color_xy", "color_temp_k"}
    assert info["color_temp_k_range"] == [2000, 6536]
    assert state == {"on": True, "brightness": 75.0, "color_xy": {"x": 0.3, "y": 0.3}, "color_temp_k": 2703}

def test_white_light_has_no_colour_fields():
    _, info, state = hue.build_device_messages(white_light())
    assert info["capabilities"] == ["on_off", "brightness"]
    assert "color_temp_k_range" not in info
    assert info["room"] is None
    assert set(state) == {"on", "brightness"}

def test_name_falls_back_to_id():
    light = white_light()
    light["metadata"] = {}
    _, info, _ = hue.build_device_messages(light)
    assert info["name"] == "hue-wht"

# BUILD_HUE_COMMANDS: valid commands (spec §3.3) ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("command, expected", [
    ({"on": True},                          {"on": {"on": True}}),
    ({"on": False},                         {"on": {"on": False}}),
    ({"brightness": 100},                   {"dimming": {"brightness": 100}}),
    ({"brightness": 0.5},                   {"dimming": {"brightness": 0.5}}),
    ({"color_temp_k": 2000},                {"color_temperature": {"mirek": 500}}),
    ({"color_temp_k": 6536},                {"color_temperature": {"mirek": 153}}),
    ({"color_xy": {"x": 0, "y": 1}},        {"color": {"xy": {"x": 0, "y": 1}}}),
    ({"on": True, "brightness": 40},        {"on": {"on": True}, "dimming": {"brightness": 40}}),
])
def test_valid_commands(command, expected):
    assert hue.build_hue_commands(command, COLOR_DEVICE) == expected

# BUILD_HUE_COMMANDS: rejected commands ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("command", [
    [],                                         # not an object
    "on",
    {},                                         # empty
    {"power": True},                            # unknown field
    {"on": True, "flash": 1},                   # one good + one unknown
    {"on": "true"},                             # wrong types
    {"on": 1},
    {"brightness": "50"},
    {"brightness": True},                       # bool is an int subclass, must still be rejected
    {"brightness": 0},                          # range: 0 < x <= 100
    {"brightness": -5},
    {"brightness": 100.1},
    {"color_temp_k": 1999},
    {"color_temp_k": 6537},
    {"color_temp_k": "warm"},
    {"color_xy": {"x": 0.3}},                   # missing y
    {"color_xy": {"x": 0.3, "y": 0.3, "z": 0}}, # extra key
    {"color_xy": {"x": 1.2, "y": 0.3}},
    {"color_xy": [0.3, 0.3]},
    {"color_xy": {"x": 0.3, "y": 0.3}, "color_temp_k": 3000},   # both colour modes
])
def test_invalid_commands_rejected(command):
    with pytest.raises(ValueError):
        hue.build_hue_commands(command, COLOR_DEVICE)

@pytest.mark.parametrize("command", [
    {"color_xy": {"x": 0.3, "y": 0.3}},
    {"color_temp_k": 3000},
])
def test_capability_not_supported_rejected(command):
    with pytest.raises(ValueError):
        hue.build_hue_commands(command, WHITE_DEVICE)

def test_brightness_nan_rejected():
    # json.loads('{"brightness": NaN}') gives float('nan'), and NaN fails every comparison
    command = json.loads('{"brightness": NaN}')
    with pytest.raises(ValueError):
        hue.build_hue_commands(command, COLOR_DEVICE)

# MERGE_LIGHT_STATE -----------------------------------------------------------------------------------------------------------------------------------------------------------
def test_merge_reports_change_only_when_value_differs():
    state = {"on": True, "brightness": 50.0}
    assert hue.merge_light_state(state, {"on": {"on": True}}) is False
    assert hue.merge_light_state(state, {"dimming": {"brightness": 50.0}}) is False
    assert hue.merge_light_state(state, {"dimming": {"brightness": 20.0}}) is True
    assert state == {"on": True, "brightness": 20.0}

def test_merge_ignores_bad_types():
    state = {"on": True, "brightness": 50.0}
    assert hue.merge_light_state(state, {"on": {"on": "yes"}, "dimming": {"brightness": None}}) is False
    assert state == {"on": True, "brightness": 50.0}

def test_merge_xy_mode_nulls_colour_temp():
    state = {"color_xy": {"x": 0.3, "y": 0.3}, "color_temp_k": 2703}
    changed = hue.merge_light_state(state, {"color": {"xy": {"x": 0.6, "y": 0.3}},
                                            "color_temperature": {"mirek": None, "mirek_valid": False}})
    assert changed is True
    assert state == {"color_xy": {"x": 0.6, "y": 0.3}, "color_temp_k": None}

# READ_SSE_EVENTS -------------------------------------------------------------------------------------------------------------------------------------------------------------
async def collect(lines):
    return [e async for e in hue.read_sse_events(FakeResponse(lines))]

def test_sse_parses_events_and_skips_noise():
    lines = [
        ": hi",                                 # comment / keep-alive
        "id: 1:0",                              # non-data field
        'data: [{"type": "update"}]',
        "",
        "",                                     # stray blank line, no event
        "data: not json",                       # bad json is logged and skipped
        "",
        'data: [{"type":',                      # multi-line data
        'data: "add"}]',
        "",
    ]
    assert run(collect(lines)) == [[{"type": "update"}], [{"type": "add"}]]

def test_sse_incomplete_event_not_yielded():
    assert run(collect(['data: [{"type": "update"}]'])) == []

# PROCESS_HUE_EVENTS (routing + publishing) -----------------------------------------------------------------------------------------------------------------------------------
def make_known(light=None, available=True):
    light = light or color_light()
    device_id, info, state = hue.build_device_messages(light)
    state["available"] = available
    return {device_id: {"light_id": light["id"], "owner_rid": light["owner"]["rid"],
                        "capabilities": info["capabilities"],
                        "color_temp_k_range": info.get("color_temp_k_range"), "state": state}}

def test_update_publishes_full_retained_state():
    mqtt, known = FakeMqtt(), make_known()
    events = [{"type": "update", "data": [{"type": "light", "id": "abc", "dimming": {"brightness": 5.0}}]}]
    run(hue.process_hue_events(mqtt, events, known, "ip", "key"))
    assert len(mqtt.published) == 1
    topic, payload, qos, retain = mqtt.published[0]
    assert (topic, qos, retain) == ("home/device/hue-abc/state", 1, True)
    state = json.loads(payload)
    assert state["brightness"] == 5.0
    assert set(state) == {"on", "brightness", "color_xy", "color_temp_k", "available"}   # full object, not partial

def test_duplicate_update_not_republished():
    mqtt, known = FakeMqtt(), make_known()
    events = [{"type": "update", "data": [{"type": "light", "id": "abc", "on": {"on": True}}]}]
    run(hue.process_hue_events(mqtt, events, known, "ip", "key"))
    assert mqtt.published == []

def test_unknown_light_and_other_resources_ignored():
    mqtt, known = FakeMqtt(), make_known()
    events = [{"type": "update", "data": [
        {"type": "light", "id": "zzz", "on": {"on": False}},
        {"type": "button", "id": "b1"},
        {"type": "grouped_light", "id": "g1", "on": {"on": False}},
    ]}]
    run(hue.process_hue_events(mqtt, events, known, "ip", "key"))
    assert mqtt.published == []

def test_non_list_batch_ignored():
    mqtt = FakeMqtt()
    run(hue.process_hue_events(mqtt, {"type": "update"}, make_known(), "ip", "key"))
    assert mqtt.published == []

def test_delete_clears_retained_topics():
    mqtt, known = FakeMqtt(), make_known()
    events = [{"type": "delete", "data": [{"type": "light", "id": "abc"}]}]
    run(hue.process_hue_events(mqtt, events, known, "ip", "key"))
    assert known == {}
    assert [(t, p, r) for t, p, _, r in mqtt.published] == [
        ("home/device/hue-abc/state", None, True),
        ("home/device/hue-abc/info", None, True),
    ]

def test_connectivity_flips_available():
    mqtt, known = FakeMqtt(), make_known()
    lost = [{"type": "update", "data": [{"type": "zigbee_connectivity", "owner": {"rid": "dev-1"}, "status": "connectivity_issue"}]}]
    run(hue.process_hue_events(mqtt, lost, known, "ip", "key"))
    assert json.loads(mqtt.published[-1][1])["available"] is False

    run(hue.process_hue_events(mqtt, lost, known, "ip", "key"))     # same status again: no publish
    assert len(mqtt.published) == 1

    back = [{"type": "update", "data": [{"type": "zigbee_connectivity", "owner": {"rid": "dev-1"}, "status": "connected"}]}]
    run(hue.process_hue_events(mqtt, back, known, "ip", "key"))
    assert json.loads(mqtt.published[-1][1])["available"] is True

# LISTEN_FOR_COMMANDS (filtering before anything reaches the bridge) ----------------------------------------------------------------------------------------------------------
def test_listen_for_commands_filters(monkeypatch):
    sent = []

    async def fake_send(client, bridge_ip, app_key, light_id, hue_payload):
        sent.append((light_id, hue_payload))

    monkeypatch.setattr(hue, "send_hue_command", fake_send)
    mqtt = FakeMqtt([
        FakeMessage("home/device/hue-abc/set", {"on": False}),                  # good
        FakeMessage("home/device/hue-abc/set", {"on": True}, retain=True),      # retained: ignored
        FakeMessage("home/device/hue-zzz/set", {"on": True}),                   # unknown device
        FakeMessage("home/device/hue-abc/info", {"on": True}),                  # not a set topic
        FakeMessage("home/device/hue-abc/set", b"\xff\xfe"),                    # not utf-8
        FakeMessage("home/device/hue-abc/set", b"{not json"),                   # not json
        FakeMessage("home/device/hue-abc/set", {"brightness": 0}),              # invalid
        FakeMessage("home/device/hue-abc/set", {"brightness": 30}),             # good, adapter still alive
    ])
    run(hue.listen_for_commands(mqtt, "ip", "key", make_known()))
    assert sent == [("abc", {"on": {"on": False}}), ("abc", {"dimming": {"brightness": 30}})]
