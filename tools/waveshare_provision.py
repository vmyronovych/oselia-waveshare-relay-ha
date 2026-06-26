#!/usr/bin/env python3
"""Bench provisioning + test tool for Waveshare Modbus RTU relay boards.

Use this on a USB/RS485 adapter with **one board wired at a time**, before the board
goes on the DIN rail / shared bus. It can discover a board, set its Modbus address and
baud rate, and exercise the relays (on/off/toggle/pulse/status).

Standalone: needs only `pyserial` (`pip install pyserial`), not Home Assistant.

Protocol: Waveshare "Protocol Manual of Modbus RTU Relay"
https://www.waveshare.com/wiki/Protocol_Manual_of_Modbus_RTU_Relay

  Read relays   : 0x01 read coils from 0x0000
  Set relay     : 0x05 write coil  <ch>   -> 0xFF00 on / 0x0000 off / 0x5500 toggle
  Set all       : 0x05 write coil  0x00FF -> 0xFFFF on / 0x0000 off / 0x5A00 toggle
  Flash (timed) : 0x05 write coil  (mode<<8 | ch) -> value = delay/100ms
  Set address   : 0x06 write reg   0x4000 (1..255)
  Set baud      : 0x06 write reg   0x2000 (code, see BAUD_RATES)
  Read sw ver   : 0x03 read reg    0x2000 (raw/100 -> vX.YZ)
  Read address  : 0x03 read reg    0x4000 (send to address 0 = broadcast, one board)

Examples:
  ./waveshare_provision.py ports
  ./waveshare_provision.py -p /dev/ttyUSB0 discover
  ./waveshare_provision.py -p /dev/ttyUSB0 info
  ./waveshare_provision.py -p /dev/ttyUSB0 -a 1 set-address 5
  ./waveshare_provision.py -p /dev/ttyUSB0 -a 5 status
  ./waveshare_provision.py -p /dev/ttyUSB0 -a 5 on 3
  ./waveshare_provision.py -p /dev/ttyUSB0 -a 5 pulse 3 --ms 800
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    sys.exit("This tool needs pyserial. Install it with:  pip install pyserial")

# --- protocol constants ---
COIL_ALL = 0x00FF
REG_BAUD = 0x2000
REG_ADDRESS = 0x4000
VAL_ON = 0xFF00
VAL_OFF = 0x0000
VAL_TOGGLE = 0x5500
VAL_ALL_ON = 0xFFFF
VAL_ALL_OFF = 0x0000
VAL_ALL_TOGGLE = 0x5A00
FLASH_MODE = {"on": 0x04, "off": 0x02}  # open-with-delay / close-with-delay

BAUD_RATES = {
    0: 4800, 1: 9600, 2: 19200, 3: 38400,
    4: 57600, 5: 115200, 6: 128000, 7: 256000,
}
BAUD_CODES = {bps: code for code, bps in BAUD_RATES.items()}


class ModbusError(Exception):
    pass


def crc16(data: bytes) -> bytes:
    """Modbus RTU CRC-16, returned low byte first (wire order)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _frame(address: int, func: int, payload: bytes) -> bytes:
    body = bytes([address, func]) + payload
    return body + crc16(body)


class Board:
    """A serial connection to one relay board (or the broadcast address)."""

    def __init__(self, port: str, baud: int, timeout: float) -> None:
        self._ser = serial.Serial(
            port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
            timeout=timeout,
        )

    def close(self) -> None:
        self._ser.close()

    def _txn(self, address: int, func: int, payload: bytes, resp_len: int) -> bytes:
        """Send one request, return the response payload bytes (after addr+func,
        before CRC). `resp_len` is the full expected frame length."""
        self._ser.reset_input_buffer()
        self._ser.write(_frame(address, func, payload))
        # Read the expected frame; allow a 5-byte exception frame to short-circuit.
        raw = self._ser.read(resp_len)
        if len(raw) < 5:
            raise ModbusError(
                f"no/short reply ({len(raw)} bytes) -- wrong address, baud, port, "
                f"or wiring?"
            )
        if raw[1] == (func | 0x80):
            raise ModbusError(f"device exception code {raw[2]:#04x}")
        if crc16(raw[:-2]) != raw[-2:]:
            raise ModbusError("bad CRC in reply")
        return raw

    # ---- reads ----
    def read_coils(self, count: int, address: int) -> list[bool]:
        nbytes = (count + 7) // 8
        raw = self._txn(address, 0x01, b"\x00\x00" + count.to_bytes(2, "big"),
                        5 + nbytes)
        data = raw[3:3 + raw[2]]
        bits = [bool((data[i // 8] >> (i % 8)) & 1) for i in range(count)]
        return bits

    def read_register(self, reg: int, address: int) -> int:
        raw = self._txn(address, 0x03, reg.to_bytes(2, "big") + b"\x00\x01", 7)
        return int.from_bytes(raw[3:5], "big")

    def read_address_broadcast(self) -> int:
        """Read a lone board's address (send on broadcast 0; reply carries the addr)."""
        raw = self._txn(0x00, 0x03, REG_ADDRESS.to_bytes(2, "big") + b"\x00\x01", 7)
        return raw[0]

    # ---- writes ----
    def write_coil(self, coil: int, value: int, address: int) -> None:
        self._txn(address, 0x05, coil.to_bytes(2, "big") + value.to_bytes(2, "big"), 8)

    def write_register(self, reg: int, value: int, address: int) -> None:
        self._txn(address, 0x06, reg.to_bytes(2, "big") + value.to_bytes(2, "big"), 8)


# --- command handlers ---------------------------------------------------
def cmd_ports(_args) -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return 1
    for p in ports:
        print(f"  {p.device:20} {p.description}")
    return 0


def cmd_discover(args) -> int:
    board = _open(args)
    try:
        addr = board.read_address_broadcast()
    finally:
        board.close()
    print(f"Found 1 board at address {addr} (baud {args.baud}).")
    print(f"  -> next: {sys.argv[0]} -p {args.port} -a {addr} info")
    return 0


def cmd_info(args) -> int:
    board = _open(args)
    try:
        addr = board.read_register(REG_ADDRESS, args.address)
        ver = board.read_register(REG_BAUD, args.address)
    finally:
        board.close()
    print(f"Address      : {addr}")
    print(f"SW version   : v{ver / 100:.2f}")
    return 0


def cmd_scan(args) -> int:
    found = []
    board = _open(args)
    try:
        for addr in range(args.start, args.end + 1):
            try:
                board.read_register(REG_BAUD, addr)
                found.append(addr)
                print(f"  address {addr}: responding")
            except ModbusError:
                pass
    finally:
        board.close()
    if not found:
        print("No boards responded. Check baud/wiring, or use 'discover' for a lone "
              "board.")
        return 1
    print(f"\nFound {len(found)} board(s): {found}")
    return 0


def cmd_status(args) -> int:
    board = _open(args)
    try:
        bits = board.read_coils(args.channels, args.address)
    finally:
        board.close()
    print(f"Board {args.address} ({args.channels}-ch):")
    for i, on in enumerate(bits, start=1):
        print(f"  Relay {i:2}: {'ON ' if on else 'off'}")
    print(f"  ({sum(bits)} on / {len(bits)})")
    return 0


def _control(args, value: int) -> int:
    board = _open(args)
    try:
        board.write_coil(args.channel - 1, value, args.address)
    finally:
        board.close()
    return 0


def cmd_on(args) -> int:
    _control(args, VAL_ON)
    print(f"Relay {args.channel} ON")
    return 0


def cmd_off(args) -> int:
    _control(args, VAL_OFF)
    print(f"Relay {args.channel} off")
    return 0


def cmd_toggle(args) -> int:
    _control(args, VAL_TOGGLE)
    print(f"Relay {args.channel} toggled")
    return 0


def cmd_all_on(args) -> int:
    board = _open(args)
    try:
        board.write_coil(COIL_ALL, VAL_ALL_ON, args.address)
    finally:
        board.close()
    print("All relays ON")
    return 0


def cmd_all_off(args) -> int:
    board = _open(args)
    try:
        board.write_coil(COIL_ALL, VAL_ALL_OFF, args.address)
    finally:
        board.close()
    print("All relays off")
    return 0


def cmd_pulse(args) -> int:
    """Software-timed pulse: on, wait, off (reliable, host-timed)."""
    board = _open(args)
    try:
        board.write_coil(args.channel - 1, VAL_ON, args.address)
        time.sleep(args.ms / 1000)
        board.write_coil(args.channel - 1, VAL_OFF, args.address)
    finally:
        board.close()
    print(f"Relay {args.channel} pulsed for {args.ms} ms")
    return 0


def cmd_flash(args) -> int:
    """Hardware-timed flash (board auto-reverts). EXPERIMENTAL: mode mapping may vary
    by firmware revision -- verify against your board."""
    coil = (FLASH_MODE[args.mode] << 8) | (args.channel - 1)
    board = _open(args)
    try:
        board.write_coil(coil, args.ms // 100, args.address)
    finally:
        board.close()
    print(f"Relay {args.channel} hardware-flash ({args.mode}) ~{args.ms} ms")
    return 0


def cmd_set_address(args) -> int:
    current = args.from_addr if args.from_addr is not None else args.address
    board = _open(args)
    try:
        board.write_register(REG_ADDRESS, args.new_address, current)
        time.sleep(0.1)
        check = board.read_register(REG_ADDRESS, args.new_address)
    finally:
        board.close()
    if check != args.new_address:
        print(f"WARNING: read back address {check}, expected {args.new_address}")
        return 1
    print(f"Address set: {current} -> {args.new_address} (verified)")
    return 0


def cmd_set_baud(args) -> int:
    code = BAUD_CODES[args.rate]
    board = _open(args)
    try:
        board.write_register(REG_BAUD, code, args.address)
    finally:
        board.close()
    print(f"Baud set to {args.rate}. Reconnect with -b {args.rate} for further commands.")
    return 0


# --- helpers ------------------------------------------------------------
def _open(args) -> Board:
    if not args.port:
        sys.exit("No --port given. List options with:  waveshare_provision.py ports")
    try:
        return Board(args.port, args.baud, args.timeout)
    except serial.SerialException as err:
        sys.exit(f"Could not open {args.port}: {err}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bench provisioning + test tool for Waveshare Modbus RTU relays.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Wire ONE board at a time when setting addresses.",
    )
    p.add_argument("-p", "--port", help="serial port (see 'ports')")
    p.add_argument("-b", "--baud", type=int, default=9600, help="baud (default 9600)")
    p.add_argument("-a", "--address", type=int, default=1,
                   help="Modbus address to talk to (default 1)")
    p.add_argument("-t", "--timeout", type=float, default=0.5,
                   help="reply timeout seconds (default 0.5)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("ports", help="list serial ports").set_defaults(func=cmd_ports)
    sub.add_parser("discover",
                   help="read a lone board's address (broadcast)").set_defaults(
        func=cmd_discover)
    sub.add_parser("info", help="read address + sw version").set_defaults(func=cmd_info)

    sp = sub.add_parser("scan", help="sweep addresses and list responders")
    sp.add_argument("--start", type=int, default=1)
    sp.add_argument("--end", type=int, default=32)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("status", help="read all relay states")
    sp.add_argument("--channels", type=int, default=8)
    sp.set_defaults(func=cmd_status)

    for name, fn, helptext in (
        ("on", cmd_on, "turn relay N on"),
        ("off", cmd_off, "turn relay N off"),
        ("toggle", cmd_toggle, "toggle relay N"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("channel", type=int, help="relay number (1-based)")
        sp.set_defaults(func=fn)

    sub.add_parser("all-on", help="turn all relays on").set_defaults(func=cmd_all_on)
    sub.add_parser("all-off", help="turn all relays off").set_defaults(func=cmd_all_off)

    sp = sub.add_parser("pulse", help="software-timed pulse of relay N")
    sp.add_argument("channel", type=int, help="relay number (1-based)")
    sp.add_argument("--ms", type=int, default=500, help="pulse length ms (default 500)")
    sp.set_defaults(func=cmd_pulse)

    sp = sub.add_parser("flash", help="hardware-timed flash of relay N (experimental)")
    sp.add_argument("channel", type=int, help="relay number (1-based)")
    sp.add_argument("--ms", type=int, default=700, help="delay ms (100ms steps)")
    sp.add_argument("--mode", choices=("on", "off"), default="on")
    sp.set_defaults(func=cmd_flash)

    sp = sub.add_parser("set-address", help="set the board's Modbus address")
    sp.add_argument("new_address", type=int, help="new address (1-255)")
    sp.add_argument("--from", dest="from_addr", type=int,
                    help="current address (defaults to -a)")
    sp.set_defaults(func=cmd_set_address)

    sp = sub.add_parser("set-baud", help="set the board's baud rate")
    sp.add_argument("rate", type=int, choices=sorted(BAUD_CODES),
                    help="new baud rate")
    sp.set_defaults(func=cmd_set_baud)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "set-address" and not (1 <= args.new_address <= 255):
        sys.exit("address must be 1..255")
    if args.command in ("on", "off", "toggle", "pulse", "flash") and args.channel < 1:
        sys.exit("relay number is 1-based (>= 1)")
    try:
        return args.func(args)
    except ModbusError as err:
        sys.exit(f"Modbus error: {err}")


if __name__ == "__main__":
    raise SystemExit(main())
