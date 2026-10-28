# Smart Display: Steps 2–4 Guide

**Order for tonight: 3 → 2 → 4.** Set up the repo first, so the Docker work in Step 2 becomes your first real commit and pull request. Realistically you'll get through Steps 3 and 2 and the exploration half of Step 4 (4a–4f). Writing the adapter code (4g) is its own evening.

As in Step 1, **predict before you press Enter**.

---

# Step 3: The repo (about 45 min)

## 3a. Where the code lives
You're working in WSL (your `shivt@GHOSTTT:~$` prompt). Clone the repo into your **WSL home** (`~/`), not `/mnt/c/...`.
- **Question:** why? Look up "WSL file system performance" and "file permissions on /mnt/c". You'll care once Docker bind-mounts your config files.

  > Delivers near-native CPU and memory performance, but speed depends heavily on wehre your files are stored and how much RAM is allocated
  > File System Location - Fast speeds when project files kept in /home/username/ or ~/
  > Accessing Windows Drives from inside WSL uses a 9P translation protocol, making file operations slower

- Open it in VS Code from WSL with `code .`. Check that the bottom-left corner says **WSL**.

## 3b. Git identity and auth
- Set `user.name` and `user.email` in git's global config.
- Authenticate to GitHub. Either install the `gh` CLI and run `gh auth login`, or set up an SSH key.
- **Question:** why does GitHub no longer accept your password for `git push`?
     > Using SSH to clone and push

## 3c. Layout
Create the folders. Git doesn't track empty folders, so add a `.gitkeep` file or a README to each.
```
docs/                  ← mqtt-topics.md goes here
docs/notes/            ← your experiment log
deploy/mosquitto/      ← broker config (Step 2)
adapters/hue/          ← Step 4
core/                  ← FastAPI, later
ui/                    ← React, later
```
**Question:** later you'll also have `adapters/govee`, `adapters/local` and others. What will they share, such as MQTT connection code and the birth/will logic? Where would shared code live? You don't need to build it yet; just write the question down in an issue.
   > Unsure about what they will share fully
   > Shared code maybe should stay in `adapters/`

## 3d. `.gitignore` and secrets
1. Find GitHub's official `.gitignore` templates (the `github/gitignore` repo) for **Python** and **Node**, and combine them.
2. Add your own entries: `.env`, `.venv/`, and the Mosquitto data and log folders you'll create in Step 2.
3. **Experiment:**
   - Create a `.env` file containing `HUE_KEY=fake` *before* adding it to `.gitignore`, then run `git status`. Predict what you'll see.
   - Add it to `.gitignore` and run `git status` again.
   - Run `git check-ignore -v .env` and work out what its output means.
4. **The `.env.example` pattern:** commit a `.env.example` with the variable *names* and dummy values. The real `.env` never leaves your machine.
   - **Question:** if you accidentally committed a real key and then deleted it in the next commit, is it safe? (Look up git history. The correct response is to *rotate* the key, meaning create a new one and revoke the old.)
   > This is not safe. History can be seen for everyone who sees the repo. 

## 3e. The workflow you'll use for everything
1. Create **GitHub Issues** for Step 2, Step 4, and "split mqtt-topics.md".
2. Create a branch: `git switch -c chore/repo-setup`.
3. Commit in small pieces. Look up **Conventional Commits** (`feat:`, `fix:`, `docs:`, `chore:`) and use them.
4. Push, open a **pull request** on GitHub, and write "Closes #N" in the description. Read your own diff in the PR view, then merge.
5. Back in your terminal: `git switch main`, `git pull`, and delete the old branch.
   - **Question:** what happened to the issue when you merged?
        > Issue stayed open

## 3f. README
Keep it short: what the project is, the architecture in one line (UI → core → MQTT → adapters), how to start the broker (fill this in after Step 2), and links to `docs/`.
   > Will do this later...

### ✅ Step 3 is done when…
- [x] The repo is cloned in WSL and opens in VS Code (WSL mode)
- [x] `.env` is provably ignored, and `.env.example` is committed
- [ ] You've merged one PR that closed an issue

---

# Step 2: Mosquitto with Docker Compose (about 1 hr)

You already have Mosquitto running in a container, so you're halfway there. This step makes it **reproducible**: the same command builds the same broker on your PC and on the Pi.

## 2a. Inspect what you have
- Run `docker ps`, then `docker inspect mosquitto`. Find the **Mounts** and **Ports** sections. Is anything mounted? Is any port mapped?
   > PORTS 127.0.0.1:1883 -> 1883
   > Mounts mosquitto/config and mosquitto/data and mosquitto/local
- **Check for clashes:** is the Windows Mosquitto *service* still running? If it is, it's holding port 1883 on Windows. Decide now: stop it and set it to manual, because Docker is your broker from here on.
   - Stop the Windows MQTT service and set it to Manual. Keep it installed, because its command-line tools (`mosquitto_sub.exe` and `mosquitto_pub.exe`) are handy for testing from Windows.
   > WHY?
   >  - Only one program can listen on Port 1883. Your Docker container may not map 1883 yet, so there's no clash TODAY. In step 2f I will end up mapping it, and it either:
   >     - Docker refuses to start with "port is already allocated"
   >     - The worse case: something on Windows connect to localhost:1883 and silently reaches the Windows Broker and not the Docker one.
   >     -  The Docker broker is the one that matters. It's the one that will run on the Pi, using the docker-compose.yml and mosquitto.conf. The windows service is dead end and it would have to keep in sync.
   >     -  Manual, not Uninstall: it won't start on boot or get in the way, but you can still start it if you ever want to compare

  > How? 
  > 1. Before: run netstat -ano | findstr 1883 in PowerShell and note the PID in the last column. In Task Manager → Details, find that PID. Is it mosquitto.exe? That confirms the Windows service is holding the port.
  > 2. Stop it and set it to Manual. Do one of these:
    > - GUI: press Win+R, type services.msc, find Mosquitto Broker, right-click → Stop. Then open Properties and set Startup type to Manual.
    > - PowerShell (run as Administrator): look up Stop-Service and Set-Service -StartupType. The service name is mosquitto, and you can confirm it with Get-Service *mosq*.
  > 3. After: run netstat again. Predict: what will it show? If your container doesn’t map 1883 yet, the answer should be nothing. After Step 2f it should show the Docker process (com.docker.backend or wslrelay) instead of mosquitto.exe.
  > 4. Reboot check: after your next restart, run Get-Service mosquitto. It should say Stopped.
  
## 2b. Experiment: how fragile is it right now?
1. Publish a **retained** message to `test/persist`.
2. Run `docker restart mosquitto`, then subscribe. **Predict:** is the retained message still there?
3. Now try `docker rm -f mosquitto`, then run the container again the same way you did originally. Is the message still there?

Write down why you got each result. The words to look up are **container filesystem** and Mosquitto's **`persistence`** setting, which is off by default.


## 2c. Experiment: can anything outside the container reach the broker?
You've been using `docker exec`, which runs the client *inside* the container. Try from outside instead: use MQTT Explorer on Windows, or `mosquitto_sub -h localhost` from Windows. **Predict:** does it connect?

Two separate things could block it:
1. **Port mapping.** Did you publish 1883 from the container to your host?
2. **Mosquitto 2.x "local only" mode.** With no config, it only accepts connections from *its own* localhost, and inside a container that means the container itself.

Figure out which one is blocking you. Probably both.

## 2d. Write `deploy/mosquitto/mosquitto.conf`
Research these settings in the official Mosquitto config docs and decide on a value for each:

| Setting | Question to answer |
|---|---|
| `listener` | Which port, and which address to bind? |
| `allow_anonymous` | `true` is acceptable for now on your home LAN. Add a TODO to set up a `password_file` before you enable remote access. |
| `persistence` + `persistence_location` | Where inside the container should data live? |
| `log_dest` | Log to stdout, so `docker compose logs` can show it? Or to a file? |

Add a comment above each line explaining it **in your own words**. That's your learning record.

## 2e. Volumes: two kinds
Read about **bind mounts** and **named volumes**, then decide which to use for each of these:
- **Config** (`mosquitto.conf`): you edit it and it's in git, so a bind mount from `deploy/mosquitto/`.
- **Data** (persisted retained messages): generated at runtime, never committed. A named volume, or a bind-mounted folder you `.gitignore`. Pick one and write down why.

Find out which paths *inside* the container the official `eclipse-mosquitto` image expects. Its Docker Hub page lists them.

## 2f. Write `docker-compose.yml`
Put it in the repo root or in `deploy/` (your call). Look up each of these keys:
- `services:` → one service, `mosquitto`
- `image:` → **pin a specific version tag** from Docker Hub.
  - **Question:** why not use `latest`? Picture the Pi pulling a new major version on its own six months from now.
- `container_name`, `ports`, `volumes`
- `restart:` → compare `no`, `always` and `unless-stopped`. Which one survives a Pi reboot but still lets you stop it on purpose?

Commands to learn: `docker compose up -d`, `ps`, `logs -f`, `down`, `restart`.

## 2g. Prove it works
1. Run `docker rm -f mosquitto` to remove the old container, then `docker compose up -d`.
2. Repeat **2b** with `docker compose down` followed by `up -d`. Does the retained message survive now?
3. Repeat **2c**. Can MQTT Explorer on Windows connect to `localhost:1883` now?
4. Read `docker compose logs`. Find the line that shows your config was loaded.
5. **Pi check:** on the image's Docker Hub tags page, confirm your pinned tag supports **`linux/arm64`**.

### ✅ Step 2 is done when…
- [ ] A fresh `docker compose up -d` gives you a working broker
- [ ] Retained messages survive `down` / `up`
- [ ] MQTT Explorer on Windows connects to `localhost:1883`
- [ ] It's merged through a PR, and the README says how to start the broker

---

# Step 4: The Hue adapter, exploration first (4a–4f about 1.5 hrs)

**Rule for this step:** understand the API completely *by hand* before writing any Python. Use `curl` in WSL. Postman is fine too if you prefer a GUI.

## 4a. Find the bridge
Three ways. Try at least two:
1. The Hue app: Settings → Bridges → (i).
2. Your router's DHCP client list.
3. Open `https://discovery.meethue.com` in a browser.
   - **Question:** how does a cloud service know your bridge's *local* IP?

Then open `https://<bridge-ip>` in a browser. You'll get a **certificate warning**.
- **Question:** why does a device on your own network have a certificate your browser doesn't trust? Look up "self-signed certificate". You'll need `curl -k` for now, and pinning Hue's own CA is a later improvement.

**Tip:** give the bridge a **DHCP reservation** in your router so its IP never changes.

## 4b. Get an application key
1. Create a free account on the **Philips Hue Developer** portal and read "Getting started" for **CLIP API v2**.
2. You register the key by POSTing to `/api` with a JSON body containing a `devicetype` (for example `smartdisplay#wsl`) and `"generatekey": true`.
3. **Predict:** what does the bridge reply the first time? Send it and read the error.
4. Press the physical button on the bridge, then resend within 30 s.
5. Put the key in `.env` immediately. Run `git status` to confirm it isn't listed.

## 4c. Read the data
v2 endpoints live under `/clip/v2/resource/...` and need your key in a `hue-application-key` header.
1. GET `light`. Pipe the output through `jq` (install it in WSL) to make it readable.
2. For **one** light, find:
   - its `id` (a UUID). Is there also an `id_v1`? Which one will you use in your topic ID, and why?
   - its name. Where is it? (Hint: `metadata`.)
   - on/off, brightness, and colour
3. **Spec check:** Hue colours are **`xy`** (the CIE colour space), not hex. Your spec says `"color": "#ff8800"`. Where should that conversion happen: adapter, core, or UI? Is hex even the right choice for your spec? Make a decision and write it down.
4. GET `device` and `room`. How does a room know which lights belong to it? Follow the IDs. This becomes the *suggested* `room` in your `info` message.
5. **Capabilities:** compare a colour bulb with a white-only one, if you have one. Which keys are present or missing? That's how your adapter will build the `capabilities` list.

## 4d. Control a light by hand
1. PUT to `light/<id>` with a body that turns it on. Find the shape in the docs.
2. **Predict:** does the response contain the new state, or only a confirmation?
3. Change brightness. Then send a body containing *only* brightness. Does on/off stay as it was? (Does that match your partial `set` design? 🙂)

## 4e. Watch it live: the event stream
1. GET `/eventstream/clip/v2` with header `Accept: text/event-stream`, using `curl -N` so the output isn't buffered.
2. Leave it running. Toggle a light in the **Hue app**, then flip a physical switch. Watch what arrives.
3. **Questions:**
   - Does the event contain the full light state, or only what changed? What does that mean for your **full-JSON `state`** rule? (The adapter must merge the change into the last state it knew.)
   - Polling every 2 s vs. this stream: compare the cost, delay, and missed changes.
   - What happens to the stream if the bridge reboots? Your adapter must reconnect.

## 4f. Write the mapping doc: `docs/adapters/hue.md`
This is the design for your code. Fill in:

| Hue field | Your `state` field | Conversion |
|---|---|---|
| `on.on` | `on` | none |
| `dimming.brightness` | `brightness` | ? (check the range) |
| `color.xy` | ? | ? |
| … | | |

Plus:
- **ID rule:** which Hue ID becomes `hue-<…>`?
- **Capability rule:** which Hue keys produce which capabilities?
- **Availability:** how does Hue tell you a bulb is unreachable? Search for `zigbee_connectivity`.

### ✅ Tonight is a win if…
- [ ] You can control a light with curl
- [ ] You've watched the event stream react to the Hue app
- [ ] `docs/adapters/hue.md` is committed

---

# 4g. Next evening: writing the adapter

Build it in **milestones**, with one commit each, checking each one in MQTT Explorer:

1. **List:** the script loads `.env`, calls the bridge, and prints your lights. (Set up a `.venv` in `adapters/hue/` and a `requirements.txt`. Research `httpx` and `python-dotenv`.)
2. **Publish:** connect to MQTT and publish retained `info` and `state` for each light. They should appear in MQTT Explorer under `home/device/`.
3. **Command:** subscribe to `home/device/+/set` and translate commands into PUT requests. Tap from MQTT Explorer, and the light changes.
4. **Live:** read the event stream, merge the changes, and republish `state`. Toggling in the Hue app now updates MQTT.
5. **Lifecycle:** add the will, the birth message, and publishing `offline` on Ctrl+C. Repeat Experiment 5, but against your real adapter.

**Concepts to read up on before you start:**
- **`asyncio`:** your adapter has to do three things at once: listen for `set`, read the event stream, and keep MQTT alive.
- **`aiomqtt`:** an async MQTT client.
- **Python signal handling:** how to catch Ctrl+C so you can publish `offline` before exiting.
