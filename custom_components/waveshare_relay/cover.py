"""Roller-shutter `cover` entities: two relay coils paired into one motor.

A shutter is driven by two relays -- an **up** coil and a **down** coil -- that must
never be energized together and that share a travel-time model. This platform turns
that pair into a single native Home Assistant `cover`, so installers stop hand-wiring
the interlock and timing per shutter and the safety-critical logic lives in one tested
place.

What the controller guarantees, in order of importance:

  * **Interlock (defense-in-depth).** Before energizing one coil the other is always
    commanded off. The board's wiring already forbids both-on; this is belt-and-braces.
  * **Break-before-make.** On a direction *reversal* we de-energize, pause
    ``REVERSAL_PAUSE`` seconds, then energize the other way -- the motor never sees an
    instant reversal.
  * **Max-run cutoff.** Every move arms a safety timer that de-energizes both coils a
    margin past the expected travel time (or a hard cap when travel time is unknown), so
    a lost "stop" can never leave a motor powered.
  * **Timed position** (only once travel times are calibrated). Position is estimated
    from motor-on time and *re-synced* to exactly 0 % / 100 % whenever a hard limit is
    reached, so estimation error can't accumulate.

Position is a refinement layered on top: with no travel times set, open/close/stop still
work and the entity simply reports no position (the dashboard slider stays hidden).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity

from . import WaveshareConfigEntry
from .const import (
    CONF_ADDRESS,
    CONF_COVERS,
    CONF_DOWN_CHANNEL,
    CONF_DOWN_TRAVEL_TIME,
    CONF_ID,
    CONF_NAME,
    CONF_UP_CHANNEL,
    CONF_UP_TRAVEL_TIME,
    DEFAULT_MAX_RUN,
    MAX_RUN_MARGIN,
    POSITION_UPDATE_INTERVAL,
    REVERSAL_PAUSE,
)
from .coordinator import RelayCoordinator
from .entity import WaveshareEntity

_LOGGER = logging.getLogger(__name__)

# Snap-to-limit tolerance: a position within this many percent of a hard limit is
# treated as fully at that limit (and the estimate re-synced to exactly 0 / 100).
_LIMIT_EPS = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaveshareConfigEntry,
    async_add_entities,
) -> None:
    """Create one cover per configured shutter whose board is on this bus."""
    coordinators = entry.runtime_data.coordinators
    entities: list[WaveshareCover] = []
    for cfg in entry.data.get(CONF_COVERS, []):
        coordinator = coordinators.get(cfg[CONF_ADDRESS])
        if coordinator is None:
            # The paired board was removed from the bus; skip its covers.
            continue
        entities.append(WaveshareCover(coordinator, cfg))
    async_add_entities(entities)


class _TravelCalc:
    """Pure time-based position estimator (no I/O, no Home Assistant).

    Position runs 0 (fully closed) .. 100 (fully open), matching Home Assistant's
    convention. "Up" opens (position rises); "down" closes (position falls). It is a
    plain estimator: feed it start/stop and it interpolates from wall-clock elapsed
    time. `resting` is ``None`` until the first move establishes a known position.
    """

    def __init__(self, up_time: float, down_time: float) -> None:
        self.up_time = up_time      # seconds, full close -> full open
        self.down_time = down_time  # seconds, full open -> full close
        self._resting: float | None = None
        self._start_pos = 0.0
        self._target = 0.0
        self._up: bool | None = None  # True up, False down, None resting
        self._t0 = 0.0

    @property
    def resting(self) -> float | None:
        return self._resting

    def set_resting(self, position: float) -> None:
        self._resting = position

    @property
    def is_moving(self) -> bool:
        return self._up is not None

    @property
    def target(self) -> float:
        return self._target

    def start(self, up: bool, target: float) -> None:
        """Begin a move toward `target`. If the resting position is still unknown,
        assume the far limit as the origin so the motor runs a full travel and the
        limit re-sync establishes a real position."""
        if self._resting is not None:
            self._start_pos = self._resting
        else:
            self._start_pos = 0.0 if up else 100.0
        self._up = up
        self._target = target
        self._t0 = time.monotonic()

    def current(self) -> float | None:
        """Estimated position right now (or the resting position when stopped)."""
        if self._up is None:
            return self._resting
        travel = self.up_time if self._up else self.down_time
        if not travel:
            return self._resting
        moved = (time.monotonic() - self._t0) / travel * 100.0
        if self._up:
            return min(self._start_pos + moved, self._target)
        return max(self._start_pos - moved, self._target)

    def stop(self) -> None:
        """Freeze the estimate at the current position and clear the move."""
        self._resting = self.current()
        self._up = None

    def position_reached(self) -> bool:
        if self._up is None:
            return False
        cur = self.current()
        if cur is None:
            return False
        return cur >= self._target if self._up else cur <= self._target

    def time_to_target(self) -> float:
        """Seconds from the move's start until `target` is reached."""
        travel = self.up_time if self._up else self.down_time
        return abs(self._target - self._start_pos) / 100.0 * travel


class WaveshareCover(WaveshareEntity, CoverEntity, RestoreEntity):
    """A roller shutter: two coils on one board, driven as one cover."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    # Position is a time estimate, not a read-back encoder, so state is "assumed":
    # Home Assistant then always offers open/close/stop rather than a single toggle.
    _attr_assumed_state = True

    def __init__(self, coordinator: RelayCoordinator, cfg: dict) -> None:
        super().__init__(coordinator)
        self._cfg = cfg
        self._up_channel: int = cfg[CONF_UP_CHANNEL]
        self._down_channel: int = cfg[CONF_DOWN_CHANNEL]
        up_time = float(cfg.get(CONF_UP_TRAVEL_TIME) or 0.0)
        down_time = float(cfg.get(CONF_DOWN_TRAVEL_TIME) or 0.0)
        # Position estimation needs *both* directions timed.
        self._calibrated = up_time > 0 and down_time > 0
        self._calc = _TravelCalc(up_time, down_time)

        self._attr_unique_id = f"{self._device_uid}_cover_{cfg[CONF_ID]}"
        self._attr_name = cfg.get(CONF_NAME) or "Roller shutter"

        self._moving: str | None = None  # "up" | "down" | None
        self._assumed_closed: bool | None = None  # only used when not calibrated
        # Serialize command/stop handling so overlapping taps can't interleave I/O.
        self._lock = asyncio.Lock()
        self._unsub_stop = None
        self._unsub_cutoff = None
        self._unsub_ticker = None

    @property
    def supported_features(self) -> CoverEntityFeature:
        features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
        )
        if self._calibrated:
            features |= CoverEntityFeature.SET_POSITION
        return features

    # ---- reported state --------------------------------------------------
    @property
    def current_cover_position(self) -> int | None:
        if not self._calibrated:
            return None
        pos = self._calc.current()
        return None if pos is None else round(pos)

    @property
    def is_closed(self) -> bool | None:
        if self._calibrated:
            pos = self._calc.current()
            return None if pos is None else pos <= _LIMIT_EPS
        return self._assumed_closed

    @property
    def is_opening(self) -> bool:
        return self._moving == "up"

    @property
    def is_closing(self) -> bool:
        return self._moving == "down"

    # ---- lifecycle -------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        """Restore the last known position across restarts (nothing moves)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        if self._calibrated:
            pos = last.attributes.get("current_position")
            if isinstance(pos, (int, float)):
                self._calc.set_resting(float(pos))
        else:
            self._assumed_closed = last.state == "closed" if last.state in (
                "open",
                "closed",
            ) else None

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_timers()
        await super().async_will_remove_from_hass()

    # ---- commands --------------------------------------------------------
    async def async_open_cover(self, **kwargs) -> None:
        await self._async_move("up", 100.0)

    async def async_close_cover(self, **kwargs) -> None:
        await self._async_move("down", 0.0)

    async def async_set_cover_position(self, **kwargs) -> None:
        target = float(kwargs["position"])
        current = self._calc.current()
        if current is not None and abs(current - target) <= _LIMIT_EPS:
            return
        # With no known position yet, bias by half-travel so the move heads to a limit.
        going_up = target >= current if current is not None else target >= 50
        await self._async_move("up" if going_up else "down", target)

    async def async_stop_cover(self, **kwargs) -> None:
        await self._async_stop(reached=False)

    # ---- movement engine -------------------------------------------------
    async def _async_move(self, direction: str, target: float) -> None:
        async with self._lock:
            up = direction == "up"
            if self._calibrated:
                current = self._calc.current()
                if current is not None and (
                    (up and current >= target) or (not up and current <= target)
                ):
                    # Already at/past the target in the requested direction.
                    if self._moving is not None:
                        await self._stop_locked(reached=True)
                    return

            reversal = self._moving is not None and self._moving != direction
            same_direction = self._moving == direction

            self._cancel_timers()
            if self._calibrated:
                self._calc.stop()  # freeze current position before (re)starting

            if not same_direction:
                # Interlock + break-before-make: drop the opposite coil first, pause on
                # a reversal, then energize the requested direction.
                opposite = self._down_channel if up else self._up_channel
                await self.coordinator.async_set_relay(opposite, False)
                if reversal:
                    await asyncio.sleep(REVERSAL_PAUSE)
                await self.coordinator.async_set_relay(
                    self._up_channel if up else self._down_channel, True
                )

            self._moving = direction

            if self._calibrated:
                self._calc.start(up, target)
                ttt = self._calc.time_to_target()
                self._unsub_stop = async_call_later(
                    self.hass, ttt, self._on_target_timer
                )
                self._unsub_cutoff = async_call_later(
                    self.hass, ttt + MAX_RUN_MARGIN, self._on_cutoff_timer
                )
                self._unsub_ticker = async_track_time_interval(
                    self.hass,
                    self._on_tick,
                    timedelta(seconds=POSITION_UPDATE_INTERVAL),
                )
            else:
                # No position model: run to the hard safety cap, then assume the limit.
                self._unsub_cutoff = async_call_later(
                    self.hass, DEFAULT_MAX_RUN, self._on_cutoff_timer
                )

            self.async_write_ha_state()

    async def _async_stop(self, reached: bool) -> None:
        async with self._lock:
            await self._stop_locked(reached)

    async def _stop_locked(self, reached: bool) -> None:
        """De-energize both coils and settle reported state. (lock held)"""
        direction = self._moving
        self._cancel_timers()
        # Safety first: command both coils off regardless of believed state.
        await self.coordinator.async_set_relay(self._up_channel, False)
        await self.coordinator.async_set_relay(self._down_channel, False)

        if self._calibrated:
            pos = self._calc.target if reached else self._calc.current()
            self._calc.stop()
            if pos is not None:
                # Re-sync to a hard limit so estimation error can't accumulate.
                if pos <= _LIMIT_EPS:
                    pos = 0.0
                elif pos >= 100.0 - _LIMIT_EPS:
                    pos = 100.0
                self._calc.set_resting(pos)
        elif reached and direction is not None:
            self._assumed_closed = direction == "down"

        self._moving = None
        self.async_write_ha_state()

    # ---- timer callbacks (scheduled, run on the event loop) --------------
    @callback
    def _on_target_timer(self, _now) -> None:
        self._unsub_stop = None
        self.hass.async_create_task(self._async_stop(reached=True))

    @callback
    def _on_cutoff_timer(self, _now) -> None:
        self._unsub_cutoff = None
        if self._moving is not None:
            _LOGGER.warning(
                "Cover %s hit the max-run cutoff; de-energizing", self.entity_id
            )
        self.hass.async_create_task(self._async_stop(reached=True))

    @callback
    def _on_tick(self, _now) -> None:
        if self._moving is None:
            return
        if self._calibrated and self._calc.position_reached():
            self.hass.async_create_task(self._async_stop(reached=True))
            return
        self.async_write_ha_state()  # refresh the position slider while moving

    @callback
    def _cancel_timers(self) -> None:
        for attr in ("_unsub_stop", "_unsub_cutoff", "_unsub_ticker"):
            unsub = getattr(self, attr)
            if unsub is not None:
                unsub()
                setattr(self, attr, None)
