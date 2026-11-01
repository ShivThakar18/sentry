# MQTT Experiments (learning log)

Hands-on experiments from Step 1. The decisions they led to are in [`../mqtt-topics.md`](../mqtt-topics.md).

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
   docker exec mosquitto mosquitto_pub -h localhost -t home/lamp/state -r -n
   ```
   - `-n` sends an empty message and `-r` makes it retained. Together they replace the retained value with nothing, which deletes it.
   - (My first attempt, `-m -r -n`, was broken. `-m` takes the *next* argument as the message, so the message became the literal text `"-r"`. Lesson: when a flag takes a value, the value is whatever comes next, even if it looks like a flag.)

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
Three separate settings, three separate questions:
- **QoS** = did the message reach the broker or subscriber? (It knows nothing about whether the *bulb* is reachable.)
- **Clean vs. persistent session** = should messages pile up while I'm offline?
- **Retained** = should a *new* subscriber see the last value?

| Message | QoS | Retained | Why |
|---|---|---|---|
| Turn on the lights | 1 | No | Losing a tap is annoying, and QoS 1 costs nothing on a LAN. The adapter uses a **clean session**, so commands don't pile up while it's down and fire hours later. |
| Temperature every 10 s | 0 | **Yes** | If one reading is lost, the next one arrives 10 s later. Retained so the display shows a value as soon as it boots. |
| Doorbell pressed | 1 | **No** | Don't miss it, but retaining it would replay it on every reboot (see Q8). |
  
## Experiment 5: Last Will and Testament (the important one)
The Last Will is how your core will find out an adapter has crashed.
- In A, subscribe to adapters/#.
- In B, start a mosquitto_sub that pretends to be an adapter. Give it a will topic adapters/fake/status, payload offline, retained, and a short keepalive (-k 5). Run mosquitto_sub --help to find the flag names.
- Stop it with Ctrl+C. Does the will fire?
- Restart it, and this time kill it: close the terminal window, or end it in Task Manager. Now does it fire? How long does it take?

> [!IMPORTANT]
> You haven't recorded the results. Did the will fire on Ctrl+C? On kill? **How many seconds** did the kill take? Add the command you used too (`--will-topic`, `--will-payload`, `--will-retain`, `-k`).
>
> **Expected:** Ctrl+C → **no** will. Kill → the will fires after about **7–8 s** with `-k 5`, because the broker waits 1.5 × keepalive. Run it and record what *you* saw.
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
