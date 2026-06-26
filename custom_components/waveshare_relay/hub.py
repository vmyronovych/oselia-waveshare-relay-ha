"""WaveshareHub -- owns the single pymodbus connection for one RS485 bus.

Two transports are supported:

  * **Serial** -- a USB/RS485 adapter on the HA host (one serial port, opened once).
  * **TCP** -- the bus reached over the network, for when HA can't see the USB port
    (e.g. Docker Desktop on macOS, which can't pass USB through). Point it at a
    `socat`/`ser2net` bridge on the machine that has the adapter, or at a hardware
    RS485-to-Ethernet gateway. Most of those are "transparent" (raw RTU frames over
    TCP) -> FRAMER_RTU; a true Modbus-TCP gateway uses MBAP -> FRAMER_SOCKET.

Either way a serial port / socket can only host one in-flight request at a time
(RS485 is half-duplex), so every transaction funnels through one `asyncio.Lock`, and
each Modbus address on the bus becomes its own Home Assistant device.

The pymodbus call signature for the slave argument churned across 3.x
(`slave=` -> `device_id=`); `_UNIT_KW` is resolved once from the live signature.
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    COIL_ALL,
    COIL_FIRST,
    CONF_BAUDRATE,
    CONF_FRAMER,
    CONF_HOST,
    CONF_PORT,
    CONF_TCP_PORT,
    CONF_TYPE,
    DEFAULT_BAUDRATE,
    DEFAULT_FRAMER,
    DEFAULT_TCP_PORT,
    FRAMER_RTU,
    REG_ADDRESS,
    REG_BAUD,
    SIGNAL_CONNECTION,
    TYPE_SERIAL,
    TYPE_TCP,
)

_LOGGER = logging.getLogger(__name__)


def _resolve_unit_kw() -> str:
    """Return the keyword pymodbus uses for the slave id ('slave' or 'device_id')."""
    try:
        params = inspect.signature(AsyncModbusSerialClient.read_coils).parameters
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return "slave"
    if "slave" in params:
        return "slave"
    if "device_id" in params:
        return "device_id"
    return "slave"


_UNIT_KW = _resolve_unit_kw()


def _resolve_framer(name: str):
    """Map our framer name to whatever this pymodbus version expects (or None)."""
    try:
        from pymodbus import FramerType  # pymodbus >= 3.7
    except ImportError:
        FramerType = None
    if FramerType is not None:
        return FramerType.RTU if name == FRAMER_RTU else FramerType.SOCKET
    if name == FRAMER_RTU:  # older pymodbus: pass the RTU framer class
        try:
            from pymodbus.framer.rtu_framer import ModbusRtuFramer

            return ModbusRtuFramer
        except ImportError:  # pragma: no cover - very old/new layout
            return None
    return None  # socket is the default TCP framer


def build_client(cfg: dict, timeout: float = 2):
    """Build the right pymodbus async client for a transport config dict."""
    if cfg.get(CONF_TYPE, TYPE_SERIAL) == TYPE_TCP:
        kwargs = {
            "host": cfg[CONF_HOST],
            "port": cfg.get(CONF_TCP_PORT, DEFAULT_TCP_PORT),
            "timeout": timeout,
        }
        framer = _resolve_framer(cfg.get(CONF_FRAMER, DEFAULT_FRAMER))
        if framer is not None:
            kwargs["framer"] = framer
        return AsyncModbusTcpClient(**kwargs)
    return AsyncModbusSerialClient(
        port=cfg[CONF_PORT],
        baudrate=cfg.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
    )


def describe(cfg: dict) -> str:
    """Human-readable label for a transport config (for titles / logs / errors)."""
    if cfg.get(CONF_TYPE, TYPE_SERIAL) == TYPE_TCP:
        return f"{cfg[CONF_HOST]}:{cfg.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)}"
    return cfg.get(CONF_PORT, "?")


def unique_id_for(cfg: dict) -> str:
    """Stable config-entry unique id for a transport (one entry per bus)."""
    return describe(cfg)


class ModbusError(Exception):
    """A Modbus transaction failed (no/garbled reply, or an exception response)."""


class WaveshareHub:
    """One bus; serializes all Modbus IO and tracks link state."""

    def __init__(self, hass: HomeAssistant, entry_id: str, cfg: dict) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.label = describe(cfg)
        self.connected = False
        self._lock = asyncio.Lock()
        self._client = build_client(cfg)

    # ---- lifecycle -------------------------------------------------------
    async def async_connect(self) -> None:
        """Open the link. Never raises: pymodbus retries in the background, and the
        per-device coordinators report 'unavailable' until the link comes up."""
        async with self._lock:
            await self._async_ensure_connected()

    async def async_close(self) -> None:
        async with self._lock:
            self._client.close()
            self.connected = False

    async def _async_ensure_connected(self) -> bool:
        """(lock held) Make sure the link is open; flip + broadcast link state."""
        if self._client.connected:
            self._set_connected(True)
            return True
        try:
            ok = await self._client.connect()
        except Exception as err:  # pragma: no cover - defensive (driver/OS errors)
            _LOGGER.debug("Waveshare connect to %s failed: %s", self.label, err)
            ok = False
        self._set_connected(bool(ok))
        return bool(ok)

    @callback
    def _set_connected(self, state: bool) -> None:
        if state == self.connected:
            return
        self.connected = state
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION.format(self.entry_id))

    # ---- relay IO --------------------------------------------------------
    async def async_read_relays(self, address: int, channels: int) -> list[bool]:
        """Read coil states for one board -> list of `channels` booleans."""
        rr = await self._execute(
            self._client.read_coils, COIL_FIRST, count=channels, address_unit=address
        )
        bits = list(rr.bits)[:channels]
        bits += [False] * (channels - len(bits))
        return bits

    async def async_write_relay(self, address: int, channel: int, on: bool) -> None:
        """Set one relay (function 0x05 -> 0xFF00 / 0x0000)."""
        await self._execute(
            self._client.write_coil, channel, on, address_unit=address
        )

    async def async_write_all(self, address: int, on: bool) -> None:
        """Set every relay on the board at once (coil 0x00FF)."""
        await self._execute(
            self._client.write_coil, COIL_ALL, on, address_unit=address
        )

    async def async_set_address(self, address: int, new_address: int) -> None:
        """Write the device-address register (0x4000)."""
        await self._execute(
            self._client.write_register, REG_ADDRESS, new_address, address_unit=address
        )

    async def async_set_baud_code(self, address: int, code: int) -> None:
        """Write the baud-rate register (0x2000) with a BAUD_RATES code."""
        await self._execute(
            self._client.write_register, REG_BAUD, code, address_unit=address
        )

    async def async_read_version(self, address: int) -> str | None:
        """Read software version from 0x2000 (raw / 100 -> 'vX.YZ')."""
        try:
            rr = await self._execute(
                self._client.read_holding_registers,
                REG_BAUD,
                count=1,
                address_unit=address,
            )
        except ModbusError:
            return None
        raw = rr.registers[0]
        return f"v{raw / 100:.2f}"

    async def async_read_address(self, address: int = 0) -> int | None:
        """Read the device-address register (0x4000). Use address=0 (broadcast) only
        when exactly ONE board is on the bus."""
        try:
            rr = await self._execute(
                self._client.read_holding_registers,
                REG_ADDRESS,
                count=1,
                address_unit=address,
            )
        except ModbusError:
            return None
        return rr.registers[0]

    # ---- transaction core ------------------------------------------------
    async def _execute(self, fn, *args, address_unit: int, **kwargs):
        """Run one Modbus transaction under the bus lock with the right unit kwarg."""
        kwargs[_UNIT_KW] = address_unit
        async with self._lock:
            if not await self._async_ensure_connected():
                raise ModbusError(f"bus {self.label} not connected")
            try:
                result = await fn(*args, **kwargs)
            except Exception as err:  # pymodbus raises ModbusException/ConnectionException
                self._set_connected(False)
                raise ModbusError(str(err)) from err
            if result is None or result.isError():
                raise ModbusError(f"modbus error response: {result!r}")
            self._set_connected(True)
            return result
