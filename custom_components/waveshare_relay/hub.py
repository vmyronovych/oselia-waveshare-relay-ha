"""WaveshareHub -- owns the single pymodbus serial connection for one RS485 bus.

A USB-RS485 adapter exposes exactly one serial port, and a serial port can only be
opened once. So the integration models the *port* as the hub (one config entry) and
every Modbus address on that bus as a separate Home Assistant device. All transactions
funnel through one `asyncio.Lock` because RS485 is half-duplex -- only one request may
be in flight at a time.

The pymodbus call signature for the unit/slave argument churned across 3.x
(`slave=` -> `device_id=`); `_UNIT_KW` is resolved once from the live signature so this
works on whatever pymodbus Home Assistant ships.
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusSerialClient

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    COIL_ALL,
    COIL_FIRST,
    REG_ADDRESS,
    REG_BAUD,
    SIGNAL_CONNECTION,
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


class ModbusError(Exception):
    """A Modbus transaction failed (no/garbled reply, or an exception response)."""


class WaveshareHub:
    """One serial bus; serializes all Modbus IO and tracks link state."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, port: str, baudrate: int
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.port = port
        self.baudrate = baudrate
        self.connected = False
        self._lock = asyncio.Lock()
        self._client = AsyncModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=2,
        )

    # ---- lifecycle -------------------------------------------------------
    async def async_connect(self) -> None:
        """Open the port. Never raises: pymodbus retries in the background, and the
        per-device coordinators will report 'unavailable' until the link comes up."""
        async with self._lock:
            await self._async_ensure_connected()

    async def async_close(self) -> None:
        async with self._lock:
            self._client.close()
            self.connected = False

    async def _async_ensure_connected(self) -> bool:
        """(lock held) Make sure the port is open; flip + broadcast link state."""
        if self._client.connected:
            self._set_connected(True)
            return True
        try:
            ok = await self._client.connect()
        except Exception as err:  # pragma: no cover - defensive (driver/OS errors)
            _LOGGER.debug("Waveshare connect to %s failed: %s", self.port, err)
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
        # pad in case the driver returned fewer than requested (shouldn't happen)
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
                raise ModbusError(f"serial port {self.port} not connected")
            try:
                result = await fn(*args, **kwargs)
            except Exception as err:  # pymodbus raises ModbusException/ConnectionException
                self._set_connected(False)
                raise ModbusError(str(err)) from err
            if result is None or result.isError():
                raise ModbusError(f"modbus error response: {result!r}")
            self._set_connected(True)
            return result
