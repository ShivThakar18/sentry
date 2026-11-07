from app.registry import Registry

INFO = (
    b'{"id":"hue-1","name":"Kitchen Lamp","adapter":"hue","manufacturer":"Philips Hue",'
    b'"type":"light","room":"Kitchen","capabilities":["on_off","brightness","color_temp_k"],'
    b'"color_temp_k_range":[2000,6536]}'
)
STATE_ON = b'{"on": true, "brightness": 80, "color_temp_k": 2700, "available": true}'


def make():
    """A registry plus a list that records every change it emits."""
    changes = []
    return Registry(on_change=changes.append), changes


def test_info_state_online_is_usable():
    r, _ = make()
    r.handle("home/device/hue-1/info", INFO)
    r.handle("home/device/hue-1/state", STATE_ON)
    assert not r.usable("hue-1")                # adapter status not seen yet
    r.handle("home/adapter/hue/status", b"online")
    assert r.usable("hue-1")


def test_adapter_offline_keeps_device_but_unusable():
    r, changes = make()
    r.handle("home/adapter/hue/status", b"online")
    r.handle("home/device/hue-1/info", INFO)
    r.handle("home/device/hue-1/state", STATE_ON)
    changes.clear()
    r.handle("home/adapter/hue/status", b"offline")
    assert "hue-1" in r.devices
    assert not r.usable("hue-1")
    # one adapter change + one device change carrying usable=False
    assert [c["type"] for c in changes] == ["adapter", "device"]
    assert changes[1]["device"]["usable"] is False


def test_state_before_info_is_hidden_then_shown():
    r, changes = make()
    r.handle("home/device/hue-1/state", STATE_ON)
    assert r.snapshot() == [] and changes == []
    r.handle("home/device/hue-1/info", INFO)
    assert r.snapshot()[0]["state"]["brightness"] == 80


def test_empty_info_deletes_device():
    r, changes = make()
    r.handle("home/device/hue-1/info", INFO)
    r.handle("home/device/hue-1/state", b"")    # §5.3: state cleared first
    r.handle("home/device/hue-1/info", b"")
    assert "hue-1" not in r.devices
    assert changes[-1] == {"type": "removed", "id": "hue-1"}


def test_bad_json_is_ignored():
    r, _ = make()
    r.handle("home/device/hue-1/info", INFO)
    r.handle("home/device/hue-1/state", STATE_ON)
    r.handle("home/device/hue-1/state", b"{not json")
    r.handle("home/device/hue-1/state", b"[1, 2]")
    assert r.devices["hue-1"].state["on"] is True  # old state kept


def test_duplicate_state_emits_nothing():
    r, changes = make()
    r.handle("home/device/hue-1/info", INFO)
    r.handle("home/device/hue-1/state", STATE_ON)
    n = len(changes)
    r.handle("home/device/hue-1/state", STATE_ON)
    assert len(changes) == n


def test_unrelated_and_set_topics_ignored():
    r, changes = make()
    r.handle("test/hello", b"hi")
    r.handle("home/device/hue-1/set", b'{"on": true}')
    r.handle("home/device//info", INFO)
    assert r.devices == {} and changes == []


def test_event_is_passed_on_not_stored():
    r, changes = make()
    r.handle("home/device/eufy-1/event", b'{"type": "ring", "ts": "2026-11-01T18:04:11Z"}')
    assert changes == [{"type": "event", "id": "eufy-1",
                        "event": {"type": "ring", "ts": "2026-11-01T18:04:11Z"}}]
    assert "eufy-1" not in r.devices


def test_to_dict_shape():
    r, _ = make()
    r.handle("home/device/hue-1/info", INFO)
    d = r.to_dict("hue-1")
    assert d["name"] == "Kitchen Lamp"
    assert d["limits"] == {"color_temp_k_range": [2000, 6536]}
    assert "manufacturer" not in d and "adapter" not in d


def test_broken_callback_does_not_break_registry():
    def boom(change):
        raise RuntimeError("hub bug")
    r = Registry(on_change=boom)
    r.handle("home/device/hue-1/info", INFO)  # must not raise
    assert "hue-1" in r.devices
