"""Repair flow for a blueprint the user edited that a newer release wants to change.

The installer never overwrites an edited blueprint (see blueprint.py); it raises a fixable
issue instead. This flow lets the user resolve it in the UI: take the new version (their
file is backed up first) or keep their edited one (we stop nagging until an even newer
version ships).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import blueprint


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a blueprint conflict issue."""
    return BlueprintConflictRepairFlow(data or {})


class BlueprintConflictRepairFlow(RepairsFlow):
    """Ask the user whether to take the new blueprint or keep their edited one."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._rel: str = data.get("rel", "")
        self._path: str = data.get("path", "")

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["take_new", "keep_mine"],
            description_placeholders={"path": self._path},
        )

    async def async_step_take_new(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await blueprint.async_take_new_version(self.hass, self._rel)
        return self.async_create_entry(title="", data={})

    async def async_step_keep_mine(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await blueprint.async_keep_user_version(self.hass, self._rel)
        return self.async_create_entry(title="", data={})
