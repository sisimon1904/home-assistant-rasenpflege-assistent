"""Hardware-independent, fail-closed valve and water-meter controller."""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any

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

    def start_blocker(self) -> str | None:
        """Return the first actionable reason the controller cannot start."""
        if self._shutting_down:
            return "homeassistant_stopping"
        if self._storage_error:
            return "storage_error"
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
        if now > end:
            return "window_expired"
        return None

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
            "automatic_blocker": self.automatic_blocker(),
            "next_automatic_start": (
                self.state.irrigation_retry_after
                if self.automatic_blocker() == "retry_cooldown"
                else self.coordinator.data.watering_window_start
                if self.coordinator.data
                and self.automatic_blocker() == "waiting_for_window"
                else None
            ),
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

    async def _async_persist_state(self) -> bool:
        try:
            await self.coordinator._store.async_save(self.state.as_dict())
        except (OSError, HomeAssistantError):
            self._report_storage_error()
            return False
        self._clear_storage_error()
        return True

    async def _async_command_valve(self, entity_id: str, *, open_valve: bool) -> None:
        """Bound slow device service calls so the watchdog can retry closure."""
        if entity_id == self.coordinator.settings.get(CONF_OTHER_VALVE):
            raise ServiceValidationError("The second valve is a read-only input")
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
            self.state.irrigation_session["measurement_gap"] = True
            await self.async_stop("interrupted_by_restart")
        await self._async_close_late_open()

    async def _async_homeassistant_stopping(self, _event) -> None:
        """Close owned watering before the regular HA shutdown completes."""
        self._shutting_down = True
        await self.async_stop("homeassistant_stopping")

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
        if self.active and self.state.irrigation_session.get("paused_at"):
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
            except Exception:
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self._async_persist_state()
                await self._async_close_locked()
                raise
        await self.async_check()
        await self.coordinator.async_request_refresh()

    async def async_set_auto_enabled(self, enabled: bool) -> None:
        """Expose a user-facing, persisted automation master switch."""
        self.state.irrigation_enabled = enabled
        await self._async_persist_state()
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
        if self.automatic_blocker() is not None:
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
                    target_mm * area,
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
                    now + timedelta(minutes=30)
                ).isoformat()
            if not await self._async_persist_state():
                self.state.irrigation_session = None
                self.state.irrigation_last_status = "stopped"
                self.state.irrigation_last_reason = "storage_error"
                self._publish_session()
                raise ServiceValidationError("Irrigation state could not be saved")
            self._publish_session()
            try:
                await self._async_command_valve(
                    self.coordinator.settings[CONF_IRRIGATION_VALVE], open_valve=True
                )
            except Exception:
                # Even a failed service call may have reached the hardware.
                session["closing_reason"] = "valve_open_failed"
                self.state.irrigation_last_status = "stopping"
                await self._async_persist_state()
                await self._async_close_locked()
                raise
        # Inputs can change while the opening service call is awaiting hardware.
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
            if session.get("paused_at"):
                if self._valve_state() != "off":
                    session["closing_reason"] = "other_valve_open"
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
            await self._async_persist_state()
            self._publish_session()

    async def _async_pause_locked(self) -> None:
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
            if (
                meter
                and other
                and (getattr(meter, "last_reported", None) or meter.last_updated)
                <= other.last_changed
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
        session["closing_reason"] = "other_valve_open"
        self.state.irrigation_last_status = "stopping"
        self.state.irrigation_last_reason = "other_valve_open"
        await self._async_persist_state()
        await self._async_close_locked()

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
            bounded_start = max(previous, now - timedelta(seconds=30))
            edge = max(bounded_start, min(now, reported_at))
            old_rate = float(session.get("meter_rate_l_min", 0.0))
            session["liters"] += (
                old_rate * (edge - bounded_start).total_seconds()
                + value * (now - edge).total_seconds()
            ) / 60
            session["meter_rate_l_min"] = value
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
        await self._async_persist_state()
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
            await self._async_persist_state()
            self._publish_session()
            await self.coordinator.async_request_refresh()
        else:
            await self._async_finish_locked(session["closing_reason"])

    async def _async_finish_locked(self, reason: str) -> None:
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
            return
        finally:
            self._finishing = False
        self._clear_storage_error()
        self._publish_session()
        await self.coordinator.async_request_refresh()

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
        self._recent_owned_until = now + timedelta(minutes=guard_minutes)
        self._recent_owned_valve_id = session.get("valve_entity_id")
        self.state.irrigation_recent_valve_id = self._recent_owned_valve_id
        self.state.irrigation_recent_until = self._recent_owned_until.isoformat()
        # The final session state and its water credit are persisted together
        # by async_mark_watered, with no intermediate save losing the credit.
        if liters is not None and liters > 0:
            area = float(self.coordinator.settings.get(CONF_AREA, DEFAULT_AREA))
            await self.coordinator.async_mark_watered(liters / area, refresh=False)
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
            await self.coordinator.async_mark_watered(0, was_wet=True, refresh=False)
        else:
            if not await self._async_persist_state():
                raise OSError("Irrigation completion could not be saved")

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
