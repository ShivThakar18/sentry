# Hue Adapter Test Plan

**Adapter under test:** `main.py` (809 lines, 2026-11-01)
**Checked against:** `docs/mqtt-topics.md` v1
**Two parts:** automated tests (Part 1, about 1 second, no hardware) and hands-on tests with the real bridge and broker (Part 2, about 45 minutes)

---

## Part 1: Automated tests

`tests/test_hue_adapter.py` has 48 tests covering everything that doesn't need hardware: command validation, building `info`/`state`, merging state, SSE parsing, event routing, and command filtering. It uses a fake MQTT client.

```bash
pip install pytest
HUE_ADAPTER_PATH=~/Desktop/main.py pytest -v tests/test_hue_adapter.py
```

When `main.py` moves into the repo at `adapters/hue/main.py`, you can drop the `HUE_ADAPTER_PATH=` part.

**Current result: 47 pass, 1 fails.** `test_brightness_nan_rejected` is a real bug (finding F1 below). Run these before every hands-on session. If they fail, there's no point testing the hardware yet.

---

## Part 2: Hands-on tests

### Setup (once)

**1. Install the MQTT command-line clients**

| Machine | Command |
|---|---|
| Mac | `brew install mosquitto` |
| Pi | `sudo apt install mosquitto-clients` |
| Either, using your compose container | Put `docker exec -it <mosquitto container> ` in front of each command |

**2. Open three terminals**

| Terminal | Purpose | Command |
|---|---|---|
| **T1** | Adapter | `python main.py` |
| **T2** | Watch everything | `mosquitto_sub -v -t 'home/#'` |
| **T3** | Send commands and checks | (see each test) |

Also keep **MQTT Explorer** open. It's the easiest way to see what is *retained*.

**3. Set these variables in T3**

```bash
export BRIDGE=<your bridge ip>
export KEY=<your hue app key>
export DEV=hue-<light id>     # a colour bulb. Copy the id from T2 after the adapter starts.
export WHITE=hue-<light id>   # a white-only bulb, if you have one (skip the W tests if not)
```

**4. Helper commands**

Send a command:
```bash
mosquitto_pub -q 1 -t "home/device/$DEV/set" -m '{"on": true}'
```

Read the adapter's current state once:
```bash
mosquitto_sub -C 1 -t "home/device/$DEV/state"
```

Ask the bridge directly (the source of truth):
```bash
curl -sk -H "hue-application-key: $KEY" https://$BRIDGE/clip/v2/resource/light/${DEV#hue-} | python3 -m json.tool | grep -A2 -E '"on"|brightness|mirek"'
```

**The golden rule for every test:** check three things. What the **T1 log** says, what **T2** shows on the broker, and what the **bulb** physically does. If two of them disagree, the test fails.

Write down ✅ / ❌ and notes as you go.

---

### A. Startup and discovery

| ID | Steps | Expected |
|---|---|---|
| **A1** Clean start | 1. Start the broker, then T2. 2. Start T1. | T1 logs `connected to mqtt broker`, `found N hue lights`, `found N zigbee…`, `found N devices assigned to rooms`, `hue adapter is online...`. T2 shows `info` and `state` for every light, then `home/adapter/hue/status online`. |
| **A2** `info` matches the spec | Look at one `info` in MQTT Explorer. | Contains `id` (= topic id), `name` (= name in the Hue app), `manufacturer`, `adapter: "hue"`, `type: "light"`, `room` (= Hue room, or `null`), `capabilities`. Colour bulbs also have `color_temp_k_range` (about `[2000, 6536]`). |
| **A3** `state` matches reality | Compare a `state` with the bulb and with the curl command. | `on`, `brightness`, `color_xy`, `color_temp_k`, `available` all match. `color_temp_k` is `null` if the bulb is in colour mode. |
| **A4** Everything is retained | Stop T2, start it again. | Every `info`, `state` and `status online` reappears straight away, without restarting the adapter. |
| **A5** Light count | Count the lights in the Hue app. | Same count as `found N hue lights` and as the number of devices in MQTT Explorer. |
| **A6** Missing config | Rename `.env` to `.env.bak`, start T1. Rename it back afterwards. | Stops immediately with `Mising Hue Configuration in .env`. No traceback loop. |
| **A7** Wrong app key | Put a wrong `HUE_APP_KEY` in `.env`, start T1. | Logs `mqtt or hue bridge connection failed` (403) and retries every 5 s. Doesn't crash. Status is **not** `online`. Fix the key and it should come up on its own at the next retry. |
| **A8** Broker down at start | Stop the broker, start T1, wait 15 s, then start the broker. | Retries every 5 s, then connects and goes online without being restarted. |

### B. Commands that should work

Before each one, check the bulb is in a state where the change will be visible.

| ID | Command (`-m` payload) | Expected |
|---|---|---|
| **B1** | `{"on": false}` | Bulb turns off within about 1 s. T1: `command accepted`. T2: new `state` with `"on": false`. |
| **B2** | `{"on": true}` | Bulb turns on. `state` updates. |
| **B3** | `{"brightness": 10}` then `{"brightness": 100}` | Visibly dim, then full. `state.brightness` ≈ 10, then 100. Hue may round slightly (for example 9.88). That's fine. |
| **B4** | `{"brightness": 0.5}` | Lowest possible level, still **on**. |
| **B5** | `{"color_temp_k": 2200}` then `{"color_temp_k": 6500}` | Warm, then cool white. `state.color_temp_k` ≈ value. `color_xy` also changes (Hue reports both). |
| **B6** | `{"color_xy": {"x": 0.675, "y": 0.322}}` (red) | Bulb goes red. `state.color_temp_k` becomes `null`. |
| **B7** | `{"color_xy": {"x": 0.17, "y": 0.7}}` (green, outside most bulbs' range) | Bulb shows the nearest green it can. `state.color_xy` is the value the **bulb reports**, not necessarily 0.17/0.7. That's correct behaviour. |
| **B8** | `{"on": true, "brightness": 40, "color_temp_k": 3000}` | All three applied in one go. |
| **B9** Partial set | Set red at 40 %, then send `{"brightness": 80}` | Only brightness changes. It stays red. |
| **B10** Command while off | Turn off, then send `{"brightness": 50}` | Write down what happens. Hue keeps the bulb **off** and stores the brightness. The `state` should still say `on: false`. Not a failure, but worth knowing for the UI. |
| **B11** White-only bulb | `-t "home/device/$WHITE/set" -m '{"on": true, "brightness": 30}'` | Works. |

### C. Commands that should be rejected

For every row, the expected result is the same: **T1 logs `[ERROR] command failed for …`, the bulb doesn't change, no new `state` appears, and the adapter keeps working.** After the whole group, send B2 to prove it's still alive.

| ID | Payload | Reason |
|---|---|---|
| C1 | `on` (not JSON) | not JSON |
| C2 | `[]` | not an object |
| C3 | `{}` | empty |
| C4 | `{"power": true}` | unknown field |
| C5 | `{"on": "true"}` / `{"on": 1}` | wrong type |
| C6 | `{"brightness": 0}` | 0 is rejected (spec §4) |
| C7 | `{"brightness": 150}` / `{"brightness": -1}` / `{"brightness": "50"}` | out of range / type |
| C8 | `{"color_temp_k": 1000}` / `{"color_temp_k": 10000}` | outside `color_temp_k_range` |
| C9 | `{"color_xy": {"x": 1.5, "y": 0.3}}` / `{"color_xy": {"x": 0.3}}` | bad xy |
| C10 | `{"color_xy": {"x": 0.3, "y": 0.3}, "color_temp_k": 3000}` | both colour modes |
| C11 | `{"color_temp_k": 3000}` sent to `$WHITE` | capability not supported |
| C12 | `{"brightness": NaN}` | ❌ **Currently NOT rejected (F1).** The bridge rejects it with 400 instead, so it's harmless in practice, but the adapter should catch it. |

| ID | Steps | Expected |
|---|---|---|
| **C13** Retained command ignored | `mosquitto_pub -r -q 1 -t "home/device/$DEV/set" -m '{"on": false}'`, then **restart the adapter**. **Clean up afterwards:** `mosquitto_pub -r -n -t "home/device/$DEV/set"` | Bulb doesn't change when the adapter starts. T1: `ignoring retained command`. |
| **C14** Unknown device | `mosquitto_pub -q 1 -t "home/device/hue-doesnotexist/set" -m '{"on": true}'` | T1: `[WARN] unknown device was found`. |
| **C15** Another adapter's device | `mosquitto_pub -q 1 -t "home/device/govee-123/set" -m '{"on": true}'` | Same as C14. Write down whether a `[WARN]` for every non-Hue device will be too noisy once Govee exists. |

### D. Live sync (changes made outside the display)

| ID | Steps | Expected |
|---|---|---|
| **D1** Hue app on/off | Toggle the bulb in the Hue app. | `state` updates within about 1 s. T1: `live state updated`. |
| **D2** Hue app dim | Drag the brightness slider in the Hue app. | Several `state` updates, each with a different brightness. No duplicate publishes with identical values. |
| **D3** Hue app colour/scene | Set a scene on a room. | Every light in the room publishes a new `state`. |
| **D4** Physical switch / Hue dimmer | Use a Hue dimmer switch or Hue wall switch, if you have one. | Same as D1. |
| **D5** No echo storm | Send B3 and count the `state` messages in T2. | One or two `state` messages per command, not a continuous stream. |

### E. Availability

| ID | Steps | Expected |
|---|---|---|
| **E1** Bulb loses power | Turn the bulb off **at the wall switch / unplug**. Wait up to about 1–2 min (Zigbee takes a while to notice). | `state` with `"available": false`. T1: `available=False (zigbee status: connectivity_issue)`. |
| **E2** Command while unreachable | Send `{"on": true}` during E1. | Write down what happens. The bridge usually accepts it (200) and nothing happens. The log will say `command accepted` even though nothing changed. That is why the UI must trust `state`, never the command. |
| **E3** Power back | Turn it back on at the wall. | `"available": true` again. Write down how long it took. |
| **E4** Unreachable at startup | Leave the bulb off at the wall, restart the adapter. | It's still published, with `"available": false`. |

### F. Adding, removing and renaming lights

| ID | Steps | Expected |
|---|---|---|
| **F1** Add | Add a new bulb in the Hue app while the adapter runs. | T1: `new hue light added`. New `info` + `state` appear. `room` may be `null` until you assign one. |
| **F2** Delete | Delete a bulb in the Hue app while the adapter runs. | T1: `removed: hue-…`. Both retained topics disappear from MQTT Explorer. Commands to it log `unknown device`. |
| **F3** Delete while adapter is off | Stop the adapter, delete a bulb in the Hue app, start the adapter. | `found N retained hue devices`, then `removed: hue-…`. No ghost left in MQTT Explorer. |
| **F4** Rename | Rename a bulb in the Hue app. | ❌ **Known gap (R6).** `info.name` doesn't change until the adapter restarts. Restart and check that it updates. |
| **F5** Move room | Move a bulb to another room in the Hue app. | ❌ Same known gap as F4. |

### G. Connection drops and restarts

| ID | Steps | Expected |
|---|---|---|
| **G1** Ctrl+C | Press Ctrl+C in T1. | T1: `hue adapter is offline...` then `Adapter stopped by user`. T2: `status offline`. **Retained `info`/`state` stay.** That's correct: the devices still exist. |
| **G2** Hard kill (Last Will) | `kill -9 $(pgrep -f main.py)` | Within about 15 s (keepalive 10 × 1.5), T2 shows `status offline`, published by the **broker**. |
| **G3** Broker restart | Restart the mosquitto container while the adapter runs. | T1 logs the error, retries every 5 s, reconnects and republishes `online`. Commands work again. Note whether retained topics survived the restart (this depends on mosquitto `persistence true`). |
| **G4** Bridge drop | Unplug the bridge's **ethernet** for 30 s, then plug it back in. | T1: `hue event stream error`, `reconnecting in 5 seconds...` repeating. Status stays `online` (MQTT is fine). Commands during the outage log `command failed` and don't crash. Once it's back: `connected to hue event stream` and states refresh. |
| **G5** Change while bridge is down | During G4, toggle a bulb with a physical switch. After reconnecting… | …the `state` is correct, because of `refresh_light_states` on reconnect. |
| **G6** Crash leaves status online | Add `raise RuntimeError("test")` as the first line inside the `for event in events:` loop in `process_hue_events`, start the adapter, toggle a bulb in the Hue app. **Remove the line afterwards.** | ❌ **Expected to fail today (F2).** The adapter exits, but T2 still shows `status online`. |
| **G7** Long run | Leave it running overnight. | Still `online` in the morning, D1 still works, and memory (`ps -o rss -p <pid>`) hasn't grown much. |

### H. Load

| ID | Steps | Expected |
|---|---|---|
| **H1** Burst | `for i in $(seq 1 30); do mosquitto_pub -q 1 -t "home/device/$DEV/set" -m "{\"brightness\": $((i*3))}"; done` | Write down what happens. The Hue bridge allows roughly 10 commands per second. Some may fail with 429 in T1. **Pass = the adapter survives, logs the failures, and the final `state` matches the bulb.** (A slider in the UI will send exactly this kind of burst. The core should throttle it.) |

### I. On the Pi

| ID | Steps | Expected |
|---|---|---|
| **I1** Python version | `python3 --version` on the Pi | **3.12 or newer.** On 3.11 (Raspberry Pi OS Bookworm), the adapter fails straight away with a `SyntaxError` on `f"hue-{light["id"]}"` (lines 653, 662, 766, review N3). |
| **I2** Full run | Run Part 1, then A1, B1, D1, E1 and G2 on the Pi. | Same results as on the Mac. |
| **I3** Pi reboot | With the adapter running as a service, `sudo reboot`. | The adapter comes back on its own once the broker is up (that's A8 again). |

---

## Findings from writing these tests

**F1. `{"brightness": NaN}` passes validation** (line 330). Python's `json.loads` accepts `NaN`, and `NaN <= 0` and `NaN > 100` are both `False`. Fix:
```python
if not 0 < brightness <= 100:
```
The `color_xy` and `color_temp_k` checks are already written this way, which is why they catch it.

**F2. A crash leaves `status` as `online`** (lines 756–798). If anything other than an `MqttError`/`HTTPError` is raised (for example a `KeyError` from an odd Hue event), `except*` doesn't catch it. The exception leaves `async with aiomqtt.Client(...)`, and aiomqtt's `__aexit__` sends a **clean** DISCONNECT. A clean disconnect cancels the Last Will, so the broker never publishes `offline`. The display would show Hue as online while the adapter is dead. Fix: publish `offline` in the cleanup path for *any* exception, not just `CancelledError`. For example, change `except asyncio.CancelledError:` to `except BaseException:` (it already re-raises). Then rerun G1, G2 and G6.

**Still open from review 3:** line 345 (leftover unpack before the `None` check), the bare `except:` at line 251, and the Python 3.12 f-strings (I1).
