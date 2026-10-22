# MQTT Questions and Experiments
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
  
Questions:
1. What’s the difference between + and #?
   - The + acts as a placeholder or variable. This means that when publishing messages any topic in that place can be sent and read. Though this is more strict and only allows the + wildcard to be replaced with any other string. As seen in experiments above, only the first message was published because the "lamp" was able to fit into place. The third message also shows that you cannot add more topics to replace the +.
   - The # acts as "anything goes". Although it cannot be used in place of a + it can only be used at the end of a given path such as home/# 
2. Why does a leading / cause trouble?
   - As it was seen in experiment 1. The subscription is very strict and requires the topics to match exactly. Additionally, the # wildcard was written at the end and only subdirectories after home are available in this case. 
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
   

**Design question:** a light’s state should almost certainly be retained. Should a command like set: on or unlock be retained? Picture the core restarting a week later.
- State should be retained
- But a command should not; it should only be a 1-time thing. Otherwise, the device will keep triggering the command indefinitely
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
- Offline delivery:
  1. Start a subscriber with a fixed client ID (-i), the “don’t clean session” flag (-c), and -q 1.
  2. Close it.
  3. Publish a few QoS 1 messages.
  4. Reconnect it with the same ID.
- What happens? Now repeat with QoS 0.
  - With QoS 1, publishes once connected and gets queued while offline
  - With QoS 0, it can publish at most once, but it can get lost. It cannot get queued for offline

**Design question:** which of these needs QoS 1?
- “Turn on the lights” - QoS 0 - i believe my google home does this at QoS 0. When my lights are offline, it doesn't get queued. 
- “Temperature is 21.4°C”, sent every 10 seconds - If this is critical this QoS 1 
- “Doorbell pressed” - QoS 1 
  
## Experiment 5: Last Will and Testament (the important one)
The Last Will is how your core will find out an adapter has crashed.
- In A, subscribe to adapters/#.
- In B, start a mosquitto_sub that pretends to be an adapter. Give it a will topic adapters/fake/status, payload offline, retained, and a short keepalive (-k 5). Run mosquitto_sub --help to find the flag names.
- Stop it with Ctrl+C. Does the will fire?
- Restart it, and this time kill it: close the terminal window, or end it in Task Manager. Now does it fire? How long does it take?

Questions:
1. Why does Ctrl+C behave differently from a kill?
   - Ctrl+C acts has a clean disconenct and sends a DISCONNECT Packet
3. The will only ever says “offline”. How should an adapter announce “online” when it starts? This pattern is often called a birth message.
   - A birth message is a retained online the adapter publishes to its own will topic right after it connects. The topic then always holds the latest truth:

## Experiment 6: JSON payloads
Real messages will be JSON, like {"on": true, "brightness": 80}. Try publishing one from PowerShell, and you’ll run into quoting problems. Work out two fixes:
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

# Questions We should answer before starting
1. Root and namespace. Does everything sit under one root, like home/? How do you keep device traffic separate from system traffic such as adapter status and core events?
2. Identity. What goes in the path: device type, room, brand, or a stable ID? What happens to your topics if you move a lamp to another room?
3. State vs. command. These need separate topics. What are they called? Which is retained? Who is allowed to publish to each one?
4. Granularity. Is a whole device one JSON state message, or does each attribute (/brightness, /power) get its own topic? List a trade-off on each side.
5. Discovery and capabilities. When the Hue adapter starts, how does it tell the core “I have 2 lights; they support on/off, brightness and colour”? Where does that message go, and is it retained?
6. Availability. Your topic for the birth message and Last Will, per adapter or per device.
7. Events vs. state. “Doorbell pressed” isn’t really a state. Does it belong somewhere else? Should it be retained?
8. Examples. Show your scheme handling a Hue light, a Govee pot light, the BME280 sensor and the Ecobee.
