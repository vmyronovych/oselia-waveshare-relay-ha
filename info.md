# Waveshare Modbus RTU Relay

Local Home Assistant integration for **Waveshare Modbus RTU relay boards** (4/8/16/32-ch,
built for the **(B)** 8-channel) on a USB/RS485 adapter.

- **Config flow** — **Serial** (USB/RS485 on the HA host) or **Network/TCP** (for HA in
  Docker that can't see USB); add boards by Modbus address.
- **One switch per relay** — see state, turn on/off, rename freely; renames stick.
- **All on / all off** buttons, an **active-relays** sensor, and a **connectivity** sensor.
- **`pulse` service** — momentary press for gates / door strikes / garage doors.
- **Commission from HA** — set a board's **Modbus address** and **baud rate** over the bus,
  no SSCOM / Modbus Poll needed.
- **OSELIA blueprint** — map any OSELIA Hearth button gesture to any relay action.
- **Bundled tools** — a bench provisioner and a Modbus-TCP gateway (for HA in Docker).

State is polled from the hardware, so switches stay truthful even if relays are flipped
elsewhere on the bus. After install, restart HA and add it via **Settings → Devices &
Services → Add integration → Waveshare Modbus RTU Relay**.

Deploying at a new site? See **ROLLOUT.md** for a start-to-finish checklist.
