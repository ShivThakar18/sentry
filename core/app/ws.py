from __future__ import annotations

import asyncio 
import logging
import typing import Any

from fastapi import APIRouter, WebSocket

log = logging.getLogger(__name__)

router = APIRouter()

QUEUE_SIZE = 100            # how many unsent changes on client may fall behind before we give up on it
