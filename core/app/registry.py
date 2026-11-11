from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

ChangeCallback = Callable[[dict[str,Any]],None]

@dataclass
class Device:
    id: str
    info: dict[str, Any] = field(default_factory=dict)      # last retained info
    state: dict[str, Any] = field(default_factory=dict)     # last full state

    @property
    def complete(self) -> bool:
        return bool(self.info)      # only show a device once we know what it is 

    @property
    def adapter(self) -> str | None:
        return self.info.get("adapter")

class Registry:
    def __init__(self, on_change: Callable[[dict],None] | None = None):
        self.devices: dict[str, Device] = {}
        self.adapters: dict[str, str] = {}                      # adapters name , online/offline
        self._on_change = on_change or (lambda change:None)     # called with a small dict describing any changes
                                                                # passing a callback in keeps this file free of FastAPI/WebSocket code
    
    def handle(self,topic: str, payload: bytes) -> None:        # route one MQTT message -> don't route bad input
        parts = topic.split("/")

        if len(parts) != 4 or parts[0] != "home" or not parts[2]:
            return  # skip invalid/bad topics 
        
        _,group,name,kind = parts       # set list as variables

        if group == "adapter" and kind == "status":
            self._on_status(name,payload)
        elif group == "device":
            handler = {
                "info": self._on_info,
                "state":self._on_state,
                "event":self._on_event
            }.get(kind)
            
            if handler:
                handler(name, payload)

    # HANDLERS -------------------------------------------------------------------
    def _on_status(self, adapter: str, payload: bytes) -> None:

        status = payload.decode("utf-8", errors="replace").strip() or "offline"
        if status not in ("online", "offline"):
            log.warning(f"adapter: {adapter}, unknown status: {status}, ignoring device")
            return
        
        if self.adapters.get(adapter) == status:
            return      # no change (i.e. duplicate retained message)

        self.adapters[adapter] = status
        log.info(f"adapter: {adapter} is {status}")
        self._emit({
            "type":"adapter",
            "adapter": adapter,
            "status": status
        })

        for dev in self.devices.values():                   # every devoce pf this adapter just changed 'usable', so tell the UI about each one
            if dev.complete and dev.adapter == adapter:
                self._emit_devices(dev)

    def _on_info(self,device_id: str, payload: bytes) -> None:

        if not payload:     # empty payload = retained deleted

            removed = self.devices.pop(device_id,None)
            if removed and removed.complete:
                log.info(f"device {device_id} removed")
                self._emit({
                    "type": "removed",
                    "id": device_id
                })
                return
        
        info = self._parse_object(device_id,"info", payload)
        if info is None:
            return
        
        if info.get("id") != device_id:     # the topic is the source of truth for the ID
            log.warning(f"info id {info.get("id")} doesn't match topic id {device_id}")

        dev = self.devices.setdefault(device_id, Device(id=device_id))
        if dev.info == info:
            return              # retained duplicate

        dev.info = info
        self._emit_devices(dev)        

    def _on_state(self,device_id: str, payload: bytes) -> None:
        dev = self.devices.setdefault(device_id, Device(id=device_id))

        if not payload:     # empty info to remove device
            new_state: dict[str, Any] = {}
        else:
            parsed = self._parse_object(device_id,"state",payload)
            if parsed is None:
                return
            new_state = parsed
        
        if dev.state == new_state:
            return

        dev.state = new_state

        if dev.complete:
            self._emit_devices(dev)

    def _on_event(self,device_id: str, payload: bytes) -> None:
        event = self._parse_object(device_id, "event", payload)
        if event is None:
            return
        if "type" not in event:
            log.warning(f"device {device_id} event without type, ignoring: {event}")
            return

        self._emit({
            "type": "event",
            "id": device_id,
            "event": event
        })

    # QUERIES ---------------------------------------------------------------------
    def usable(self, device_id: str) -> bool:          # the adapter is online and state.available is true

        dev = self.devices.get(device_id)
        if dev is None or not dev.complete:
            return False
        
        adapter_online = self.adapters.get(dev.adapter or "") == "online"

        return adapter_online and dev.state.get("available") is True

    def to_dict(self, device_id: str) -> dict[str,Any] | None:
        
        dev = self.devices.get(device_id)
        if dev is None or not dev.complete:
            return None

        info = dev.info
        return {
            "id": dev.id,
            "name": info.get("name") or dev.id,
            "type": info.get("type", "unknown"),
            "room": info.get("room"),
            "capabilities": list(info.get("capabilities",[])),
            "limits": {k: v for k, v in info.items() if k.endswith("_range")},
            "state": dict(dev.state),
            "usable": self.usable(dev.id)
        }
    
    def snapshot(self) -> list[dict[str, Any]]:     # for every complete device, for GET /devices and the Websocket snapshot
        return [d for d in (self.to_dict(i) for i in self.devices) if d is not None]

    # HELPERS ---------------------------------------------------------------------
    def _emit_devices(self, dev: Device) -> None:
        self._emit({
            "type": "device",
            "device": self.to_dict(dev.id)
        })
    
    def _emit(self, change: dict[str,Any]) -> None:

        try:
            self._on_change(change)
        except Exception:                                               # if there is a bug in a listener, it should not crash / break
            log.exception(f"on_change callback failed for {change}")

    @staticmethod
    def _parse_object(device_id: str, kind: str, payload: bytes) -> dict[str, Any] | None:          # json.loads that returns None (and logs) instead of raising

        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.warning(f"device {device_id}: bad {kind} JSON {e}: {payload[:80]}")
            return None
        
        if not isinstance(value,dict):
            log.warning(f"device {device_id}: {kind} is not a JSON object: {value}")    # valid JSON but not an object
            return None
        return value