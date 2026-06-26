"""Per-board convenience buttons: All on / All off.

Both use the hardware's single-frame "all relays" coil (0x00FF) rather than looping,
so every relay flips in one transaction.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
            AllRelaysButton(coord, on=True),
            AllRelaysButton(coord, on=False),
        ],
    )


class AllRelaysButton(WaveshareEntity, ButtonEntity):
    def __init__(self, coordinator: RelayCoordinator, on: bool) -> None:
        super().__init__(coordinator)
        self._on = on
        suffix = "all_on" if on else "all_off"
        self._attr_unique_id = f"{self._device_uid}_{suffix}"
        self._attr_name = "All on" if on else "All off"
        self._attr_icon = "mdi:flash" if on else "mdi:flash-off"

    async def async_press(self) -> None:
        await self.coordinator.async_set_all(self._on)
