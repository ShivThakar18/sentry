from __future__ import annotations

import asyncio 
import logging
from typing import Any

from fastapi import APIRouter, WebSocket

log = logging.getLogger(__name__)

router = APIRouter()

QUEUE_SIZE = 100            # how many unsent changes on client may fall behind before we give up on it
_CLOSE = object()           # client handler "stop and close conenction"
CLOSE_TRY_AGAIN = 1013      # Close Code 1013 = Try Again Later. The UI should reconnect when it see it

class Hub():

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()

    @property
    def count(self) -> int:
        return len(self._clients)       # handy for logging and for the closing a tab doesn't leak check

    def connect(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._clients.add(q)
        log.info(f"websocket client connected ({self.count} open)")
        return q 

    def disconnect(self, q: asyncio.Queue) -> None:
        if q in self._clients:
            self._clients.discard(q)
            log.info(f"websocket client disconnected ({self.count} open)")

    def broadcast(self, change: dict[str, Any]) -> None:
        for q in list(self._clients):
            try:
                q.put_nowait(change)
            except asyncio.QueueFull:
                self._kick(q)

    def _kick(self , q: asyncio.Queue) -> None:         # a client fell QUEUE_SIZE changes behind. Disconnect it
        log.warning(f"websocket client too slow ({q.qsize()} changes behind); disconnecting")
        self._clients.discard(q)
        while not q.empty():
            q.get_nowait()
        q.put_nowait(_CLOSE)

@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()            # the browser asked to upgrade HTTP -> WebSocket

    hub: Hub = websocket.app.state.hub
    registry = websocket.app.state.registry

    q = hub.connect()

    try:
        await websocket.send_json({
            "type": "snapshot",
            "devices": registry.snapshot()
        })

        sender = asyncio.create_task(_send_changes(websocket,q))        # wait for next change in queue -> send it
        receiver = asyncio.create_task(_wait_for_close(websocket))      # wait for browser to close the connection

        done, pending = await asyncio.wait(
            {sender, receiver},
            return_when= asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
        
        for task in done:
            if not task.cancelled() and task.exception() is not None:
                log.info(f"websocket connection ended: {task.exception()}")
        
    except Exception as e:
        log.info(f"websocket connection ended early: {e}")

    finally:
        hub.disconnect(q)

async def _send_changes(websocket: WebSocket, q: asyncio.Queue) -> None:
    while True:
        change = await q.get()
        if change is _CLOSE:
            await websocket.close(code=CLOSE_TRY_AGAIN)
            return
        await websocket.send_json(change)

async def _wait_for_close(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return