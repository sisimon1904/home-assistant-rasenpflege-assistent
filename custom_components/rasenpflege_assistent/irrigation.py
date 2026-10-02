"""Hardware-independent, fail-closed valve and water-meter controller."""

from __future__ import annotations

import asyncio
import logging
import math
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
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

from .explanations import reason_text
from .planning import (
    allocate_volume,
    consumption_summary,
    next_schedule_time,
    schedule_allowed,
)

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
        self._shutting_down = False
        self._storage_error = False
        self._finishing = False
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
        return self.state.irrigation_session is not None or self._finishing

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
        """Budgets count all recorded watering; incomplete totals block automation."""
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
                            dt_util.as_local(
                                dt_util.parse_datetime(session["started_at"])
                            ),
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

    def _rain_reading(self) -> tuple[str, str, float, str] | None:
        """Read the existing precipitation entity without modifying model sampling."""
        entity_id = (
            self.coordinator.settings.get(CONF_PRECIPITATION_ENTITY)
            or self.coordinator._find_openweathermap_precipitation_entity()
        )
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {"unknown", "unavailable"}:
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
        """Debounce live rain and wind; cumulative rainfall starts at the session edge."""
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
                self.coordinator.settings.get(CONF_WEATHER_ENTITY)
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
            since = dt_util.parse_datetime(pending[code])
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

    def next_start_details(self) -> dict:
        """Intersect the cached forecast window with schedule, hold and cooldown."""
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
        """Estimate completion from current measured flow, including soak pauses."""
        session = self.state.irrigation_session
        result = {
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
        if (
            reading
            and reading[0] == "rate"
            and dt_util.now() - self.coordinator._reported_at(meter)
            > timedelta(
                seconds=max(
                    120,
                    int(
                        self.coordinator.settings.get(
                            CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                        )
                    ),
                )
            )
        ):
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
                    - dt_util.parse_datetime(
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
                        - dt_util.parse_datetime(
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
                    - dt_util.parse_datetime(
                        session.get("segment_started_at") or session["started_at"]
                    )
                ).total_seconds()
                / 60
            )
            first = max(0, cycle - segment_minutes)
            pauses = max(0, math.ceil((minutes - first) / cycle))
        delay = 0
        resume = dt_util.parse_datetime(session.get("resume_after") or "")
        if resume:
            delay = max(0, (resume - dt_util.now()).total_seconds() / 60)
        end = dt_util.utcnow() + timedelta(
            minutes=minutes
            + delay
            + pauses
            * float(self.coordinator.settings.get("irrigation_soak_minutes", 15))
        )
        deadline = dt_util.parse_datetime(session["started_at"]) + timedelta(
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
        """Keep per-day allocations in the same persisted transaction as session liters."""
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
        """Return the first actionable reason the controller cannot start."""
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
            if reading is None:
                return "meter_unavailable"
            if reading[0] == "rate" and dt_util.now() - (
                getattr(meter, "last_reported", None) or meter.last_updated
            ) > timedelta(
                seconds=max(
                    120,
                    int(
                        self.coordinator.settings.get(
                            CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                        )
                    ),
                )
            ):
                return "meter_stale"
        return None

    def readiness(self) -> str:
        """Summarize start eligibility for a diagnostic entity."""
        if not self.configured:
            return "not_configured"
        if self.active:
            return self.state.irrigation_last_status
        return self.start_blocker() or "ready"

    def automatic_blocker(self) -> str | None:
        """Explain why an automatic session cannot start right now."""
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
        if data.forecast_stale or data.current_temperature is None:
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
        """Expose every independently checked start condition together."""
        data = self.coordinator.data
        now = dt_util.now()
        meter_id = self.coordinator.settings.get(CONF_IRRIGATION_FLOW)
        meter = self.hass.states.get(meter_id) if meter_id else None
        reading = _meter_reading(meter)
        meter_fresh = reading is not None and (
            reading[0] == "volume"
            or now - (getattr(meter, "last_reported", None) or meter.last_updated)
            <= timedelta(
                seconds=max(
                    120,
                    int(
                        self.coordinator.settings.get(
                            CONF_FLOW_START_GRACE, DEFAULT_FLOW_START_GRACE
                        )
                    ),
                )
            )
        )
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
        """Persist a temporary automation hold; manual starts remain available."""
        if until is not None and until <= dt_util.now():
            raise ServiceValidationError(
                "Suspension must end in the future",
                translation_domain=DOMAIN,
                translation_key="action_8",
            )
        previous = self.state.irrigation_suspended_until
        self.state.irrigation_suspended_until = until.isoformat() if until else None
        if not await self._async_persist_state():
            self.state.irrigation_suspended_until = previous
            raise ServiceValidationError(
                "Suspension could not be saved",
                translation_domain=DOMAIN,
                translation_key="action_9",
            )
        if until and self.active and self.state.irrigation_session["source"] == "auto":
            await self.async_stop("automation_suspended")
        self._publish_session()

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
                    dt_util.now() - dt_util.parse_datetime(session["started_at"])
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
                        - dt_util.parse_datetime(
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
                        dt_util.now() - dt_util.parse_datetime(session["paused_at"])
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
                        dt_util.now() - dt_util.parse_datetime(session["started_at"])
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
        """Bound slow device service calls so the watchdog can retry closure."""
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
        """Install immediate state checks and a separate safety watchdog."""
        self._unsubscribers.append(
            self.hass.bus.async_listen_once(
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
            # A restart cannot prove how long the valve was open or how much
            # water was delivered. Close it instead of resuming an old timer.
            self.state.irrigation_session["measurement_gap"] = True
            await self.async_stop("interrupted_by_restart")
        await self._async_close_late_open()

    async def _async_homeassistant_stopping(self, _event) -> None:
        """Close owned watering before the regular HA shutdown completes."""
        self._shutting_down = True
        await self.async_stop("homeassistant_stopping")
        if not self.active:
            self.detach()

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
            await self._async_persist_state()
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
        if self._storage_error:
            async with self._lock:
                await self._async_persist_state()
        await self.async_check()
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
        """Resume an owned session only when every interlock is safe again."""
        async with self._lock:
            session = self.state.irrigation_session
            if self._shutting_down or session is None or not session.get("paused_at"):
                return
            now = dt_util.now()
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
                + (now - dt_util.parse_datetime(session["paused_at"])).total_seconds()
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
        """Expose a user-facing, persisted automation master switch."""
        async with self._lock:
            previous = self.state.irrigation_enabled
            self.state.irrigation_enabled = enabled
            saved = await self._async_persist_state()
            if not saved and enabled:
                self.state.irrigation_enabled = previous
            self._publish_session()
        session = self.state.irrigation_session
        if not enabled and session and session["source"] == "auto":
            await self.async_stop("automation_disabled")
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
        """Open a valve only after the mower and meter pass validation."""
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
            session = {
                "session_id": uuid4().hex,
                "allocations": [],
                "rain_reading": list(self._rain_reading())
                if self._rain_reading()
                else None,
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
        """Observe flow, enforce interlocks and attempt closure as necessary."""
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
                    await self._async_persist_state()
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
                session["ever_confirmed_open"] = True
            if valve_state == "off" and not session.get("confirmed_open"):
                if (
                    now
                    - dt_util.parse_datetime(
                        session.get("opening_started_at") or session["started_at"]
                    )
                ).total_seconds() < 30:
                    return
                await self._async_stop_locked("valve_did_not_open")
                return
            if valve_state == "off":
                valve = self.hass.states.get(session["valve_entity_id"])
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
            started = dt_util.parse_datetime(session["started_at"])
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
                - dt_util.parse_datetime(
                    session.get("opening_started_at") or session["started_at"]
                )
            ).total_seconds()
            if self._valve_state() not in {"on", "off"} and opening_elapsed > 30:
                await self._async_stop_locked("valve_unavailable")
                return
            fault = self._sample_meter(session, now)
            if fault:
                await self._async_stop_locked(fault)
                return
            if session["source"] == "auto" and self._budget_blocker(session):
                await self._async_stop_locked(self._budget_blocker(session))
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
                if session["source"] == "manual" and not session.get("explicit_target")
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
            cycle = float(self.coordinator.settings.get("irrigation_cycle_minutes", 0))
            if (
                cycle > 0
                and (
                    now
                    - dt_util.parse_datetime(
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
        """Close only our valve, retaining a supervised resumable session."""
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
        session["active_seconds"] = float(session.get("active_seconds", 0)) + max(
            0,
            (
                now
                - dt_util.parse_datetime(
                    session.get("segment_started_at") or session["started_at"]
                )
            ).total_seconds(),
        )
        session["segment_accounted"] = True
        session["pause_reason"] = reason
        session["closing_reason"] = reason
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = reason
        await self._async_close_locked()
        if self.active:
            await self._async_persist_state()

    def _sample_meter(self, session: dict[str, Any], now) -> str | None:
        """Measure incremental water without inventing data across gaps."""
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
                session["measured_flow_l_min"] = round(flow_rate, 3)
                self._credit_volume(session, last_change, now, delta, estimated=True)
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
            segment_start = dt_util.parse_datetime(
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
        async with self._lock:
            if self.active:
                await self._async_stop_locked(reason)

    async def _async_stop_locked(self, reason: str) -> None:
        """Close hardware before awaiting maintenance or storage writes."""
        session = self.state.irrigation_session
        if self._valve_state() == "on":
            session["confirmed_open"] = True
            session["ever_confirmed_open"] = True
        if (
            reason != "interrupted_by_restart"
            and self._valve_state() == "on"
            and not session.get("paused_at")
            and self._other_valve_state() == "off"
        ):
            self._sample_meter(session, dt_util.now())
        self.state.irrigation_session["closing_reason"] = reason
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = reason
        await self._async_close_locked()
        if self.active:
            await self._async_persist_state()
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
        if session["closing_reason"] in {"other_valve_open", "soak_pause"}:
            session["pause_reason"] = session["closing_reason"]
            session["resume_after"] = (
                (
                    dt_util.utcnow()
                    + timedelta(
                        minutes=float(
                            self.coordinator.settings.get("irrigation_soak_minutes", 15)
                        )
                    )
                ).isoformat()
                if session["pause_reason"] == "soak_pause"
                else None
            )
            session["paused_at"] = dt_util.now().isoformat()
            session["closing_reason"] = None
            self.state.irrigation_last_status = "paused"
            await self._async_persist_state()
            self._publish_session()
            self._emit_event("paused", reason=session["pause_reason"])
            await self.coordinator.async_request_refresh()
        else:
            await self._async_finish_locked(session["closing_reason"])

    async def _async_finish_locked(self, reason: str) -> None:
        """Serialize physical water credits against maintenance and model writes."""
        async with self.coordinator._state_lock:
            finished = await self._async_finish_state_locked(reason)
        if finished:
            await self.coordinator.async_request_refresh()

    async def _async_finish_state_locked(self, reason: str) -> bool:
        """Retry failed water credits without double-booking or reopening."""
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
        try:
            await self._async_finish_attempt_locked(reason)
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
        return True

    async def _async_finish_attempt_locked(self, reason: str) -> None:
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
        if session["source"] == "auto" and liters is not None and liters > 0:
            self.state.irrigation_last_auto_date = (
                dt_util.as_local(dt_util.now()).date().isoformat()
            )
        now = dt_util.now()
        self.state.irrigation_last_active_seconds = round(
            float(session.get("active_seconds", 0))
            + (
                0
                if session.get("paused_at") or session.get("segment_accounted")
                else max(
                    0,
                    (
                        now
                        - dt_util.parse_datetime(
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
                (now - dt_util.parse_datetime(session["paused_at"])).total_seconds()
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
                    dt_util.as_local(dt_util.parse_datetime(session["started_at"])),
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
        self._recent_owned_until = dt_util.as_utc(now) + timedelta(
            minutes=guard_minutes
        )
        self._recent_owned_valve_id = session.get("valve_entity_id")
        self.state.irrigation_recent_valve_id = self._recent_owned_valve_id
        self.state.irrigation_recent_until = self._recent_owned_until.isoformat()
        # The final session state and its water credit are persisted together
        # by async_mark_watered, with no intermediate save losing the credit.
        if liters is not None and liters > 0:
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            await self.coordinator._async_mark_watered_locked(
                liters / area, usage=False
            )
        elif (
            (
                session["meter_kind"] == "timer"
                and (
                    session.get("ever_confirmed_open") or session.get("confirmed_open")
                )
                and float(session.get("active_seconds", 0))
                + (
                    0
                    if session.get("paused_at") or session.get("segment_accounted")
                    else (
                        dt_util.now()
                        - dt_util.parse_datetime(
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
                0, was_wet=True, usage=False
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
        """Close owned water before unloading, retaining safety on failure."""
        self._shutting_down = True
        if self.active:
            await self.async_stop("integration_unloaded")
        if self.active:
            self._shutting_down = False
            return False
        if detach:
            self.detach()
        return True
