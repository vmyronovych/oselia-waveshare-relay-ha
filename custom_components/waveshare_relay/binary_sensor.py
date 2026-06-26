"""Per-board connectivity sensor -- is the board answering on the bus?

Always available (it *is* the availability indicator), so it can drive automations
that alert when a board stops responding.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
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
        lambda coord: [RelayConnectivity(coord)],
    )


class RelayConnectivity(WaveshareEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Connection"

    def __init__(self, coordinator: RelayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_uid}_connection"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
