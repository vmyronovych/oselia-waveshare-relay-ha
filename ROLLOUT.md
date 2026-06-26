# Site rollout guide

Start-to-finish steps to deploy Waveshare Modbus RTU relays at a new site with Home
Assistant. Follow it top to bottom. Allow ~30–45 min for a single bus.

> **The golden rule:** only one program can use the serial port at a time. While the
> **gateway** (or HA) is using the adapter, the **bench tool** can't — and vice-versa.
> Stop one before running the other.

---

## 0. What you need

- [ ] Home Assistant running (note: can it see the USB adapter, or is it in Docker? — Step 4).
- [ ] USB → RS485 adapter.
- [ ] One or more Waveshare Modbus RTU relay boards (4/8/16/32-ch).
- [ ] DIN-rail space, 7–36 V supply for the boards, RS485 A/B + GND wiring.
- [ ] A laptop with Python 3 + `pyserial` for bench provisioning (`pip install pyserial`).
- [ ] This repo checked out (for `tools/`): `git clone https://github.com/vmyronovych/oselia-waveshare-relay-ha`

---

## 1. Bench-provision each board (BEFORE installing)

Every board ships as **address 1**, so multiple boards on one bus collide. Give each a
unique address on the bench, one at a time, with **only that board** connected to the
adapter.

```sh
cd oselia-waveshare-relay-ha/tools

# find the adapter
python3 waveshare_provision.py ports

# confirm the lone board + its current address (broadcast)
python3 waveshare_provision.py -p /dev/ttyUSB0 discover      # macOS: /dev/cu.usbserial-XXXX

# assign a unique address (1, 2, 3, … per board). Example: make this one address 2
python3 waveshare_provision.py -p /dev/ttyUSB0 -a 1 set-address 2

# smoke-test it
python3 waveshare_provision.py -p /dev/ttyUSB0 -a 2 status
python3 waveshare_provision.py -p /dev/ttyUSB0 -a 2 on 1
python3 waveshare_provision.py -p /dev/ttyUSB0 -a 2 off 1
```

- [ ] **Label each board with its address** before moving on.
- [ ] Repeat for every board (addresses must be unique on the same bus).
- [ ] Keep the **same baud** on all boards (default **9600** — leave it unless you have a reason).

> A single board? Leave it at address **1** — no provisioning needed, just smoke-test it.
> Some firmware reports `SW version: unknown` in `info` — harmless.

---

## 2. Install the hardware

- [ ] Mount boards on the DIN rail; power them (7–36 V).
- [ ] Daisy-chain the RS485 bus: **A↔A, B↔B, GND↔GND** across all boards to the adapter.
- [ ] Plug the adapter into the HA host (or the machine that will run the gateway).

---

## 3. Decide the connection path

| Situation | Use | Go to |
| --- | --- | --- |
| HA can directly see the USB adapter (HA OS, or Docker on Linux with `--device`) | **Serial** transport | Step 5 |
| HA is in Docker and can't see USB (e.g. **Docker Desktop on macOS**) | **Modbus-TCP gateway** | Step 4 |

---

## 4. (Docker only) Start the Modbus-TCP gateway

Run on the machine with the adapter. It exposes the bus as reliable **Modbus TCP**.

```sh
pip install pyserial
python3 oselia-waveshare-relay-ha/tools/modbus_gateway.py \
  --port /dev/ttyUSB0 --baud 9600 --listen 5020      # macOS: --port /dev/cu.usbserial-XXXX
```

Leave it running. Make it permanent so it survives reboots:

- **macOS** → launchd LaunchAgent, **Linux/Pi** → systemd unit. Copy-paste units are in the
  main [README → Home Assistant in Docker](README.md#home-assistant-in-docker-no-usb-access).

> Don't use a plain `socat` pipe — transparent RTU-over-TCP fragments frames and reads fail
> intermittently. The gateway avoids that (MBAP framing). See the README for the why.

---

## 5. Install the integration (HACS)

- [ ] HACS → ⋮ → **Custom repositories** → `https://github.com/vmyronovych/oselia-waveshare-relay-ha`, category **Integration**.
- [ ] Install **Waveshare Modbus RTU Relay** → **restart Home Assistant**.

---

## 6. Add the integration

**Settings → Devices & Services → Add integration → Waveshare Modbus RTU Relay**, then:

**Serial path:**
- [ ] Pick the serial port + baud (9600).

**Gateway path (Docker):**
- [ ] Host = `host.docker.internal` (Docker Desktop) or the gateway host's LAN IP.
- [ ] TCP port = `5020`.
- [ ] Framing = **Modbus TCP** ← important (not "RTU over TCP").

Then add the first board:
- [ ] **Modbus address** = the one you labelled it with (e.g. `2`).
- [ ] Name + channel count (e.g. 8). It's pinged before being added.
- [ ] Add the rest via the hub's **Configure → Add a relay board** (one per address).

---

## 7. Name the relays

- [ ] Open each `switch.relay_N`, rename to what it controls ("Kitchen lights", "Gate", …).
      Names stick to the relay across restarts.

---

## 8. Wire the wall switches → relays (OSELIA)

- [ ] HA → Settings → Automations & Scenes → **Blueprints → Import Blueprint**, paste:
  `https://github.com/vmyronovych/oselia-waveshare-relay-ha/blob/main/blueprints/automation/waveshare_relay/oselia_button_to_relay.yaml`
- [ ] Create one automation per mapping: pick the **OSELIA input**, the **gesture**
      (single/double/long), the **relay**, and the **action** (toggle / on / off / pulse).
- [ ] Press the physical switch → confirm the relay flips.

---

## Verify & troubleshoot

| Symptom | Likely cause / fix |
| --- | --- |
| "Could not open the bus" on Add | Serial: wrong port / adapter busy. Gateway: gateway not running, wrong host/port, or `host.docker.internal` not reachable from the container (use the host LAN IP). |
| "No relay board answered at that address" | Wrong **address** (check the label / run `discover`), wrong **baud**, or A/B swapped. |
| Reads flap / "No response after 3 retries" in logs | You're on a transparent `socat` pipe — switch to the **gateway** (framing = Modbus TCP). |
| Board shows **unavailable** | Bus/gateway down, or address wrong. Check the **Connection** sensor + HA logs (`waveshare`). |
| Bench tool says port busy | The gateway/HA owns it — stop the gateway first. |

Quick re-test of the whole path from the HA host (Docker):

```sh
docker exec -i homeassistant python3 - <<'EOF'
import asyncio, inspect
from pymodbus.client import AsyncModbusTcpClient
async def m():
    c=AsyncModbusTcpClient("host.docker.internal",port=5020,timeout=3); await c.connect()
    kw="slave" if "slave" in inspect.signature(c.read_coils).parameters else "device_id"
    r=await c.read_coils(0,count=8,**{kw:2}); print("OK", list(r.bits)[:8]); c.close()
asyncio.run(m())
EOF
```
(set the address `2` and host/port to match your site)

---

## Per-site cheat sheet (fill in)

```
Site:            ______________________
Adapter path:    ______________________   Baud: 9600
Connection:      [ ] Serial   [ ] Gateway @ host:port ______________
Boards:
  addr __  name ________________  channels ____
  addr __  name ________________  channels ____
Gateway autostart installed: [ ] launchd  [ ] systemd
```
