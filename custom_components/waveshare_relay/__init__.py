"""Waveshare Modbus RTU Relay integration -- setup/teardown.

One config entry == one RS485 serial bus (one USB adapter). Each Modbus address on
that bus becomes its own Home Assistant device, driven by its own coordinator. See
hub.py for why the port (not the board) is the unit of configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .blueprint import async_install_bundled_blueprints
from .const import (
    CONF_ADDRESS,
    CONF_CHANNELS,
    CONF_DEVICES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CHANNELS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import RelayCoordinator
from .hub import WaveshareHub
from .services import async_setup_services, async_unload_services


@dataclass
class WaveshareData:
    """Runtime data for one bus entry."""

    hub: WaveshareHub
    coordinators: dict[int, RelayCoordinator] = field(default_factory=dict)


type WaveshareConfigEntry = ConfigEntry[WaveshareData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Run once when the integration loads: install the bundled blueprint(s).

    Done here rather than in async_setup_entry so it happens once regardless of how many
    bus entries exist, and it never blocks setup -- a write failure only logs.
    """
    await async_install_bundled_blueprints(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WaveshareConfigEntry) -> bool:
    """Open the bus, build a coordinator per configured board, set up platforms."""
    hub = WaveshareHub(hass, entry_id=entry.entry_id, cfg=dict(entry.data))
    await hub.async_connect()
    if not hub.connected:
        # The link couldn't be opened (adapter unplugged / bridge down?). Retry later
        # rather than fail hard -- HA calls setup again with backoff.
        raise ConfigEntryNotReady(f"Could not open bus {hub.label}")

    data = WaveshareData(hub=hub)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    for dev in entry.data.get(CONF_DEVICES, []):
        address = dev[CONF_ADDRESS]
        coordinator = RelayCoordinator(
            hass,
            hub,
            address=address,
            name=dev.get(CONF_NAME) or f"Relay board {address}",
            channels=dev.get(CONF_CHANNELS, DEFAULT_CHANNELS),
            scan_interval=scan_interval,
        )
        # Best-effort version read for the device card; never blocks setup.
        coordinator.sw_version = await hub.async_read_version(address)
        # Tolerant refresh: one unresponsive board shows "unavailable" but doesn't
        # block the rest of the bus from loading.
        await coordinator.async_refresh()
        data.coordinators[address] = coordinator

    entry.runtime_data = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: WaveshareConfigEntry) -> None:
    """Reload when devices are added/removed or the scan interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WaveshareConfigEntry) -> bool:
    """Tear down platforms and release the serial port."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.hub.async_close()
    # Drop the shared services once the last bus entry goes away.
    if len(hass.config_entries.async_entries(DOMAIN)) <= 1:
        async_unload_services(hass)
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: WaveshareConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a board's device from the device page.

    Deleting the device drops that board from the bus config and reloads, so it isn't
    re-created. (Removing several at once is still easier via Configure -> Remove a
    relay board.) A device we don't recognise is always allowed to be removed.
    """
    prefix = f"{entry.entry_id}_"
    address: int | None = None
    for domain, ident in device.identifiers:
        if domain == DOMAIN and ident.startswith(prefix):
            try:
                address = int(ident[len(prefix):])
            except ValueError:
                address = None
            break
    if address is None:
        return True  # unknown / stale device -> let the UI remove it

    devices = entry.data.get(CONF_DEVICES, [])
    remaining = [d for d in devices if d[CONF_ADDRESS] != address]
    if len(remaining) != len(devices):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_DEVICES: remaining}
        )  # triggers a reload via the update listener
    return True
