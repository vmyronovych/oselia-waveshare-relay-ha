# Waveshare Modbus RTU Relay — Home Assistant integration

[![Validate](https://github.com/vmyronovych/oselia-waveshare-relay-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/vmyronovych/oselia-waveshare-relay-ha/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/vmyronovych/oselia-waveshare-relay-ha)](https://github.com/vmyronovych/oselia-waveshare-relay-ha/releases)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

A clean, local-only Home Assistant integration for **Waveshare Modbus RTU relay boards**
on an RS485/USB adapter — built for the
[**Modbus RTU Relay (B)** (8-ch)](https://www.waveshare.com/modbus-rtu-relay-b.htm), and
working across the **4 / 8 / 16 / 32-channel** family since they share one protocol.

Unlike hand-written `modbus:` YAML, this gives you a proper **config flow**, a tidy
**device per board**, native **switch** entities you can rename, and — uniquely —
**commissioning from inside HA** (set a board's Modbus address / baud rate over the bus,
no SSCOM or Modbus Poll needed).

> Designed to pair with the [**OSELIA Hearth**](https://github.com/vmyronovych/oselia-hearth-di16g-ha)
> wall-switch gateway: a bundled **blueprint** maps any OSELIA button gesture
> (single / double / long) to any relay action in two clicks.

> 📋 **Deploying at a new site?** Follow [**ROLLOUT.md**](ROLLOUT.md) — a start-to-finish
> checklist (bench-provision addresses → wire the bus → bridge/serial → HA → wire buttons).

## Install

### HACS (recommended)

1. In Home Assistant, open **HACS** (sidebar) → top-right **⋮** → **Custom repositories**.
2. Paste `https://github.com/vmyronovych/oselia-waveshare-relay-ha`, set category **Integration**, click **Add**, then close the dialog.
3. **Download the integration into Home Assistant:**
   1. In HACS, search for **Waveshare Modbus RTU Relay** and open its page (it shows up after step 2).
   2. Click **Download** (bottom-right), keep the latest version, and confirm **Download**.
      This copies the files into `config/custom_components/waveshare_relay` — it does **not** load them yet.
   3. **Restart Home Assistant** so it loads the new integration:
      **Settings → System → ⏻ (top-right) → Restart Home Assistant**
      (or Developer Tools → **Actions** → run `homeassistant.restart`).
4. After the restart: **Settings → Devices & Services → Add integration**, search
   **Waveshare Modbus RTU Relay**.

#### Don't have HACS yet?

HACS is a one-time install (it's the store this integration is distributed through).

1. **Download HACS** onto the HA host:
   - **HA OS / Supervised** — open the **Terminal & SSH** add-on and run:
     ```sh
     wget -O - https://get.hacs.xyz | bash -
     ```
   - **Docker / Container** — run the same script *inside* the HA container:
     ```sh
     docker exec -it homeassistant bash -c "wget -O - https://get.hacs.xyz | bash -"
     ```
     (replace `homeassistant` with your container name)
   - Either way it drops HACS into `config/custom_components/hacs`.
2. **Restart Home Assistant**, then hard-refresh your browser (Ctrl/Cmd-Shift-R).
3. **Settings → Devices & Services → Add integration → HACS**, accept the prompts.
4. **Authorize with GitHub**: open <https://github.com/login/device> and enter the code HACS shows.
5. HACS now appears in the sidebar — continue from step 1 above.

> Full upstream guide: <https://hacs.xyz/docs/use/download/download/>.

### Manual

Copy `custom_components/waveshare_relay/` into your HA `config/custom_components/`,
restart HA, and add the integration as above.

## Setup

1. **Choose the transport:**
   - **Serial** — a USB/RS485 adapter on the HA host. Pick the port (auto-detected) and the
     **bus baud rate** (factory default **9600**).
   - **Network (TCP)** — the bus reached over the network. Use this when HA can't see the USB
     port (see [HA in Docker](#home-assistant-in-docker) below). Enter the
     bridge/gateway **host**, **port**, and **framing** (RTU over TCP for socat / transparent
     gateways; Modbus TCP only for an MBAP gateway).
2. **Add the first board** — its **Modbus address** (factory default **1**), a **name**, and
   the **channel count** (4/8/16/32). The board is pinged before it's added.
3. Add more boards on the same bus any time via the integration's **Configure → Add a relay
   board** (each needs a unique address).

> **One config entry = one bus.** A serial port (or bridge socket) can only be opened once, so
> every board on that RS485 bus lives under the same entry, each as its own HA device.

## Home Assistant in Docker

Which path you need depends on whether the **Docker host can see the RS485 adapter**:

- **HA in Docker _on the machine the bus is wired to_** (the usual **Raspberry Pi**
  setup) → pass the serial device into the container and use the **Serial** transport.
  No gateway. See just below.
- **HA can't see the port** — Docker Desktop on macOS (no USB passthrough at all), or HA
  on a _different_ machine from the bus → put the bus on the network with the bundled
  **Modbus-TCP gateway** and use the **Network (TCP)** transport. See
  [further down](#when-ha-cant-see-the-usb-port--the-bundled-modbus-tcp-gateway).

### Raspberry Pi (or any Linux host) with the bus attached — pass the device in (recommended, no gateway)

When HA runs in Docker **on the same machine the USB/RS485 adapter (or a Pi's onboard
UART) is plugged into**, give the container direct access to the serial device and use the
**Serial** transport. No extra process to run or keep alive.

**`docker run`** — add the device:

```sh
docker run -d --name homeassistant --restart unless-stopped \
  --network host \
  -v /PATH/TO/config:/config \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  ghcr.io/home-assistant/home-assistant:stable
#  USB adapter: /dev/ttyUSB0   •   Pi onboard UART: /dev/ttyAMA0 (a.k.a. /dev/serial0)
```

**`docker-compose.yml`**:

```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./config:/config
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0   # or /dev/ttyAMAx for a Pi onboard UART
```

Restart the container after adding the device, then add the integration →
**Serial** → port `/dev/ttyUSB0` (or your `/dev/ttyAMAx`), bus baud **9600**.

**Raspberry Pi notes:**

- **Onboard UART (RS485 HAT / GPIO header):** enable the UART and free it from the serial
  console first — `sudo raspi-config` → *Interface Options → Serial Port* → login shell
  over serial **No**, serial hardware **Yes** (equivalently `enable_uart=1` plus the right
  `dtoverlay=` in `/boot/firmware/config.txt`). The port then appears as `/dev/ttyAMAx` /
  `/dev/serial0`. Pass that path with `--device`.
- **Stable path:** for USB adapters prefer `/dev/serial/by-id/usb-...` over `/dev/ttyUSB0`
  (which can renumber across reboots/replugs), and pass the `by-id` path through.
- **Permissions:** the device is `root:dialout`; `--device=` exposes it to the container as-is,
  which is enough. (Some setups instead run the container `privileged: true` — that also
  exposes every `/dev/tty*`; heavier, but it works.)

> **Already running the gateway and want to switch?** Stop `modbus_gateway.py` (and disable
> its launchd/systemd unit), add `--device`/`devices:` as above, recreate the container, and
> set up the integration as **Serial**. Only one process can own the port at a time.

### When HA can't see the USB port — the bundled Modbus-TCP gateway

Run [`tools/modbus_gateway.py`](tools/modbus_gateway.py) on the machine that has the USB
adapter. It speaks **Modbus TCP (MBAP)** to HA and does proper RTU framing on the serial
side — reliable, unlike a transparent `socat` pipe (see the caveat below). Only needs
`pyserial`:

```sh
pip install pyserial
python3 tools/modbus_gateway.py --port /dev/cu.usbserial-AQ025HGO --baud 9600 --listen 5020
# Linux: --port /dev/ttyUSB0
```

Then add the integration → **Network (TCP)**:

| Field | Value |
| --- | --- |
| **Host** | `host.docker.internal` (HA-in-Docker → the Docker host). On Linux Docker, the host's LAN IP, or add `--add-host=host.docker.internal:host-gateway` to the container. |
| **TCP port** | `5020` |
| **Framing** | **Modbus TCP** |

**Keep it running across reboots:**

*macOS (launchd)* — create `~/Library/LaunchAgents/com.local.waveshare-gateway.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.local.waveshare-gateway</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/python3</string>
    <string>/ABSOLUTE/PATH/oselia-waveshare-relay-ha/tools/modbus_gateway.py</string>
    <string>--port</string><string>/dev/cu.usbserial-AQ025HGO</string>
    <string>--baud</string><string>9600</string>
    <string>--listen</string><string>5020</string>
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/modbus-gateway.log</string>
  <key>StandardErrorPath</key><string>/tmp/modbus-gateway.log</string>
</dict></plist>
```
```sh
launchctl load -w ~/Library/LaunchAgents/com.local.waveshare-gateway.plist
launchctl list | grep waveshare        # 2nd column 0 = running
# stop/remove later: launchctl unload -w ~/Library/LaunchAgents/com.local.waveshare-gateway.plist
```

*Raspberry Pi OS / Linux (systemd)* — `/etc/systemd/system/waveshare-gateway.service`:

```ini
[Unit]
Description=Waveshare Modbus TCP gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/oselia-waveshare-relay-ha/tools/modbus_gateway.py \
  --port /dev/serial/by-id/usb-FTDI-if00-port0 --baud 9600 --listen 5020
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```
```sh
sudo apt install python3-serial
sudo systemctl enable --now waveshare-gateway
journalctl -u waveshare-gateway -f
```

> On a Pi, prefer a stable `/dev/serial/by-id/...` path over `/dev/ttyUSB0` (which can
> renumber across reboots). Remember the gateway is **only** for when HA can't see the USB
> port — if HA runs in Docker on this same Pi, pass the device into the container and use
> the **Serial** transport instead
> ([above](#raspberry-pi-or-any-linux-host-with-the-bus-attached--pass-the-device-in-recommended-no-gateway)).

### Why not plain `socat`?

A transparent `socat TCP-LISTEN … FILE:/dev/tty…` pipe forwards **raw RTU over TCP**. RTU
has no length field — it delimits frames by inter-byte timing gaps, which TCP destroys — so
clients receive fragmented frames and reads fail intermittently (with pymodbus you'll see
`recv: … extra data` / `No response received after 3 retries`). The gateway above avoids
this entirely by using length-delimited MBAP on the wire. (A hardware RS485-to-Ethernet
gateway in **Modbus-TCP** mode works the same way; one in transparent mode has the RTU
fragmentation problem — point the integration at **RTU over TCP** only for those and
expect to tune timing.)

> The [bench provisioning tool](#bench-provisioning-tool-recommended-before-install) talks
> to the USB adapter directly — no gateway needed for it. Only one process can own the
> serial port at a time, so **stop the gateway before bench-testing** (and vice-versa).

## Entities (per board)

| Entity | What it does |
| --- | --- |
| **Switch** ×N | One per relay — see live state, turn on/off. **Rename freely** in the UI; the name sticks to the relay. |
| **All on / All off** (buttons) | Flip every relay in a single bus frame (uses the hardware "all relays" coil). |
| **Connection** (binary sensor) | Connectivity — is the board answering on the bus? Always available, so you can alert on a dead board. |
| **Active relays** (sensor) | How many relays are currently on. |
| **Modbus address** (sensor) | The board's address (diagnostic, disabled by default). |

State is **polled** from the hardware (default every 10 s, adjustable in *Configure → Bus
settings*), so the switches stay truthful even if a relay is flipped by something else on
the bus. Writes update the UI instantly and re-read to confirm.

## Services

| Service | Purpose |
| --- | --- |
| `waveshare_relay.pulse` | **Momentary** press — turn a relay on for *N* seconds then off (or `invert` for NC wiring). Perfect for gates, door strikes, garage doors. |
| `waveshare_relay.all_on` / `all_off` | All relays on/off in one bus frame; target any switch on the board. |
| `waveshare_relay.set_device_address` | **Commission a board's Modbus address from HA.** Put one board on the bus, target it, give a new address — the integration writes it, updates its own config, and reconnects on the new address. |
| `waveshare_relay.set_baud_rate` | Change a board's RS485 baud rate (set every board on the bus to match). |

### Bench provisioning tool (recommended before install)

Before a board ever touches the shared bus, use the standalone CLI in
[`tools/`](tools/) to set its address and smoke-test the relays on the bench (one board
on a USB/RS485 adapter). It needs only `pyserial`, not Home Assistant:

```sh
./tools/waveshare_provision.py -p /dev/ttyUSB0 discover          # find the lone board
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 1 set-address 5
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 on 3         # test relay 3
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 status
```

See [`tools/README.md`](tools/README.md) for the full command list. (Once boards are on
the bus, the same address change is also available in-app via `set_device_address`.)

### Address commissioning, the easy way

Out of the box every Waveshare board ships as **address 1**, so two boards on one bus
collide. To assign addresses without extra software:

1. Wire **one** new board to the bus, set up the integration (or *Add a relay board*) at
   address **1**.
2. Call **`waveshare_relay.set_device_address`** targeting it with the address you want.
3. Power down, wire the **next** board, repeat. Now all boards have unique addresses.

## Wiring OSELIA buttons → relays

The integration **installs its blueprint for you**: the
[`OSELIA button → Waveshare relay`](blueprints/automation/waveshare_relay/oselia_button_to_relay.yaml)
blueprint ships inside the integration and is written to
`/config/blueprints/automation/waveshare_relay/` on startup — so it's there after install,
and **updates ride along with the integration** (just update via HACS and restart; no
re-import). Go straight to **Settings → Automations → Blueprints** to use it. Each automation
maps **one OSELIA input + gesture → one relay action** (toggle / on / off / pulse). Add as
many as you like — e.g. *“kitchen switch, double-press → pulse the gate relay.”*

> **Customizing the blueprint?** Edits to the installed file are **not** overwritten on
> update — the integration detects your changes, keeps them, and raises a Repairs notice
> that a newer version exists. To run a modified version *and* keep getting updates, copy
> the blueprint to your own name/path and build automations from that copy.

Because the relays are standard `switch` entities, they also work with any normal
automation, scene, voice assistant, or dashboard card.

## Ideas / roadmap

These build naturally on the protocol and are good next steps:

- **Hardware-timed flash** — the boards support an on-device timed pulse (open/close with a
  `delay × 100 ms`); using it instead of the software `pulse` would survive an HA restart
  mid-pulse. (Needs a raw Modbus frame; current `pulse` is software-timed for reliability.)
- **Power-on default state** — some variants persist a boot state; expose it as a `select`.
- **Bus auto-scan** — a config-flow step that walks addresses 1–N and lists responders.
- **Latching-relay variants (C/E)** — flash/feedback registers differ; add a model option.
- **Per-relay device-class / icon** override (outlet vs switch vs light) in options.
- **USB-unplug resilience polish** — surface a repair issue when the adapter disappears.

PRs welcome.

## How it works

- Talks **Modbus RTU** via `pymodbus` (async) over either a **serial** port or a **TCP**
  bridge/gateway (RTU-over-TCP or Modbus-TCP framing). `local_polling`.
- Reads relay state with **function 0x01** (read coils from `0x0000`), sets relays with
  **0x05** (write coil; `0xFF00`/`0x0000`), all-relays via coil `0x00FF`, and writes the
  address/baud registers (`0x4000` / `0x2000`) with **0x06**. Matches Waveshare's
  [Protocol Manual](https://www.waveshare.com/wiki/Protocol_Manual_of_Modbus_RTU_Relay).
- All transactions are serialized behind one lock (RS485 is half-duplex), and the pymodbus
  slave-id keyword is resolved at runtime so it works across pymodbus 3.x versions.

## Releasing

See [`RELEASING.md`](RELEASING.md). In short: create a `v*` GitHub Release and the
`release` workflow stamps the version, zips the component, and attaches
`waveshare_relay.zip` (the asset HACS installs).
