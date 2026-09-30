"""Read-only observation of plausible robot mowing sessions."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.core import Event
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_MOWED_ENTITY,
    CONF_MOWING_ACTIVE_STATE,
    CONF_MOWING_DONE_STATE,
    CONF_MOWING_ENTITY,
    CONF_MOWING_MIN_MINUTES,
    CONF_MOWING_MODE,
    DEFAULT_MOWING_MIN_MINUTES,
)


class MowingObserver:
    """Record observed work followed by docking; never command a device.

    Docking may mean charging rather than full coverage. Records are explicitly
    estimates. A configured completion binary input takes precedence. In-flight
    observations are deliberately discarded across restart/reconfiguration.
    """

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._lock = asyncio.Lock()
        self._reset()

    def _reset(self) -> None:
        self.started_at = None
        self.active_since = None
        self.active_seconds = 0.0

    def subscribe(self, entry) -> None:
        settings = self.coordinator.settings
        entity_id = settings.get(CONF_MOWING_ENTITY)
        if (
            settings.get(CONF_MOWING_MODE) == "robot"
            and entity_id
            and not settings.get(CONF_MOWED_ENTITY)
        ):
            entry.async_on_unload(
                async_track_state_change_event(
                    self.coordinator.hass, [entity_id], self.async_handle_event
                )
            )

    async def async_handle_event(self, event: Event) -> None:
        """Accumulate mowing time, excluding returns and pauses."""
        async with self._lock:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if new is None or old is None:
                self._reset()
                return
            if old.state == new.state:
                return
            now = event.time_fired
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
                self._reset()
                return
            if state == active:
                if self.started_at is None:
                    self.started_at = now
                self.active_since = now
            elif state == done:
                started_at, seconds = self.started_at, self.active_seconds
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
                    )
            elif state not in {"paused", "returning"}:
                self._reset()
