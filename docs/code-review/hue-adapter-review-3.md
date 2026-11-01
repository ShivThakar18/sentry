# Hue Adapter Review: Round 3

**File reviewed:** `adapters/hue/main.py` (810 lines)
**Date:** 2026-11-01
**Checked against:** `docs/mqtt-topics.md` v1, updated today to match the adapter

**Legend:** ✅ fixed · ⚠️ partly fixed · ❌ not done · 🆕 new finding

---

## Round 2 scorecard

| # | Item | Status |
|---|---|---|
| R1 | Leftover `publish_lights` call crashed startup | ✅ |
| R2 | `"remove"` → `"delete"` | ✅ |
| R3 | `"owner_rid"` string literal | ✅ |
| R4 | `len(room)` → `len(rooms)` | ✅ |
| R5 | Ghosts from deletions while the adapter was off | ✅ `find_retained_devices` is a really good solution. See the praise below. |
| R6 | `info` goes stale on a rename or room move | ❌ Not done. It's now listed in spec §9 as a known gap. |
| R7 | Leftover unpack before the `None` check | ❌ **Still there, at line 345.** Delete it. |
| R8 | Bare `except:` at line 755 | ✅ Now `except aiomqtt.MqttError`. But see 🆕 N1. |
| R9 | Capability and field naming | ✅ `color_temp_k` now matches. The unused `capabilities` variable is gone too. |
| R10 | Spec update | ✅ Done for you. See `docs/mqtt-topics.md`. |

---

## 👏 What's genuinely good this round

**`find_retained_devices` (lines 235–266)** gets three subtle things right:
1. **It runs *before* `publish_lights`** (line 765 before 768). If it ran after, it would see the adapter's own fresh `info` messages, and every bridge light would look "retained".
2. **It filters on `info.adapter == "hue"`.** That's exactly why `adapter` belongs in `info`: the Hue adapter never deletes a Govee device.
3. **It unsubscribes in `finally`**, so the subscription is cleaned up even after a timeout.

**Line 430, `topic_parts[3] != "set"`.** You noticed that `mqtt.messages` is **one shared queue for every subscription**. A retained `info` message that arrives late, after the 1 s window, would otherwise land in `listen_for_commands` and be treated as a command. Most people only find that bug in production.

---

## 🆕 New findings

### N1. Another bare `except:`, line 251
```python
try:
    info = json.loads(message.payload.decode("utf-8"))
except:
```
The same issue as R8, just in a new place. Here it would even swallow a `CancelledError` from Ctrl+C, in the middle of a timeout block. Both errors you actually expect here (`json.JSONDecodeError` and `UnicodeDecodeError`) are subclasses of `ValueError`, so `except ValueError:` covers them.

### N2. One-time cleanup of old retained topics (manual, not code)
Earlier versions of the adapter left retained messages that the new code will never clean up:
- `home/adapter/hue/availability`, from round 1, before the topic was renamed to `status`
- any `home/device/hue-…/info` published before `adapter` was added (round 1). `find_retained_devices` skips those, because `info.adapter` is missing.

Open MQTT Explorer and look under `home/`. Delete anything that shouldn't be there, using its delete button or `mosquitto_pub -t <topic> -r -n` (Experiment 3!).

### N3. Python 3.12 f-strings: now in 3 places
Lines **653, 662 and 766** (`f"hue-{light["id"]}"`). Line 766 is new. Before the Pi, check `python3 --version` there, or switch to single quotes inside: `f"hue-{light['id']}"`.

---

## Still open (not blocking)
- **R6:** republish `info` on a rename or room move.
- **#13:** `read=None` on the event stream. Test 7 (unplug the bridge) will show whether it hangs.
- **#15–18:** the `logging` module, comment density, a shared `httpx` client, splitting the file. Do these when you start the Govee adapter and create `adapters/common/`.
- **pytest** for the pure functions (see the round 2 review).

---

## Verdict
After **R7, N1, N2 and N3** (about 10 minutes), the adapter is **ready for the acceptance tests**. Run all 12 from `hue-adapter-review-1.md` and record the results. In particular, record how long test 6 (bulb unplugged) takes, and whether test 7 (bridge unplugged) hangs.

If the tests pass, the Hue adapter is done, and Step 5 (the FastAPI core) is next. The core will be built **only from `docs/mqtt-topics.md`**, which is a good test of whether the spec is complete.
