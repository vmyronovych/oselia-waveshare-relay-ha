# Waveshare Modbus RTU Relay

Local Home Assistant integration for **Waveshare Modbus RTU relay boards** (4/8/16/32-ch,
built for the **(B)** 8-channel) on a USB/RS485 adapter.

- **Config flow** — **Serial** (USB/RS485 on the HA host, incl. HA-in-Docker on a Pi with
  the device passed in) or **Network/TCP** (for when HA can't see the port); add boards by
  Modbus address.
- **One switch per relay** — see state, turn on/off, rename freely; renames stick.
- **Roller-shutter covers** — pair two relays (up + down) into one native `cover` with a
  software interlock, break-before-make on reversal, a max-run safety cutoff, and timed
  position (open / close / stop, plus a position slider once calibrated).
- **All on / all off** buttons, an **active-relays** sensor, and a **connectivity** sensor.
- **`pulse` service** — momentary press for gates / door strikes / garage doors.
- **Commission from HA** — set a board's **Modbus address** and **baud rate** over the bus,
  no SSCOM / Modbus Poll needed.
- **OSELIA blueprints** — map any OSELIA Hearth button gesture to a relay action *or* to a
  roller shutter (tap = light, hold = shutter; press-while-moving = stop).
- **Bundled tools** — a bench provisioner and a Modbus-TCP gateway (for when HA can't see
  the USB port, e.g. Docker Desktop on macOS).

State is polled from the hardware, so switches stay truthful even if relays are flipped
elsewhere on the bus. After install, restart HA and add it via **Settings → Devices &
Services → Add integration → Waveshare Modbus RTU Relay**.

Deploying at a new site? See **ROLLOUT.md** for a start-to-finish checklist.
