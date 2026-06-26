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

## Install

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**.
2. Repository: `https://github.com/vmyronovych/oselia-waveshare-relay-ha`, category **Integration**.
3. Install **Waveshare Modbus RTU Relay**, then restart Home Assistant.
4. **Settings → Devices & Services → Add integration → Waveshare Modbus RTU Relay**.

### Manual

Copy `custom_components/waveshare_relay/` into your HA `config/custom_components/`,
restart HA, and add the integration as above.

## Setup

1. **Pick the serial port** of your USB/RS485 adapter (auto-detected in a dropdown) and the
   **bus baud rate** (factory default **9600**). The port is opened to verify it works.
2. **Add the first board** — its **Modbus address** (factory default **1**), a **name**, and
   the **channel count** (4/8/16/32). The board is pinged before it's added.
3. Add more boards on the same bus any time via the integration's **Configure → Add a relay
   board** (each needs a unique address).

> **One config entry = one serial port.** A serial port can only be opened once, so every
> board on that RS485 bus lives under the same entry, each as its own HA device.

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
| `waveshare_relay.all_on` / `all_off` | All relays on/off (device target) for automations. |
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

Import the bundled blueprint
[`blueprints/automation/waveshare_relay/oselia_button_to_relay.yaml`](blueprints/automation/waveshare_relay/oselia_button_to_relay.yaml)
(HA → Settings → Automations → Blueprints → Import, paste the raw URL). Each automation
maps **one OSELIA input + gesture → one relay action** (toggle / on / off / pulse). Add as
many as you like — e.g. *“kitchen switch, double-press → pulse the gate relay.”*

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

- Talks **Modbus RTU** over the serial port via `pymodbus` (async). `local_polling`.
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
