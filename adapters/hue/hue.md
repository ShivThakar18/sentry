# Philips Hue adapter mapping (API v2)

## Purpose
Translate Philips Hue CLIP API v2 resources and events into device-independent MQTT `info` and complete `state` messages. This is a proposed contract; align field names and topics with the core specification before implementing.

## Light state mapping

| Hue API v2 field | MQTT `state` field | Conversion / rule |
|---|---|---|
| `on.on` | `on` | Boolean unchanged. `false` means off, not unreachable. |
| `dimming.brightness` | `brightness` | Hue reports percent (0–100); preserve as number. Hue's writable dimming minimum is above zero on many bulbs; use `on:false` to turn off, not brightness 0. |
| `color.xy` | `color` | CIE xy → sRGB hex `#RRGGBB` using brightness and gamut where possible; approximate. On commands, hex → xy, clamp to supported `color.gamut`. |
| `color_temperature.mirek` | `color_temperature` | Proposed field in Kelvin: `round(1_000_000 / mirek)` when valid. Respect per-light `mirek_schema` limits. Omit if unsupported or invalid. |
| `metadata.name` | `info.name` | Copy human-readable name. |
| `id` | `info.id` | Prefix v2 light UUID with `hue-`. |
| `id_v1` | — | Legacy ID only; do not use for MQTT identity. |
| `owner.rid` | `info.room` (indirect) | Resolve owner device, then match room `children` references; publish room name as suggestion, not an immutable identifier. |
| Associated `zigbee_connectivity.status` | `availability` | `connected` → online; `disconnected` or `connectivity_issue` → offline/unavailable. Unknown or absent → unknown, not automatically online. |

`color` is a convenient UI-oriented approximation, not a lossless representation of Hue xy. Brightness and white-temperature mode can affect its interpretation. Do not synthesize `color` for white-only bulbs. Avoid reporting stale color as a currently active white-temperature color. A future revision could use structured `xy` internally while retaining hex at the UI/MQTT boundary.

## Identity and topics

- Stable device ID: `hue-<light.id>` using the v2 light-resource UUID, never `id_v1` or a user-editable name.
- Example: `hue-123e4567-e89b-12d3-a456-426614174000`.
- Suggested topics: `home/hue/light/<light.id>/info`, `home/hue/light/<light.id>/state`, and `home/hue/light/<light.id>/availability`. Confirm topic convention against core specification.
- If supporting multiple bridges, include bridge identity in the internal composite key or public ID to prevent collisions and to route commands correctly.

## Capabilities

Build the list from properties of each actual light resource, not model names:

| Hue key present | Capability |
|---|---|
| `on` | `on` |
| `dimming` | `brightness` |
| `color` | `color` |
| `color_temperature` | `color_temperature` |

Do not advertise `color` for white-only lights. `color_temperature` does not imply full colour support. Optionally add `effects` or `dynamics` later, after defining their core schema.

## Availability via Zigbee connectivity

1. GET `/clip/v2/resource/device` and `/clip/v2/resource/zigbee_connectivity`.
2. Resolve the light's `owner.rid` (device UUID).
3. Find that device's `services[]` entry whose `rtype` is `zigbee_connectivity` and match its `rid` to a connectivity resource's `id`.
4. Interpret its `status` (normally `connected`, `disconnected`, or `connectivity_issue`).
5. Publish availability separately from power state. A powered-off light can be reachable; a physically disconnected bulb can retain its last reported `on` value.
6. If connectivity is missing or ambiguous, publish `unknown` and do not assume the bulb is online.

## Initial sync, events, and reconnect

1. Establish event-stream listener (`GET /eventstream/clip/v2`, `Accept: text/event-stream`) and GET initial `light`, `device`, `room`, and `zigbee_connectivity` resources; reconcile any updates arriving during initialization.
2. Cache a complete normalized state for each light.
3. Merge partial SSE `update` objects by resource ID into the raw cached resource (nested-object merge, not top-level replacement). Recompute normalized state and publish the full JSON snapshot, never a partial delta.
4. Handle `add` and `delete` events and changes to room/device/connectivity references by refreshing relevant resources.
5. On stream disconnect or bridge restart, retry with bounded exponential backoff and jitter; resubscribe, refresh full snapshots, reconcile, and republish complete state and availability. SSE does not guarantee replay of events missed while disconnected.
6. Report bridge-wide outage separately from per-bulb Zigbee availability.

## Example normalized messages

`info`:

```json
{
  "id": "hue-123e4567-e89b-12d3-a456-426614174000",
  "name": "Desk Light",
  "room": "Office",
  "capabilities": ["on", "brightness", "color", "color_temperature"]
}
```

`state` (illustrative values):

```json
{
  "on": true,
  "brightness": 75,
  "color": "#ff8800",
  "color_temperature": 2700
}
```

Only include supported and meaningful optional fields. An inactive colour-temperature mode may mean the last valid temperature is retained rather than currently active; implementation should document this distinction. The `color` and `color_temperature` examples are illustrative, not a conversion of the same Hue sample.

## Local verification commands

With `HUE_BRIDGE_IP` and `HUE_APP_KEY` loaded:

```bash
curl -sk -H "hue-application-key: $HUE_APP_KEY" "https://$HUE_BRIDGE_IP/clip/v2/resource/light" | jq '.data[] | {id, id_v1, name:.metadata.name, on:.on.on, brightness:.dimming.brightness, xy:.color.xy, mirek:.color_temperature.mirek}'
curl -sk -H "hue-application-key: $HUE_APP_KEY" "https://$HUE_BRIDGE_IP/clip/v2/resource/device" | jq '.data[] | {id, name:.metadata.name, services}'
curl -sk -H "hue-application-key: $HUE_APP_KEY" "https://$HUE_BRIDGE_IP/clip/v2/resource/room" | jq '.data[] | {name:.metadata.name, children}'
curl -sk -H "hue-application-key: $HUE_APP_KEY" "https://$HUE_BRIDGE_IP/clip/v2/resource/zigbee_connectivity" | jq '.data[] | {id, owner, status}'
```

Use `-k` only for development; validate or trust the bridge certificate in production. Never commit the application key.

## References

- Philips Hue developer API v2: https://developers.meethue.com/new-hue-api/
- API field reference (Microsoft connector): https://learn.microsoft.com/en-us/connectors/philipshueip/
- Hue integration and connectivity considerations: https://www.home-assistant.io/integrations/hue
