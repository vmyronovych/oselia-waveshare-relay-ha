"""One switch entity per relay channel -- the core of the integration.

Default names are "Relay 1".."Relay N"; rename any of them in the UI (the friendly
name is stored by Home Assistant against the stable unique_id, so renames survive
restarts and reconnects). State is read back from the hardware on every poll, so the
switch reflects relays toggled by anything else on the bus too.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant

from . import WaveshareConfigEntry
from .coordinator import RelayCoordinator
from .entity import WaveshareEntity, setup_board_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaveshareConfigEntry,
    async_add_entities,
) -> None:
    setup_board_entities(
        entry,
        async_add_entities,
        lambda coord: [
            RelaySwitch(coord, channel) for channel in range(coord.channels)
        ],
    )


class RelaySwitch(WaveshareEntity, SwitchEntity):
    """A single relay coil."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: RelayCoordinator, channel: int) -> None:
        super().__init__(coordinator)
        self._channel = channel
        self._attr_unique_id = f"{self._device_uid}_relay_{channel}"
        self._attr_name = f"Relay {channel + 1}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None or self._channel >= len(data):
            return None
        return data[self._channel]

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_relay(self._channel, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_relay(self._channel, False)
