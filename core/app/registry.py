import json
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Device:
    id: str
    info: dict[str, Any] = field(default_factory=dict)      # last retained info
    state: dict[str, Any] = field(default_factory=dict)     # last full state

class Registry:
    def __init__(self, on_change: Callable[[dict],None] | None = None):
        self.devices: dict[str, Device] = {}
        self.adapters: dict[str, str] = {}                      # adapters name , online/offline
        self._on_change = on_change or (lambda change:None)     # called with a small dict describing any changes
                                                                # passing a callback in keeps this file free of FastAPI/WebSocket code
    
    def handle(self,topic: str, payload: bytes) -> None:
        parts = topic.split("/")

    # HANDLERS -------------------------------------------------------------------
    def _on_status(self, adapter: str, payload: bytes) -> None:

        return

    def _on_info(self,device_id: str, payload: bytes) -> None:

        return

    def _on_state(self,device_id: str, payload: bytes) -> None:
        
        return

    def _on_event(self,device_id: str, payload: bytes) -> None:
        
        return

    # QUERIES ---------------------------------------------------------------------
    def usable(self, device_id: str) -> bool:

        return