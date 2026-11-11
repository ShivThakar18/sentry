import aiomqtt
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .mqtt import mqtt_loop
from .api import router as api_router 
from .registry import Registry
from .ws import Hub, router as ws_router
logging.basicConfig(level=logging.INFO)

# uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.hub = Hub()
    app.state.registry = Registry(on_change=app.state.hub.broadcast)
    app.state.mqtt = None                           # runs at startup before first request
    task = asyncio.create_task(mqtt_loop(app))      # start task
    yield                                           # app serves requests here

    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

app = FastAPI(title="SENTRY Core", lifespan=lifespan)          # the AGIS app object 
app.include_router(api_router)      # HTTP routes (api.py)
app.include_router(ws_router)       # /ws (ws.py)


