#!/usr/bin/env python3
"""Modbus TCP -> RTU gateway for a serial RS485 bus.

Bridges a USB/RS485 adapter to **Modbus TCP (MBAP)** so Home Assistant (or any
Modbus-TCP client) can reach the bus over the network. Use this when HA runs in Docker
and can't see the USB port (e.g. Docker Desktop on macOS).

Why not a plain `socat` pipe? socat is *transparent* -- it forwards raw RTU bytes over
TCP, and RTU has no length field (it relies on inter-byte timing gaps that TCP destroys).
The result is frame fragmentation that confuses RTU-over-TCP clients. This gateway speaks
**MBAP on the network side** (length-delimited, fragmentation-proof) and does proper,
length-aware **RTU framing on the serial side** -- the same approach as the bench tool,
which is 100% reliable against the real board.

Only needs pyserial. Run it on the machine with the adapter:

    ./modbus_gateway.py --port /dev/cu.usbserial-AQ025HGO --baud 9600 --listen 5020

Then add the HA integration as **Network (TCP)**, framing **"Modbus TCP"**, port 5020.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import struct
import sys

try:
    import serial
except ImportError:  # pragma: no cover
    sys.exit("This gateway needs pyserial:  pip install pyserial")

LOG = logging.getLogger("modbus_gateway")

# function code -> how the RTU response length is determined
_READ_FUNCS = (0x01, 0x02, 0x03, 0x04)          # reply: unit func bytecount data.. crc
_WRITE_FUNCS = (0x05, 0x06, 0x0F, 0x10)         # reply: unit func addr(2) val(2) crc -> 8


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class Gateway:
    def __init__(self, ser: "serial.Serial", read_retries: int = 2) -> None:
        self.ser = ser
        self.read_retries = read_retries
        self.lock = asyncio.Lock()

    # ---- serial (RTU) side, runs in an executor thread ----
    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf

    def _rtu_once(self, unit: int, pdu: bytes) -> bytes | None:
        frame = bytes([unit]) + pdu
        self.ser.reset_input_buffer()
        self.ser.write(frame + crc16(frame))
        hdr = self._read_exact(2)  # unit, func
        if len(hdr) < 2:
            return None
        func = hdr[1]
        if func & 0x80:                       # exception: + code + crc
            resp = hdr + self._read_exact(3)
        elif func in _READ_FUNCS:             # + bytecount + data + crc
            bc = self._read_exact(1)
            if not bc:
                return None
            resp = hdr + bc + self._read_exact(bc[0] + 2)
        elif func in _WRITE_FUNCS:            # + addr(2) + val(2) + crc
            resp = hdr + self._read_exact(6)
        else:                                  # unknown: best effort
            resp = hdr + self._read_exact(6)
        if len(resp) < 4 or crc16(resp[:-2]) != resp[-2:]:
            LOG.warning("bad/short RTU reply: %s", resp.hex(" "))
            return None
        return resp[1:-2]  # PDU only (func + data), without unit and CRC

    def _rtu_txn(self, unit: int, pdu: bytes) -> bytes | None:
        # Retry reads a couple times: the first frame right after the USB adapter is
        # opened can be dropped while the line settles. Writes are not retried.
        attempts = self.read_retries + 1 if pdu and pdu[0] in _READ_FUNCS else 1
        for _ in range(attempts):
            resp = self._rtu_once(unit, pdu)
            if resp is not None:
                return resp
        return None

    # ---- network (MBAP) side ----
    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        LOG.info("client %s connected", peer)
        loop = asyncio.get_event_loop()
        try:
            while True:
                header = await reader.readexactly(7)  # tid(2) pid(2) len(2) unit(1)
                length = struct.unpack(">H", header[4:6])[0]
                unit = header[6]
                pdu = await reader.readexactly(length - 1)
                async with self.lock:
                    resp_pdu = await loop.run_in_executor(None, self._rtu_txn, unit, pdu)
                if resp_pdu is None:
                    # No serial reply -> drop; the TCP client will time out and retry.
                    continue
                mbap = header[0:4] + struct.pack(">H", len(resp_pdu) + 1) + bytes([unit])
                writer.write(mbap + resp_pdu)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            LOG.info("client %s disconnected", peer)
            writer.close()


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="serial device, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--listen", type=int, default=5020, help="TCP port (default 5020)")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--timeout", type=float, default=0.5, help="serial read timeout s")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=args.timeout)
    except serial.SerialException as err:
        sys.exit(f"Could not open {args.port}: {err}")

    gw = Gateway(ser)
    server = await asyncio.start_server(gw.handle, args.bind, args.listen)
    LOG.info("Modbus TCP gateway on %s:%d  ->  %s @ %d baud",
             args.bind, args.listen, args.port, args.baud)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
