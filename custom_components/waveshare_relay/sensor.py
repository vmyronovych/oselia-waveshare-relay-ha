"""Diagnostic sensors per board: Modbus address and a live count of relays that are on."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
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
        lambda coord: [RelayAddressSensor(coord), ActiveRelaysSensor(coord)],
    )


class RelayAddressSensor(WaveshareEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Modbus address"
    _attr_icon = "mdi:identifier"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: RelayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_uid}_address"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.address


class ActiveRelaysSensor(WaveshareEntity, SensorEntity):
    _attr_name = "Active relays"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RelayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_uid}_active_relays"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return sum(1 for on in data if on)
