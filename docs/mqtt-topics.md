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
**Predictions:** do those last two arrive? What does that tell you about how strictly topics are matched?
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

Questions:
1. What’s the difference between + and #?
2. Why does a leading / cause trouble?
3. Can # go in the middle of a topic? Try it.

## Experiment 3: Retained messages
1. Publish on to home/lamp/state without -r. Then start a new subscriber. Does it get anything?
2. Now publish with -r. Start another new subscriber.
3. Find out how to delete a retained message. Hint: send an empty payload, and look at the -n flag.

**Design question:** a light’s state should almost certainly be retained. Should a command like set: on or unlock be retained? Picture the core restarting a week later.
## Experiment 4: QoS and persistent sessions
QoS is hard to see on one machine, so make it visible:

- Add -d (debug) to both the subscriber and the publisher, then publish with -q 0, then -q 1, then -q 2. Count the packets each time (PUBLISH, PUBACK, PUBREC…).
- Offline delivery:
  1. Start a subscriber with a fixed client ID (-i), the “don’t clean session” flag (-c), and -q 1.
  2. Close it.
  3. Publish a few QoS 1 messages.
  4. Reconnect it with the same ID.
- What happens? Now repeat with QoS 0.

**Design question:** which of these needs QoS 1?
- “Turn on the lights”
- “Temperature is 21.4°C”, sent every 10 seconds
- “Doorbell pressed”
  
## Experiment 5: Last Will and Testament (the important one)
The Last Will is how your core will find out an adapter has crashed.
- In A, subscribe to adapters/#.
- In B, start a mosquitto_sub that pretends to be an adapter. Give it a will topic adapters/fake/status, payload offline, retained, and a short keepalive (-k 5). Run mosquitto_sub --help to find the flag names.
- Stop it with Ctrl+C. Does the will fire?
- Restart it, and this time kill it: close the terminal window, or end it in Task Manager. Now does it fire? How long does it take?

Questions:
1. Why does Ctrl+C behave differently from a kill?
2. The will only ever says “offline”. How should an adapter announce “online” when it starts? This pattern is often called a birth message.

## Experiment 6: JSON payloads
Real messages will be JSON, like {"on": true, "brightness": 80}. Try publishing one from PowerShell and you’ll run into quoting problems. Work out two fixes:
- Quote it correctly for your shell.
- Use the -f flag to publish from a file.

# Questions We should answer before starting
1. Root and namespace. Does everything sit under one root, like home/? How do you keep device traffic separate from system traffic such as adapter status and core events?
2. Identity. What goes in the path: device type, room, brand, or a stable ID? What happens to your topics if you move a lamp to another room?
3. State vs. command. These need separate topics. What are they called? Which is retained? Who is allowed to publish to each one?
4. Granularity. Is a whole device one JSON state message, or does each attribute (/brightness, /power) get its own topic? List a trade-off on each side.
5. Discovery and capabilities. When the Hue adapter starts, how does it tell the core “I have 2 lights; they support on/off, brightness and colour”? Where does that message go, and is it retained?
6. Availability. Your topic for the birth message and Last Will, per adapter or per device.
7. Events vs. state. “Doorbell pressed” isn’t really a state. Does it belong somewhere else? Should it be retained?
8. Examples. Show your scheme handling a Hue light, a Govee pot light, the BME280 sensor and the Ecobee.
