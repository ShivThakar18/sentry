# S.E.N.T.R.Y - Smart Environment Network for Tracking, Response & Yield
Project SENTRY is a smart home display similar to Apple HomeView and Alexa Echo Show. 

SENTRY is a custom solution where I have control on 
- Device Compatiability
- UI Look
- Features

# Components


# Overview of Architecture 
<img width="650" height="647" alt="image" src="https://github.com/user-attachments/assets/ab763d0e-d37a-4d28-bce3-d42d142316b0" />
## Components
✅ working · 🚧 in progress · 📋 planned
- Mosquitto (MQTT) Broker
- Device Adapters 
- Node.js/REACT UI
- Raspberry PI
- Peripherals -> Touch Display
- Smart Device:
  - Philips Hue Lights
  - Govee Pot Lights
  - Smart Plugs
  - Eufy Doorbell
  - Ecobee Thermostats
  
### Mosquitto Broker ✅
Mosquitto, running in Docker on the Pi (`docker-compose.yml`, config in `deploy/mosquitto/`). This is the message bus between the core and the adapters. Everything sits under `home/`:

- `home/device/<id>/{info,state,set,event}`: one set of topics per device
- `home/adapter/<name>/status`: `online` / `offline` (retained, with a Last Will)

### Device Adapters
One small service for each device type. An adapter talks to the vendor's API and turns it into the MQTT topics above. It's the only thing allowed to publish its devices' `info`/`state`/`event`. Device IDs look like `<adapter>-<native id>`.
| Adapter | Status | Notes |
|---|---|---|
| Philips Hue | ✅ | Reference implementation (`adapters/hue/`), runs as a compose service |
| Govee | 📋 | Will bring in shared code (`adapters/common/`) |
| Ecobee | 📋 | Through HomeKit (`aiohomekit`), because Ecobee's public API is closed |
| Sonos, Google Cast, Samsung TV, Roku | 📋 | |
| Eufy doorbell | 📋 | Doorbell pop-up comes later |
| Smart plugs | 📋 | Try `tinytuya` first, otherwise switch to Kasa/Tapo |

### FastAPI Core 📋
A FastAPI service that holds the device registry (rooms, names), scenes and automations. It's the **only** publisher of `set`, so the UI never talks MQTT directly.

### Touch UI 📋
A React app running in Chromium kiosk mode on the Pi's 7" display. It talks to the core over HTTP/WebSocket.

### Dev CLI 🚧
`adapters/send_mqtt.py` (rename file LOL) is a debugging helper with `watch`, `list`, `set` and `status`. It's dev-only: it publishes `set` directly, which skips the core on purpose.

## Repository Structure 
```
<repo>/
├── README.md
├── .gitignore
│
├── docs/
│   ├── mqtt-topics.md
│   ├── adapters/hue.md
│   └── notes/
│
├── deploy/
│   ├── docker-compose.yml        ← ONE file for every service
│   └── mosquitto/
│       └── mosquitto.conf
│
├── adapters/
│   └── hue/                      ✅ done
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── requirements.txt
│       ├── .env                  (not in git)
│       ├── .env.example
│       ├── main.py
│       └── tests/
│
├── tools/                        ← Part B (dev CLI)
│   └── mqtt_cli.py
│
├── core/                         ← Step 5 (new)
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements.txt          fastapi, uvicorn, aiomqtt, pydantic-settings
│   ├── .env / .env.example
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               FastAPI app + lifespan (start/stop MQTT)
│   │   ├── settings.py           MQTT_HOST etc. from env
│   │   ├── models.py             Pydantic: Device, SetCommand
│   │   ├── registry.py           in-memory dict of devices, updated from MQTT
│   │   ├── mqtt.py               connect, subscribe to info/state, publish set
│   │   └── routers/
│   │       └── devices.py        GET /devices, POST /devices/{id}/set
│   └── tests/
│
└── ui/                           ← later (React)
```
