"""Shared base for Waveshare entities: device_info bound to one relay board."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WaveshareConfigEntry
from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import RelayCoordinator


@callback
def setup_board_entities(
    entry: WaveshareConfigEntry,
    async_add_entities,
    factory: Callable[[RelayCoordinator], Iterable[Entity]],
) -> None:
    """Add a platform's entities for every relay board on the bus.

    `factory(coordinator)` returns this platform's entities for one board.
    """
    entities: list[Entity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        entities.extend(factory(coordinator))
    async_add_entities(entities)


class WaveshareEntity(CoordinatorEntity[RelayCoordinator]):
    """Base entity tied to one relay board (one Modbus address)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RelayCoordinator) -> None:
        super().__init__(coordinator)
        hub = coordinator.hub
        self._device_uid = f"{hub.entry_id}_{coordinator.address}"

    @property
    def device_info(self):
        coordinator = self.coordinator
        return {
            "identifiers": {(DOMAIN, self._device_uid)},
            "name": coordinator.device_name,
            "manufacturer": MANUFACTURER,
            "model": f"{DEFAULT_MODEL} ({coordinator.channels}-ch)",
            "sw_version": coordinator.sw_version,
            "serial_number": f"addr {coordinator.address}",
        }
