"""Hardware-independent, fail-closed valve and water-meter controller."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALLOW_UNMETERED_MANUAL,
    CONF_AREA,
    CONF_FLOW_START_GRACE,
    CONF_IRRIGATION_FLOW,
    CONF_IRRIGATION_VALVE,
    CONF_MAX_FLOW_L_MIN,
    CONF_MAX_IRRIGATION_LITERS,
    CONF_MAX_IRRIGATION_MINUTES,
    CONF_MIN_FLOW_L_MIN,
    CONF_MIN_IRRIGATION_MINUTES,
    CONF_MOWER_LOCATION,
    CONF_MOWER_SAFE_STATE,
    CONF_OTHER_VALVE,
    DEFAULT_AREA,
    DEFAULT_FLOW_START_GRACE,
    DEFAULT_MAX_FLOW_L_MIN,
    DEFAULT_MAX_IRRIGATION_LITERS,
    DEFAULT_MAX_IRRIGATION_MINUTES,
    DEFAULT_MIN_FLOW_L_MIN,
    DEFAULT_MIN_IRRIGATION_MINUTES,
    DOMAIN,
    IRRIGATION_WATCHDOG_INTERVAL,
)

if TYPE_CHECKING:
    from .coordinator import LawnCoordinator

_LOGGER = logging.getLogger(__name__)


def _meter_reading(state: Any) -> tuple[str, float] | None:
    """Normalize supported flow and volume sensors to L/min or L."""
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        raw = float(state.state)
    except (TypeError, ValueError):
        return None
    if not 0 <= raw < 1e9:
        return None
    unit = str(state.attributes.get("unit_of_measurement", "")).strip()
    rates = {
        "L/min": 1.0,
        "L/h": 1 / 60,
        "L/s": 60.0,
        "m³/h": 1000 / 60,
        "m³/min": 1000.0,
        "m³/s": 60000.0,
    }
    volumes = {"L": 1.0, "m³": 1000.0, "gal": 3.785411784}
    if unit in rates:
        return "rate", raw * rates[unit]
    if unit in volumes:
        return "volume", raw * volumes[unit]
    return None


class IrrigationController:
    """Supervise owned watering sessions independently of weather polling."""

    def __init__(self, hass: HomeAssistant, coordinator: LawnCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._lock = asyncio.Lock()
        self._unsubscribers: list[Any] = []
        self._recent_owned_until = dt_util.parse_datetime(
            coordinator._state.irrigation_recent_until or ""
        )
        self._recent_owned_valve_id = coordinator._state.irrigation_recent_valve_id

    @property
    def state(self):
        """Return persisted session and toggle state."""
        assert self.coordinator._state is not None
        return self.coordinator._state

    @property
    def configured(self) -> bool:
        """Whether an optional valve was selected."""
        return bool(self.coordinator.settings.get(CONF_IRRIGATION_VALVE))

    @property
    def active(self) -> bool:
        """Whether the controller currently owns an open or closing valve."""
        return self.state.irrigation_session is not None

    def _mower_is_docked(self) -> bool:
        """Trust only the configured explicit dock state."""
        entity_id = self.coordinator.settings.get(CONF_MOWER_LOCATION)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return False
        if entity_id.startswith(("lawn_mower.", "vacuum.")):
            return state.state == "docked"
        if entity_id.startswith("binary_sensor."):
            return state.state == "on"
        safe_state = str(
            self.coordinator.settings.get(CONF_MOWER_SAFE_STATE, "docked")
        ).strip()
        return state.state.casefold() == safe_state.casefold()

    def _valve_state(self) -> str | None:
        """Return the reported state of the chosen switch."""
        session = self.state.irrigation_session
        entity_id = (
            session.get("valve_entity_id") if session else None
        ) or self.coordinator.settings.get(CONF_IRRIGATION_VALVE)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.state if state is not None else None

    def _other_valve_state(self) -> str:
        """An omitted competing valve is closed; an unknown one blocks starts."""
        entity_id = self.coordinator.settings.get(CONF_OTHER_VALVE)
        if not entity_id:
            return "off"
        state = self.hass.states.get(entity_id)
        return state.state if state is not None else "unavailable"

    def start_blocker(self) -> str | None:
        """Return the first actionable reason the controller cannot start."""
        if not self._mower_is_docked():
            return "mower_not_docked"
        if self._valve_state() != "off":
            return "valve_not_closed"
        if self._other_valve_state() != "off":
            return (
                "other_valve_open"
                if self._other_valve_state() == "on"
                else "other_valve_unavailable"
            )
        meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
        if meter_id and _meter_reading(self.hass.states.get(meter_id)) is None:
            return "meter_unavailable"
        return None

    def readiness(self) -> str:
        """Summarize start eligibility for a diagnostic entity."""
        if not self.configured:
            return "not_configured"
        if self.active:
            return self.state.irrigation_last_status
        return self.start_blocker() or "ready"

    def diagnostic_attributes(self) -> dict[str, Any]:
        """Expose live safety inputs without additional weather requests."""
        session = self.state.irrigation_session
        meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
        meter = self.hass.states.get(meter_id) if meter_id else None
        report = (
            (getattr(meter, "last_reported", None) or meter.last_updated)
            if meter
            else None
        )
        return {
            "valve_state": self._valve_state(),
            "other_valve_state": self._other_valve_state(),
            "mower_docked": self._mower_is_docked(),
            "meter_reading": meter.state if meter else None,
            "meter_unit": meter.attributes.get("unit_of_measurement")
            if meter
            else None,
            "meter_age_seconds": max(0, round((dt_util.now() - report).total_seconds()))
            if report
            else None,
            "meter_attribution": "all_flow_while_lawn_valve_open",
            "session_source": session.get("source") if session else None,
            "session_liters": round(session["liters"], 1)
            if session and session["meter_kind"] != "timer"
            else None,
            "session_target_liters": session.get("target_liters") if session else None,
            "session_elapsed_seconds": round(
                (
                    dt_util.now() - dt_util.parse_datetime(session["started_at"])
                ).total_seconds()
            )
            if session
            else None,
            "last_stop_reason": self.state.irrigation_last_reason,
            "last_session_liters": self.state.irrigation_last_liters,
        }

    def _publish_session(self) -> None:
        """Update irrigation entities without resetting weather poll timers."""
        data = self.coordinator.data
        if data is None:
            return
        session = self.state.irrigation_session
        data.irrigation_status = self.state.irrigation_last_status
        data.irrigation_enabled = self.state.irrigation_enabled
        data.irrigation_reason = self.state.irrigation_last_reason
        data.irrigation_liters = (
            round(session["liters"], 1)
            if session and session["meter_kind"] != "timer"
            else self.state.irrigation_last_liters
        )
        self.coordinator.async_update_listeners()

    async def _async_command_valve(self, entity_id: str, *, open_valve: bool) -> None:
        """Bound slow device service calls so the watchdog can retry closure."""
        await asyncio.wait_for(
            self.hass.services.async_call(
                "switch",
                "turn_on" if open_valve else "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            ),
            timeout=15,
        )

    async def async_initialize(self) -> None:
        """Install immediate state checks and a separate safety watchdog."""
        inputs = [
            self.coordinator.settings.get(key)
            for key in (
                CONF_IRRIGATION_VALVE,
                CONF_IRRIGATION_FLOW,
                CONF_MOWER_LOCATION,
                CONF_OTHER_VALVE,
            )
        ]
        inputs.append(self._recent_owned_valve_id)
        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                list({item for item in inputs if item}),
                self._async_input_changed,
            )
        )
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._async_watchdog,
                IRRIGATION_WATCHDOG_INTERVAL,
                name="lawn_irrigation_watchdog",
            )
        )
        self._unsubscribers.append(
            self.coordinator.async_add_listener(self._coordinator_updated)
        )
        if self.active:
            # A restart cannot prove how long the valve was open or how much
            # water was delivered. Close it instead of resuming an old timer.
            await self.async_stop("interrupted_by_restart")
        await self._async_close_late_open()

    async def _async_input_changed(self, _event) -> None:
        """Check mower, valve and meter immediately when their state changes."""
        await self._async_close_late_open()
        await self.async_check()
        self._publish_session()

    async def _async_close_late_open(self) -> None:
        """Close an on report that arrived after a stopped owned session."""
        if (
            self._recent_owned_until is not None
            and dt_util.now() >= self._recent_owned_until
        ):
            self._recent_owned_until = None
            self._recent_owned_valve_id = None
            self.state.irrigation_recent_valve_id = None
            self.state.irrigation_recent_until = None
            await self.coordinator._store.async_save(self.state.as_dict())
            return
        if (
            not self.active
            and self._recent_owned_until is not None
            and dt_util.now() < self._recent_owned_until
            and self._recent_owned_valve_id
            and self.hass.states.get(self._recent_owned_valve_id) is not None
            and self.hass.states.get(self._recent_owned_valve_id).state == "on"
        ):
            # A delayed switch report after an abort must not leave the valve
            # running without an owned session or a safety watchdog.
            try:
                await self._async_command_valve(
                    self._recent_owned_valve_id, open_valve=False
                )
            except (HomeAssistantError, TimeoutError):
                _LOGGER.exception("Could not close a late-opening irrigation valve")

    async def _async_watchdog(self, _now) -> None:
        """Enforce a maximum duration even without new state events."""
        await self._async_close_late_open()
        await self.async_check()
        if self.active and self.state.irrigation_session.get("paused_at"):
            await self._async_maybe_resume()
        elif not self.active:
            await self._async_maybe_auto_start()
        if self.active:
            self._publish_session()

    def _coordinator_updated(self) -> None:
        """Schedule automatic decisions after a completed weather update."""
        self.hass.async_create_task(
            self._async_maybe_auto_start(), "lawn_irrigation_auto_check"
        )

    async def _async_maybe_resume(self) -> None:
        """Resume an owned session only when every interlock is safe again."""
        async with self._lock:
            session = self.state.irrigation_session
            if session is None or not session.get("paused_at"):
                return
            now = dt_util.now()
            if (
                now - dt_util.parse_datetime(session["started_at"])
            ).total_seconds() >= 60 * float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                )
            ):
                await self._async_stop_locked("maximum_runtime")
                return
            if session["source"] == "auto" and not self.state.irrigation_enabled:
                await self._async_stop_locked("automation_disabled")
                return
            if self.start_blocker() is not None:
                return
            meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
            reading = (
                _meter_reading(self.hass.states.get(meter_id)) if meter_id else None
            )
            if session["meter_kind"] != "timer" and (
                reading is None or reading[0] != session["meter_kind"]
            ):
                return
            if reading is not None:
                session["meter_baseline"] = reading[1]
            session["last_meter_at"] = now.isoformat()
            session["last_volume_change_at"] = now.isoformat()
            session["last_flow_at"] = None
            session["flow_seen"] = False
            session["paused_at"] = None
            session["segment_started_at"] = now.isoformat()
            session["confirmed_open"] = False
            self.state.irrigation_last_status = "running"
            self.state.irrigation_last_reason = None
            await self.coordinator._store.async_save(self.state.as_dict())
            try:
                await self._async_command_valve(
                    session["valve_entity_id"], open_valve=True
                )
            except Exception:
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self.coordinator._store.async_save(self.state.as_dict())
                await self._async_close_locked()
                raise
        await self.coordinator.async_request_refresh()

    async def async_set_auto_enabled(self, enabled: bool) -> None:
        """Expose a user-facing, persisted automation master switch."""
        self.state.irrigation_enabled = enabled
        await self.coordinator._store.async_save(self.state.as_dict())
        self._publish_session()
        if (
            not enabled
            and self.active
            and self.state.irrigation_session["source"] == "auto"
        ):
            await self.async_stop("automation_disabled")
        await self.coordinator.async_request_refresh()

    async def _async_maybe_auto_start(self) -> None:
        """Start at most one well-supported recommended session per local day."""
        data = self.coordinator.data
        if (
            not self.configured
            or self.active
            or not self.state.irrigation_enabled
            or not self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
            or data is None
            or data.watering_status != "water_now"
            or not data.watering_recommended
            or data.watering_mm <= 0
            or data.watering_confidence == "low"
            or data.soil_model_confidence == "low"
            or data.forecast_stale
            or data.current_temperature is None
            or data.observed_rain_today_mm is None
        ):
            return
        now = dt_util.now()
        today = dt_util.as_local(now).date().isoformat()
        if self.state.irrigation_last_auto_date == today or (
            self.state.last_watering == today
        ):
            return
        start = dt_util.parse_datetime(data.watering_window_start or "")
        end = dt_util.parse_datetime(data.watering_window_end or "")
        if start is None or end is None or not start <= now <= end:
            return
        try:
            await self.async_start(manual=False)
        except (HomeAssistantError, ServiceValidationError):
            # The regular check will retry only while all prerequisites hold.
            _LOGGER.debug("Automatic irrigation deferred", exc_info=True)

    async def async_start(self, *, manual: bool) -> None:
        """Open a valve only after the mower and meter pass validation."""
        if not self.configured:
            raise ServiceValidationError("No irrigation valve is configured")
        async with self._lock:
            if self.active:
                raise ServiceValidationError("Irrigation is already running")
            if not manual and not self.state.irrigation_enabled:
                raise ServiceValidationError("Automatic irrigation is disabled")
            blocker = self.start_blocker()
            if blocker:
                raise ServiceValidationError(blocker)
            meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
            meter_state = self.hass.states.get(meter_id) if meter_id else None
            meter = _meter_reading(meter_state)
            if not meter:
                if not manual or not self.coordinator.settings.get(
                    CONF_ALLOW_UNMETERED_MANUAL, False
                ):
                    raise ServiceValidationError("A working water meter is required")
                kind, baseline = "timer", 0.0
            else:
                kind, baseline = meter
                # Idle cumulative meters may not publish until water flows.
            now = dt_util.now()
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            # A voluntary manual start with no recommendation runs only for
            # the minimum time; it must not inherit the default 15 mm dose.
            target_mm = (
                self.coordinator.data.watering_mm
                if self.coordinator.data and self.coordinator.data.watering_mm > 0
                else 0.0
            )
            session = {
                "source": "manual" if manual else "auto",
                "valve_entity_id": self.coordinator.settings[CONF_IRRIGATION_VALVE],
                "started_at": now.isoformat(),
                "meter_kind": kind,
                "meter_entity_id": meter_id,
                "meter_baseline": baseline,
                "last_meter_at": now.isoformat(),
                "last_volume_change_at": now.isoformat(),
                "active_seconds": 0.0,
                "segment_started_at": now.isoformat(),
                "paused_at": None,
                "liters": 0.0,
                "target_liters": min(
                    target_mm * area,
                    float(
                        self.coordinator.settings.get(
                            CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
                        )
                    ),
                ),
                "flow_seen": False,
                "confirmed_open": False,
                "last_flow_at": None,
                "closing_reason": None,
            }
            self.state.irrigation_session = session
            self.state.irrigation_last_status = "running"
            self.state.irrigation_last_reason = None
            if not manual:
                self.state.irrigation_last_auto_date = (
                    dt_util.as_local(now).date().isoformat()
                )
            await self.coordinator._store.async_save(self.state.as_dict())
            self._publish_session()
            try:
                await self._async_command_valve(
                    self.coordinator.settings[CONF_IRRIGATION_VALVE], open_valve=True
                )
            except Exception:
                # Even a failed service call may have reached the hardware.
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self.coordinator._store.async_save(self.state.as_dict())
                await self._async_close_locked()
                raise
        await self.coordinator.async_request_refresh()

    async def async_check(self) -> None:
        """Observe flow, enforce interlocks and attempt closure as necessary."""
        async with self._lock:
            session = self.state.irrigation_session
            if session is None:
                return
            now = dt_util.now()
            if session.get("closing_reason"):
                await self._async_close_locked()
                return
            if session.get("paused_at"):
                if self._valve_state() != "off":
                    session["closing_reason"] = "other_valve_open"
                    await self.coordinator._store.async_save(self.state.as_dict())
                    await self._async_close_locked()
                    return
                if (
                    now - dt_util.parse_datetime(session["started_at"])
                ).total_seconds() >= 60 * float(
                    self.coordinator.settings.get(
                        CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                    )
                ):
                    await self._async_stop_locked("maximum_runtime")
                elif not self._mower_is_docked():
                    await self._async_stop_locked("mower_left_dock")
                return
            if not self._mower_is_docked():
                await self._async_stop_locked("mower_left_dock")
                return
            valve_state = self._valve_state()
            if self._other_valve_state() != "off":
                if self._other_valve_state() != "on":
                    await self._async_stop_locked("other_valve_unavailable")
                else:
                    await self._async_pause_locked()
                return
            if valve_state == "on":
                session["confirmed_open"] = True
            if valve_state == "off" and not session.get("confirmed_open"):
                if (
                    now - dt_util.parse_datetime(session["started_at"])
                ).total_seconds() < 30:
                    return
                await self._async_stop_locked("valve_did_not_open")
                return
            if valve_state == "off":
                await self._async_finish_locked("valve_closed_externally")
                return
            started = dt_util.parse_datetime(session["started_at"])
            elapsed = (now - started).total_seconds()
            if elapsed >= 60 * float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                )
            ):
                await self._async_stop_locked("maximum_runtime")
                return
            if self._valve_state() not in {"on", "off"} and elapsed > 30:
                await self._async_stop_locked("valve_unavailable")
                return
            fault = self._sample_meter(session, now)
            if fault:
                await self._async_stop_locked(fault)
                return
            grace = int(
                self.coordinator.settings.get(
                    CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                )
            )
            if session["meter_kind"] != "timer":
                last_flow = dt_util.parse_datetime(session.get("last_flow_at") or "")
                segment_elapsed = (
                    now
                    - dt_util.parse_datetime(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
                if segment_elapsed > grace and (
                    not session["flow_seen"]
                    or last_flow is None
                    or (now - last_flow).total_seconds() > grace
                ):
                    await self._async_stop_locked("no_flow")
                    return
                if session["liters"] >= float(
                    self.coordinator.settings.get(
                        CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
                    )
                ):
                    await self._async_stop_locked("maximum_volume")
                    return
            minimum = (
                60
                * float(
                    self.coordinator.settings.get(
                        CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
                    )
                )
                if session["source"] == "manual"
                else 0
            )
            active_seconds = (
                float(session.get("active_seconds", 0))
                + (
                    now
                    - dt_util.parse_datetime(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
            )
            if active_seconds >= minimum and (
                session["meter_kind"] == "timer"
                or session["liters"] >= session["target_liters"]
            ):
                await self._async_stop_locked("target_reached")
                return
            await self.coordinator._store.async_save(self.state.as_dict())
            self._publish_session()

    async def _async_pause_locked(self) -> None:
        """Close only our valve, retaining a supervised resumable session."""
        session = self.state.irrigation_session
        now = dt_util.now()
        session["active_seconds"] = float(session.get("active_seconds", 0)) + max(
            0,
            (
                now
                - dt_util.parse_datetime(
                    session.get("segment_started_at") or session["started_at"]
                )
            ).total_seconds(),
        )
        session["closing_reason"] = "other_valve_open"
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = "other_valve_open"
        await self.coordinator._store.async_save(self.state.as_dict())
        await self._async_close_locked()

    def _sample_meter(self, session: dict[str, Any], now) -> str | None:
        """Measure incremental water without inventing data across gaps."""
        if session["meter_kind"] == "timer":
            return None
        meter_id = session.get("meter_entity_id") or self.coordinator.settings.get(
            CONF_IRRIGATION_FLOW
        )
        entity = self.hass.states.get(meter_id) if meter_id else None
        reading = _meter_reading(entity)
        if reading is None or reading[0] != session["meter_kind"]:
            return "meter_unavailable"
        reported_at = getattr(entity, "last_reported", None) or entity.last_updated
        maximum_age = max(
            120,
            int(
                self.coordinator.settings.get(
                    CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                )
            ),
        )
        if reading[0] == "rate" and now - reported_at > timedelta(seconds=maximum_age):
            return "meter_stale"
        kind, value = reading
        previous = dt_util.parse_datetime(session["last_meter_at"])
        elapsed = max(0.0, (now - previous).total_seconds())
        if kind == "volume":
            delta = value - session["meter_baseline"]
            if delta < -0.01:
                # Per-session meters can reset to zero as the valve opens.
                if (
                    session["liters"] == 0
                    and (
                        now - dt_util.parse_datetime(session["started_at"])
                    ).total_seconds()
                    < 120
                ):
                    session["meter_baseline"] = value
                    delta = 0.0
                else:
                    return "meter_reset"
            if delta > 0:
                last_change = dt_util.parse_datetime(
                    session.get("last_volume_change_at") or session["started_at"]
                )
                minutes = max((now - last_change).total_seconds() / 60, 1 / 12)
                flow_rate = delta / minutes
                if flow_rate > float(
                    self.coordinator.settings.get(
                        CONF_MAX_FLOW_L_MIN, DEFAULT_MAX_FLOW_L_MIN
                    )
                ):
                    return "excessive_flow"
                session["liters"] += delta
                session["meter_baseline"] = value
                session["last_volume_change_at"] = now.isoformat()
                if flow_rate >= float(
                    self.coordinator.settings.get(
                        CONF_MIN_FLOW_L_MIN, DEFAULT_MIN_FLOW_L_MIN
                    )
                ):
                    session["flow_seen"] = True
                    session["last_flow_at"] = now.isoformat()
        else:
            if value > float(
                self.coordinator.settings.get(
                    CONF_MAX_FLOW_L_MIN, DEFAULT_MAX_FLOW_L_MIN
                )
            ):
                return "excessive_flow"
            if (
                value
                >= float(
                    self.coordinator.settings.get(
                        CONF_MIN_FLOW_L_MIN, DEFAULT_MIN_FLOW_L_MIN
                    )
                )
                and value > 0
            ):
                session["flow_seen"] = True
                session["last_flow_at"] = now.isoformat()
            # The watchdog caps elapsed integration after process stalls.
            session["liters"] += value * min(elapsed, 30) / 60
        session["last_meter_at"] = now.isoformat()
        return None

    async def async_stop(self, reason: str = "stopped_manually") -> None:
        """Always close an owned valve, including after automation is disabled."""
        async with self._lock:
            if self.active:
                await self._async_stop_locked(reason)

    async def _async_stop_locked(self, reason: str) -> None:
        """Persist the closing intent before calling the external switch."""
        session = self.state.irrigation_session
        if (
            self._valve_state() == "on"
            and not session.get("paused_at")
            and self._other_valve_state() == "off"
        ):
            self._sample_meter(session, dt_util.now())
        self.state.irrigation_session["closing_reason"] = reason
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = reason
        await self.coordinator._store.async_save(self.state.as_dict())
        await self._async_close_locked()
        if self.active:
            await self.coordinator.async_request_refresh()

    async def _async_close_locked(self) -> None:
        """Retry closure until the valve actually reports off."""
        if self._valve_state() == "off":
            await self._async_closed_locked()
            return
        try:
            await self._async_command_valve(
                self.state.irrigation_session.get("valve_entity_id")
                or self.coordinator.settings[CONF_IRRIGATION_VALVE],
                open_valve=False,
            )
        except (HomeAssistantError, TimeoutError):
            _LOGGER.exception("Could not close the irrigation valve; will retry")
        if self._valve_state() == "off":
            await self._async_closed_locked()
        else:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{self.coordinator.config_entry.entry_id}_irrigation_valve_stuck",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="irrigation_valve_stuck",
            )

    async def _async_closed_locked(self) -> None:
        """Pause after a competing valve opens; finish other closures."""
        session = self.state.irrigation_session
        ir.async_delete_issue(
            self.hass,
            DOMAIN,
            f"{self.coordinator.config_entry.entry_id}_irrigation_valve_stuck",
        )
        if session["closing_reason"] == "other_valve_open":
            session["paused_at"] = dt_util.now().isoformat()
            session["closing_reason"] = None
            self.state.irrigation_last_status = "paused"
            await self.coordinator._store.async_save(self.state.as_dict())
            self._publish_session()
            await self.coordinator.async_request_refresh()
        else:
            await self._async_finish_locked(session["closing_reason"])

    async def _async_finish_locked(self, reason: str) -> None:
        """Apply measured water once the valve is confirmed closed."""
        session = self.state.irrigation_session
        if session is None:
            return
        # A shared meter may continue changing while our valve is closed.
        liters = (
            round(session["liters"], 2) if session["meter_kind"] != "timer" else None
        )
        self.state.irrigation_session = None
        self.state.irrigation_last_status = (
            "completed" if reason == "target_reached" else "stopped"
        )
        self.state.irrigation_last_reason = reason
        self.state.irrigation_last_liters = liters
        self.state.irrigation_last_auto_date = (
            dt_util.as_local(dt_util.now()).date().isoformat()
        )
        self._recent_owned_until = dt_util.now() + timedelta(minutes=2)
        self._recent_owned_valve_id = session.get("valve_entity_id")
        self.state.irrigation_recent_valve_id = self._recent_owned_valve_id
        self.state.irrigation_recent_until = self._recent_owned_until.isoformat()
        await self.coordinator._store.async_save(self.state.as_dict())
        if liters is not None and liters > 0:
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            await self.coordinator.async_mark_watered(liters / area)
        elif (
            session["meter_kind"] == "timer"
            and session.get("confirmed_open")
            and float(session.get("active_seconds", 0))
            + (
                0
                if session.get("paused_at")
                else (
                    dt_util.now()
                    - dt_util.parse_datetime(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
            )
            >= 60
        ):
            await self.coordinator.async_mark_watered(0, was_wet=True)
        else:
            await self.coordinator.async_request_refresh()

    async def async_shutdown(self) -> bool:
        """Stop an active session before removing the safety watchdog."""
        if self.active:
            await self.async_stop("integration_unloaded")
        if self.active:
            return False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        return True
