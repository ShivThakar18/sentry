# MQTT Topic Spec

**Status:** v1 (draft) · **Last updated:** 2026-11-01
**Reference implementation:** `adapters/hue/main.py`

This document is the contract between adapters, the core and anything else on the broker. Code is written *against* this spec. If the code and the spec disagree, fix one of them in the same PR.

The learning notes and experiments behind these decisions are in [`notes/mqtt-experiments.md`](notes/mqtt-experiments.md).

---

## 1. Conventions

### Topics
- **One root, `home/`.** `home/#` shows the entire system.
- **Lowercase only.** Topics are case-sensitive (`Test` ≠ `test`).
- **No leading or trailing `/`.** Each one adds an empty level (`/home` ≠ `home`).
- **Device IDs** use `a-z`, `0-9`, `-` and `_` only.
- **Topics hold identity, never location or brand.** Room, name and manufacturer are *data* in `info`.

### Device IDs
- Format: **`<adapter>-<native id>`**, for example `hue-3f9a1c2e-…`.
- The adapter prefix guarantees uniqueness across adapters.
- An ID **never changes** for the life of the device. Renaming a device or moving it to another room does not change its ID or its topics.

### Payloads
- **JSON objects**, UTF-8, keys in `snake_case`. The only exception is the adapter `status` topic, which is a plain string.
- **Units go in the key name:** `_c` (°C), `_k` (Kelvin), `_pct` (%), `_hpa` (hPa).
- **Booleans** are JSON `true` / `false`, never `"on"` / `1`.
- **Unknown or unavailable values** are `null`. Don't omit the key.
- **Timestamps:** the key is `ts`, in ISO 8601 UTC (`2026-11-01T18:04:11Z`), added by the publisher. Required on `event`; optional on `state`.
- **Empty retained payload** = "this topic no longer exists" (see §5.3).

---

## 2. Topic tree

```
home/
├── adapter/<adapter>/status    online | offline                (retained)
└── device/<id>/
    ├── info                    what the device is and can do  (retained)
    ├── state                   what it is doing now            (retained)
    ├── set                     please change something         (NOT retained)
    └── event                   something happened              (NOT retained)
```

| Topic | Publisher | Retained | QoS | Payload |
|---|---|---|---|---|
| `home/adapter/<adapter>/status` | adapter (`online`, clean `offline`), broker (Last Will `offline`) | **yes** | 1 | `online` / `offline` |
| `home/device/<id>/info` | owning adapter **only** | **yes** | 1 | §3.1 |
| `home/device/<id>/state` | owning adapter **only** | **yes** | 1 (0 allowed for high-frequency sensors) | §3.2 |
| `home/device/<id>/set` | **core only** | **no** | 1 | §3.3 |
| `home/device/<id>/event` | owning adapter **only** | **no** | 1 | §3.4 |

**Who may publish:** the UI never talks MQTT. It calls the core over HTTP/WebSocket, and the core publishes `set`. Only the adapter that owns a device may publish its `info`, `state` and `event`. This is what stops the display from ever showing a state that isn't real. Mosquitto ACLs will enforce it before remote access is enabled.

---

## 3. Messages

### 3.1 `info`: what the device is
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | ✅ | Same as the `<id>` in the topic |
| `name` | string | ✅ | Display name from the vendor app. Falls back to `id`. |
| `adapter` | string | ✅ | Must match `home/adapter/<adapter>/status` |
| `manufacturer` | string | ✅ | Display only. **Never branch on it in the UI or core.** |
| `type` | string | ✅ | `light`, `sensor`, `thermostat`, `doorbell`, `presence`, `plug`, … |
| `room` | string \| null | ✅ | The room *suggested* by the vendor (for example Hue room name). `null` if unassigned. |
| `capabilities` | string[] | ✅ | From the registry in §4 |
| *limits* | varies | per capability | For example `color_temp_k_range`. See §4. |

- Republished (retained) whenever any field changes, such as a rename or a room move.
- **Room override:** the core's registry wins over `info.room`. The adapter's value is only a suggestion.

### 3.2 `state`: what it's doing now
- **Always the full object.** Every publish contains every field the device supports, never a partial update. The adapter merges vendor updates into its cached state before publishing.
- Contains the fields from §4 for each capability, plus:

| Field | Type | Required | Notes |
|---|---|---|---|
| `available` | bool | ✅ | `false` when the adapter is running but can't reach this device (for example a bulb unplugged at the wall) |
| `ts` | string | optional | When the reading was taken. Recommended for sensors. |

- Published only when something actually changed.

### 3.3 `set`: please change something
- **Partial.** Include only the fields you want to change: `{"brightness": 40}` leaves `on`, colour and everything else alone.
- Only fields marked *settable* in §4 are allowed.
- The adapter **must reject** (log, don't apply) any command that:
  - isn't a non-empty JSON object
  - contains an unknown or non-settable field
  - targets a capability the device doesn't have
  - has a value of the wrong type or out of range
  - contains both `color_xy` and `color_temp_k`
- The adapter **must ignore** retained `set` messages, so an old command is never replayed.
- `set` gets **no direct reply**. Success shows up as a new `state` from the device. (See open question Q2.)

### 3.4 `event`: something happened
```json
{"type": "ring", "ts": "2026-11-01T18:04:11Z"}
```
- `type` (string, required) and `ts` (required). Extra fields are allowed per event type.
- Never retained. A reboot must not replay a doorbell ring from hours ago.

### 3.5 Adapter `status`
- Plain string: `online` or `offline`.

---

## 4. Capability registry

| Capability | `state` field | Type / unit | Settable | Limits in `info` | Notes |
|---|---|---|---|---|---|
| `on_off` | `on` | bool | ✅ | — | |
| `brightness` | `brightness` | number, `0 < x ≤ 100` (%) | ✅ | — | `0` is **rejected**. To turn off, use `{"on": false}`. |
| `color_xy` | `color_xy` | `{"x": n, "y": n}`, each `0–1` (CIE 1931) | ✅ | — | Mutually exclusive with `color_temp_k` in one `set` |
| `color_temp_k` | `color_temp_k` | integer, Kelvin, or `null` | ✅ | `color_temp_k_range: [min, max]` | `null` while the light is in colour (xy) mode |
| `temperature` | `temperature_c` | number, °C | ❌ | — | |
| `humidity` | `humidity_pct` | number, % | ❌ | — | |
| `pressure` | `pressure_hpa` | number, hPa | ❌ | — | |
| `target_temperature` | `target_temp_c` | number, °C | ✅ | `target_temp_c_range: [min, max]` | |
| `hvac_mode` | `mode` | `"heat"`, `"cool"`, `"auto"` or `"off"` | ✅ | — | |
| `occupancy` | `occupied` | bool | ❌ | — | Paired with `motion` events |
| `battery` | `battery_pct` | number, % | ❌ | — | |

**Rule for new capabilities:** add a row here *before* writing adapter code that uses it. Prefer making the capability name equal to the field name. (`on_off` → `on` is the one historical exception.)

---

## 5. Lifecycle

### 5.1 Adapter startup
1. Connect with Last Will `home/adapter/<adapter>/status` = `offline` (retained, QoS 1), keepalive 10 s, **clean session**.
2. Fetch every device from the vendor (bridge, cloud or hardware).
3. **Reconcile ghosts:** briefly subscribe to `home/device/+/info` and collect the retained IDs where `adapter` is this adapter. Unsubscribe.
4. Publish `info` + `state` for every device (retained).
5. Clear any ID from step 3 that the vendor no longer has (§5.3).
6. Publish `online` to `home/adapter/<adapter>/status` (the birth message).
7. Subscribe to `home/device/+/set` and start listening for vendor events.

### 5.2 Running
- A vendor change → merge into the cached state → publish the full `state` (only if something changed).
- A device added at the vendor → publish its `info` + `state`.
- A device removed at the vendor → clear it (§5.3).
- The vendor connection drops → reconnect, then **resync**: re-fetch everything and publish whatever differs.
- The MQTT connection drops → the broker fires the Last Will. The adapter reconnects and restarts from §5.1.

### 5.3 Removing a device
Publish an **empty retained payload** to `state`, then to `info`. Subscribers treat an empty `info` as "device deleted".

### 5.4 Shutdown
- **Clean** (Ctrl+C, update): publish `offline` (retained), then disconnect. A clean DISCONNECT discards the Last Will, so the adapter has to publish `offline` itself.
- **Crash or kill:** the broker publishes the Last Will `offline` after about 1.5 × keepalive (around 15 s).

### 5.5 Availability rule (core)
A device is **usable** only if:
`home/adapter/<info.adapter>/status == "online"` **AND** `state.available == true`

---

## 6. Examples

### Hue colour light (reference implementation)
**`home/device/hue-3f9a1c2e-…/info`**
```json
{
  "id": "hue-3f9a1c2e-…",
  "name": "Kitchen Lamp",
  "manufacturer": "Philips Hue",
  "adapter": "hue",
  "type": "light",
  "room": "Kitchen",
  "capabilities": ["on_off", "brightness", "color_xy", "color_temp_k"],
  "color_temp_k_range": [2000, 6536]
}
```
**`…/state`** (in colour mode, so `color_temp_k` is `null`)
```json
{"on": true, "brightness": 80.0, "color_xy": {"x": 0.4573, "y": 0.41}, "color_temp_k": null, "available": true}
```
**`…/set`** examples
```json
{"on": false}
{"brightness": 40}
{"color_temp_k": 2700}
{"color_xy": {"x": 0.675, "y": 0.322}, "brightness": 100}
```

### Hue white-ambiance light
The same shape without colour: `capabilities: ["on_off", "brightness", "color_temp_k"]`, and there's no `color_xy` in `state`. A `set` containing `color_xy` is rejected.

### Govee pot light (`govee-…`)
**Identical shape** to Hue. Only `id`, `adapter` and `manufacturer` differ. If the UI ever needs `if adapter == "govee"`, the abstraction has leaked.

### BME280 (`local-bme280`), a sensor wired to the Pi
```json
// info
{"id": "local-bme280", "name": "Display Sensor", "manufacturer": "Bosch", "adapter": "local", "type": "sensor", "room": null,
 "capabilities": ["temperature", "humidity", "pressure"]}
// state  (QoS 0, about every 10 s)
{"temperature_c": 21.4, "humidity_pct": 45.2, "pressure_hpa": 1013.2, "available": true, "ts": "2026-11-01T18:04:00Z"}
```
No settable capabilities, so every `set` is rejected.

### Ecobee (`ecobee-main`), a thermostat
```json
// state
{"temperature_c": 20.8, "target_temp_c": 21.5, "mode": "heat", "humidity_pct": 38, "available": true}
// set
{"target_temp_c": 22}
{"mode": "off"}
```
`{"temperature_c": 5}` is rejected, because it's a measurement, not a setting.

### Doorbell (`eufy-…`)
```json
// state
{"battery_pct": 76, "available": true}
// event
{"type": "ring", "ts": "2026-11-01T18:04:11Z"}
```

### mmWave presence sensor (`local-mmwave`)
```json
// state: cleared by the adapter after N seconds with no motion
{"occupied": true, "available": true}
// event: one per detection
{"type": "motion", "ts": "2026-11-01T22:10:03Z"}
```
Wake-on-approach listens to the **event**. Night-dim logic reads the **state**.

---

## 7. Walkthrough: start → tap → crash
1. The Hue adapter connects with Last Will `home/adapter/hue/status` → `offline`.
2. It fetches the lights from the bridge, clears ghosts, and publishes `info` + `state` for each one (retained).
3. It publishes `home/adapter/hue/status` → `online` and subscribes to `home/device/+/set`.
4. The core (subscribed to `home/#`) builds its registry, and the UI draws the lights.
5. You tap "Kitchen Lamp on". The UI calls the core API, and the core publishes `home/device/hue-…/set` → `{"on": true}`.
6. The adapter validates it and PUTs to the bridge. The bridge's event stream reports the change, and the adapter publishes the full `state`. **The UI changes only now**, not when you tap.
7. The adapter crashes. After about 15 s, the broker publishes `home/adapter/hue/status` → `offline`.
8. The core marks every device with `adapter: "hue"` unusable, and the UI greys them out.

---

## 8. Open questions
- **Q1, versioning:** add a `"v": 1` field to `info`/`state` before a second adapter exists? Otherwise a payload change means updating every adapter and the core at once.
- **Q2, command feedback:** a rejected `set` is only logged by the adapter, so the core can't tell the user "that didn't work". Options: a non-retained `home/device/<id>/error` topic, or the core times out waiting for `state`.
- **Q3, colour in the UI:** `color_xy` is easy for adapters but not for a colour picker. Does the core or the UI convert hex/HSV → xy, and is the gamut per bulb needed?
- **Q4, security:** `allow_anonymous true` is fine on the LAN only. Set up a password file and ACLs (enforcing §2's publisher rules) before Tailscale/remote access.

## 9. Known gaps (Hue adapter)
- `info` isn't republished on a rename or room move (it needs the light `metadata` and `room` update events).
- Ghost cleanup (§5.1 step 3) only recognises `info` messages that contain `adapter`. Retained topics from older versions have to be cleared by hand once.

---

## Changelog
| Date | Change |
|---|---|
| 2026-10-22 | First scheme: `home/device/<id>/…`, stable IDs, full-JSON state, partial set, two-level availability |
| 2026-11-01 | Capability registry added (`on_off`, `brightness`, `color_xy`, `color_temp_k`). `color_temp_k_range` in `info`. Adapter `status` topic finalised. State QoS 1. Startup lifecycle with ghost reconciliation. Device removal via empty retained payloads. Experiments moved to `notes/`. |
