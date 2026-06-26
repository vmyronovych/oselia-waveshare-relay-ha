"""One DataUpdateCoordinator per relay board (per Modbus address on the bus).

`data` is the list of relay states (booleans, index 0 == relay 1). Writes update the
cache optimistically and request an immediate refresh so the UI is snappy but stays
truthful to the hardware (relays can also be flipped by something else on the bus).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .hub import ModbusError, WaveshareHub

_LOGGER = logging.getLogger(__name__)


class RelayCoordinator(DataUpdateCoordinator[list[bool]]):
    """Polls one board's coil states and serves them to its entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: WaveshareHub,
        address: int,
        name: str,
        channels: int,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.hub = hub
        self.address = address
        self.device_name = name
        self.channels = channels
        self.sw_version: str | None = None

    async def _async_update_data(self) -> list[bool]:
        try:
            return await self.hub.async_read_relays(self.address, self.channels)
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set_relay(self, channel: int, on: bool) -> None:
        await self.hub.async_write_relay(self.address, channel, on)
        self._optimistic(channel, on)

    async def async_set_all(self, on: bool) -> None:
        await self.hub.async_write_all(self.address, on)
        if self.data is not None:
            self.async_set_updated_data([on] * self.channels)
        await self.async_request_refresh()

    def _optimistic(self, channel: int, on: bool) -> None:
        if self.data is not None and 0 <= channel < len(self.data):
            new = list(self.data)
            new[channel] = on
            self.async_set_updated_data(new)
        self.hass.async_create_task(self.async_request_refresh())
