"""Owned-valve irrigation state machine, interlocks and measured water accounting.

File: custom_components/rasenpflege_assistent/irrigation.py

The controller serializes start, pause, resume, close and completion using
its own lock. State-change listeners and a local watchdog supervise hardware
independently of the slower weather/model update interval.

Only an owned lawn valve may be commanded. The optional second valve
is a read-only shared-meter interlock. Sessions are persisted before opening,
then live safety conditions are rechecked after awaits. Restarted sessions
close rather than resume; missing measurements are flagged instead of invented.
Completion holds controller then model locks and credits delivered water once.
"""

from __future__ import annotations

import asyncio
import logging
import math
from copy import deepcopy
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, State
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
    CONF_DAILY_WATER_LIMIT,
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
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_RAIN_STOP_MM,
    CONF_SOIL_TEMPERATURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STOP,
    CONF_WEATHER_STOP_DELAY,
    CONF_WEEKLY_WATER_LIMIT,
    CONF_WIND_STOP_M_S,
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

from .calculations import soil_profile
from .everyday import cycle_guidance
from .explanations import reason_text
from .inputs import MeterObservation, meter_observation
from .inputs import meter_reading as _meter_reading
from .insights import aware_time, finite_number
from .planning import (
    allocate_volume,
    consumption_summary,
    next_schedule_time,
    schedule_allowed,
)

_LOGGER = logging.getLogger(__name__)


def _session_timestamp(raw: str) -> datetime:
    """Require a valid aware timestamp in controller-owned session data.

    Session timestamps are created locally. Restored invalid timing fields are
    repaired only for restart closure by async_initialize; they never authorize
    resuming a persisted session. This contract avoids optional-date arithmetic.
    """
    parsed = dt_util.parse_datetime(raw) if isinstance(raw, str) else None
    if parsed is None or parsed.tzinfo is None:
        raise HomeAssistantError("Invalid irrigation session timestamp")
    return parsed


class IrrigationController:
    """Supervise owned watering sessions independently of weather polling."""

    def __init__(self, hass: HomeAssistant, coordinator: LawnCoordinator) -> None:
        """Initialize per-entry controller state.

        Keep controller serialization separate from the coordinator model lock.
        Restore recent valve ownership so late device replies remain supervised
        after completion/restart; never infer ownership from a valve being on.
        """
        self.hass = hass
        self.coordinator = coordinator
        self._lock = asyncio.Lock()
        self._shutting_down = False
        self._storage_error = False
        self._finishing = False
        self._unsubscribers: list[Any] = []
        self._recent_owned_until = dt_util.parse_datetime(
            coordinator.state.irrigation_recent_until or ""
        )
        self._recent_owned_valve_id = coordinator.state.irrigation_recent_valve_id

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
        """Whether the controller currently owns an open or closing valve.

        A paused, closing or finishing session still belongs to the controller.
        Callers must not treat physical valve closure alone as completed
        accounting or permission for a second start.
        """
        return self.state.irrigation_session is not None or self._finishing

    def _meter_observation(
        self, state: State | None, now: datetime | None = None
    ) -> MeterObservation:
        """Share rate age acceptance with input diagnostics and running checks."""
        return meter_observation(
            state,
            now or dt_util.now(),
            int(
                self.coordinator.settings.get(
                    CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                )
            ),
        )

    def _mower_is_docked(self) -> bool:
        """Trust only the configured explicit dock state.

        Standard mower/vacuum entities must explicitly report docked; binary
        dock inputs must report on. Custom text sources use the configured
        safe state. Missing and unknown states never grant permission.
        """
        entity_id = self.coordinator.settings.get(CONF_MOWER_LOCATION)
        state = self.hass.states.get(entity_id) if entity_id else None
        if not entity_id or state is None or state.state in ("unknown", "unavailable"):
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

    def _frost_detected(self) -> bool:
        """Read current HA states before every start, resume and safety check."""
        now = dt_util.now()
        air, _, _ = self.coordinator._read_temperature(now)
        soil = self.coordinator._read_soil_temperature()
        data = self.coordinator.data
        # Retain calculated values only when there is no live replacement.
        if air is None and data:
            air = data.current_temperature
        if soil is None and data:
            soil = data.soil_temperature
        return any(value is not None and value <= 0 for value in (air, soil))

    def budget_details(self, session: dict | None = None) -> dict:
        """Budgets count all recorded watering; incomplete totals block automation.

        Include delivered water from the current session as well as committed
        ledger records. Missing volume or measurement gaps make the relevant
        budget uncertain, blocking automatic starts instead of assuming zero.
        """
        records = list(self.state.water_usage)
        if session:
            records.append(
                {
                    "date": dt_util.as_local(dt_util.now()).date().isoformat(),
                    "liters": session["liters"]
                    if session["meter_kind"] != "timer"
                    else None,
                    "allocations": session.get("allocations", []),
                    "measurement_gap": session.get("measurement_gap", False),
                    "uncertainty_dates": [
                        item["date"]
                        for item in allocate_volume(
                            dt_util.as_local(_session_timestamp(session["started_at"])),
                            dt_util.as_local(dt_util.now()),
                            1,
                        )
                    ]
                    if session.get("measurement_gap")
                    else [],
                }
            )
        summary = consumption_summary(records, dt_util.as_local(dt_util.now()).date())
        remaining = []
        uncertain = False
        for period, key in (
            ("day", CONF_DAILY_WATER_LIMIT),
            ("week", CONF_WEEKLY_WATER_LIMIT),
        ):
            limit = float(self.coordinator.settings.get(key, 0))
            if limit > 0:
                remaining.append(max(0.0, limit - summary[f"{period}_liters"]))
                uncertain |= bool(
                    summary[f"{period}_unmetered_sessions"]
                    or summary[f"{period}_measurement_gap_sessions"]
                )
        return {
            "remaining_liters": min(remaining) if remaining else None,
            "uncertain": uncertain,
            "day_liters": summary["day_liters"],
            "week_liters": summary["week_liters"],
        }

    def _budget_blocker(self, session: dict | None = None) -> str | None:
        budget = self.budget_details(session)
        if budget["uncertain"]:
            return "budget_uncertain"
        if budget["remaining_liters"] is not None and budget["remaining_liters"] <= 0:
            return "water_budget_exhausted"
        return None

    def _closed_session_stop_reason(self, session: dict, now) -> str | None:
        """Check final limits before retaining or resuming a closed session.

        Evaluate completed volume/runtime and automatic budgets at a pause
        boundary, using accumulated physical active time. A satisfied limit
        ends the session rather than reopening it after a soak/interlock pause.
        """
        if (
            now - _session_timestamp(session["started_at"])
        ).total_seconds() >= 60 * float(
            self.coordinator.settings.get(
                CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
            )
        ):
            return "maximum_runtime"
        if session["meter_kind"] != "timer" and session["liters"] >= float(
            self.coordinator.settings.get(
                CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
            )
        ):
            return "maximum_volume"
        if session["source"] == "auto":
            blocker = self._budget_blocker(session)
            if blocker:
                return blocker
        minimum = (
            60
            * float(
                self.coordinator.settings.get(
                    CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
                )
            )
            if session["source"] == "manual" and not session.get("explicit_target")
            else 0
        )
        if float(session.get("active_seconds", 0)) >= minimum and (
            session["meter_kind"] == "timer"
            or session["liters"] >= session["target_liters"]
        ):
            return "target_reached"
        return None

    def _rain_reading(self) -> tuple[str, str, float, str] | None:
        """Read the existing precipitation entity without modifying model sampling."""
        entity_id = (
            self.coordinator.settings.get(CONF_PRECIPITATION_ENTITY)
            or self.coordinator._find_openweathermap_precipitation_entity()
        )
        state = self.hass.states.get(entity_id) if entity_id else None
        if not entity_id or state is None or state.state in {"unknown", "unavailable"}:
            return None
        reported = self.coordinator._reported_at(state)
        if dt_util.now() - reported > timedelta(hours=2):
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        unit = str(state.attributes.get("unit_of_measurement", "mm"))
        if unit not in {"mm", "mm/h", "in", "in/h"}:
            return None
        if unit.startswith("in"):
            value *= 25.4
        mode = self.coordinator.settings.get(CONF_PRECIPITATION_MODE, "auto")
        if mode == "auto":
            mode = (
                "rate"
                if "/h" in unit
                else "cumulative"
                if state.attributes.get("state_class") in {"total", "total_increasing"}
                else "increment"
            )
        return entity_id, mode, value, reported.isoformat()

    def _weather_stop_reason(self, session: dict) -> str | None:
        """Debounce live rain and wind; cumulative rainfall starts at the session edge.

        Use current HA weather/rain inputs during a running automatic session.
        Compare with the session rain baseline where needed so a historical
        daily total is not mistaken for rain that began after opening.
        """
        if not self.coordinator.settings.get(CONF_WEATHER_STOP, True):
            return None
        now = dt_util.now()
        weather = self.coordinator._read_weather_conditions(now)
        wind = weather.get("wind_speed_m_s")
        windy = (
            not weather.get("stale")
            and wind is not None
            and wind >= float(self.coordinator.settings.get(CONF_WIND_STOP_M_S, 8))
        )
        threshold = float(self.coordinator.settings.get(CONF_RAIN_STOP_MM, 0.5))
        rain = self._rain_reading()
        raining = False
        if rain:
            entity_id, mode, value, reported = rain
            previous = session.get("rain_reading")
            if (
                previous
                and previous[:2] == [entity_id, mode]
                and previous[3] != reported
            ):
                if mode == "cumulative":
                    session["rain_since_start_mm"] = float(
                        session.get("rain_since_start_mm", 0)
                    ) + max(0, value - previous[2] if value >= previous[2] else value)
                elif mode == "increment":
                    session["rain_since_start_mm"] = (
                        float(session.get("rain_since_start_mm", 0)) + value
                    )
            session["rain_reading"] = list(rain)
            raining = (
                value >= threshold
                if mode == "rate"
                else float(session.get("rain_since_start_mm", 0)) >= threshold
            )
        else:
            state = self.hass.states.get(
                self.coordinator.settings.get(CONF_WEATHER_ENTITY, "")
            )
            raining = bool(
                state
                and not weather.get("stale")
                and state.state in {"rainy", "pouring", "lightning-rainy"}
            )
        pending = session.setdefault("weather_pending", {})
        reason = None
        for code, detected in (("rain_detected", raining), ("wind_too_strong", windy)):
            if not detected:
                pending.pop(code, None)
                continue
            pending.setdefault(code, now.isoformat())
            since = _session_timestamp(pending[code])
            if (now - since).total_seconds() >= float(
                self.coordinator.settings.get(CONF_WEATHER_STOP_DELAY, 120)
            ):
                reason = reason or code
        return reason

    def _weather_start_blocker(self) -> str | None:
        """Do not open into a currently reported rain or strong-wind condition."""
        old = (dt_util.utcnow() - timedelta(seconds=601)).isoformat()
        return self._weather_stop_reason(
            {"weather_pending": {"rain_detected": old, "wind_too_strong": old}}
        )

    def next_check_details(self) -> dict[str, Any]:
        """Describe local safety rechecks and slower model refresh separately.

        Boundaries are reasons to re-evaluate, not promises that watering starts.
        State events may trigger earlier checks; reads do not schedule work.
        """
        now = dt_util.now()
        boundaries = []
        for reason, raw in (
            ("automation_suspended", self.state.irrigation_suspended_until),
            ("retry_cooldown", self.state.irrigation_retry_after),
            (
                "waiting_for_window",
                self.coordinator.data.watering_window_start
                if self.coordinator.data
                else None,
            ),
        ):
            at = dt_util.parse_datetime(raw or "")
            if at and at.tzinfo is not None and at > now:
                boundaries.append({"at": at.isoformat(), "reason": reason})
        boundaries.sort(key=lambda item: dt_util.parse_datetime(item["at"]) or now)
        from .const import UPDATE_INTERVAL
        from .insights import aware_time

        last_update = aware_time(
            self.coordinator.update_diagnostics()["last_success_at"]
        )
        model_at = max(now, last_update + UPDATE_INTERVAL) if last_update else None
        return {
            "estimated": True,
            "local_check_within_seconds": IRRIGATION_WATCHDOG_INTERVAL.total_seconds()
            if self.configured and not self._shutting_down
            else None,
            "model_refresh_at": model_at.isoformat() if model_at else None,
            "model_interval_minutes": UPDATE_INTERVAL.total_seconds() / 60,
            "waiting_reason": self.automatic_blocker(),
            "boundaries": boundaries,
            "earlier_state_events_possible": True,
        }

    def next_start_details(self) -> dict:
        """Intersect the cached forecast window with schedule, hold and cooldown.

        Intersect forecast suitability with local schedule permission, daily
        locks, retries and suspension. The result is a diagnostic estimate;
        async_start still rechecks all actual start conditions.
        """
        data = self.coordinator.data
        if data is None or data.forecast_stale:
            return {"at": None, "reason": "weather_unavailable", "estimated": True}
        start = dt_util.parse_datetime(data.watering_window_start or "")
        end = dt_util.parse_datetime(data.watering_window_end or "")
        if start is None or end is None:
            return {"at": None, "reason": "no_suitable_window", "estimated": True}
        earliest = max(dt_util.now(), start)
        for value in (
            self.state.irrigation_suspended_until,
            self.state.irrigation_retry_after,
        ):
            at = dt_util.parse_datetime(value or "")
            if at:
                earliest = max(earliest, at)
        # Safety and demand prerequisites can change; do not advertise an
        # executable start while a non-time prerequisite is currently blocked.
        blocker = self.automatic_blocker()
        temporal = {
            "outside_schedule",
            "automation_suspended",
            "retry_cooldown",
            "waiting_for_window",
        }
        if blocker and blocker not in temporal:
            return {"at": None, "reason": blocker, "estimated": True}
        conditions = self.automatic_conditions()
        temporal_conditions = {
            "not_suspended",
            "schedule_allowed",
            "retry_allowed",
            "forecast_window_active",
        }
        failed = [
            key
            for key, passed in conditions.items()
            if not passed and key not in temporal_conditions
        ]
        if failed:
            return {"at": None, "reason": failed[0], "estimated": True}
        candidate = next_schedule_time(
            self.coordinator.settings, dt_util.as_local(earliest), dt_util.as_local(end)
        )
        return {
            "at": candidate.isoformat() if candidate else None,
            "reason": "planned_start" if candidate else "no_schedule_overlap",
            "estimated": True,
        }

    def remaining_time_details(self) -> dict:
        """Estimate completion from current measured flow, including soak pauses.

        Estimate active time from remaining volume and usable flow, then add
        soak delays and report schedule/runtime limits. Missing flow leaves
        the estimate unknown; an ETA is not permission to bypass safety limits.
        """
        session = self.state.irrigation_session
        result: dict[str, Any] = {
            "session_remaining_active_minutes": None,
            "session_estimated_end": None,
            "session_eta_reason": "no_active_session",
            "session_eta_estimated": True,
        }
        if not session:
            return result
        if session.get("closing_reason"):
            result["session_eta_reason"] = "stopping"
            return result
        if session.get("paused_at") and session.get("pause_reason") != "soak_pause":
            result["session_eta_reason"] = "other_valve_open"
            return result
        meter_id = session.get("meter_entity_id")
        meter = self.hass.states.get(meter_id) if meter_id else None
        reading = _meter_reading(meter)
        if self._meter_observation(meter).reason in {"stale", "invalid_timestamp"}:
            result["session_eta_reason"] = "meter_stale"
            return result
        rate = (
            reading[1]
            if reading and reading[0] == "rate" and not session.get("paused_at")
            else session.get("measured_flow_l_min") or session.get("meter_rate_l_min")
        )
        if session["meter_kind"] == "timer":
            active = float(session.get("active_seconds", 0))
            if not session.get("paused_at"):
                active += (
                    dt_util.now()
                    - _session_timestamp(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
            minutes = max(
                0,
                float(
                    self.coordinator.settings.get(
                        CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
                    )
                )
                - active / 60,
            )
        elif (
            not rate
            or rate <= 0
            or not session.get("flow_seen")
            and not session.get("paused_at")
        ):
            result["session_eta_reason"] = "waiting_for_flow"
            return result
        else:
            minutes = max(0, session["target_liters"] - session["liters"]) / rate
            if session["source"] == "manual" and not session.get("explicit_target"):
                active = float(session.get("active_seconds", 0)) + (
                    0
                    if session.get("paused_at")
                    else (
                        dt_util.now()
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds()
                )
                minutes = max(
                    minutes,
                    float(
                        self.coordinator.settings.get(
                            CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
                        )
                    )
                    - active / 60,
                )
        cycle = float(self.coordinator.settings.get("irrigation_cycle_minutes", 0))
        pauses = 0
        if cycle > 0 and minutes > 0:
            segment_minutes = (
                0
                if session.get("paused_at")
                else (
                    dt_util.now()
                    - _session_timestamp(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
                / 60
            )
            first = max(0, cycle - segment_minutes)
            pauses = max(0, math.ceil((minutes - first) / cycle))
        delay = 0.0
        resume = dt_util.parse_datetime(session.get("resume_after") or "")
        if resume:
            delay = max(0, (resume - dt_util.now()).total_seconds() / 60)
        end = dt_util.utcnow() + timedelta(
            minutes=minutes
            + delay
            + pauses
            * float(self.coordinator.settings.get("irrigation_soak_minutes", 15))
        )
        deadline = _session_timestamp(session["started_at"]) + timedelta(
            minutes=float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                )
            )
        )
        if session["source"] == "auto" and not schedule_allowed(
            self.coordinator.settings, dt_util.as_local(end - timedelta(microseconds=1))
        ):
            result["session_remaining_active_minutes"] = round(minutes, 1)
            result["session_eta_reason"] = "schedule_ends_before_target"
            return result
        result.update(
            session_remaining_active_minutes=round(minutes, 1),
            session_estimated_end=end.isoformat() if end <= deadline else None,
            session_eta_reason="estimated_completion"
            if end <= deadline
            else "maximum_runtime_before_target",
        )
        return result

    def _credit_volume(
        self, session: dict, start, end, liters: float, *, estimated=False
    ) -> None:
        """Keep per-day allocations in the same persisted transaction as session liters.

        Split delivered liters across local calendar dates while retaining
        the measured total. A cumulative reading spanning an interval only
        supports an estimated temporal distribution, not exact delivery times.
        """
        allocations = allocate_volume(
            dt_util.as_local(start), dt_util.as_local(end), liters
        )
        session["allocation_estimated"] = session.get(
            "allocation_estimated", False
        ) or (estimated and len(allocations) > 1)
        by_day = {
            item["date"]: item["liters"] for item in session.get("allocations", [])
        }
        for item in allocations:
            by_day[item["date"]] = by_day.get(item["date"], 0) + item["liters"]
        session["allocations"] = [
            {"date": day, "liters": amount} for day, amount in sorted(by_day.items())
        ]

    def start_blocker(self) -> str | None:
        """Return the first actionable reason the controller cannot start.

        Shared manual/automatic interlocks check mower docking, valve state,
        the read-only competing valve, frost and meter validity. Automatic
        starts add recommendation, confidence, schedule and budget checks.
        """
        if self._shutting_down:
            return "homeassistant_stopping"
        if self._storage_error:
            return "storage_error"
        if self._frost_detected():
            return "frost"
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
        if meter_id:
            meter = self.hass.states.get(meter_id)
            reading = _meter_reading(meter)
            if meter is None or reading is None:
                return "meter_unavailable"
            if self._meter_observation(meter).reason in {"stale", "invalid_timestamp"}:
                return "meter_stale"
        return None

    def readiness(self) -> str:
        """Summarize start eligibility for a diagnostic entity."""
        if not self.configured:
            return "not_configured"
        if self.active:
            return self.state.irrigation_last_status
        return self.start_blocker() or "ready"

    def _prepare_opening(self, session: dict) -> str | None:
        """Recheck live inputs and meter at the valve edge after storage awaits.

        Storage and locks can delay opening. Repeat live safety checks at the
        device edge and reset the segment meter baseline there. Initial
        automatic eligibility may expire while waiting; resumed sessions keep
        their existing target but must satisfy current safety conditions.
        """
        if session.get("closing_reason"):
            return session["closing_reason"]
        blocker = self.start_blocker()
        if blocker:
            return blocker
        now = dt_util.now()
        if (
            now - _session_timestamp(session["started_at"])
        ).total_seconds() >= 60 * float(
            self.coordinator.settings.get(
                CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
            )
        ):
            return "maximum_runtime"
        if session["source"] == "auto":
            if not self.state.irrigation_enabled:
                return "automation_disabled"
            temperature, _, _ = self.coordinator._read_temperature(now)
            if temperature is None or self.coordinator._read_weather_conditions(
                now
            ).get("stale", True):
                return "weather_unavailable"
            # Initial eligibility can expire while awaiting storage. Resumes
            # retain their original session target and use live safety gates.
            if int(session.get("cycle_number", 1)) == 1:
                data = self.coordinator.data
                if data is None or data.forecast_stale:
                    return "weather_unavailable"
                if data.observed_rain_today_mm is None:
                    return "rain_unavailable"
                if (
                    data.watering_confidence == "low"
                    or data.soil_model_confidence == "low"
                ):
                    return "low_confidence"
                if (
                    not data.watering_recommended
                    or data.watering_status != "water_now"
                    or data.watering_mm <= 0
                ):
                    return "watering_not_due"
                start = dt_util.parse_datetime(data.watering_window_start or "")
                end = dt_util.parse_datetime(data.watering_window_end or "")
                if start is None or end is None:
                    return "no_suitable_window"
                if now < start:
                    return "waiting_for_window"
                if now >= end:
                    return "window_expired"
            blocker = self._weather_start_blocker() or self._budget_blocker(session)
            if blocker:
                return blocker
            suspended = dt_util.parse_datetime(
                self.state.irrigation_suspended_until or ""
            )
            if suspended and now < suspended:
                return "automation_suspended"
            if not schedule_allowed(self.coordinator.settings, dt_util.as_local(now)):
                return "outside_schedule"
        meter = (
            self.hass.states.get(session["meter_entity_id"])
            if session.get("meter_entity_id")
            else None
        )
        reading = _meter_reading(meter)
        if session["meter_kind"] != "timer":
            if meter is None or reading is None or reading[0] != session["meter_kind"]:
                return "meter_unavailable"
            if meter.attributes.get("unit_of_measurement") != session.get("meter_unit"):
                return "meter_unit_changed"
            session["meter_baseline"] = reading[1]
        # Ignore shared-meter usage and active time while our valve was closed.
        session["segment_initial_liters"] = session["liters"]
        if int(session.get("cycle_number", 1)) > 1:
            session["paused_seconds"] += max(
                0,
                (
                    now - _session_timestamp(session["segment_started_at"])
                ).total_seconds(),
            )
        for key in (
            "last_meter_at",
            "last_volume_change_at",
            "segment_started_at",
            "opening_started_at",
        ):
            session[key] = now.isoformat()
        return None

    def automatic_blocker(self) -> str | None:
        """Explain why an automatic session cannot start right now.

        Return the first failing automatic prerequisite as a stable reason
        code. Readiness diagnostics and start decisions must both account for
        data quality, current weather, budgets and local scheduling.
        """
        if not self.configured:
            return "not_configured"
        if not self.state.irrigation_enabled:
            return "automation_disabled"
        if self.active:
            return "session_active"
        blocker = self.start_blocker()
        if blocker:
            return blocker
        suspended = dt_util.parse_datetime(self.state.irrigation_suspended_until or "")
        if suspended and dt_util.now() < suspended:
            return "automation_suspended"
        weather_blocker = self._weather_start_blocker()
        if weather_blocker:
            return weather_blocker
        budget_blocker = self._budget_blocker()
        if budget_blocker:
            return budget_blocker
        if not schedule_allowed(
            self.coordinator.settings, dt_util.as_local(dt_util.now())
        ):
            return "outside_schedule"
        data = self.coordinator.data
        if data is None:
            return "waiting_for_weather"
        if not self.coordinator.settings.get(CONF_IRRIGATION_FLOW):
            return "meter_required"
        if data.observed_rain_today_mm is None:
            return "rain_unavailable"
        temperature, _, _ = self.coordinator._read_temperature(dt_util.now())
        if (
            data.forecast_stale
            or data.current_temperature is None
            or temperature is None
            or self.coordinator._read_weather_conditions(dt_util.now()).get(
                "stale", True
            )
        ):
            return "weather_unavailable"
        if data.watering_confidence == "low" or data.soil_model_confidence == "low":
            return "low_confidence"
        today = dt_util.as_local(dt_util.now()).date().isoformat()
        if (
            self.state.irrigation_last_auto_date == today
            or self.state.last_watering == today
        ):
            return "already_watered_today"
        retry_after = dt_util.parse_datetime(self.state.irrigation_retry_after or "")
        if retry_after is not None and dt_util.now() < retry_after:
            return "retry_cooldown"
        if (
            data.watering_status != "water_now"
            or not data.watering_recommended
            or data.watering_mm <= 0
        ):
            return "watering_not_due"
        now = dt_util.now()
        start = dt_util.parse_datetime(data.watering_window_start or "")
        end = dt_util.parse_datetime(data.watering_window_end or "")
        if start is None or end is None:
            return "no_suitable_window"
        if now < start:
            return "waiting_for_window"
        if now >= end:
            return "window_expired"
        return None

    def automatic_conditions(self) -> dict[str, bool]:
        """Expose every independently checked start condition together.

        Expose individual prerequisite booleans for diagnostics. These help
        explain a failed decision but do not replace the final live checks
        performed immediately before commanding a valve.
        """
        data = self.coordinator.data
        now = dt_util.now()
        meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
        meter = self.hass.states.get(meter_id) if meter_id else None
        reading = _meter_reading(meter)
        meter_fresh = self._meter_observation(meter).reason == "accepted"
        suspended = dt_util.parse_datetime(self.state.irrigation_suspended_until or "")
        start = (
            dt_util.parse_datetime(data.watering_window_start or "") if data else None
        )
        end = dt_util.parse_datetime(data.watering_window_end or "") if data else None
        today = dt_util.as_local(now).date().isoformat()
        retry = dt_util.parse_datetime(self.state.irrigation_retry_after or "")
        return {
            "configured": self.configured,
            "automation_enabled": self.state.irrigation_enabled,
            "no_active_session": not self.active,
            "homeassistant_running": not self._shutting_down,
            "storage_available": not self._storage_error,
            "mower_docked": self._mower_is_docked(),
            "valve_closed": self._valve_state() == "off",
            "other_valve_closed": self._other_valve_state() == "off",
            "meter_available": reading is not None,
            "meter_fresh": meter_fresh,
            "weather_available": bool(
                data
                and not data.forecast_stale
                and data.current_temperature is not None
                and self.coordinator._read_temperature(now)[0] is not None
                and not self.coordinator._read_weather_conditions(now).get(
                    "stale", True
                )
            ),
            "rain_available": bool(data and data.observed_rain_today_mm is not None),
            "confidence_sufficient": bool(
                data
                and data.watering_confidence != "low"
                and data.soil_model_confidence != "low"
            ),
            "frost_free": not self._frost_detected(),
            "water_budget_available": self._budget_blocker() is None,
            "current_weather_safe": self._weather_start_blocker() is None,
            "not_suspended": suspended is None or now >= suspended,
            "schedule_allowed": schedule_allowed(
                self.coordinator.settings, dt_util.as_local(now)
            ),
            "not_watered_today": self.state.irrigation_last_auto_date != today
            and self.state.last_watering != today,
            "retry_allowed": retry is None or now >= retry,
            "watering_due": bool(
                data
                and data.watering_status == "water_now"
                and data.watering_recommended
                and data.watering_mm > 0
            ),
            "forecast_window_active": bool(start and end and start <= now < end),
        }

    def _emit_event(
        self, phase: str, *, reason: str | None = None, session: dict | None = None
    ) -> None:
        """Provide stable, entry-scoped events for user-owned automations."""
        session = session or self.state.irrigation_session or {}
        self.hass.bus.async_fire(
            f"{DOMAIN}_irrigation",
            {
                "config_entry_id": self.coordinator.config_entry.entry_id,
                "phase": phase,
                "reason": reason,
                "source": session.get("source"),
                "started_at": session.get("started_at"),
                "session_id": session.get("session_id"),
                "target_liters": session.get("target_liters"),
                "reason_text": reason_text(reason, self.hass.config.language)
                if reason
                else None,
                "liters": session.get("liters")
                if session.get("meter_kind") != "timer"
                else None,
                "measurement_gap": session.get("measurement_gap", False),
            },
        )

    async def async_suspend_automation(self, until) -> None:
        """Persist a temporary automation hold; manual starts remain available.

        A new safety hold takes effect in memory before lock/storage waits.
        Close an automatic session before saving; manual sessions remain
        available. A failed hold release restores the prior safety hold.
        """
        if until is not None and until <= dt_util.now():
            raise ServiceValidationError(
                "Suspension must end in the future",
                translation_domain=DOMAIN,
                translation_key="action_8",
            )
        requested = until.isoformat() if until else None
        if until:
            # Apply the safety hold before waiting for either storage lock.
            self.state.irrigation_suspended_until = requested
            session = self.state.irrigation_session
            if session and session["source"] == "auto":
                session["closing_reason"] = "automation_suspended"
                await self._async_close_unsafe_busy_valve()
        async with self._lock:
            previous = self.state.irrigation_suspended_until
            self.state.irrigation_suspended_until = requested
            session = self.state.irrigation_session
            if until and session and session["source"] == "auto":
                await self._async_stop_locked("automation_suspended")
            saved = await self._async_persist_state()
            if not saved and until is None:
                # A failed release keeps the existing safety hold in memory.
                self.state.irrigation_suspended_until = previous
            self._publish_session()
        if not saved:
            raise ServiceValidationError(
                "Suspension could not be saved",
                translation_domain=DOMAIN,
                translation_key="action_9",
            )

    def action_hint(self, language: str) -> str | None:
        """Pair the current blocker with a concrete user action."""
        blocker = self.automatic_blocker()
        hints = {
            "meter_stale": (
                "Durchflusssensor und dessen letzte Meldung prüfen.",
                "Check the flow sensor and its last report.",
            ),
            "meter_unavailable": (
                "Wasserzähler und Verbindung prüfen.",
                "Check the water meter and its connection.",
            ),
            "mower_not_docked": (
                "Mäher zur Station schicken und Stationsstatus prüfen.",
                "Return the mower to its dock and check its dock status.",
            ),
            "other_valve_open": (
                "Warten, bis das zweite Ventil geschlossen ist.",
                "Wait until the other valve is closed.",
            ),
            "other_valve_unavailable": (
                "Statusquelle des zweiten Ventils prüfen.",
                "Check the other valve's state source.",
            ),
            "budget_uncertain": (
                "Unvollständige Verbrauchseinträge prüfen. Automatik wartet bis zum nächsten Budgetzeitraum.",
                "Review incomplete consumption records. Automation waits for the next budget period.",
            ),
            "water_budget_exhausted": (
                "Verbrauchslimit prüfen oder nächsten Budgetzeitraum abwarten.",
                "Review the consumption limit or wait for the next budget period.",
            ),
            "outside_schedule": (
                "Erlaubte Wochentage und Uhrzeiten prüfen.",
                "Review allowed weekdays and hours.",
            ),
            "weather_unavailable": (
                "Wetterentität und Vorhersage prüfen.",
                "Check the weather entity and forecast.",
            ),
            "automation_suspended": (
                "Ende der Automatikpause abwarten oder Pause aufheben.",
                "Wait for the automation hold to end or clear it.",
            ),
            "frost": (
                "Auf frostfreie Luft- und Bodentemperaturen warten.",
                "Wait for frost-free air and soil temperatures.",
            ),
        }
        return (
            hints[blocker][0 if language == "de" else 1]
            if blocker in hints
            else reason_text(blocker, language)
        )

    def cycle_plan_details(self) -> dict[str, Any]:
        """Use owned measured flow only; shared-meter traffic while closed is excluded."""
        session = self.state.irrigation_session
        rate = None
        flow_source = "unknown"
        if (
            session
            and not session.get("paused_at")
            and not session.get("closing_reason")
            and not session.get("measurement_gap")
            and session.get("flow_seen")
            and self._valve_state() == "on"
            and self._other_valve_state() == "off"
        ):
            meter_id = session.get("meter_entity_id") or self.coordinator.settings.get(
                CONF_IRRIGATION_FLOW
            )
            observation = self._meter_observation(
                self.hass.states.get(meter_id) if meter_id else None
            )
            if observation.reason == "accepted":
                rate = finite_number(
                    session.get("measured_flow_l_min")
                    or session.get("meter_rate_l_min")
                )
            if rate is not None and rate > 0:
                flow_source = "owned_session"
        last = self.state.irrigation_last_session
        if (
            (rate is None or rate <= 0)
            and last
            and not last.get("measurement_gap")
            and not last.get("undone")
        ):
            finished = aware_time(last.get("finished_at"))
            amount, seconds = (
                finite_number(last.get("liters")),
                finite_number(last.get("active_seconds")),
            )
            if (
                finished
                and timedelta(0) <= dt_util.now() - finished <= timedelta(days=7)
                and amount is not None
                and amount > 0
                and seconds is not None
                and seconds >= 60
            ):
                rate = amount / (seconds / 60)
                flow_source = "recent_complete_session"
        soil = self.coordinator.settings.get("soil_type", "loamy")
        infiltration = soil_profile(soil)["infiltration_mm_per_hour"]
        infiltration *= (
            0.65 if self.coordinator.settings.get("compaction") == "compacted" else 1.0
        )
        infiltration *= {"flat": 1.0, "gentle": 0.85, "steep": 0.6}.get(
            self.coordinator.settings.get("slope", "flat"), 1.0
        )
        liters = (
            max(0.0, session["target_liters"] - session["liters"])
            if session
            else self.coordinator.data.watering_liters
            if self.coordinator.data
            else 0.0
        )
        maximum_minutes = float(
            self.coordinator.settings.get(
                CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
            )
        )
        if session and (started := aware_time(session.get("started_at"))) is not None:
            maximum_minutes = max(
                0.0,
                maximum_minutes
                - max(0.0, (dt_util.now() - started).total_seconds()) / 60,
            )
        result = cycle_guidance(
            liters=liters,
            area_m2=float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA)),
            flow_l_min=rate,
            infiltration_mm_h=infiltration,
            cycle_minutes=float(
                self.coordinator.settings.get("irrigation_cycle_minutes", 0)
            ),
            soak_minutes=float(
                self.coordinator.settings.get("irrigation_soak_minutes", 0)
            ),
            maximum_minutes=maximum_minutes,
        )
        return {
            **result,
            "flow_l_min": rate,
            "flow_source": flow_source,
            "remaining_runtime_minutes": round(maximum_minutes, 1),
            "amount_basis": "remaining_session_target"
            if session
            else "current_recommendation",
            "cycle_phase_estimated": bool(session),
            "reasons_text": [
                reason_text(code, self.hass.config.language)
                for code in result["review_reasons"]
            ],
        }

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
        reading = _meter_reading(meter)
        return {
            "automatic_blocker": self.automatic_blocker(),
            "next_check": self.next_check_details(),
            "cycle_plan": self.cycle_plan_details(),
            "watering_explanation": dict(self.coordinator.data.watering_explanation)
            if self.coordinator.data
            else {},
            "next_automatic_start": self.next_start_details()["at"],
            "next_start_plan": self.next_start_details(),
            "water_budget": self.budget_details(session),
            "recent_sessions": [
                item
                for item in reversed(self.state.water_usage)
                if item.get("source") == "irrigation"
            ][:10],
            **self.remaining_time_details(),
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
                    dt_util.now() - _session_timestamp(session["started_at"])
                ).total_seconds()
            )
            if session
            else None,
            "session_active_seconds": round(
                float(session.get("active_seconds", 0))
                + (
                    0
                    if session.get("paused_at") or session.get("closing_reason")
                    else (
                        dt_util.now()
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds()
                )
            )
            if session
            else None,
            "session_paused_seconds": round(
                float(session.get("paused_seconds", 0))
                + (
                    (
                        dt_util.now() - _session_timestamp(session["paused_at"])
                    ).total_seconds()
                    if session.get("paused_at")
                    else 0
                )
            )
            if session
            else None,
            "session_measurement_gap": session.get("measurement_gap", False)
            if session
            else None,
            "session_remaining_liters": max(
                0.0, round(session["target_liters"] - session["liters"], 1)
            )
            if session
            and session["target_liters"] > 0
            and session["meter_kind"] != "timer"
            else None,
            "session_progress_percent": min(
                100.0, round(100 * session["liters"] / session["target_liters"], 1)
            )
            if session
            and session["target_liters"] > 0
            and session["meter_kind"] != "timer"
            else None,
            "session_delivered_mm": round(
                session["liters"]
                / float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA)),
                2,
            )
            if session and session["meter_kind"] != "timer"
            else None,
            "storage_error": self._storage_error,
            "automatic_conditions": self.automatic_conditions(),
            "automatic_blockers": [
                key for key, passed in self.automatic_conditions().items() if not passed
            ],
            "automation_suspended_until": self.state.irrigation_suspended_until,
            "session_cycle_number": session.get("cycle_number", 1) if session else None,
            "session_pause_reason": session.get("pause_reason") if session else None,
            "session_resume_after": session.get("resume_after") if session else None,
            "session_flow_l_min": (
                reading[1]
                if reading and reading[0] == "rate"
                else session.get("measured_flow_l_min")
            )
            if session
            and not session.get("paused_at")
            and not session.get("closing_reason")
            and self._valve_state() == "on"
            else None,
            "session_remaining_seconds": max(
                0,
                round(
                    float(
                        self.coordinator.settings.get(
                            CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                        )
                    )
                    * 60
                    - (
                        dt_util.now() - _session_timestamp(session["started_at"])
                    ).total_seconds()
                ),
            )
            if session
            else None,
            "last_session": self.state.irrigation_last_session,
            "last_stop_reason": self.state.irrigation_last_reason,
            "last_session_liters": self.state.irrigation_last_liters,
            "last_active_seconds": self.state.irrigation_last_active_seconds,
            "last_paused_seconds": self.state.irrigation_last_paused_seconds,
            "last_measurement_gap": self.state.irrigation_last_measurement_gap,
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
        self.coordinator.apply_live_irrigation_status(data)
        self.coordinator.async_update_listeners()

    def _report_storage_error(self) -> None:
        if not self._storage_error:
            _LOGGER.error(
                "Irrigation state could not be saved; closure remains active",
            )
        self._storage_error = True
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{self.coordinator.config_entry.entry_id}_irrigation_storage_error",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="irrigation_storage_error",
        )

    def _clear_storage_error(self) -> None:
        self._storage_error = False
        ir.async_delete_issue(
            self.hass,
            DOMAIN,
            f"{self.coordinator.config_entry.entry_id}_irrigation_storage_error",
        )

    async def _async_persist_state(self, *, already_locked: bool = False) -> bool:
        """Persist controller state under the model lock and report write failures.

        Acquire the model lock unless the caller already holds it. Failed
        verified writes create a repair/blocker and return False, allowing
        callers to roll back or retain safe closed state without reopening.
        """
        try:
            if already_locked:
                await self.coordinator._store.async_save(self.state.as_dict())
            else:
                async with self.coordinator._state_lock:
                    await self.coordinator._store.async_save(self.state.as_dict())
        except (OSError, HomeAssistantError):
            self._report_storage_error()
            return False
        self._clear_storage_error()
        return True

    async def _async_command_valve(self, entity_id: str, *, open_valve: bool) -> None:
        """Bound slow device service calls so the watchdog can retry closure.

        Reject commands targeting the second valve even if configuration is
        inconsistent. Bound HA service waits so a slow device cannot prevent
        the watchdog from attempting further safety closure indefinitely.
        """
        if entity_id == self.coordinator.settings.get(CONF_OTHER_VALVE):
            raise ServiceValidationError(
                "The second valve is a read-only input",
                translation_domain=DOMAIN,
                translation_key="action_10",
            )
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
        """Install immediate state checks and a separate safety watchdog.

        Subscribe to relevant HA state changes, shutdown and the local watchdog.
        Any persisted active session is interrupted and closed: a restart
        cannot prove elapsed valve time or water delivered while HA was down.
        """
        self._unsubscribers.append(
            self.hass.bus.async_listen(
                EVENT_HOMEASSISTANT_STOP, self._async_homeassistant_stopping
            )
        )
        inputs = [
            self.coordinator.settings.get(key)
            for key in (
                CONF_IRRIGATION_VALVE,
                CONF_IRRIGATION_FLOW,
                CONF_MOWER_LOCATION,
                CONF_OTHER_VALVE,
                CONF_TEMPERATURE_ENTITY,
                CONF_SOIL_TEMPERATURE_ENTITY,
                CONF_WEATHER_ENTITY,
                CONF_PRECIPITATION_ENTITY,
            )
        ]
        if self.state.irrigation_session:
            inputs.append(self.state.irrigation_session.get("valve_entity_id"))
        inputs.append(self._recent_owned_valve_id)
        inputs.append(self.coordinator._find_openweathermap_precipitation_entity())
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
                cancel_on_shutdown=True,
            )
        )
        self._unsubscribers.append(
            self.coordinator.async_add_listener(self._coordinator_updated)
        )
        if self.active:
            session = self.state.irrigation_session
            if session is not None:
                repaired = []
                for key in (
                    "started_at",
                    "segment_started_at",
                    "last_meter_at",
                    "paused_at",
                    "closed_at",
                    "opening_started_at",
                    "last_volume_change_at",
                ):
                    value = session.get(key)
                    required = key in {"started_at", "last_meter_at"}
                    if value is None and not required:
                        # An absent closed edge must be established by physical closure.
                        if key == "closed_at":
                            session.pop(key, None)
                        continue
                    parsed = (
                        dt_util.parse_datetime(value)
                        if isinstance(value, str)
                        else None
                    )
                    if (
                        parsed is None
                        or parsed.tzinfo is None
                        or parsed > dt_util.utcnow()
                    ):
                        session[key] = dt_util.utcnow().isoformat()
                        repaired.append(key)
                if repaired:
                    session["timing_repaired"] = repaired
                    session["measurement_gap"] = True
            # A restart cannot prove how long the valve was open or how much
            # water was delivered. Close it instead of resuming an old timer.
            self.state.irrigation_session["measurement_gap"] = True
            await self.async_stop("interrupted_by_restart")
        await self._async_close_late_open()

    async def _async_homeassistant_stopping(self, _event) -> None:
        """Close owned watering before the regular HA shutdown completes."""
        self._shutting_down = True
        await self._async_close_unsafe_busy_valve()
        await self.async_stop("homeassistant_stopping")
        if not self.active:
            self.detach()

    async def _async_input_changed(self, _event) -> None:
        """Check mower, valve and meter immediately when their state changes."""
        await self._async_close_unsafe_busy_valve()
        await self.async_check()
        await self._async_close_late_open()
        self._publish_session()

    async def _async_close_unsafe_busy_valve(self) -> None:
        """Allow physical safety closure while a controller write holds its lock.

        This path may command immediate physical closure while the ordinary
        controller lock is busy. It handles unsafe live inputs before waiting
        for bookkeeping/storage; serialized checks later finish accounting.
        """
        session = self.state.irrigation_session
        if not self._lock.locked() or session is None or self._valve_state() != "on":
            return
        now = dt_util.now()
        unsafe = (
            self._shutting_down
            or bool(session.get("closing_reason"))
            or bool(session.get("paused_at"))
            or self._frost_detected()
            or not self._mower_is_docked()
            or self._other_valve_state() != "off"
            or (now - _session_timestamp(session["started_at"])).total_seconds()
            >= 60
            * float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                )
            )
        )
        if session["source"] == "auto":
            suspended = dt_util.parse_datetime(
                self.state.irrigation_suspended_until or ""
            )
            unsafe = unsafe or (
                not self.state.irrigation_enabled
                or bool(suspended and now < suspended)
                or not schedule_allowed(
                    self.coordinator.settings, dt_util.as_local(now)
                )
                or self._weather_stop_reason(session) is not None
            )
        if not session.get("paused_at") and self._other_valve_state() == "off":
            # Sampling has no awaits and must happen before physical closure:
            # later shared-meter reports cannot safely be assigned to this lawn.
            fault = self._sample_meter(session, now)
            reason = fault
            if fault:
                session["measurement_gap"] = True
            if session["meter_kind"] != "timer":
                if session["liters"] >= float(
                    self.coordinator.settings.get(
                        CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
                    )
                ):
                    reason = reason or "maximum_volume"
                grace = float(
                    self.coordinator.settings.get(
                        CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                    )
                )
                last_flow = dt_util.parse_datetime(session.get("last_flow_at") or "")
                segment = _session_timestamp(session["segment_started_at"])
                if (now - segment).total_seconds() > grace and (
                    not session["flow_seen"]
                    or last_flow is None
                    or (now - last_flow).total_seconds() > grace
                ):
                    reason = reason or "no_flow"
            if session["source"] == "auto":
                reason = reason or self._budget_blocker(session)
            active_seconds = float(session.get("active_seconds", 0)) + max(
                0,
                (
                    now - _session_timestamp(session["segment_started_at"])
                ).total_seconds(),
            )
            minimum = (
                60
                * float(
                    self.coordinator.settings.get(
                        CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
                    )
                )
                if session["source"] == "manual" and not session.get("explicit_target")
                else 0
            )
            if active_seconds >= minimum and (
                session["meter_kind"] == "timer"
                or session["liters"] >= session["target_liters"]
            ):
                reason = reason or "target_reached"
            if reason:
                session["closing_reason"] = session.get("closing_reason") or reason
                unsafe = True
        if unsafe:
            session["confirmed_open"] = True
            session["ever_confirmed_open"] = True
            if self._other_valve_state() != "off" and session["meter_kind"] != "timer":
                session["measurement_gap"] = True
            try:
                # Final model/journal credits remain serialized; physical
                # turn-off may bypass a pending storage operation.
                await self._async_command_valve(
                    session["valve_entity_id"], open_valve=False
                )
            except (HomeAssistantError, TimeoutError):
                _LOGGER.exception(
                    "Could not close unsafe irrigation during a pending write"
                )

    async def _async_close_late_open(self) -> None:
        """Close an on report that arrived after a stopped owned session.

        A timed-out/cancelled service can still complete at the device later.
        Recent ownership lets the controller close that late opening without
        taking control of arbitrary valves opened by other automations.
        """
        if (
            self._recent_owned_until is not None
            and dt_util.now() >= self._recent_owned_until
        ):
            self._recent_owned_until = None
            self._recent_owned_valve_id = None
            self.state.irrigation_recent_valve_id = None
            self.state.irrigation_recent_until = None
            await self._async_persist_state()
            return
        recent_valve = (
            self.hass.states.get(self._recent_owned_valve_id)
            if self._recent_owned_valve_id
            else None
        )
        if (
            not self.active
            and self._recent_owned_until is not None
            and dt_util.now() < self._recent_owned_until
            and self._recent_owned_valve_id
            and recent_valve is not None
            and recent_valve.state == "on"
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
        """Enforce a maximum duration even without new state events.

        Run local safety, late-open, resume and start checks on a short timer.
        This path uses cached/current HA state and does not add regular
        weather-provider requests.
        """
        await self._async_close_unsafe_busy_valve()
        # Check physical safety before any retry of a failed storage write.
        await self.async_check()
        await self._async_close_late_open()
        if self._storage_error:
            async with self._lock:
                await self._async_persist_state()
        session = self.state.irrigation_session
        if session and session.get("paused_at"):
            await self._async_maybe_resume()
        elif not self.active:
            await self._async_maybe_auto_start()
        if self.active:
            self._publish_session()

    def _coordinator_updated(self) -> None:
        """Schedule automatic decisions after a completed weather update."""
        if self._shutting_down:
            return
        self.hass.async_create_task(
            self._async_maybe_auto_start(), "lawn_irrigation_auto_check"
        )

    async def _async_maybe_resume(self) -> None:
        """Resume an owned session only when every interlock is safe again.

        Keep the existing session/target and finish already satisfied limits
        before attempting another segment. Recheck all interlocks, persist
        the resumed state, then repeat live conditions at the opening edge.
        """
        async with self._lock:
            session = self.state.irrigation_session
            if self._shutting_down or session is None or not session.get("paused_at"):
                return
            now = dt_util.now()
            terminal_reason = self._closed_session_stop_reason(session, now)
            if terminal_reason:
                await self._async_stop_locked(terminal_reason)
                return
            resume_after = dt_util.parse_datetime(session.get("resume_after") or "")
            if resume_after and now < resume_after:
                return
            if session["source"] == "auto":
                weather_reason = (
                    self._weather_start_blocker() or self._weather_stop_reason(session)
                )
                if weather_reason:
                    await self._async_stop_locked(weather_reason)
                    return
                budget_reason = self._budget_blocker(session)
                if budget_reason:
                    await self._async_stop_locked(budget_reason)
                    return
                suspended = dt_util.parse_datetime(
                    self.state.irrigation_suspended_until or ""
                )
                if suspended and now < suspended:
                    await self._async_stop_locked("automation_suspended")
                    return
                if not schedule_allowed(
                    self.coordinator.settings, dt_util.as_local(now)
                ):
                    await self._async_stop_locked("outside_schedule")
                    return
            if (
                now - _session_timestamp(session["started_at"])
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
            meter_state = self.hass.states.get(meter_id) if meter_id else None
            if (
                meter_state is not None
                and "meter_unit" in session
                and meter_state.attributes.get("unit_of_measurement")
                != session["meter_unit"]
            ):
                await self._async_stop_locked("meter_unit_changed")
                return
            reading = (
                _meter_reading(self.hass.states.get(meter_id)) if meter_id else None
            )
            if session["meter_kind"] != "timer" and (
                reading is None or reading[0] != session["meter_kind"]
            ):
                return
            previous_session = deepcopy(session)
            if reading is not None:
                session["meter_baseline"] = reading[1]
            session["paused_seconds"] = (
                float(session.get("paused_seconds", 0))
                + (now - _session_timestamp(session["paused_at"])).total_seconds()
            )
            session["meter_rate_l_min"] = 0.0
            session["last_meter_at"] = now.isoformat()
            session["last_volume_change_at"] = now.isoformat()
            session["last_flow_at"] = None
            session["flow_seen"] = False
            session["paused_at"] = None
            session["resume_after"] = None
            session["pause_reason"] = None
            session["cycle_number"] = int(session.get("cycle_number", 1)) + 1
            session["segment_started_at"] = now.isoformat()
            session["opening_started_at"] = now.isoformat()
            session["segment_accounted"] = False
            session["confirmed_open"] = False
            self.state.irrigation_last_status = "running"
            self.state.irrigation_last_reason = None
            if not await self._async_persist_state():
                self.state.irrigation_session = previous_session
                self.state.irrigation_last_status = "paused"
                self.state.irrigation_last_reason = "storage_error"
                self._publish_session()
                return
            blocker = self._prepare_opening(session)
            if blocker:
                await self._async_stop_locked(blocker)
                return
            try:
                await self._async_command_valve(
                    session["valve_entity_id"], open_valve=True
                )
            except (Exception, asyncio.CancelledError):
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self._async_close_locked()
                if self.active:
                    await self._async_persist_state()
                raise
        self._emit_event("resumed")
        await self.async_check()
        await self.coordinator.async_request_refresh()

    async def async_set_auto_enabled(self, enabled: bool) -> None:
        """Expose a user-facing, persisted automation master switch.

        Disable automatic watering in memory before any await so ongoing
        safety checks see the request immediately. Failed enabling rolls back;
        failed disabling remains safely off and reports the storage failure.
        """
        if not enabled:
            # A disable request must reach physical safety before any storage
            # await, including another operation already holding our lock.
            self.state.irrigation_enabled = False
            session = self.state.irrigation_session
            if session and session["source"] == "auto":
                session["closing_reason"] = "automation_disabled"
                await self._async_close_unsafe_busy_valve()
        async with self._lock:
            previous = self.state.irrigation_enabled
            self.state.irrigation_enabled = enabled
            session = self.state.irrigation_session
            if not enabled and session and session["source"] == "auto":
                await self._async_stop_locked("automation_disabled")
            saved = await self._async_persist_state()
            if not saved and enabled and self.state.irrigation_enabled:
                self.state.irrigation_enabled = previous
            self._publish_session()
        await self.coordinator.async_request_refresh()
        if not saved:
            raise ServiceValidationError(
                "Automation setting could not be saved",
                translation_domain=DOMAIN,
                translation_key="action_21",
            )

    async def _async_maybe_auto_start(self) -> None:
        """Start at most one well-supported recommended session per local day."""
        if self.automatic_blocker() is not None:
            return
        try:
            await self.async_start(manual=False)
        except (HomeAssistantError, ServiceValidationError):
            # The regular check will retry only while all prerequisites hold.
            _LOGGER.debug("Automatic irrigation deferred", exc_info=True)

    async def async_start(
        self,
        *,
        manual: bool,
        target_liters: float | None = None,
        target_mm: float | None = None,
    ) -> None:
        """Open a valve only after the mower and meter pass validation.

        The controller lock prevents duplicate sessions. Build and persist
        ownership/targets before the opening command, then recheck eligibility
        after storage waits. Cancellation or opening failure must enter the
        close path because the device may still execute a delayed command.
        """
        if target_liters is not None and target_mm is not None:
            raise ServiceValidationError(
                "Choose either liters or millimeters",
                translation_domain=DOMAIN,
                translation_key="action_11",
            )
        if not manual and (target_liters is not None or target_mm is not None):
            raise ServiceValidationError(
                "Explicit targets are manual only",
                translation_domain=DOMAIN,
                translation_key="action_12",
            )
        for value in (target_liters, target_mm):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ServiceValidationError(
                    "Target must be finite and positive",
                    translation_domain=DOMAIN,
                    translation_key="action_13",
                )
        explicit_target = target_liters is not None or target_mm is not None
        if not self.configured:
            raise ServiceValidationError(
                "No irrigation valve is configured",
                translation_domain=DOMAIN,
                translation_key="action_14",
            )
        async with self._lock:
            if self.active:
                raise ServiceValidationError(
                    "Irrigation is already running",
                    translation_domain=DOMAIN,
                    translation_key="action_15",
                )
            if not manual and not self.state.irrigation_enabled:
                raise ServiceValidationError(
                    "Automatic irrigation is disabled",
                    translation_domain=DOMAIN,
                    translation_key="action_16",
                )
            blocker = self.start_blocker() if manual else self.automatic_blocker()
            if blocker:
                raise ServiceValidationError(
                    blocker,
                    translation_domain=DOMAIN,
                    translation_key=f"irrigation_blocked_{blocker}",
                )
            meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
            meter_state = self.hass.states.get(meter_id) if meter_id else None
            meter = _meter_reading(meter_state)
            if not meter:
                if not manual or not self.coordinator.settings.get(
                    CONF_ALLOW_UNMETERED_MANUAL, False
                ):
                    raise ServiceValidationError(
                        "A working water meter is required",
                        translation_domain=DOMAIN,
                        translation_key="action_17",
                    )
                kind, baseline = "timer", 0.0
            else:
                kind, baseline = meter
                # Idle cumulative meters may not publish until water flows.
            if explicit_target and kind == "timer":
                raise ServiceValidationError(
                    "A requested volume requires a working meter",
                    translation_domain=DOMAIN,
                    translation_key="action_18",
                )
            now = dt_util.now()
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            # A voluntary manual start with no recommendation runs only for
            # the minimum time; it must not inherit the default 15 mm dose.
            recommended_mm = (
                self.coordinator.data.watering_mm
                if self.coordinator.data and self.coordinator.data.watering_mm > 0
                else 0.0
            )
            requested_liters = (
                target_liters
                if target_liters is not None
                else target_mm * area
                if target_mm is not None
                else recommended_mm * area
            )
            maximum_liters = float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
                )
            )
            if not manual:
                remaining = self.budget_details()["remaining_liters"]
                if remaining is not None:
                    requested_liters = min(requested_liters, remaining)
            if explicit_target and requested_liters > maximum_liters:
                raise ServiceValidationError(
                    "Requested amount exceeds the safety volume limit",
                    translation_domain=DOMAIN,
                    translation_key="action_19",
                )
            initial_rain = self._rain_reading()
            session = {
                "session_id": uuid4().hex,
                "allocations": [],
                "rain_reading": list(initial_rain) if initial_rain else None,
                "explicit_target": explicit_target,
                "cycle_number": 1,
                "pause_reason": None,
                "resume_after": None,
                "source": "manual" if manual else "auto",
                "valve_entity_id": self.coordinator.settings[CONF_IRRIGATION_VALVE],
                "started_at": now.isoformat(),
                "meter_kind": kind,
                "meter_entity_id": meter_id,
                "meter_unit": (
                    meter_state.attributes.get("unit_of_measurement")
                    if meter_state
                    else None
                ),
                "meter_baseline": baseline,
                "meter_rate_l_min": 0.0,
                "last_meter_at": now.isoformat(),
                "last_volume_change_at": now.isoformat(),
                "active_seconds": 0.0,
                "paused_seconds": 0.0,
                "measurement_gap": False,
                "segment_started_at": now.isoformat(),
                "segment_accounted": False,
                "paused_at": None,
                "liters": 0.0,
                "target_liters": min(
                    requested_liters,
                    float(
                        self.coordinator.settings.get(
                            CONF_MAX_IRRIGATION_LITERS, DEFAULT_MAX_IRRIGATION_LITERS
                        )
                    ),
                ),
                "flow_seen": False,
                "confirmed_open": False,
                "ever_confirmed_open": False,
                "last_flow_at": None,
                "closing_reason": None,
            }
            self.state.irrigation_session = session
            self.state.irrigation_last_status = "running"
            self.state.irrigation_last_reason = None
            if not manual:
                self.state.irrigation_retry_after = (
                    dt_util.as_utc(now) + timedelta(minutes=30)
                ).isoformat()
            if not await self._async_persist_state():
                self.state.irrigation_session = None
                self.state.irrigation_last_status = "stopped"
                self.state.irrigation_last_reason = "storage_error"
                self._publish_session()
                raise ServiceValidationError(
                    "Irrigation state could not be saved",
                    translation_domain=DOMAIN,
                    translation_key="action_20",
                )
            self._publish_session()
            blocker = self._prepare_opening(session)
            if blocker:
                await self._async_stop_locked(blocker)
                raise ServiceValidationError(
                    blocker,
                    translation_domain=DOMAIN,
                    translation_key=f"irrigation_blocked_{blocker}",
                )
            try:
                await self._async_command_valve(
                    self.coordinator.settings[CONF_IRRIGATION_VALVE], open_valve=True
                )
            except (Exception, asyncio.CancelledError):
                # Even a failed service call may have reached the hardware.
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self._async_close_locked()
                if self.active:
                    await self._async_persist_state()
                raise
        # Inputs can change while the opening service call is awaiting hardware.
        self._emit_event("started")
        await self.async_check()
        await self.coordinator.async_request_refresh()

    async def async_check(self) -> None:
        """Observe flow, enforce interlocks and attempt closure as necessary.

        Order immediate safety reasons before routine target/cycle handling.
        Track confirmation of physical opening, sample owned meter intervals
        and close on faults/limits. Paused sessions remain supervised, but
        meter readings while another consumer runs are not lawn consumption.
        """
        async with self._lock:
            session = self.state.irrigation_session
            if session is None:
                return
            now = dt_util.now()
            if session.get("closing_reason"):
                await self._async_close_locked()
                return
            if self._frost_detected():
                await self._async_stop_locked("frost")
                return
            if session["source"] == "auto":
                weather_reason = self._weather_stop_reason(session)
                if weather_reason:
                    await self._async_stop_locked(weather_reason)
                    return
                budget_reason = self._budget_blocker(session)
                if budget_reason:
                    await self._async_stop_locked(budget_reason)
                    return
                suspended = dt_util.parse_datetime(
                    self.state.irrigation_suspended_until or ""
                )
                if suspended and now < suspended:
                    await self._async_stop_locked("automation_suspended")
                    return
                if not schedule_allowed(
                    self.coordinator.settings, dt_util.as_local(now)
                ):
                    await self._async_stop_locked("outside_schedule")
                    return
            if session.get("paused_at"):
                if self._valve_state() != "off":
                    session["closing_reason"] = (
                        session.get("pause_reason") or "other_valve_open"
                    )
                    await self._async_close_locked()
                    if self._valve_state() != "off":
                        await self._async_persist_state()
                    return
                if (
                    now - _session_timestamp(session["started_at"])
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
                session["ever_confirmed_open"] = True
            if valve_state == "off" and not session.get("confirmed_open"):
                if (
                    now
                    - _session_timestamp(
                        session.get("opening_started_at") or session["started_at"]
                    )
                ).total_seconds() < 30:
                    return
                await self._async_stop_locked("valve_did_not_open")
                return
            if valve_state == "off":
                valve = self.hass.states.get(session["valve_entity_id"])
                assert valve is not None
                closed_at = min(now, valve.last_changed)
                meter_id = session.get("meter_entity_id")
                meter = self.hass.states.get(meter_id) if meter_id else None
                reported = (
                    (getattr(meter, "last_reported", None) or meter.last_updated)
                    if meter
                    else None
                )
                if reported is not None and reported <= closed_at:
                    if self._sample_meter(session, closed_at):
                        session["measurement_gap"] = True
                elif session["meter_kind"] != "timer":
                    session["measurement_gap"] = True
                await self._async_finish_locked("valve_closed_externally")
                return
            started = _session_timestamp(session["started_at"])
            elapsed = (now - started).total_seconds()
            if elapsed >= 60 * float(
                self.coordinator.settings.get(
                    CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                )
            ):
                await self._async_stop_locked("maximum_runtime")
                return
            opening_elapsed = (
                now
                - _session_timestamp(
                    session.get("opening_started_at") or session["started_at"]
                )
            ).total_seconds()
            if self._valve_state() not in {"on", "off"} and opening_elapsed > 30:
                await self._async_stop_locked("valve_unavailable")
                return
            fault = self._sample_meter(session, now)
            if fault:
                session["measurement_gap"] = True
                await self._async_stop_locked(fault)
                return
            budget_reason = (
                self._budget_blocker(session) if session["source"] == "auto" else None
            )
            if budget_reason:
                await self._async_stop_locked(budget_reason)
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
                    - _session_timestamp(
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
                if session["source"] == "manual" and not session.get("explicit_target")
                else 0
            )
            active_seconds = (
                float(session.get("active_seconds", 0))
                + (
                    now
                    - _session_timestamp(
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
            cycle = float(self.coordinator.settings.get("irrigation_cycle_minutes", 0))
            if (
                cycle > 0
                and (
                    now
                    - _session_timestamp(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
                >= cycle * 60
            ):
                await self._async_pause_locked("soak_pause")
                return
            await self._async_persist_state()
            self._publish_session()

    async def _async_pause_locked(self, reason: str = "other_valve_open") -> None:
        """Close only our valve, retaining a supervised resumable session.

        Request physical closure for a soak or competing-valve pause. Do not
        finalize segment duration at the request timestamp: the device may
        deliver more water before its off state is confirmed.
        """
        session = self.state.irrigation_session
        now = dt_util.now()
        if self._valve_state() == "on":
            session["confirmed_open"] = True
            session["ever_confirmed_open"] = True
        # A shared reading reported after the other valve opened cannot be
        # assigned to the lawn. Keep only measurements from before that edge.
        meter_id = session.get("meter_entity_id")
        meter = self.hass.states.get(meter_id) if meter_id else None
        other_id = self.coordinator.settings.get(CONF_OTHER_VALVE)
        other = self.hass.states.get(other_id) if other_id else None
        if session["meter_kind"] != "timer" and self._valve_state() == "on":
            if meter and (
                reason == "soak_pause"
                or (
                    other
                    and (getattr(meter, "last_reported", None) or meter.last_updated)
                    <= other.last_changed
                )
            ):
                fault = self._sample_meter(session, now)
                if fault:
                    session["measurement_gap"] = True
            else:
                session["measurement_gap"] = True
        session["pause_reason"] = reason
        session["closing_reason"] = reason
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = reason
        await self._async_close_locked()
        if self.active:
            await self._async_persist_state()

    def _sample_meter(self, session: dict[str, Any], now) -> str | None:
        """Measure incremental water without inventing data across gaps.

        Cumulative meters use positive baseline differences. A reset at the
        start of an otherwise uncredited segment is accepted; later resets
        are faults. Rate meters hold the previous rate to the report edge,
        then apply the new rate, limiting extrapolation and marking gaps.
        """
        if session["meter_kind"] == "timer":
            return None
        meter_id = session.get("meter_entity_id") or self.coordinator.settings.get(
            CONF_IRRIGATION_FLOW
        )
        entity = self.hass.states.get(meter_id) if meter_id else None
        if (
            entity is not None
            and "meter_unit" in session
            and entity.attributes.get("unit_of_measurement") != session["meter_unit"]
        ):
            return "meter_unit_changed"
        reading = _meter_reading(entity)
        if entity is None or reading is None or reading[0] != session["meter_kind"]:
            return "meter_unavailable"
        reported_at = getattr(entity, "last_reported", None) or entity.last_updated
        if self._meter_observation(entity, now).reason in {
            "stale",
            "invalid_timestamp",
        }:
            return "meter_stale"
        kind, value = reading
        previous = _session_timestamp(session["last_meter_at"])
        if kind == "volume":
            delta = value - session["meter_baseline"]
            if delta < -0.01:
                # Per-session meters can reset to zero as the valve opens.
                if (
                    session["liters"] == session.get("segment_initial_liters", 0)
                    and (
                        now
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds()
                    < 120
                ):
                    session["meter_baseline"] = value
                    delta = 0.0
                else:
                    return "meter_reset"
            if delta > 0:
                last_change = _session_timestamp(
                    session.get("last_volume_change_at") or session["started_at"]
                )
                minutes = max((now - last_change).total_seconds() / 60, 1 / 12)
                flow_rate = delta / minutes
                session["measured_flow_l_min"] = round(flow_rate, 3)
                self._credit_volume(session, last_change, now, delta, estimated=True)
                session["liters"] += delta
                session["meter_baseline"] = value
                session["last_volume_change_at"] = now.isoformat()
                if flow_rate > float(
                    self.coordinator.settings.get(
                        CONF_MAX_FLOW_L_MIN, DEFAULT_MAX_FLOW_L_MIN
                    )
                ):
                    return "excessive_flow"
                if flow_rate >= float(
                    self.coordinator.settings.get(
                        CONF_MIN_FLOW_L_MIN, DEFAULT_MIN_FLOW_L_MIN
                    )
                ):
                    session["flow_seen"] = True
                    session["last_flow_at"] = now.isoformat()
        else:
            segment_start = _session_timestamp(
                session.get("segment_started_at") or session["started_at"]
            )
            if reported_at <= segment_start:
                # An old non-zero shared-meter rate is not proof of lawn flow.
                session["meter_rate_l_min"] = 0.0
                session["last_meter_at"] = now.isoformat()
                return None
            if value > float(
                self.coordinator.settings.get(
                    CONF_MAX_FLOW_L_MIN, DEFAULT_MAX_FLOW_L_MIN
                )
            ):
                # The spike is unsafe, but the prior valid rate still covers
                # the interval before its report. Do not discard known water.
                bounded_start = max(previous, now - timedelta(seconds=30))
                edge = max(bounded_start, min(now, reported_at))
                liters = (
                    float(session.get("meter_rate_l_min", 0))
                    * (edge - bounded_start).total_seconds()
                    / 60
                )
                self._credit_volume(session, bounded_start, edge, liters)
                session["liters"] += liters
                session["last_meter_at"] = now.isoformat()
                session["meter_rate_l_min"] = 0.0
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
                session["last_flow_at"] = reported_at.isoformat()
            # Hold each rate forward to its report edge; never apply a new
            # zero or spike retroactively to the whole preceding interval.
            if now - previous > timedelta(seconds=30):
                session["measurement_gap"] = True
            bounded_start = max(previous, now - timedelta(seconds=30))
            edge = max(bounded_start, min(now, reported_at))
            old_rate = float(session.get("meter_rate_l_min", 0.0))
            old_liters = old_rate * (edge - bounded_start).total_seconds() / 60
            new_liters = value * (now - edge).total_seconds() / 60
            self._credit_volume(session, bounded_start, edge, old_liters)
            self._credit_volume(session, edge, now, new_liters)
            session["liters"] += old_liters + new_liters
            session["meter_rate_l_min"] = value
        session["last_meter_at"] = now.isoformat()
        return None

    async def async_stop(self, reason: str = "stopped_manually") -> None:
        """Always close an owned valve, including after automation is disabled."""
        session = self.state.irrigation_session
        if self._lock.locked() and session is not None:
            session["closing_reason"] = reason
            await self._async_close_unsafe_busy_valve()
        async with self._lock:
            if self.state.irrigation_session is not None:
                await self._async_stop_locked(reason)

    async def _async_stop_locked(self, reason: str) -> None:
        """Close hardware before awaiting maintenance or storage writes.

        Record a terminal reason and attempt closure while the controller
        lock is held. Failure retains session ownership for watchdog retries;
        it must not be converted into a successful completion.
        """
        session = self.state.irrigation_session
        if self._valve_state() == "on":
            session["confirmed_open"] = True
            session["ever_confirmed_open"] = True
        if (
            reason != "interrupted_by_restart"
            and self._valve_state() == "on"
            and not session.get("paused_at")
            and self._other_valve_state() == "off"
            and self._sample_meter(session, dt_util.now())
        ):
            session["measurement_gap"] = True
        self.state.irrigation_session["closing_reason"] = reason
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = reason
        await self._async_close_locked()
        if self.active:
            await self._async_persist_state()
        if self.active:
            await self.coordinator.async_request_refresh()

    async def _async_close_locked(self) -> None:
        """Retry closure until the valve actually reports off.

        A close service response alone does not prove the valve is off.
        Inspect the reported state and keep the session/repair active when
        physical closure remains unconfirmed.
        """
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
        """Pause after a competing valve opens; finish other closures.

        Use the physical off timestamp to finish the active segment exactly
        once. Safely sample the final meter edge, then either finish terminal
        conditions or establish pause/resume timing from actual closure.
        """
        session = self.state.irrigation_session
        ir.async_delete_issue(
            self.hass,
            DOMAIN,
            f"{self.coordinator.config_entry.entry_id}_irrigation_valve_stuck",
        )
        if session["closing_reason"] in {"other_valve_open", "soak_pause"}:
            fault = None
            valve = self.hass.states.get(session["valve_entity_id"])
            closed_at = (
                min(dt_util.now(), valve.last_changed)
                if valve and valve.state == "off"
                else dt_util.now()
            )
            if not session.get("segment_accounted"):
                meter_id = session.get("meter_entity_id")
                meter = self.hass.states.get(meter_id) if meter_id else None
                if session["meter_kind"] != "timer":
                    if (
                        meter
                        and self._other_valve_state() == "off"
                        and self.coordinator._reported_at(meter) <= closed_at
                    ):
                        fault = self._sample_meter(session, closed_at)
                        if fault:
                            session["measurement_gap"] = True
                    else:
                        session["measurement_gap"] = True
                session["active_seconds"] = float(
                    session.get("active_seconds", 0)
                ) + max(
                    0,
                    (
                        closed_at
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds(),
                )
                session["segment_accounted"] = True
            terminal_reason = fault or self._closed_session_stop_reason(
                session, closed_at
            )
            if terminal_reason:
                session["closing_reason"] = terminal_reason
                await self._async_finish_locked(terminal_reason)
                return
            session["pause_reason"] = session["closing_reason"]
            session["resume_after"] = (
                (
                    dt_util.as_utc(closed_at)
                    + timedelta(
                        minutes=float(
                            self.coordinator.settings.get("irrigation_soak_minutes", 15)
                        )
                    )
                ).isoformat()
                if session["pause_reason"] == "soak_pause"
                else None
            )
            session["paused_at"] = closed_at.isoformat()
            session["closing_reason"] = None
            self.state.irrigation_last_status = "paused"
            await self._async_persist_state()
            self._publish_session()
            self._emit_event("paused", reason=session["pause_reason"])
            await self.coordinator.async_request_refresh()
        else:
            await self._async_finish_locked(session["closing_reason"])

    async def _async_finish_locked(self, reason: str) -> None:
        """Serialize physical water credits against maintenance and model writes.

        Finalize only after closing. Avoid crediting shared-meter reports
        received after the physical off edge because another consumer may
        have contributed. Acquire model state only inside controller ownership.
        """
        session = self.state.irrigation_session
        if session is None:
            return
        valve = self.hass.states.get(session["valve_entity_id"])
        # Freeze the physical end before waiting for model/storage locks.
        session.setdefault(
            "closed_at",
            min(dt_util.now(), valve.last_changed).isoformat()
            if valve and valve.state == "off"
            else dt_util.now().isoformat(),
        )
        closed_at = _session_timestamp(session["closed_at"])
        if (
            reason != "interrupted_by_restart"
            and session.get("ever_confirmed_open")
            and not session.get("paused_at")
            and not session.get("segment_accounted")
            and session["meter_kind"] != "timer"
        ):
            meter_id = session.get("meter_entity_id")
            meter = self.hass.states.get(meter_id) if meter_id else None
            if (
                meter
                and self._other_valve_state() == "off"
                and self.coordinator._reported_at(meter) <= closed_at
            ):
                if self._sample_meter(session, closed_at):
                    session["measurement_gap"] = True
            else:
                # Reports after the off edge may include another consumer.
                session["measurement_gap"] = True
        async with self.coordinator._state_lock:
            finished = await self._async_finish_state_locked(reason)
        if finished:
            await self.coordinator.async_request_refresh()

    async def _async_finish_state_locked(self, reason: str) -> bool:
        """Retry failed water credits without double-booking or reopening.

        Both controller and model locks are held by the caller. Run completion
        as a cancellation-shielded transaction; failed saves restore credits
        and retain a closed session for retry. Publish completion only once
        the durable result is known, then propagate caller cancellation.
        """
        keys = (
            "irrigation_session",
            "irrigation_last_status",
            "irrigation_last_reason",
            "irrigation_last_liters",
            "irrigation_last_auto_date",
            "irrigation_last_active_seconds",
            "irrigation_last_paused_seconds",
            "irrigation_last_measurement_gap",
            "irrigation_recent_valve_id",
            "irrigation_recent_until",
            "last_watering",
            "last_watering_at",
            "irrigation_last_session",
            "water_usage",
        )
        previous = {key: deepcopy(getattr(self.state, key)) for key in keys}
        previous_history = list(self.state.maintenance_history)
        history_ids = {id(event) for event in previous_history}
        self._finishing = True
        cancelled = False

        async def finish_transaction() -> OSError | HomeAssistantError | None:
            # Return expected storage failures so a cancelled shield does not
            # report them as unhandled errors before our rollback consumes them.
            try:
                await self._async_finish_attempt_locked(reason)
            except (OSError, HomeAssistantError) as err:
                return err
            return None

        finishing = asyncio.create_task(
            finish_transaction(), name="lawn_finish_irrigation"
        )
        try:
            while True:
                try:
                    result = await asyncio.shield(finishing)
                    break
                except asyncio.CancelledError:
                    # Resolve the transaction while retaining both locks.
                    # Repeated cancellation must not cancel the inner write.
                    cancelled = True
                    if finishing.cancelled():
                        raise
            if result is not None:
                raise result
        except (OSError, HomeAssistantError):
            # Undo only this attempt's credit. Keep unrelated mowing/fertilizer
            # events and weather sampling that may have arrived while saving.
            new_water = [
                event
                for event in self.state.maintenance_history
                if id(event) not in history_ids and event.get("action") == "watering"
            ]
            credit = sum(
                float(event.get("details", {}).get("applied_mm", 0))
                for event in new_water
            )
            self.state.soil_water_mm = max(
                0.0, float(self.state.soil_water_mm or 0) - credit
            )
            self.state.maintenance_history = [
                event
                for event in self.state.maintenance_history
                if event not in new_water
            ]
            retained_ids = {id(event) for event in self.state.maintenance_history}
            self.state.maintenance_history = (
                [event for event in previous_history if id(event) not in retained_ids]
                + self.state.maintenance_history
            )[-20:]
            for key, value in previous.items():
                setattr(self.state, key, value)
            self.state.irrigation_session["closing_reason"] = reason
            self.state.irrigation_last_status = "stopping"
            self.state.irrigation_last_reason = "storage_error"
            self._report_storage_error()
            self._publish_session()
            if cancelled:
                raise asyncio.CancelledError
            return False
        finally:
            self._finishing = False
        self._clear_storage_error()
        self._publish_session()
        self._emit_event(
            "completed" if reason == "target_reached" else "stopped",
            reason=reason,
            session=previous["irrigation_session"],
        )
        if cancelled:
            raise asyncio.CancelledError
        return True

    async def _async_finish_attempt_locked(self, reason: str) -> None:
        """Apply measured water once the valve is confirmed closed.

        Create the session summary and usage ledger, apply delivered water to
        the soil model when measurable, and persist the resulting state.
        This is the inner attempt; the surrounding transaction owns rollback.
        """
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
        now = dt_util.parse_datetime(session.get("closed_at") or "") or dt_util.now()
        if session["source"] == "auto" and liters is not None and liters > 0:
            self.state.irrigation_last_auto_date = (
                dt_util.as_local(now).date().isoformat()
            )
        self.state.irrigation_last_active_seconds = round(
            float(session.get("active_seconds", 0))
            + (
                0
                if session.get("paused_at") or session.get("segment_accounted")
                else max(
                    0,
                    (
                        now
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds(),
                )
            ),
            1,
        )
        self.state.irrigation_last_paused_seconds = round(
            float(session.get("paused_seconds", 0))
            + (
                (now - _session_timestamp(session["paused_at"])).total_seconds()
                if session.get("paused_at")
                else 0
            ),
            1,
        )
        self.state.irrigation_last_measurement_gap = bool(
            session.get("measurement_gap")
        )
        uncertain_dates = []
        if liters is None or session.get("measurement_gap"):
            uncertain_dates = [
                item["date"]
                for item in allocate_volume(
                    dt_util.as_local(_session_timestamp(session["started_at"])),
                    dt_util.as_local(now),
                    1,
                )
            ]
        if liters is None:
            session["allocations"] = [
                {"date": day, "liters": None} for day in uncertain_dates
            ]
        area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
        self.state.irrigation_last_session = {
            "timing_repaired": session.get("timing_repaired", []),
            "session_id": session.get("session_id"),
            "target_liters": session["target_liters"],
            "allocations": session.get("allocations", []),
            "allocation_estimated": session.get("allocation_estimated", False),
            "started_at": session["started_at"],
            "finished_at": now.isoformat(),
            "liters": liters,
            "delivered_mm": round(liters / area, 3) if liters is not None else None,
            "effective_model_mm": 0.0,
            "active_seconds": self.state.irrigation_last_active_seconds,
            "paused_seconds": self.state.irrigation_last_paused_seconds,
            "reason": reason,
            "source": session["source"],
            "measurement_gap": bool(session.get("measurement_gap")),
        }
        if (liters is not None and liters > 0) or session.get("ever_confirmed_open"):
            self.state.irrigation_last_session["usage_id"] = (
                self.coordinator.record_water_usage(
                    now,
                    liters,
                    source="irrigation",
                    measurement_gap=bool(session.get("measurement_gap")),
                    allocations=session.get("allocations"),
                    allocation_estimated=session.get("allocation_estimated", False),
                    session_id=session.get("session_id"),
                    uncertainty_dates=uncertain_dates,
                )
            )
        if self.state.irrigation_last_session.get("usage_id"):
            record = next(
                item
                for item in self.state.water_usage
                if item["id"] == self.state.irrigation_last_session["usage_id"]
            )
            record.update(
                {
                    key: self.state.irrigation_last_session[key]
                    for key in (
                        "started_at",
                        "finished_at",
                        "active_seconds",
                        "paused_seconds",
                        "reason",
                        "target_liters",
                    )
                }
            )
        guard_minutes = (
            max(
                10,
                min(
                    240,
                    int(
                        self.coordinator.settings.get(
                            CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES
                        )
                    ),
                ),
            )
            if reason in {"valve_open_failed", "interrupted_by_restart"}
            else 2
        )
        self._recent_owned_until = dt_util.utcnow() + timedelta(minutes=guard_minutes)
        self._recent_owned_valve_id = session.get("valve_entity_id")
        self.state.irrigation_recent_valve_id = self._recent_owned_valve_id
        self.state.irrigation_recent_until = self._recent_owned_until.isoformat()
        # The final session state and its water credit are persisted together
        # by async_mark_watered, with no intermediate save losing the credit.
        if liters is not None and liters > 0:
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            await self.coordinator._async_mark_watered_locked(
                liters / area, usage=False, completed_at=now
            )
        elif (
            (
                (session["meter_kind"] == "timer" or session.get("measurement_gap"))
                and (
                    session.get("ever_confirmed_open") or session.get("confirmed_open")
                )
                and float(session.get("active_seconds", 0))
                + (
                    0
                    if session.get("paused_at") or session.get("segment_accounted")
                    else (
                        now
                        - _session_timestamp(
                            session.get("segment_started_at") or session["started_at"]
                        )
                    ).total_seconds()
                )
                >= 60
            )
            or reason == "interrupted_by_restart"
            and (session.get("ever_confirmed_open") or session.get("confirmed_open"))
        ):
            await self.coordinator._async_mark_watered_locked(
                0, was_wet=True, usage=False, completed_at=now
            )
        else:
            if not await self._async_persist_state(already_locked=True):
                raise OSError("Irrigation completion could not be saved")

    def detach(self) -> None:
        """Remove listeners only when entry setup/unload has completed."""
        self._shutting_down = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    async def async_shutdown(self, *, detach: bool = True) -> bool:
        """Close owned water before unloading, retaining safety on failure.

        Refuse unload while an owned session remains unresolved. Only detach
        listeners after safe completion, otherwise restore supervision so
        closure/accounting can be retried.
        """
        self._shutting_down = True
        if self.active:
            await self.async_stop("integration_unloaded")
        if self.active:
            self._shutting_down = False
            return False
        if detach:
            self.detach()
        return True
