"""Read-only robot mowing observation and conservative completion estimates.

File: custom_components/rasenpflege_assistent/mowing.py

The observer accumulates time in the configured active state and excludes
pauses/returns. A later dock transition can record an estimated mowing action
when the minimum active duration has been reached.

Docking does not prove full coverage. Unknown/error states invalidate the
observation, and in-flight observations are discarded on restart. A configured
completion input takes precedence. This module never commands a mower.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MOWED_ENTITY,
    CONF_MOWING_ACTIVE_STATE,
    CONF_MOWING_DONE_STATE,
    CONF_MOWING_ENTITY,
    CONF_MOWING_MIN_MINUTES,
    CONF_MOWING_MODE,
    DEFAULT_MOWING_MIN_MINUTES,
)
from .explanations import reason_text
from .guidance import duration_context
from .insights import aware_time, finite_number
from .review import program_context

if TYPE_CHECKING:
    from .coordinator import LawnCoordinator


class MowingObserver:
    """Record observed work followed by docking; never command a device.

    Docking may mean charging rather than full coverage. Records are explicitly
    estimates. A configured completion binary input takes precedence. In-flight
    observations are deliberately discarded across restart/reconfiguration.
    """

    def __init__(self, coordinator: LawnCoordinator) -> None:
        self.coordinator = coordinator
        self._lock = asyncio.Lock()
        self.last_event_at: datetime | None = None
        self._reset()

    def _reset(self, reason: str = "idle") -> None:
        """Reset uncommitted mowing observation.

        Discard in-flight evidence, leaving previously committed maintenance
        history unchanged. Unknown states or implausibly long observations
        must not later produce a convincing completion estimate.
        """
        self.started_at: datetime | None = None
        self.active_since: datetime | None = None
        self.active_seconds = 0.0
        self.interruptions = 0
        self.observation_reason = reason
        self.settings_context: str | None = None
        self.program: dict[str, str | int | bool] = {}
        self.program_stable = True

    def diagnostic_attributes(self) -> dict[str, Any]:
        """Expose an in-flight estimate; it never claims completed lawn coverage."""
        active_seconds = self.active_seconds + (
            max(0, (dt_util.now() - self.active_since).total_seconds())
            if self.active_since
            else 0
        )
        now = dt_util.now()
        elapsed = (
            max(0.0, (now - self.started_at).total_seconds())
            if self.started_at
            else 0.0
        )
        last_start = aware_time(self.coordinator.state.last_robot_session_started_at)
        last_end = aware_time(self.coordinator.state.last_robot_session_finished_at)
        last_active = finite_number(
            self.coordinator.state.last_robot_session_active_seconds
        )
        if last_active is not None and last_active < 0:
            last_active = None
        last_interruptions = finite_number(
            self.coordinator.state.last_robot_session_interruptions
        )
        if (
            last_interruptions is None
            or last_interruptions < 0
            or not last_interruptions.is_integer()
        ):
            last_interruptions = None
        last_elapsed = (
            max(0.0, (last_end - last_start).total_seconds())
            if last_start and last_end
            else None
        )
        return {
            "elapsed_minutes": round(elapsed / 60, 1),
            "inactive_minutes": round(max(0.0, elapsed - active_seconds) / 60, 1),
            "interruptions": self.interruptions,
            "program_context": dict(self.program),
            "program_stable": self.program_stable,
            "minimum_active_minutes": float(
                self.coordinator.settings.get(
                    CONF_MOWING_MIN_MINUTES, DEFAULT_MOWING_MIN_MINUTES
                )
            ),
            "reason": self.observation_reason,
            "reason_text": reason_text(
                self.observation_reason, self.coordinator.hass.config.language
            ),
            "coverage_confirmed": False,
            "completion_basis": "observed_active_time_and_dock",
            "last_observation": {
                "started_at": last_start.isoformat() if last_start else None,
                "finished_at": last_end.isoformat() if last_end else None,
                "active_minutes": round(last_active / 60, 1)
                if last_active is not None
                else None,
                "inactive_minutes": round(max(0.0, last_elapsed - last_active) / 60, 1)
                if last_elapsed is not None and last_active is not None
                else None,
                "interruptions": int(last_interruptions)
                if last_interruptions is not None
                else None,
                "coverage_confirmed": False,
            },
            "status": "mowing"
            if self.active_since
            else "waiting_for_dock"
            if self.started_at
            else "idle",
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "active_minutes": round(active_seconds / 60, 1),
            "estimated": True,
        }

    @callback
    def _tick(self, _now: datetime) -> None:
        """Update live minutes locally without requesting weather."""
        if self.started_at:
            if _now - self.started_at > timedelta(hours=12):
                self._reset("robot_observation_expired")
            self.coordinator.async_update_listeners()

    def subscribe(self, entry: ConfigEntry) -> None:
        """Observe a robot source only when robot mode is selected and no explicit
        completion input is configured. Register both event and timer cleanup
        with the config entry so reload cannot leave duplicate observers.
        """
        settings = self.coordinator.settings
        entity_id = settings.get(CONF_MOWING_ENTITY)
        if (
            settings.get(CONF_MOWING_MODE) == "robot"
            and entity_id
            and not settings.get(CONF_MOWED_ENTITY)
        ):
            entry.async_on_unload(
                async_track_time_interval(
                    self.coordinator.hass,
                    self._tick,
                    timedelta(seconds=30),
                    cancel_on_shutdown=True,
                )
            )
            entry.async_on_unload(
                async_track_state_change_event(
                    self.coordinator.hass, [entity_id], self.async_handle_event
                )
            )

    async def async_handle_event(self, event: Event[EventStateChangedData]) -> None:
        """Accumulate mowing time, excluding returns and pauses.

        Serialize transitions; attribute-only reports do not add active time.
        Accumulate time before leaving the active state, reset uncertain
        sequences, and commit a sufficiently long session only at docking.
        The event timestamp preserves physical ordering in maintenance history.
        """
        async with self._lock:
            now = event.time_fired
            if self.last_event_at is not None and now <= self.last_event_at:
                self.observation_reason = "robot_old_event_ignored"
                self.coordinator.async_update_listeners()
                return
            self.last_event_at = now
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if new is None or old is None:
                self._reset()
                self.coordinator.async_update_listeners()
                return
            # Attribute-only metadata changes invalidate duration comparability.
            if (
                self.started_at
                and new.state.casefold()
                == self.coordinator.settings.get(
                    CONF_MOWING_ACTIVE_STATE, "mowing"
                ).casefold()
                and (
                    program_context(new.attributes) != self.program
                    or duration_context(self.coordinator.settings)
                    != self.settings_context
                )
            ):
                self.program_stable = False
            if old.state == new.state:
                return
            settings = self.coordinator.settings
            active = settings.get(CONF_MOWING_ACTIVE_STATE, "mowing").casefold()
            done = settings.get(CONF_MOWING_DONE_STATE, "docked").casefold()
            if self.started_at and now - self.started_at > timedelta(hours=12):
                self._reset()
            if self.active_since is not None:
                self.active_seconds += max(0, (now - self.active_since).total_seconds())
                self.active_since = None
            state = new.state.casefold()
            if state in {"unknown", "unavailable", "error", "idle"}:
                self._reset("robot_observation_discarded")
                self.coordinator.async_update_listeners()
                return
            if state == active:
                if self.started_at is None:
                    self.started_at = now
                    self.settings_context = duration_context(settings)
                    self.program = program_context(new.attributes)
                self.active_since = now
                self.observation_reason = "robot_observing"
            elif state == done:
                started_at, seconds, interruptions = (
                    self.started_at,
                    self.active_seconds,
                    self.interruptions,
                )
                metadata = {
                    "settings_context": self.settings_context,
                    "program_context": self.program,
                    "program_stable": self.program_stable
                    and self.settings_context == duration_context(settings),
                }
                self._reset()
                minimum = (
                    float(
                        settings.get(
                            CONF_MOWING_MIN_MINUTES, DEFAULT_MOWING_MIN_MINUTES
                        )
                    )
                    * 60
                )
                if started_at is not None and seconds >= minimum:
                    entity_id = new.entity_id
                    await self.coordinator.async_mark_mowed(
                        event_id=f"{entity_id}:{started_at.isoformat()}",
                        recorded_at=now,
                        source="robot_estimate",
                        active_seconds=seconds,
                        session_started_at=started_at,
                        interruptions=interruptions,
                        observation_metadata=metadata,
                    )
            elif state in {"paused", "returning"}:
                if old.state.casefold() == active:
                    self.interruptions += 1
                self.observation_reason = "robot_waiting_for_dock"
            else:
                self._reset("robot_observation_discarded")
            self.coordinator.async_update_listeners()
