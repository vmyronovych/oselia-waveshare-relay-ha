"""Integration services: momentary pulse, all on/off, and on-bus address/baud setup.

The address/baud services let you commission a board entirely from Home Assistant --
no SSCOM or Modbus Poll needed. After a successful change the owning config entry is
rewritten and reloaded so the board keeps working on its new address/baud immediately.
"""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_referenced_entity_ids

from .const import (
    ATTR_BAUD_RATE,
    ATTR_DURATION,
    ATTR_INVERT,
    ATTR_NEW_ADDRESS,
    BAUD_CODES,
    CONF_ADDRESS,
    CONF_BAUDRATE,
    CONF_DEVICES,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
    MAX_ADDRESS,
    MIN_ADDRESS,
    SERVICE_ALL_OFF,
    SERVICE_ALL_ON,
    SERVICE_PULSE,
    SERVICE_SET_ADDRESS,
    SERVICE_SET_BAUD_RATE,
)
from .coordinator import RelayCoordinator
from .hub import ModbusError

_LOGGER = logging.getLogger(__name__)

PULSE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DURATION, default=DEFAULT_PULSE_DURATION): vol.All(
            vol.Coerce(float), vol.Range(min=0.05, max=3600)
        ),
        vol.Optional(ATTR_INVERT, default=False): cv.boolean,
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
    }
)

DEVICE_TARGET_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
    }
)

SET_ADDRESS_SCHEMA = DEVICE_TARGET_SCHEMA.extend(
    {
        vol.Required(ATTR_NEW_ADDRESS): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_ADDRESS, max=MAX_ADDRESS)
        ),
    }
)

SET_BAUD_SCHEMA = DEVICE_TARGET_SCHEMA.extend(
    {
        vol.Required(ATTR_BAUD_RATE): vol.All(vol.Coerce(int), vol.In(BAUD_CODES)),
    }
)


def _iter_coordinators(hass: HomeAssistant):
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = getattr(entry, "runtime_data", None)
        if data is None:
            continue
        for coord in data.coordinators.values():
            yield entry, coord


def _relay_for_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[RelayCoordinator, int] | None:
    """Map a switch entity_id back to its (coordinator, channel)."""
    ent = er.async_get(hass).async_get(entity_id)
    if ent is None or ent.platform != DOMAIN:
        return None
    for _entry, coord in _iter_coordinators(hass):
        for channel in range(coord.channels):
            uid = f"{coord.hub.entry_id}_{coord.address}_relay_{channel}"
            if uid == ent.unique_id:
                return coord, channel
    return None


def _coordinator_for_entity(hass: HomeAssistant, entity_id: str):
    """Map any of a board's entity ids back to its (entry, coordinator)."""
    ent = er.async_get(hass).async_get(entity_id)
    if ent is None or ent.platform != DOMAIN:
        return None
    for entry, coord in _iter_coordinators(hass):
        if ent.unique_id.startswith(f"{coord.hub.entry_id}_{coord.address}_"):
            return entry, coord
    return None


def _referenced_coordinators(hass: HomeAssistant, call: ServiceCall):
    """Resolve a service call's target into a deduplicated list of (entry, coord)."""
    selected = async_extract_referenced_entity_ids(hass, call)
    entity_ids = selected.referenced | selected.indirectly_referenced
    found: dict[int, tuple] = {}
    for eid in entity_ids:
        match = _coordinator_for_entity(hass, eid)
        if match is not None:
            found[id(match[1])] = match
    return list(found.values())


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services (idempotent across multiple entries)."""
    if hass.services.has_service(DOMAIN, SERVICE_PULSE):
        return

    async def _async_pulse(call: ServiceCall) -> None:
        duration: float = call.data[ATTR_DURATION]
        invert: bool = call.data[ATTR_INVERT]
        active, idle = (False, True) if invert else (True, False)

        selected = async_extract_referenced_entity_ids(hass, call)
        entity_ids = selected.referenced | selected.indirectly_referenced
        targets = [
            match
            for eid in entity_ids
            if (match := _relay_for_entity(hass, eid)) is not None
        ]
        if not targets:
            raise ServiceValidationError("No Waveshare relay switches in the target")

        async def _one(coord: RelayCoordinator, channel: int) -> None:
            await coord.async_set_relay(channel, active)
            await asyncio.sleep(duration)
            await coord.async_set_relay(channel, idle)

        await asyncio.gather(*(_one(coord, ch) for coord, ch in targets))

    async def _async_all(call: ServiceCall, on: bool) -> None:
        coords = [coord for _entry, coord in _referenced_coordinators(hass, call)]
        if not coords:
            raise ServiceValidationError("No Waveshare relay boards in the target")
        await asyncio.gather(*(coord.async_set_all(on) for coord in coords))

    async def _async_set_address(call: ServiceCall) -> None:
        new_address: int = call.data[ATTR_NEW_ADDRESS]
        pairs = _referenced_coordinators(hass, call)
        if len(pairs) != 1:
            raise ServiceValidationError(
                "Target exactly one relay board when changing its address"
            )
        entry, coord = pairs[0]
        old = coord.address
        try:
            await coord.hub.async_set_address(old, new_address)
        except ModbusError as err:
            raise HomeAssistantError(f"Failed to set address: {err}") from err
        _LOGGER.info("Waveshare relay address %s -> %s", old, new_address)
        _rewrite_device(hass, entry, old, {CONF_ADDRESS: new_address})

    async def _async_set_baud(call: ServiceCall) -> None:
        bps: int = call.data[ATTR_BAUD_RATE]
        pairs = _referenced_coordinators(hass, call)
        if len(pairs) != 1:
            raise ServiceValidationError(
                "Target exactly one relay board when changing the baud rate"
            )
        entry, coord = pairs[0]
        try:
            await coord.hub.async_set_baud_code(coord.address, BAUD_CODES[bps])
        except ModbusError as err:
            raise HomeAssistantError(f"Failed to set baud rate: {err}") from err
        _LOGGER.warning(
            "Waveshare relay baud -> %s; ALL boards on this bus must use the same baud",
            bps,
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_BAUDRATE: bps}
        )

    hass.services.async_register(DOMAIN, SERVICE_PULSE, _async_pulse, PULSE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_ALL_ON, lambda c: _async_all(c, True), DEVICE_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALL_OFF, lambda c: _async_all(c, False), DEVICE_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ADDRESS, _async_set_address, SET_ADDRESS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BAUD_RATE, _async_set_baud, SET_BAUD_SCHEMA
    )


def _rewrite_device(hass: HomeAssistant, entry, old_address: int, changes: dict) -> None:
    """Patch one board's config in the entry's device list and reload it."""
    devices = []
    for dev in entry.data.get(CONF_DEVICES, []):
        if dev[CONF_ADDRESS] == old_address:
            devices.append({**dev, **changes})
        else:
            devices.append(dev)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_DEVICES: devices}
    )


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_PULSE,
        SERVICE_ALL_ON,
        SERVICE_ALL_OFF,
        SERVICE_SET_ADDRESS,
        SERVICE_SET_BAUD_RATE,
    ):
        hass.services.async_remove(DOMAIN, service)
