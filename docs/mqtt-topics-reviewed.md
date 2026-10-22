# MQTT Questions and Experiments

> [!NOTE]
> **Review legend.** Comments in boxes like this one are review notes. Your original text is untouched.
> - **WARNING** = something is wrong or will cause a bug. Fix it.
> - **TIP** = works, but there's a better way or a deeper reason.
> - **IMPORTANT** = a design decision you still need to make.
>
> Delete each box once you've dealt with it. When none are left, the doc is "approved".

> [!TIP]
> **Split this file in two.** The experiments are a *learning log*. The design questions are a *contract* your code will depend on. Suggestion:
> - `docs/notes/mqtt-experiments.md`: everything from Experiment 1 to 6 (keep it, it's a great reference)
> - `docs/mqtt-topics.md`: only the final topic spec (the rules and examples, not the Q&A)
>
> Adapters and the core will be written *against* `mqtt-topics.md`, so it should read like a spec, not a worksheet.

## Experiment 1: Hello World
  ```
  # to subscribe: 
  docker exec -it mosquitto mosquitto_sub -h localhost -t test/hello -v

  # to publish
  docker exec mosquitto mosquitto_pub -h localhost -t test/hello -m "Hello MQTT!"
  ```
- In A, subscribe to test/hello.
- In B, publish hi to test/hello.
- Then publish to Test/hello and to test/hello/ (with a trailing slash).
**Predictions:** Do those last two arrive? What does that tell you about how strictly topics are matched?
  - The last 2 do not arrive. This shows the path to publish must match exactly to what the subscribe path is. Otherwise the no message will be seen on the subscribed localhost. 

> [!TIP]
> Correct. Two precise reasons are worth writing down, because they become rules in your spec:
> 1. Topics are **case-sensitive**: `Test` ≠ `test`. *Rule: all topic segments lowercase.*
> 2. `test/hello/` has **three levels**: `test`, `hello`, and an empty string `""`. A trailing slash isn't ignored; it's an extra, empty level. *Rule: no trailing slashes.*
>
> Also, it's not quite "must match exactly". Wildcards (Experiment 2) loosen the match, but only on the **subscribe** side.

## Experiment 2: Wildcards
- In A, subscribe to home/+/state.
- Open a third terminal and subscribe to home/#.
- From B, publish to each of these:
  - home/lamp/state
  - home/lamp/set
  - home/kitchen/lamp/state
  - home
  - /home/lamp/state

**Before you publish:** write down which subscriber gets each message. Then check.
1. home/lamp/state
   - Prediction: Publish to Terminal A and B
   - Result: Same as prediction
2. home/lamp/set
   - Prediction: Publish to Terminal B
   - Result: Same as prediction
3. home/kitchen/lamp/state
   - Prediction: Publish to Terminal B
   - Result: Same as prediction
4. home
   - Prediction: Publish to Terminal B
   - Result: Same as prediction
5. /home/lamp/state
   - Prediction: None
   - Result: None

> [!TIP]
> All five predictions are right. 👍 Small labelling slip: **B was the publisher**. The `home/#` subscriber was your *third* terminal, so call it **C** to keep the notes clear.
>
> #4 is the interesting one. `home/#` matched the topic `home` itself, which means `#` matches **zero or more** levels, including the parent. Write that down; it's a common surprise.
  
Questions:
1. What's the difference between + and #?
   - The + acts as a placeholder or variable. This means that when publishing messages any topic in that place can be sent and read. Though this is more strict and only allows the + wildcard to be replaced with any other string. As seen in experiments above, only the first message was published because the "lamp" was able to fit into place. The third message also shows that you cannot add more topics to replace the +.
   - The # acts as "anything goes". Although it cannot be used in place of a + it can only be used at the end of a given path such as home/# 

> [!TIP]
> Right idea. Here's a tighter version for your notes:
> - `+` matches **exactly one** level.
> - `#` matches **zero or more** levels, and must be the **last** character.
>
> One correction to "*when publishing messages any topic in that place can be sent*": wildcards are **subscribe-only**. Try `mosquitto_pub -t "home/+/state" -m x` and note the error. Publishers always use a concrete topic.

2. Why does a leading / cause trouble?
   - As it was seen in experiment 1. The subscription is very strict and requires the topics to match exactly. Additionally, the # wildcard was written at the end and only subdirectories after home are available in this case. 

> [!WARNING]
> Not quite the reason. It's the same thing as the trailing slash in Experiment 1. `/home/lamp/state` splits into **four** levels: `""`, `home`, `lamp`, `state`. The first level is an empty string, not `home`, so it lives in a completely different tree from `home/...`. `home/#` can't match it because the first level isn't `home`.
>
> *Rule for your spec: topics never start or end with `/`.*

3. Can # go in the middle of a topic? Try it.
   - Error: Invalid subscription topic

## Experiment 3: Retained messages
1. Publish on to home/lamp/state without -r. Then start a new subscriber. Does it get anything?
   - Nothing gets published to the subscriber
2. Now publish with -r. Start another new subscriber.
   - The message that was sent earlier gets published when the subscription is established
3. Find out how to delete a retained message. Hint: send an empty payload, and look at the -n flag.
   ```
   docker exec mosquitto mosquitto_pub -h localhost -t home/lamp/state -m -r -n
   ```

> [!WARNING]
> **This command is broken.** `-m` takes the *next* argument as the message, so `-m -r` sets the message to the literal text `"-r"`, and `-r` is never seen as a flag. Then `-n` (null message) clashes with `-m`. Mosquitto either errors out or does something you didn't intend.
>
> Fix: drop `-m` completely. `-n` *is* the message (an empty one) and `-r` makes it retained. Run your fixed command, then start a new subscriber to prove the retained message is gone. Paste the corrected command here.
>
> **Lesson:** when a CLI flag takes a value, the value is whatever comes next, even if it looks like a flag.

**Design question:** a light's state should almost certainly be retained. Should a command like set: on or unlock be retained? Picture the core restarting a week later.
- State should be retained
- But a command should not; it should only be a 1-time thing. Otherwise, the device will keep triggering the command indefinitely

> [!TIP]
> Correct conclusion. The exact mechanism: a retained message is redelivered **every time anything subscribes** to that topic. If `unlock` were retained, then every time the adapter restarts (power cut, crash, update) and re-subscribes, it gets "unlock" again and the door unlocks, possibly a week later. That's the scenario to remember.

## Experiment 4: QoS and persistent sessions
QoS is hard to see on one machine, so make it visible:

- Add -d (debug) to both the subscriber and the publisher, then publish with -q 0, then -q 1, then -q 2. Count the packets each time (PUBLISH, PUBACK, PUBREC…).
  ```
  shivt@GHOSTTT:~$ docker exec mosquitto mosquitto_pub -h localhost -t home -d -m "home 0" -q 0
  Client null sending CONNECT
  Client (null) received CONNACK (0)
  Client null sending PUBLISH (d0, q0, r0, m1, 'home', ... (6 bytes))
  Client null sending DISCONNECT
  shivt@GHOSTTT:~$ docker exec mosquitto mosquitto_pub -h localhost -t home -d -m "home 1" -q 1
  Client null sending CONNECT
  Client (null) received CONNACK (0)
  Client null sending PUBLISH (d0, q1, r0, m1, 'home', ... (6 bytes))
  Client null received PUBACK (Mid: 1, RC:0)
  Client null sending DISCONNECT
  shivt@GHOSTTT:~$ docker exec mosquitto mosquitto_pub -h localhost -t home -d -m "home 2" -q 2
  Client null sending CONNECT
  Client (null) received CONNACK (0)
  Client null sending PUBLISH (d0, q2, r0, m1, 'home', ... (6 bytes))
  Client null received PUBREC (Mid: 1)
  Client null sending PUBREL (m1)
  Client null received PUBCOMP (Mid: 1, RC:0)
  Client null sending DISCONNECT
  ```

> [!TIP]
> Great capture. Add a one-line summary under it so future-you doesn't have to decode the log:
> | QoS | Packets after PUBLISH | Guarantee |
> |---|---|---|
> | 0 | none | at most once (fire and forget) |
> | 1 | PUBACK | at least once (duplicates possible) |
> | 2 | PUBREC → PUBREL → PUBCOMP | exactly once (slowest) |
>
> Two more things to know:
> - QoS is set **separately on each hop**: publisher → broker, and broker → subscriber. The subscriber gets the **lower** of the two. Publishing at QoS 1 to a QoS 0 subscription gives QoS 0 delivery.
> - The `shivt@GHOSTTT:~$` prompt means you were in **WSL bash** here, not PowerShell. That's why quoting will behave differently in Experiment 6.

- Offline delivery:
  1. Start a subscriber with a fixed client ID (-i), the "don't clean session" flag (-c), and -q 1.
  2. Close it.
  3. Publish a few QoS 1 messages.
  4. Reconnect it with the same ID.
- What happens? Now repeat with QoS 0.
  - With QoS 1, publishes once connected and gets queued while offline
  - With QoS 0, it can publish at most once, but it can get lost. It cannot get queued for offline

**Design question:** which of these needs QoS 1?
- "Turn on the lights" - QoS 0 - i believe my google home does this at QoS 0. When my lights are offline, it doesn't get queued. 
- "Temperature is 21.4°C", sent every 10 seconds - If this is critical this QoS 1 
- "Doorbell pressed" - QoS 1 

> [!WARNING]
> **"Turn on the lights": the reasoning mixes up two different "offlines".** QoS only covers delivery between an **MQTT client and the broker**. It knows nothing about whether the *bulb* is reachable. If the bulb is unplugged, the Hue adapter still receives the command fine; it's the adapter's call to the Hue bridge that fails.
>
> Your instinct ("I don't want a light command queued for 3 hours and then firing") is a **good** one. But the tool for that isn't QoS 0. It's **not using a persistent session for the adapter** (connect with clean session), so commands aren't queued while it's down. On a home LAN, QoS 1 for commands costs basically nothing and protects against a dropped packet.
>
> Rethink and rewrite these three answers with this split in mind:
> - **QoS** = did the message reach the broker or subscriber?
> - **Clean vs. persistent session** = should messages pile up while I'm offline?
> - **Retained** = should a *new* subscriber see the last value?
>
> Hint for temperature: if one reading is lost, what happens 10 seconds later? Does it need a guarantee at all? And should it be retained?
  
## Experiment 5: Last Will and Testament (the important one)
The Last Will is how your core will find out an adapter has crashed.
- In A, subscribe to adapters/#.
- In B, start a mosquitto_sub that pretends to be an adapter. Give it a will topic adapters/fake/status, payload offline, retained, and a short keepalive (-k 5). Run mosquitto_sub --help to find the flag names.
- Stop it with Ctrl+C. Does the will fire?
- Restart it, and this time kill it: close the terminal window, or end it in Task Manager. Now does it fire? How long does it take?

> [!IMPORTANT]
> You haven't recorded the results. Did the will fire on Ctrl+C? On kill? **How many seconds** did the kill take? Add the command you used too (`--will-topic`, `--will-payload`, `--will-retain`, `-k`).
>
> Tip for the docker setup: "closing the window" kills the `docker exec` client on your PC, but the `mosquitto_sub` process might keep running *inside the container*. If the will never fires, that's why. Try `docker exec mosquitto pkill -9 mosquitto_sub` instead. You should see the will after about **1.5 × keepalive** (around 7–8 s with `-k 5`). Did your number match?

Questions:
1. Why does Ctrl+C behave differently from a kill?
   - Ctrl+C acts has a clean disconenct and sends a DISCONNECT Packet

> [!TIP]
> Right, and finish the thought: the broker treats a DISCONNECT as "I'm leaving on purpose" and **throws the will away**. A kill sends nothing, so the broker only notices when the keepalive runs out, and then publishes the will.
>
> Design consequence: when your adapter shuts down *cleanly* (for example during an update), the will **won't** fire. So the adapter must publish `offline` itself before disconnecting.

3. The will only ever says "offline". How should an adapter announce "online" when it starts? This pattern is often called a birth message.
   - A birth message is a retained online the adapter publishes to its own will topic right after it connects. The topic then always holds the latest truth:

> [!TIP]
> Spot on. The sentence ends at "latest truth:", so finish it. A good way to end it is the three-step lifecycle:
> 1. connect (with will = `offline`, retained) →
> 2. publish `online` (retained) to the same topic →
> 3. on a clean shutdown, publish `offline` (retained), then disconnect.
>
> (Also, your numbering jumps from 1 to 3.)

## Experiment 6: JSON payloads
Real messages will be JSON, like {"on": true, "brightness": 80}. Try publishing one from PowerShell, and you'll run into quoting problems. Work out two fixes:
  ```
  # Powershell
  docker exec mosquitto mosquitto_pub -h localhost -t home/kitchen/light -m '{"on": true, "brightness": 80}'

  # MQTT
  home/kitchen/light {on: true, brightness: 80}
  ```
- Quote it correctly for your shell.
  ```
  # Powershell
  docker exec mosquitto mosquitto_pub -h localhost -t home/kitchen/light -m '{\"on\": true, \"brightness\": 80}'

  # MQTT
  home/kitchen/light {"on": true, "brightness": 80}
  ```
- Use the -f flag to publish from a file.
  ```
  # Creating a file
  >Set-Content -Path light.json -Value '{"on": true, "brightness": 80}' -Encoding ascii
  >docker cp light.json mosquitto:/tmp/light.json

  # Powershell -f command
  docker exec mosquitto mosquitto_pub -h localhost -t home/kitchen/light -f /tmp/light.json
  
  # MQTT
  home/kitchen/light {"on": true, "brightness": 80}
  ```

> [!TIP]
> Nice, both fixes work. Add one line explaining **why** the first attempt lost its quotes: Windows PowerShell 5.1 strips embedded `"` when it passes arguments to a native `.exe` (PowerShell 7.3+ fixed this). In WSL bash, the single-quoted version just works.
>
> `-Encoding ascii` was a smart choice. PowerShell 5.1's `utf8` adds a hidden BOM byte at the start of the file, which breaks JSON parsers. Note that down; it will bite you again.
>
> Later (Step 2), you can bind-mount a folder into the container with a Docker **volume** instead of running `docker cp` every time.

# Questions We should answer before starting

> [!NOTE]
> This is the part that matters most, and it's where most of the review notes are. Overall your answers **mirror a folder structure**: topics organised like a file system by where things physically are. The main shift in thinking: **topics should be organised by what never changes (identity), not by what might change (location, brand).** Most of the notes below come back to that.

1. Root and namespace. Does everything sit under one root, like home/? How do you keep device traffic separate from system traffic such as adapter status and core events?
   - Lets have everything sit under home/
   - Each device will be tracked with rooms
   - System Traffic should be kept and tracked in another folder maybe sys/

> [!WARNING]
> **Inconsistent with your own answer #6**, which puts adapters at `home/adapters/...`. Is system traffic under `home/` or under `sys/`? Pick one.
>
> Things to weigh:
> - **One project root** (everything under `home/`, with `home/device/...`, `home/adapter/...` and so on). `home/#` then shows *everything* in MQTT Explorer, and if the broker is ever shared with another project, nothing collides.
> - **Two roots** (`home/` and `sys/`). Device traffic and system traffic are visually separate, but you need two subscriptions to see everything.
>
> Either is defensible. Write down which one and **one sentence on why**.

2. Identity. What goes in the path: device type, room, brand, or a stable ID? What happens to your topics if you move a lamp to another room?
   - home -> room -> device type/brand -> device -> status
   - If a lamp is moved to another room it should be moved into a directory related to that room
   - home/kitchen/govee/lamp -> home/bedroom/govee/lamp

> [!WARNING]
> **This is the most important fix in the doc.** Walk through what actually happens when you move that lamp from kitchen to bedroom:
> 1. The old retained state is still sitting at `home/kitchen/govee/lamp/state`. Nothing deletes it. The UI now shows a **ghost lamp** in the kitchen.
> 2. Every automation and scene that referenced the kitchen topic silently stops working.
> 3. The adapter has to change which topics it publishes to, so moving a lamp is a code or config change in the adapter.
>
> And brand in the path: if you replace a Govee light with a Hue light, its topic changes, and so does every scene that used it. The UI shouldn't care what brand a light is.
>
> **The fix:** the topic holds a **stable ID** that never changes for the life of the device. Room, display name, brand and type become **data**: fields in the device's info message or in the core's device registry. Moving a lamp means editing one field, and no topic changes at all.
>
> Questions to answer:
> - Where does the ID come from? Hue gives every light a UUID. Govee and Ecobee have their own IDs. Or you assign readable ones like `kitchen_pot_1`. (Careful: does `kitchen_` in an ID cause the same problem again?)
> - Should the adapter name stay in the path (`.../hue/<id>`) or not? Hint: could two adapters ever produce the same ID?
>
> Then rewrite your path pattern. It should look something like `<root>/<something>/<id>/<state|set|...>`.

3. State vs. command. These need separate topics. What are they called? Which is retained? Who is allowed to publish to each one?
   - e.g. home/kitchen/govee/lamp/state or home/kitchen/govee/lamp/command
   - States Retained, Commands Not Retained
   - Unsure who should be allowed to publish

> [!TIP]
> Retained/not-retained is right. 👍 `command` works. `set` is the common convention (zigbee2mqtt, Tasmota and others use it), but either is fine as long as you're consistent.
>
> **Who publishes**, worked out from your own architecture (React → FastAPI core → MQTT → adapters):
> - `state`: published **only** by the adapter that owns the device. It's the only thing that actually *knows* the state.
> - `set`/`command`: published by the **core**. The React UI talks HTTP/WebSocket to the core and never touches MQTT directly.
>
> Why that matters: if the UI published a `state` saying "light is on" when the light didn't actually turn on, the display would lie. The UI says "please turn on" (command), and only the adapter is allowed to answer "it is on" (state).
>
> Write those two rules into the spec. Later, Mosquitto's ACL file can *enforce* them.

5. Granularity. Is a whole device one JSON state message, or does each attribute (/brightness, /power) get its own topic? List a trade-off on each side.
   - I think it makes sense to have separate JSON messages per state of device based on commands
   - Unsure about trade-offs

> [!IMPORTANT]
> The answer isn't clear yet. "Separate JSON messages per state … based on commands" could mean either option. Here's a scenario to help you decide:
>
> *You change a Hue light from dim red to bright blue.*
> - **Per-attribute topics** (`.../brightness`, `.../color`): two separate messages arrive. For a moment, the UI might show **bright red**, a state that never existed. You also have N retained messages per device to clean up. On the plus side, a subscriber that only cares about brightness gets tiny, simple payloads.
> - **One JSON state per device**: `{"on": true, "brightness": 100, "color": "blue"}` arrives as one message, so the change is atomic. There's one retained message per device and the UI parses one thing. The cost: every change resends the whole object, which is trivial for a light.
>
> Common pattern worth considering: **state = full JSON object**, while **commands may be partial** (`{"brightness": 50}` changes only brightness and leaves the rest alone).
>
> Pick one, and write the trade-off you accepted in a sentence. (Also, numbering skips 4.)

6. Discovery and capabilities. When the Hue adapter starts, how does it tell the core "I have 2 lights; they support on/off, brightness and colour"? Where does that message go, and is it retained?
   - lets have it retained in a topic called home/adapters/phillips/device/info/
   - Message shall be a JSON with information about lights, support, brightness, colours, etc. 

> [!WARNING]
> Retained JSON is the right call. 👍 Three problems with the topic itself:
> 1. **Trailing `/`.** Remember Experiment 1: that's an extra empty level. Remove it.
> 2. **"phillips"** is misspelled (it's *Philips*). Typos in topics are permanent bugs: a subscriber spelling it correctly will never match. Another reason to keep brand names out of paths, or to use a short adapter name like `hue`.
> 3. **One message for all lights, or one per light?** Your topic has a literal `device` in it, so it's unclear. Think about it this way: you add a third Hue light. With one big message, the adapter rewrites the whole list. With **one retained info message per device** (next to its `state` and `set` topics), adding a device means adding one message, and removing one means clearing one retained topic (Experiment 3!).
>
> Then decide **what fields** go in the info message. At minimum, think about: id, name, adapter, model, and a **capabilities** list (`on_off`, `brightness`, `color`, `temperature_reading`, …). This capability list is what will let your UI draw the right controls for any device without knowing its brand.
>
> Open question: the adapter might *suggest* a room (Hue knows its rooms), but you can override it on the display. Who wins, adapter or core? Where does your override live?
>
> **Now** is a good time to read Home Assistant's "MQTT Discovery" docs and compare.

7. Availability. Your topic for the birth message and Last Will, per adapter or per device.
    - Should be per device!!

> [!WARNING]
> Look back at Experiment 5. The will belongs to an **MQTT connection**, and each connection gets **exactly one** will. How many MQTT connections does the Hue adapter have: one per light, or one in total?
>
> That means the **Last Will can only be per adapter**. But your instinct for per-device is still useful, because there are **two different failures**:
> - **The adapter process crashed** → the broker fires the will → `<adapter availability topic>` = `offline`
> - **The adapter is fine but one bulb is unplugged** → the will can't help, because the connection is still alive. The adapter has to *notice* and publish it itself (an `available` field in the device state, or its own per-device topic).
>
> So you need **both**. The core shows a device as online only if *its adapter is online* **and** *the device itself is reachable*. Rewrite this answer with both topics.

8. Events vs. state. "Doorbell pressed" isn't really a state. Does it belong somewhere else? Should it be retained?
    - This is definately an event because
    - This should be another topic like

> [!IMPORTANT]
> Unfinished. Finish the "because" first, then the topic. Questions to guide you:
> - **Retained?** Picture this: the doorbell rang at 2 pm, and you reboot the display at 9 pm. With retention, what would the UI do on startup?
> - **QoS?** You already answered this in Experiment 4. Make the two answers agree.
> - **Payload:** an event is a moment, not a value. What does the receiver need? Think about *which* event, and *when* it happened.
> - **Topic:** an event comes *from a device*, so should it live next to that device's `state` and `set`? Does a doorbell even have meaningful state? (It might, e.g. battery level.)
> - Is a motion detection from the mmWave sensor an event, a state, or both? (Hint: "motion detected" vs. "room occupied".)

9. Examples. Show your scheme handling a Hue light, a Govee pot light, the BME280 sensor and the Ecobee.
    - no clue need help

> [!IMPORTANT]
> Do this **last**, after fixing #1, #2, #5, #6 and #7. The examples are just those answers applied to real devices. Here's a template plus one worked example using **placeholder** names. Swap in *your* chosen root, path pattern and names.
>
> **Example: Hue light** (placeholders: `<root>`, `<id>`, and `set` vs. `command`)
> | Topic | Who publishes | Retained | QoS | Example payload |
> |---|---|---|---|---|
> | `<root>/device/<id>/info` | hue adapter | yes | 1 | `{"id": "...", "name": "Kitchen Lamp", "adapter": "hue", "capabilities": ["on_off", "brightness", "color"]}` |
> | `<root>/device/<id>/state` | hue adapter | yes | ? | `{"on": true, "brightness": 80, "color": "#ff8800", "available": true}` |
> | `<root>/device/<id>/set` | core | **no** | 1 | `{"brightness": 40}` |
> | `<root>/adapter/hue/status` | hue adapter (birth) / broker (will) | yes | 1 | `online` / `offline` |
>
> Now do the other three yourself. What makes each one **different**:
> - **Govee pot light:** almost the same as Hue. If your scheme is right, the *only* things that change are the id and the adapter name. If the UI would need to know it's a Govee, something has leaked.
> - **BME280:** it's wired straight to the Pi, with no cloud and no bridge. Who is its "adapter"? (A tiny local adapter is fine.) Can you *command* a temperature sensor? So does it need a `set` topic? Think about units: `21.4`, or `{"temperature_c": 21.4}`?
> - **Ecobee:** a thermostat is both sensor **and** actuator. What's in its state (current temp, target temp, mode, humidity, maybe occupancy)? What can you `set`? Should "current temp" ever be accepted in a command? (No. Why not?)
>
> Then do the walkthrough from Step 1: *Hue adapter starts → you tap a light on the display → the adapter crashes*. List every message, in order, using your real topic names.

> [!NOTE]
> **Not covered yet. Add a short "Conventions" section at the top of the spec:**
> - Topic rules: lowercase, no leading or trailing `/`, allowed characters in IDs (`a-z0-9_`?)
> - Payload rules: always JSON? Key naming (`snake_case`)? Units in the key name (`temperature_c`) or in a separate field?
> - Timestamps: who adds them, and in which format (ISO 8601 UTC is a safe default)?
> - Versioning: if you change the payload shape in six months, how will an old adapter and a new core cope? (One answer: a `"v": 1` field. Just think about it for now.)
