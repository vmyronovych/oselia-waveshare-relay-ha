# Tools

Two standalone helpers (only need `pyserial`):

- **`waveshare_provision.py`** — bench CLI to preconfigure/test a board (below).
- **`modbus_gateway.py`** — a Modbus-TCP→RTU gateway so Home Assistant in Docker can
  reach the bus over the network (see *Modbus-TCP gateway* at the bottom).

> Only one process can own the serial port at a time. **Stop the gateway before using the
> bench tool**, and vice-versa.

# Bench provisioning tool

`waveshare_provision.py` — a standalone CLI to **preconfigure and test a Waveshare
Modbus RTU relay board before it goes on the DIN rail / shared RS485 bus**.

Out of the box every board ships as **address 1, 9600 baud**, so two boards on one bus
collide. The workflow is: wire **one** board to a USB/RS485 adapter on the bench, give it
a unique address, smoke-test the relays, then install it. Repeat per board.

Needs only `pyserial` (no Home Assistant):

```sh
pip install -r tools/requirements.txt   # or: pip install pyserial
chmod +x tools/waveshare_provision.py
```

## Typical session

```sh
# 1. Find your adapter
./tools/waveshare_provision.py ports

# 2. Confirm the (single) board and its current address
./tools/waveshare_provision.py -p /dev/ttyUSB0 discover
./tools/waveshare_provision.py -p /dev/ttyUSB0 info

# 3. Give it a unique address (writes + reads back to verify)
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 1 set-address 5

# 4. Smoke-test on the new address
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 status
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 on 3
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 off 3
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 pulse 3 --ms 800
./tools/waveshare_provision.py -p /dev/ttyUSB0 -a 5 all-off
```

Label the board with its address, then install it. After all boards are on the bus, add
them in Home Assistant (one device per address) via the integration.

## Commands

| Command | What it does |
| --- | --- |
| `ports` | List serial ports. |
| `discover` | Read a **lone** board's address via broadcast (only one board on the bus). |
| `info` | Read the address + software version at `-a`. |
| `scan [--start 1 --end 32]` | Sweep addresses and list responders (multiple boards OK). |
| `status [--channels 8]` | Read and print every relay state. |
| `on N` / `off N` / `toggle N` | Control relay *N* (1-based). |
| `all-on` / `all-off` | Flip every relay in one frame. |
| `pulse N [--ms 500]` | Host-timed momentary press (on→wait→off). Reliable. |
| `flash N [--ms 700] [--mode on\|off]` | Board-timed flash (auto-reverts). **Experimental** — verify the mode mapping on your firmware. |
| `set-address NEW [--from CUR]` | Set the Modbus address; reads back to confirm. |
| `set-baud RATE` | Set baud rate (4800…256000). Reconnect with `-b RATE` afterwards. |

Global options: `-p/--port`, `-b/--baud` (default 9600), `-a/--address` (default 1),
`-t/--timeout` (default 0.5 s).

## Notes

- **One board at a time** when setting addresses — `set-address` and `discover` rely on a
  single device answering. `set-address` verifies the change via the **broadcast**
  address-read, so it works even on firmware that won't answer the address register at its
  own unit id.
- Relay numbers are **1-based** on the CLI (Relay 1 = coil 0 on the wire).
- Some firmware revisions don't answer the **version register** (`0x2000`); `info` then
  shows `SW version: unknown` — harmless.
- The protocol is documented in
  [Waveshare's Protocol Manual](https://www.waveshare.com/wiki/Protocol_Manual_of_Modbus_RTU_Relay);
  this tool builds the Modbus RTU frames directly (CRC included) so it can use the
  broadcast address-read and timed-flash commands the HA integration doesn't.

# Modbus-TCP gateway

`modbus_gateway.py` — run it on the machine with the USB/RS485 adapter to expose the bus
as **Modbus TCP** for Home Assistant in Docker (which can't see the USB port):

```sh
python3 modbus_gateway.py --port /dev/cu.usbserial-AQ025HGO --baud 9600 --listen 5020
#   Linux: --port /dev/ttyUSB0  (or a stable /dev/serial/by-id/... path)
```

Then add the HA integration as **Network (TCP)** → host = `host.docker.internal` (or the
host's LAN IP), port `5020`, framing **"Modbus TCP"**.

It speaks length-delimited MBAP on the network side and does proper RTU framing on the
serial side, so it doesn't suffer the frame-fragmentation a transparent `socat` pipe does.
See the main README's *Home Assistant in Docker* section for launchd/systemd unit files to
keep it running across reboots.
