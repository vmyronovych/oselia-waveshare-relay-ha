"""Config + options flow.

User flow: choose the transport -- **Serial** (USB/RS485 adapter on the HA host) or
**Network/TCP** (a socat/ser2net bridge or an RS485-to-Ethernet gateway, for when HA
can't see the USB port, e.g. Docker Desktop on macOS) -- then add the first relay board
(Modbus address, name, channel count). The link and the board are both probed before the
entry is created, so a wrong port/host/address/baud fails here with a clear reason.

Options flow: add or remove boards on the same bus, and tune the poll interval.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BAUD_RATES,
    CHANNEL_OPTIONS,
    COIL_FIRST,
    CONF_ADDRESS,
    CONF_BAUDRATE,
    CONF_CHANNELS,
    CONF_DEVICES,
    CONF_FRAMER,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TCP_PORT,
    CONF_TYPE,
    DEFAULT_ADDRESS,
    DEFAULT_BAUDRATE,
    DEFAULT_CHANNELS,
    DEFAULT_FRAMER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TCP_PORT,
    DOMAIN,
    FRAMER_RTU,
    FRAMER_SOCKET,
    MAX_ADDRESS,
    MIN_ADDRESS,
    TYPE_SERIAL,
    TYPE_TCP,
)
from .hub import build_client, describe, unique_id_for

_LOGGER = logging.getLogger(__name__)


async def _list_ports(hass) -> list[selector.SelectOptionDict]:
    from serial.tools import list_ports

    ports = await hass.async_add_executor_job(list_ports.comports)
    return [
        selector.SelectOptionDict(
            value=p.device, label=f"{p.device} ({p.description})"
        )
        for p in ports
    ]


def _serial_schema(port_options: list[selector.SelectOptionDict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_PORT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=port_options,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[str(b) for b in BAUD_RATES.values()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _network_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=65535, step=1, mode="box")
            ),
            vol.Required(CONF_FRAMER, default=DEFAULT_FRAMER): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=FRAMER_RTU,
                            label="RTU over TCP (socat / transparent gateway)",
                        ),
                        selector.SelectOptionDict(
                            value=FRAMER_SOCKET, label="Modbus TCP (MBAP gateway)"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _device_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ADDRESS, default=d.get(CONF_ADDRESS, DEFAULT_ADDRESS)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_ADDRESS, max=MAX_ADDRESS, step=1, mode="box"
                )
            ),
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "Relay board")): str,
            vol.Required(
                CONF_CHANNELS, default=str(d.get(CONF_CHANNELS, DEFAULT_CHANNELS))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[str(c) for c in CHANNEL_OPTIONS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


async def _test_connection(cfg: dict) -> bool:
    client = build_client(cfg)
    try:
        if await client.connect():
            return True
        _LOGGER.warning("Waveshare: could not connect to %s", describe(cfg))
        return False
    except Exception as err:  # pragma: no cover - driver/OS/socket errors
        _LOGGER.warning("Waveshare: connection to %s failed: %s", describe(cfg), err)
        return False
    finally:
        client.close()


async def _probe_board(cfg: dict, address: int, channels: int) -> bool:
    client = build_client(cfg)
    try:
        if not await client.connect():
            return False
        rr = await client.read_coils(
            COIL_FIRST, count=channels, **{_unit_kw(): address}
        )
        return rr is not None and not rr.isError()
    except Exception as err:
        _LOGGER.warning(
            "Waveshare: no reply from address %s on %s: %s",
            address, describe(cfg), err,
        )
        return False
    finally:
        client.close()


def _unit_kw() -> str:
    from .hub import _UNIT_KW

    return _UNIT_KW


class WaveshareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one bus (serial or TCP) and its first relay board."""

    VERSION = 1

    def __init__(self) -> None:
        self._transport: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaveshareOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["serial", "network"]
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cfg = {
                CONF_TYPE: TYPE_SERIAL,
                CONF_PORT: user_input[CONF_PORT],
                CONF_BAUDRATE: int(user_input[CONF_BAUDRATE]),
            }
            await self.async_set_unique_id(unique_id_for(cfg))
            self._abort_if_unique_id_configured()
            if not await _test_connection(cfg):
                errors["base"] = "cannot_connect"
            else:
                self._transport = cfg
                return await self.async_step_device()

        schema = _serial_schema(await _list_ports(self.hass))
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="serial", data_schema=schema, errors=errors
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cfg = {
                CONF_TYPE: TYPE_TCP,
                CONF_HOST: user_input[CONF_HOST],
                CONF_TCP_PORT: int(user_input[CONF_TCP_PORT]),
                CONF_FRAMER: user_input[CONF_FRAMER],
            }
            await self.async_set_unique_id(unique_id_for(cfg))
            self._abort_if_unique_id_configured()
            if not await _test_connection(cfg):
                errors["base"] = "cannot_connect"
            else:
                self._transport = cfg
                return await self.async_step_device()

        schema = _network_schema()
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="network", data_schema=schema, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = int(user_input[CONF_ADDRESS])
            channels = int(user_input[CONF_CHANNELS])
            if not await _probe_board(self._transport, address, channels):
                errors["base"] = "no_response"
            else:
                return self.async_create_entry(
                    title=f"Waveshare relays ({describe(self._transport)})",
                    data={
                        **self._transport,
                        CONF_DEVICES: [
                            {
                                CONF_ADDRESS: address,
                                CONF_NAME: user_input[CONF_NAME],
                                CONF_CHANNELS: channels,
                            }
                        ],
                    },
                )

        return self.async_show_form(
            step_id="device", data_schema=_device_schema(user_input), errors=errors
        )


class WaveshareOptionsFlow(OptionsFlow):
    """Add/remove boards on the bus and tune the poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "remove_device", "settings"],
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            address = int(user_input[CONF_ADDRESS])
            channels = int(user_input[CONF_CHANNELS])
            existing = {d[CONF_ADDRESS] for d in entry.data.get(CONF_DEVICES, [])}
            if address in existing:
                errors["base"] = "duplicate_address"
            elif not await _probe_board(dict(entry.data), address, channels):
                errors["base"] = "no_response"
            else:
                devices = [
                    *entry.data.get(CONF_DEVICES, []),
                    {
                        CONF_ADDRESS: address,
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_CHANNELS: channels,
                    },
                ]
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_DEVICES: devices}
                )
                return self.async_create_entry(title="", data=dict(entry.options))

        return self.async_show_form(
            step_id="add_device", data_schema=_device_schema(user_input), errors=errors
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        devices = entry.data.get(CONF_DEVICES, [])
        if user_input is not None:
            drop = set(user_input.get("remove", []))
            remaining = [d for d in devices if str(d[CONF_ADDRESS]) not in drop]
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_DEVICES: remaining}
            )
            return self.async_create_entry(title="", data=dict(entry.options))

        options = [
            selector.SelectOptionDict(
                value=str(d[CONF_ADDRESS]),
                label=f"{d.get(CONF_NAME)} (address {d[CONF_ADDRESS]})",
            )
            for d in devices
        ]
        schema = vol.Schema(
            {
                vol.Required("remove", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_device", data_schema=schema)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=3600, step=1, unit_of_measurement="s", mode="box"
                    )
                )
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
