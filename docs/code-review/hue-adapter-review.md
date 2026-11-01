# Hue Adapter Review: Round 1

**File reviewed:** `adapters/hue/main.py`
**Date:** 2026-10-31
**Checked against:** `docs/mqtt-topics.md` and the 12 acceptance tests (listed at the end)

This is a strong first adapter. The structure is clear, the design decisions are right, and Steps 1–4 clearly landed. Below is what to fix, ordered by how much it matters. Each item points at the problem and the concept you need, without writing the fix for you.

**Legend:** 🔴 bug that fails an acceptance test · 🟠 doesn't match the spec · 🟡 risk to check · 🔵 code quality (not blocking)

---

## ✅ What you got right
- **`message.retain` check on commands (line 261).** You didn't just avoid retaining your own commands, you defended against *someone else* doing it. That's thinking like a systems engineer.
- **State only changes from the bridge.** After a `set`, you wait for the event stream to report the real state instead of publishing what you *asked* for. That's exactly the "UI only changes once the real state comes back" rule.
- **`refresh_light_states` after every event-stream reconnect (line 483).** Events can be missed while disconnected, and you resync afterwards. Most first attempts miss this.
- **`merge_light_state` with a `changed` flag** avoids publishing duplicate messages.
- **The SSE parser** handles comments, multi-line data and blank-line terminators correctly.
- **Command validation**: types, ranges, unknown fields, capabilities.
- **Will and birth message, plus `offline` in `finally`.**

---

## 🔴 Bugs that will fail the acceptance tests

### 1. Invalid JSON crashes the whole adapter (line 288). Fails test 5.
Walk through it: the *first* `set` the adapter receives is `not json`. `json.loads` raises, and the `except` block runs. It logs `{command}`, but `command` was never assigned, so you get an **`UnboundLocalError` from inside your error handler**. Nothing catches that. `listen_for_commands` dies, and `gather` takes everything down with it.

There's a sneakier variant too. If an *earlier* message was valid, `command` still holds that old value, so the log blames the wrong command.

*Hint:* what should the log line show when you don't have a parsed command yet?

### 2. No MQTT reconnect. Fails test 8.
You reconnect to the *Hue* stream (nicely done), but not to the *broker*. On `docker compose restart`, aiomqtt raises `MqttError` from `mqtt.messages` and from `publish`. Then your `finally` tries to *publish* `offline` over the dead connection, which raises again, and the process exits.

*Hint:* the aiomqtt docs have a section on reconnection, built around a loop wrapped around `async with Client(...)`. Think about:
- what has to be re-published after a reconnect (birth message, `info`, `state`)
- where the publish of `offline` in `finally` can safely go

### 3. `asyncio.gather` leaves an orphan task (line 549)
If one listener crashes, `gather` raises, but it **does not cancel the other one**. Your `async with mqtt` block then exits while the event listener keeps running against a closed client.

*Hint:* look up **`asyncio.TaskGroup`** (Python 3.11+). It cancels the sibling tasks when one fails, which is the behaviour you actually want.

### 4. If the bridge is down at startup, the adapter crashes (line 519)
`get_hue_lights` runs before anything else and isn't inside a retry. On the Pi, if the adapter boots before the bridge or the Wi-Fi is up, it exits immediately. Docker's `restart:` policy would cover this, but think about whether the adapter should wait and retry by itself.

---

## 🟠 Doesn't match your spec (`mqtt-topics.md`)

### 5. Wrong availability topic (line 512)
Your spec says `home/adapter/hue/status`; the code uses `.../availability`. The core will listen to the spec, so one of them has to change. This is exactly why the spec exists.

### 6. Capabilities use Hue's vocabulary (line 78)
`"dimming"` and `"on"` are Hue words. Your spec's examples use `on_off`, `brightness` and `color`. Remember the Govee test: if the UI has to know that `dimming` means brightness, the Hue details have leaked out of the adapter.

Notice that your *state* already says `brightness` while *capabilities* says `dimming`, so even inside one message the two disagree.

### 7. Capabilities promise more than `set` delivers
`info` advertises `color` and `color_temperature`, but `build_hue_commands` only accepts `on` and `brightness` (line 168). The UI will draw a colour picker, and every tap on it will be rejected. Either support those fields in `set`, or only advertise what you can actually control.

### 8. State values are in Hue units
`color` is an `xy` list and `color_temperature` is in **mirek**. Your comments say "converted later", but later *where*? If the core or UI does the conversion, they need to know about Hue.

This is the decision from Step 4c. Make it and write it into the spec:
- Mirek → Kelvin is just `1,000,000 / mirek`.
- `xy` is harder. Decide whether your spec uses xy, hex or HSV.

### 9. No device-level `available` field. Fails test 6.
Spec Q7 says the adapter publishes `"available": true/false` in each device's state. Hue reports unplugged bulbs through `zigbee_connectivity` resources, and line 385 filters those out (`type != "light"`).

*Catch:* a `zigbee_connectivity` resource belongs to the **device**, not the **light**, so you'll have to follow `owner.rid` to map it back to the light.

### 10. Lights added or deleted after startup are ignored. Fails test 11.
`known_devices` is built once. A new bulb just logs "unknown hue light", and a deleted bulb stays in MQTT forever as a ghost. The event stream sends `"type": "add"` and `"type": "delete"` events, and right now line 380 drops them.

*Question:* what should happen to a deleted light's retained topics? (Think back to Experiment 3.)

### 11. `info` is missing `adapter` and `room`
The spec includes both. `adapter: "hue"` is how the core will know which devices to grey out when `hue/status` goes `offline`. That's more reliable than matching ID prefixes.

---

## 🟡 Risks to check

### 12. Python version: line 425 needs Python 3.12+
`f"hue-{light["id"]}"` reuses the same quote style inside an f-string, which is only legal from 3.12 onward. Run `python3 --version` on the Pi. If it's older, this is a `SyntaxError` before anything runs. Easy fix: use single quotes inside.

### 13. The event stream could hang silently
With `read=None` (line 461), if the bridge loses power, the TCP connection may never actually close, and your `async for` waits forever without reconnecting. Test 7 will tell you. If it hangs, look into a read timeout, or a watchdog that does a periodic refresh.

### 14. Brightness range message (line 196)
The check rejects `0`, but the error message says "acceptable range 0-100%". Decide what `0` means. (Hue treats brightness 0 as its lowest level, not off.)

---

## 🔵 Code quality (for later, not blocking)

### 15. Use Python's `logging` module
Use it instead of `log()` and `getTimestamp()`. It gives you:
- levels, so you can turn `DEBUG` off on the Pi
- the module name and timestamps
- tracebacks via `logger.exception(...)`

Related: your exceptions put the timestamp and prefix *inside* the message (line 161 and others), so errors get logged with two timestamps. Exceptions should describe *what* went wrong; the logger adds *when* and *where*.

### 16. Comments
Commenting nearly every line was great while you were learning. But in long-lived code, comments like `# loop through lights` on a `for` loop add noise. Keep the **why** comments (line 261's retained check is a perfect one) and move the tutorial-style explanations into `docs/notes/`.

### 17. Three separate `httpx.AsyncClient` instances
You could create one in `main()` and pass it around. That means one connection pool and one place to configure TLS when you pin the Hue CA later.

### 18. One 570-line file
It's fine for now. But the will/birth logic, the MQTT reconnect loop, and logging setup will be identical in the Govee adapter. That's the "shared code" question from Step 3c, so start an `adapters/common/` once you begin the second adapter.

---

## Suggested fix order
1. **#1 → #3 → #2**: the crash bugs. TaskGroup makes the reconnect simpler.
2. **#5, #6, #7**: quick spec alignment.
3. **#12**: Python version.
4. **#9, #10**: the bigger features.
5. Re-run all 12 acceptance tests.

---

## Acceptance tests (re-run after fixes)

### Happy path
- [ ] **1. Cold start:** after clearing retained messages, `home/adapter/hue/status` = `online`, and every light has `info` + `state`
- [ ] **2. Command:** `{"on": false}` → the light turns off, *then* `state` updates
- [ ] **3. Partial command:** `{"brightness": 30}` leaves on/off as it was
- [ ] **4. Outside change:** a toggle in the Hue app updates `state` within about 1 s

### Things going wrong
- [ ] **5. Bad input:** invalid JSON, `{"brightness": 150}`, `{"current_temp_c": 5}`, and an unknown device ID are all logged, and the adapter survives
- [ ] **6. Bulb unplugged:** `available` flips to `false` (note how long it takes)
- [ ] **7. Bridge unplugged, then back:** the adapter survives, reconnects the stream, and resyncs
- [ ] **8. Broker restart:** the adapter reconnects and re-publishes `online` by itself
- [ ] **9. Ctrl+C** → `offline` immediately. **`kill -9`** → `offline` after about 1.5 × keepalive
- [ ] **10. No stale commands:** a `set` published while the adapter is stopped is *not* applied on restart
- [ ] **11. Light deleted in the Hue app:** its retained `info` and `state` are cleared (no ghost)
- [ ] **12. Secrets:** the Hue key never appears in `git log -p`
