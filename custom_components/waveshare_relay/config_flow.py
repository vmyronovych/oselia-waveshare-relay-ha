"""Config + options flow.

User flow: pick the USB/RS485 serial port + bus baud rate, then add the first relay
board (Modbus address, name, channel count). The bus link and the board are both
probed before the entry is created, so a wrong port/address/baud fails here with a
clear reason instead of producing a dead device.

Options flow: add or remove boards on the same bus, and tune the poll interval.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusSerialClient

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
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_ADDRESS,
    DEFAULT_BAUDRATE,
    DEFAULT_CHANNELS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_ADDRESS,
    MIN_ADDRESS,
)
from .hub import _UNIT_KW

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


def _port_schema(port_options: list[selector.SelectOptionDict]) -> vol.Schema:
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
            vol.Required(
                CONF_NAME, default=d.get(CONF_NAME, "Relay board")
            ): str,
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


async def _test_port(port: str, baud: int) -> bool:
    client = AsyncModbusSerialClient(port=port, baudrate=baud, timeout=2)
    try:
        return bool(await client.connect())
    except Exception:  # pragma: no cover - driver/OS errors
        return False
    finally:
        client.close()


async def _probe_board(port: str, baud: int, address: int, channels: int) -> bool:
    client = AsyncModbusSerialClient(port=port, baudrate=baud, timeout=2)
    try:
        if not await client.connect():
            return False
        rr = await client.read_coils(COIL_FIRST, count=channels, **{_UNIT_KW: address})
        return rr is not None and not rr.isError()
    except Exception:
        return False
    finally:
        client.close()


class WaveshareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one RS485 bus and its first relay board."""

    VERSION = 1

    def __init__(self) -> None:
        self._port: str | None = None
        self._baud: int = DEFAULT_BAUDRATE

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaveshareOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT]
            baud = int(user_input[CONF_BAUDRATE])
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            if not await _test_port(port, baud):
                errors["base"] = "cannot_connect"
            else:
                self._port = port
                self._baud = baud
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=_port_schema(await _list_ports(self.hass)),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = int(user_input[CONF_ADDRESS])
            channels = int(user_input[CONF_CHANNELS])
            if not await _probe_board(self._port, self._baud, address, channels):
                errors["base"] = "no_response"
            else:
                return self.async_create_entry(
                    title=f"Waveshare relays ({self._port})",
                    data={
                        CONF_PORT: self._port,
                        CONF_BAUDRATE: self._baud,
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
            elif not await _probe_board(
                entry.data[CONF_PORT], entry.data[CONF_BAUDRATE], address, channels
            ):
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
            keep = set(user_input.get("remove", []))
            remaining = [d for d in devices if str(d[CONF_ADDRESS]) not in keep]
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
