from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

class DeviceOut(BaseModel):
    id: str
    name: str
    type: str
    room: str | None
    capabilities: list[str]
    state: dict
    usable: bool

def to_out(registry, dev) -> DeviceOut:
    return

@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(request: Request):
    reg = request.app.state.registry
    return [to_out(reg,d) for d in reg.devices.values()]

@router.get("/devices/{device_id}", response_model=list[DeviceOut])
async def get_device(device_id: str, request: Request):
    return