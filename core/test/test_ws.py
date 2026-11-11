
"""WebSocket tests: no broker.

`with TestClient(app) as client` runs the app on its own event loop in a
background thread. Registry changes must happen ON that loop (asyncio queues
aren't thread-safe), so we push fake MQTT messages with client.portal.call(...),
which runs a function on the app's loop and waits for it.
"""
import json

import anyio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ws as ws_module
from app.registry import Registry
from app.ws import Hub, router

INFO = json.dumps({
    "id": "hue-1", "name": "Kitchen Lamp", "adapter": "hue", "manufacturer": "Philips Hue",
    "type": "light", "room": "Kitchen", "capabilities": ["on_off"],
}).encode()


def make_app():
    app = FastAPI()
    app.include_router(router)
    hub = Hub()
    app.state.hub = hub
    app.state.registry = Registry(on_change=hub.broadcast)
    app.state.registry.handle("home/device/hue-1/info", INFO)
    return app


def test_snapshot_then_push():
    app = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws") as sock:
        first = sock.receive_json()
        assert first["type"] == "snapshot"
        assert first["devices"][0]["name"] == "Kitchen Lamp"

        client.portal.call(app.state.registry.handle,
                           "home/device/hue-1/state", b'{"on": false, "available": true}')
        msg = sock.receive_json()
        assert msg["type"] == "device"
        assert msg["device"]["state"]["on"] is False


def test_event_and_removed_are_pushed():
    app = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws") as sock:
        sock.receive_json()  # snapshot
        client.portal.call(app.state.registry.handle,
                           "home/device/eufy-1/event", b'{"type": "ring", "ts": "2026-11-08T10:00:00Z"}')
        assert sock.receive_json()["event"]["type"] == "ring"
        client.portal.call(app.state.registry.handle, "home/device/hue-1/info", b"")
        assert sock.receive_json() == {"type": "removed", "id": "hue-1"}


def test_closed_tab_leaves_no_queue():
    app = make_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as sock:
            sock.receive_json()
            assert app.state.hub.count == 1
        # The receiver task notices the close, and `finally` removes the queue.
        # Give the server a moment: ask the loop for the count a few times.
        for _ in range(50):
            if client.portal.call(lambda: app.state.hub.count) == 0:
                break
            client.portal.call(anyio.sleep, 0.01)
        assert app.state.hub.count == 0


def test_slow_client_is_kicked_with_1013(monkeypatch):
    monkeypatch.setattr(ws_module, "QUEUE_SIZE", 2)
    app = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws") as sock:
        sock.receive_json()  # snapshot

        def flood():
            # 5 changes in one go, without letting the sender run in between.
            for i in range(5):
                app.state.hub.broadcast({"type": "adapter", "adapter": "x", "status": str(i)})
        client.portal.call(flood)

        msg = sock.receive()
        assert msg["type"] == "websocket.close" and msg["code"] == 1013
        assert app.state.hub.count == 0


def test_hub_unit_two_clients_get_copies():
    import asyncio

    async def run():
        hub = Hub()
        a, b = hub.connect(), hub.connect()
        hub.broadcast({"type": "x"})
        return a.get_nowait(), b.get_nowait()

    assert asyncio.run(run()) == ({"type": "x"}, {"type": "x"})
