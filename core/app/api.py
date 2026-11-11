from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

import aiomqtt

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .capabilities import FIELD_TO_RANGE_KEY, SETTABLE_FIELD_TO_CAPABILITIY
from .registry import Registry

log = logging.getLogger(__name__)

router = APIRouter()            # a group of routes that main.py plugs in with app.include_router(router)

# DEPENDENCIES -------------------------------------------------------------------------------------------
def get_registry(request: Request) -> Registry:
    return request.app.state.registry           # lifespan put it here at startup (main.py)

def get_mqtt(request: Request) -> aiomqtt.Client | None:
    return request.app.state.mqtt                     # mqtt_loop sets this while connected, and None while reconnecting

RegistryDep = Annotated[Registry, Depends(get_registry)]
MqttDep = Annotated[aiomqtt.Client | None, Depends(get_mqtt)]

# RESPONSE MODEL -----------------------------------------------------------------------------------------
class DeviceOut(BaseModel):
    id: str
    name: str
    type: str
    room: str | None
    capabilities: list[str]
    limits: dict[str, Any]
    state: dict
    usable: bool
    manufacturer: str

# READ ROUTES --------------------------------------------------------------------------------------------
# response_model makes FastAPI:
#   - check return value has exactly this shape
#   - drop any extra keys
#   - document the shape in /docs
@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(registry: RegistryDep):
    return registry.snapshot()

@router.get("/devices/{device_id}", response_model=DeviceOut)
async def get_device(device_id: str, registry: RegistryDep):
    device = registry.to_dict(device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown device {device_id!r}")
    return device

# THE COMMON MODEL ---------------------------------------------------------------------------------------
class XY(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    x: float = Field(ge=0, le=1)    # ge = greater than or equal , le = less than or equal to
    y: float = Field(ge=0, le=1)

class SetCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)      # unknown keys -> 422, strict mode means no type guessing. 
                                                                # Without Pydantic turns " true" or 1 into True, and "40" int 40
    # set default value to None for all fields
    on: bool | None = None
    brightness: float | None = Field (default=None, gt=0, le=100)
    color_xy: XY | None = None
    color_temp_k: int | None = None                             # range is checked when routing
    target_temp_c: float | None = None
    mode: Literal["heat","cool","auto","off"] | None = None

    @model_validator(mode="after")              # runs after the per-field checks, so it can look at several fields together. Raises ValueError 422 
    def check_whole_command(self) -> "SetCommand":
        sent = self.model_fields_set            # model_fields_set the names the caller actually put in the JSON

        if not sent:
            raise ValueError(f"empty command: send at least one field")
        
        nulls = [name for name in sent if getattr(self,name) is None]
        if nulls:
            raise ValueError(f"fields can't be null: {", ".join(sorted(nulls))}")
        
        if "color_xy" in sent and "color_temp_k" in sent:
            raise ValueError(f"send color_xy or color_temp_k, not both ")
        
        return self

    def _to_payload(self) -> dict[str, Any]: 
        return self.model_dump(exclude_unset=True)

# THE COMMAND ROUTE ---------------------------------------------------------------------------------------------
@router.post("/devices/{device_id}/set", status_code=status.HTTP_202_ACCEPTED)
async def set_device(
    device_id: str,
    cmd: SetCommand,            # a Pydantic model parameter = "read it from the JSON body"
    registry: RegistryDep,
    mqtt: MqttDep
):
    payload = cmd._to_payload()

    device = registry.to_dict(device_id)        
    if device is None:                              # does the device exist? 
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown device {device_id!r}")

    caps = set(device["capabilities"])              # what can the device do? 
    unsupported = [f for f in payload if SETTABLE_FIELD_TO_CAPABILITIY[f] not in caps]

    if unsupported:
        raise HTTPException(
            422,
            f"{device['name']} doesn't support: {", ".join(unsupported)}"
        )

    for field,  range_key in FIELD_TO_RANGE_KEY.items():        # is every value inside this device's limits? 
        limits = device['limits'].get(range_key)
        if field in payload and limits:
            lo, hi = limits
            if not lo <= payload[field] <= hi:
                raise HTTPException(
                    422,
                    f"{field} must be between {lo} and {hi} for {device['name']}"
                )
            
    if not device['usable']:            # check if the device is usuable 
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{device['name']} is unavailable (adapter offline or device unreachable)"
        )
    
    if mqtt is None:                    # is the core connected to the broker?
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "core is not connected to MQTT")

    try:
        await mqtt.publish(                     # mqtt publish payload to device_id/set
            f"home/device/{device_id}/set",
            json.dumps(payload),
            qos=1,
            retain=False
        )
    except aiomqtt.MqttError as e: 
        log.warning(f"publish to {device_id} failed: {e}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"MQTT failed to publish to home/device/{device_id}/set") from e

    log.info(f"set {device_id}  {payload}")

    return {"accepted": payload}
