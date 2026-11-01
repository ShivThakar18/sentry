# Hue Adapter Review: Round 2

**File reviewed:** `adapters/hue/main.py` (772 lines)
**Date:** 2026-11-01
**Scope:** fixes for round 1 items #1–#11, plus anything new

**Legend:** 🔴 bug that fails an acceptance test · 🟠 gap or spec mismatch · 🟡 risk or cleanup · ✅ fixed

---

## Round 1 scorecard

| # | Item | Status |
|---|---|---|
| 1 | Invalid JSON crashes the adapter | ✅ `command = None`, and logging `message.payload!r` instead of the parsed command. Clean fix. |
| 2 | No MQTT reconnect | ✅ The reconnect loop around `async with aiomqtt.Client` is the right pattern. A new client on every iteration is correct too. |
| 3 | `gather` leaves orphan tasks | ✅ `TaskGroup` plus `except*`. Using `except*` to pull `MqttError` out of the group is a genuinely advanced move. |
| 4 | Bridge down at startup crashes | ✅ `httpx.HTTPError` covers connect errors, so startup now retries every 5 s. |
| 5 | Availability topic name | ✅ `home/adapter/hue/status` |
| 6 | Hue vocabulary in capabilities | ✅ The `HUE_TO_CAPABILITY` map is a nice, data-driven solution. (Naming nit in #R9.) |
| 7 | Capabilities promise more than `set` delivers | ✅ `color_xy` and `color_temp_k` are now settable, with range checks taken from the bulb's own `mirek_schema`. Excellent. |
| 8 | Hue units in state | ✅ Kelvin conversion, and handling `mirek_valid`. You kept xy as the spec format. That's fine, but **write it into the spec** (#R10). |
| 9 | No device-level `available` | ⚠️ Mostly done. The ownership mapping (`owner_rid`) is correct, but there's a typo bug at startup (#R3). |
| 10 | Add/delete ignored | ⚠️ Add works, and the resync deletes missing lights, but the live delete never fires (#R2) and ghosts from offline deletions remain (#R5). |
| 11 | `info` missing adapter and room | ✅ Both added. Values don't update live, though (#R6). |

Real progress. The architecture is now right. What's left is mostly typos and edge cases, and **two of them stop the adapter from working**.

---

## 🔴 Bugs

### R1. The adapter can't start: line 731
```python
known_devices = await publish_lights(mqtt,hue_lights,connectivity)      # line 731
...
known_devices = await publish_lights(mqtt,hue_lights,connectivity,rooms) # line 733
```
Line 731 is left over from before you added `rooms`. `publish_lights` now takes 4 arguments, so this raises **`TypeError: missing 1 required positional argument: 'rooms'`** on every start.

Your `except*` only catches `MqttError` and `HTTPError`, so the `TypeError` escapes and the process exits.

**Lesson:** this means the code wasn't run after the last edit. Two habits prevent it:
1. Run the adapter after **every** change, even a "small" one. (The milestone approach from 4g.)
2. In VS Code, set **Python › Analysis › Type Checking Mode** to `basic`. Pylance would underline line 731 in red before you even save.

### R2. Live deletes never fire: line 607
```python
elif event_type == "remove":
```
Hue's event type is **`"delete"`**, not `"remove"`. Check what you saw in the `curl -N` event stream back in 4e. Right now a deleted light stays in MQTT until the next stream reconnect triggers `refresh_light_states`. That fails test 11.

*How to verify:* delete a light in the Hue app (or just watch the raw stream while you do) and read the `type` field.

### R3. Every light starts as unavailable: line 197
```python
state["available"] = connectivity.get("owner_rid") in AVAILABLE_STATUSES
```
`"owner_rid"` is a **string literal**, so this looks up a key that's literally named `owner_rid`, gets `None`, and sets `available` to `False` for every light.

It's masked at startup, because `refresh_light_states` (line 637) does it correctly a moment later, so you'd only see a brief flicker. But lights added live through `handle_light_add` stay `available: false` until something else updates them.

**Lesson:** two lines doing the same job (197 and 637) drifted apart. Could `publish_device` and `refresh_light_states` share one helper that builds the full state, *including* `available`?

---

## 🟠 Gaps

### R4. `len(room)` instead of `len(rooms)`: line 89
`room` is the loop variable, so this logs how many *keys the last room dict has*, not how many devices you mapped. And if the bridge has **no rooms**, `room` is never assigned, and you get a **`NameError`** that crashes startup.

### R5. Ghosts from deletions while the adapter was off
`refresh_light_states` only removes devices that are in `known_devices`. But `known_devices` is rebuilt **from the bridge** at startup. So if a light is deleted while the adapter is stopped, its retained `info`/`state` stay in Mosquitto forever. Nothing in this run ever knew about it.

*Hint:* the broker remembers what you published last time (retained `info` messages that have `"adapter": "hue"`). At startup, how could the adapter find out what's *in MQTT* and compare it with what's *on the bridge*? Think about subscribing to `home/device/+/info` for a moment.

### R6. `info` goes stale (name and room)
- **Rename** a light in the Hue app: it arrives as a light `update` with `metadata.name`, but `merge_light_state` only looks at state fields, so `info.name` never changes.
- **Move** a light to another room: that's an update on a **`room`** resource, and line 602 ignores it.

Both only correct themselves after an adapter restart. (Remember from the spec: moving a lamp should just mean editing a field. Right now that field doesn't update.)

*Question:* should `refresh_light_states` also rebuild and compare `info`, not only `state`?

---

## 🟡 Risks and cleanup

### R7. Leftover unpack: line 312
```python
k_min, k_max = device["color_temp_k_range"]   # line 312
k_range = device.get("color_temp_k_range")    # line 314
if not k_range: ...
k_min, k_max = k_range                        # line 318
```
Line 312 unpacks **before** the `None` check, so the check below it can never protect it. Today it can't actually fail, because the capability check on line 305 guarantees a range exists. But if that order ever changes, you get a `TypeError` (not a `ValueError`) that kills the listener and the whole adapter. Delete line 312.

### R8. Bare `except:`: line 755
A bare `except:` catches *everything*, including `CancelledError` and `KeyboardInterrupt`. Catch what you actually expect here: `aiomqtt.MqttError`.

### R9. Naming consistency
| Capability | State and command key |
|---|---|
| `color_xy` | `color_xy` ✅ |
| `color_temp` | `color_temp_k` ❓ |

Pick one rule: either the capability name equals the field name, or it doesn't. The UI will be simpler if it can check `if field in capabilities`.

Also, `capabilities` on line 412 is now unused, since you pass `device` instead.

### R10. Update the spec
The adapter now publishes things `mqtt-topics.md` doesn't describe:
- `color_xy` as `{"x": .., "y": ..}`
- `color_temp_k`
- `color_temp_k_range` in `info`
- the capability names

The core will be written against the **spec**, not this file. Add them to the Hue example table and the conventions section in the same PR as the code.

### Still open from round 1
- **#12, Python 3.12 f-strings:** now on lines **621 and 630** (`f"hue-{light["id"]}"`). Check `python3 --version` on the Pi.
- **#13, event stream hang** (`read=None`): test 7 will tell you.
- **#14, brightness `0`:** the check still rejects 0, and the message still says "0-100%".
- **#15–18:** the `logging` module, comment density, shared `httpx` client, splitting the file. Not blocking.

---

## Next level: automated tests

R1, R3, R4 and R7 are all bugs a **2-second automated test** would have caught. Look at what you've already got: `build_hue_commands`, `build_device_messages`, `merge_light_state` and `color_temp_to_kelvin` are all **pure functions**. They take dicts and return dicts, with no network involved. That makes them perfect for **pytest**.

Things to research:
- `pytest` basics: test files named `test_*.py`, and plain `assert`
- `pytest.raises(ValueError)` to check that bad commands are rejected
- `@pytest.mark.parametrize` to run one test against many inputs

Starter test ideas (you write them):
- `{"brightness": 150}` → raises `ValueError`
- `{"color_temp_k": 4000}` on a light with no colour temperature → raises `ValueError`
- a Hue update containing only `dimming` → `changed` is `True`, and `on` is untouched
- a light dict with `color_temperature.mirek = 250` → `color_temp_k == 4000`

The real acceptance tests (unplugging things) stay manual. But the logic that sits between Hue and MQTT should be under pytest before the Govee adapter copies it.

---

## Suggested fix order
1. **R1** (one line) → run it.
2. **R2, R3, R4** (one-word fixes each) → run it.
3. **R7, R8** → then **R10**, the spec update.
4. **#12** → then **R5, R6** (the bigger design pieces).
5. Add pytest for the pure functions.
6. Re-run all 12 acceptance tests and tick them off in `hue-adapter-review-1.md`.
