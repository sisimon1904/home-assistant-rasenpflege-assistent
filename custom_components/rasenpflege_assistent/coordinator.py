"""Observation normalization, persistent lawn model and maintenance transactions.

File: custom_components/rasenpflege_assistent/coordinator.py

LawnCoordinator reads existing HA entities and cached HA weather forecasts,
updates local-day temperature/rain totals and the soil model, and publishes
LawnData. RuntimeState holds the durable history and controller session state.

The state lock serializes model updates and maintenance writes. Operations
that also need controller serialization acquire the controller lock first.
Safety closure may act while a write waits; rollback must preserve that safety
state. No separate regular HTTP polling loop is introduced for OpenWeatherMap.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import date, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Any, TypeGuard
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    PressureConverter,
    SpeedConverter,
    TemperatureConverter,
)

from .calculations import (
    assess_soil_confidence,
    days_since,
    fertilizing_recommendation,
    grassland_temperature_increment,
    growth_state,
    hargreaves_evapotranspiration,
    interval_evapotranspiration,
    lawn_status,
    mower_recommendation,
    next_lawn_action,
    penman_monteith_evapotranspiration,
    precipitation_rate_amounts,
    recommended_watering_window,
    soil_capacity,
    soil_profile,
    update_soil_water_balance,
    watering_recommendation,
)
from .const import (
    CONF_AREA,
    CONF_COMPACTION,
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_IRRIGATION_EFFICIENCY,
    CONF_IRRIGATION_VALVE,
    CONF_LAST_FERTILIZING,
    CONF_LAST_MOWING,
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_MOWING_INTERVAL_FACTOR,
    CONF_MOWING_MODE,
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_RAIN_CORRECTION,
    CONF_ROOT_DEPTH,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_SENSOR_DRY,
    CONF_SOIL_SENSOR_MAX_AGE,
    CONF_SOIL_SENSOR_WET,
    CONF_SOIL_TEMPERATURE_ENTITY,
    CONF_SOIL_TYPE,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WEATHER_ENTITY,
    CURRENT_WEATHER_STALE_AFTER,
    DEFAULT_AREA,
    DEFAULT_COMPACTION,
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_IRRIGATION_EFFICIENCY,
    DEFAULT_LAWN_TYPE,
    DEFAULT_PRECIPITATION_MODE,
    DEFAULT_RAIN_CORRECTION,
    DEFAULT_ROOT_DEPTH,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_SENSOR_DRY,
    DEFAULT_SOIL_SENSOR_MAX_AGE,
    DEFAULT_SOIL_SENSOR_WET,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_EXPOSURE,
    DEFAULT_WATERING_AMOUNT,
    DOMAIN,
    FORECAST_CACHE_INTERVAL,
    FORECAST_STALE_AFTER,
    MAX_SOIL_MODEL_INTERVAL,
    PRECIPITATION_RATE_STALE_AFTER,
    SOIL_SENSOR_BLEND_FACTOR,
    SOIL_SENSOR_CALIBRATION_INTERVAL,
    STORE_KEY_PREFIX,
    STORE_VERSION,
    UPDATE_INTERVAL,
)
from .diagnostic_types import ModelConfidence, SoilTrace, SoilUpdate
from .models import LawnData, RuntimeState
from .storage import VerifiedStore as Store

if TYPE_CHECKING:
    from .irrigation import IrrigationController
    from .mowing import MowingObserver

_LOGGER = logging.getLogger(__name__)


def _parse_date(value: Any) -> date | None:
    """Parse a date selector/storage value."""
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


class LawnCoordinator(DataUpdateCoordinator[LawnData]):
    """Collect OpenWeatherMap state and calculate lawn recommendations."""

    config_entry: ConfigEntry[LawnCoordinator]

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry[LawnCoordinator]
    ) -> None:
        """Initialize the coordinator.

        Create per-entry caches, verified storage and independent state/mowing
        locks. The update coordinator owns recommendation refreshes; physical
        valve supervision belongs to the separately attached controller.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{STORE_KEY_PREFIX}{entry.entry_id}"
        )
        self._state: RuntimeState | None = None
        self._forecast_cache: list[dict[str, Any]] = []
        self._forecast_updated_at: datetime | None = None
        self._hourly_forecast_cache: list[dict[str, Any]] = []
        self._hourly_forecast_updated_at: datetime | None = None
        self.irrigation: IrrigationController | None = None
        self.mowing_observer: MowingObserver | None = None
        self._mowing_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._maintenance_committed = False
        self._weather_unavailable = False
        self._last_soil_trace: SoilTrace | None = None
        self._last_model_confidence: ModelConfidence | None = None
        self._last_calculation_success_at: str | None = None
        self._last_calculation_failure_at: str | None = None
        self._last_calculation_error_type: str | None = None

    @property
    def state(self) -> RuntimeState:
        """Require completed model setup before runtime state is accessed."""
        assert self._state is not None
        return self._state

    @property
    def irrigation_controller(self) -> IrrigationController:
        """Require controller attachment for actions and optional platform reads."""
        assert self.irrigation is not None
        return self.irrigation

    @property
    def settings(self) -> dict[str, Any]:
        """Return merged setup data and editable options."""
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def water_model_version(self) -> int:
        """Return the persisted water-balance model version."""
        return self.state.water_model_version if self._state is not None else 3

    async def _async_setup(self) -> None:
        """Load persisted running totals once.

        Restore durable state before the first calculation. Reconcile configured
        baselines and model revisions without discarding unrelated history.
        Older UTC partial-day samples cannot be assigned confidently to a local
        date, so migration marks missing information rather than inventing it.
        """
        today = dt_util.as_local(dt_util.now()).date()
        stored = await self._store.async_load()
        settings = self.settings
        initial_gts = float(settings.get(CONF_INITIAL_GTS, DEFAULT_INITIAL_GTS))
        initial_moisture = float(
            settings.get(CONF_INITIAL_SOIL_MOISTURE, DEFAULT_INITIAL_SOIL_MOISTURE)
        )
        soil_type = settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)
        root_depth = float(settings.get(CONF_ROOT_DEPTH, DEFAULT_ROOT_DEPTH))
        capacity = soil_capacity(soil_type, root_depth)

        if stored:
            self._state = RuntimeState(
                year=int(stored.get("year", today.year)),
                gts=float(stored.get("gts", initial_gts)),
                sample_date=str(stored.get("sample_date", today.isoformat())),
                temperature_sum=float(stored.get("temperature_sum", 0.0)),
                temperature_samples=int(stored.get("temperature_samples", 0)),
                temperature_sample_at=stored.get("temperature_sample_at"),
                last_watering=stored.get("last_watering"),
                last_fertilizing=stored.get("last_fertilizing"),
                last_mowing=stored.get("last_mowing"),
                last_mowing_at=stored.get("last_mowing_at"),
                last_mowing_source=stored.get("last_mowing_source"),
                last_mowing_event_id=stored.get("last_mowing_event_id"),
                configured_last_mowing=stored.get("configured_last_mowing"),
                configured_last_mowing_revision=stored.get(
                    "configured_last_mowing_revision"
                ),
                configured_initial_gts=float(
                    stored.get("configured_initial_gts", initial_gts)
                ),
                configured_last_watering=stored.get("configured_last_watering"),
                configured_last_watering_revision=stored.get(
                    "configured_last_watering_revision"
                ),
                last_robot_session_started_at=stored.get(
                    "last_robot_session_started_at"
                ),
                last_robot_session_finished_at=stored.get(
                    "last_robot_session_finished_at"
                ),
                last_robot_session_active_seconds=stored.get(
                    "last_robot_session_active_seconds"
                ),
                configured_last_fertilizing_revision=stored.get(
                    "configured_last_fertilizing_revision"
                ),
                configured_last_fertilizing=stored.get("configured_last_fertilizing"),
                temperature_min=stored.get("temperature_min"),
                temperature_max=stored.get("temperature_max"),
                daily_rain_mm=float(stored.get("daily_rain_mm", 0.0)),
                daily_rain_unknown=bool(stored.get("daily_rain_unknown", True)),
                soil_water_mm=stored.get("soil_water_mm"),
                current_day_evapotranspiration_mm=float(
                    stored.get("current_day_evapotranspiration_mm", 0.0)
                ),
                daily_temperature_history=[
                    float(value)
                    for value in stored.get("daily_temperature_history", [])[-14:]
                ],
                mower_started_year=stored.get("mower_started_year"),
                configured_initial_soil_moisture=float(
                    stored.get("configured_initial_soil_moisture", initial_moisture)
                ),
                precipitation_last_value=stored.get("precipitation_last_value"),
                precipitation_last_sample_at=stored.get("precipitation_last_sample_at"),
                precipitation_last_source=stored.get("precipitation_last_source"),
                precipitation_last_mode=stored.get("precipitation_last_mode"),
                soil_sensor_last_calibrated_at=stored.get(
                    "soil_sensor_last_calibrated_at"
                ),
                last_soil_update_at=stored.get("last_soil_update_at"),
                last_soil_model_gap_at=stored.get("last_soil_model_gap_at"),
                last_soil_model_gap_hours=float(
                    stored.get("last_soil_model_gap_hours", 0.0)
                ),
                last_growth_state=stored.get("last_growth_state"),
                maintenance_history=list(stored.get("maintenance_history", []))[-20:],
                weather_samples=list(stored.get("weather_samples", []))[-96:],
                daily_effective_rain_mm=float(
                    stored.get("daily_effective_rain_mm", 0.0)
                ),
                daily_runoff_mm=float(stored.get("daily_runoff_mm", 0.0)),
                daily_drainage_mm=float(stored.get("daily_drainage_mm", 0.0)),
                daily_interception_mm=float(stored.get("daily_interception_mm", 0.0)),
                water_model_version=int(stored.get("water_model_version", 1)),
                canopy_storage_mm=float(stored.get("canopy_storage_mm", 0.0)),
                last_rain_at=stored.get("last_rain_at"),
                last_wet_rain_at=stored.get("last_wet_rain_at"),
                last_watering_at=stored.get("last_watering_at"),
                configured_soil_type=stored.get("configured_soil_type"),
                configured_root_depth_cm=float(
                    stored.get("configured_root_depth_cm", root_depth)
                ),
                missing_temperature_days=int(stored.get("missing_temperature_days", 0)),
                irrigation_enabled=bool(stored.get("irrigation_enabled", False)),
                irrigation_session=stored.get("irrigation_session"),
                irrigation_last_auto_date=stored.get("irrigation_last_auto_date"),
                irrigation_suspended_until=stored.get("irrigation_suspended_until"),
                irrigation_last_session=stored.get("irrigation_last_session"),
                water_usage=list(stored.get("water_usage", [])),
                irrigation_last_status=stored.get("irrigation_last_status", "idle"),
                irrigation_last_reason=stored.get("irrigation_last_reason"),
                irrigation_last_liters=stored.get("irrigation_last_liters"),
                irrigation_valve_id=stored.get("irrigation_valve_id"),
                irrigation_recent_valve_id=stored.get("irrigation_recent_valve_id"),
                irrigation_recent_until=stored.get("irrigation_recent_until"),
                irrigation_retry_after=stored.get("irrigation_retry_after"),
                irrigation_last_active_seconds=stored.get(
                    "irrigation_last_active_seconds"
                ),
                irrigation_last_paused_seconds=stored.get(
                    "irrigation_last_paused_seconds"
                ),
                irrigation_last_measurement_gap=bool(
                    stored.get("irrigation_last_measurement_gap", False)
                ),
            )
            if not stored.get("local_day_model", False):
                # Earlier releases stored UTC-based partial days. They cannot be
                # safely attributed to a local calendar day after migration.
                self.state.sample_date = today.isoformat()
                self.state.temperature_sum = 0.0
                self.state.temperature_samples = 0
                self.state.temperature_min = None
                self.state.temperature_max = None
                self.state.daily_rain_mm = 0.0
                self.state.daily_rain_unknown = True
                self.state.current_day_evapotranspiration_mm = 0.0
                self.state.daily_effective_rain_mm = 0.0
                self.state.daily_runoff_mm = 0.0
                self.state.daily_drainage_mm = 0.0
                self.state.daily_interception_mm = 0.0
                if initial_gts == 0:
                    self.state.missing_temperature_days = max(
                        self.state.missing_temperature_days,
                        (today - date(today.year, 1, 1)).days,
                    )
                self.state.local_day_model = True
        else:
            initial_watering = settings.get(CONF_LAST_WATERING)
            initial_fertilizing = settings.get(CONF_LAST_FERTILIZING)
            self._state = RuntimeState(
                year=today.year,
                gts=initial_gts,
                sample_date=today.isoformat(),
                last_watering=initial_watering,
                last_fertilizing=initial_fertilizing,
                last_mowing=settings.get(CONF_LAST_MOWING),
                configured_last_mowing=settings.get(CONF_LAST_MOWING),
                configured_last_mowing_revision=settings.get("last_mowing_revision"),
                configured_initial_gts=initial_gts,
                configured_last_watering=initial_watering,
                configured_last_watering_revision=settings.get(
                    "last_watering_revision"
                ),
                configured_last_fertilizing=initial_fertilizing,
                configured_last_fertilizing_revision=settings.get(
                    "last_fertilizing_revision"
                ),
                soil_water_mm=capacity * initial_moisture / 100,
                configured_initial_soil_moisture=initial_moisture,
                water_model_version=3,
                configured_soil_type=soil_type,
                configured_root_depth_cm=root_depth,
                irrigation_valve_id=settings.get(CONF_IRRIGATION_VALVE),
                missing_temperature_days=(
                    (today - date(today.year, 1, 1)).days if initial_gts == 0 else 0
                ),
            )

        if self.state.configured_soil_type is None:
            self.state.configured_soil_type = soil_type
            self.state.configured_root_depth_cm = root_depth
        elif (
            self.state.configured_soil_type != soil_type
            or self.state.configured_root_depth_cm != root_depth
        ):
            old_capacity = soil_capacity(
                self.state.configured_soil_type,
                self.state.configured_root_depth_cm,
            )
            fill_fraction = min(
                1.0, max(0.0, float(self.state.soil_water_mm or 0.0) / old_capacity)
            )
            self.state.soil_water_mm = capacity * fill_fraction
            self.state.configured_soil_type = soil_type
            self.state.configured_root_depth_cm = root_depth
        self.state.water_model_version = max(self.state.water_model_version, 3)
        if self.state.irrigation_valve_id != settings.get(CONF_IRRIGATION_VALVE):
            self.state.irrigation_enabled = False
            self.state.irrigation_valve_id = settings.get(CONF_IRRIGATION_VALVE)

        if initial_gts != self.state.configured_initial_gts:
            self.state.gts = initial_gts
            self.state.configured_initial_gts = initial_gts
            self.state.missing_temperature_days = (
                0 if initial_gts > 0 else (today - date(today.year, 1, 1)).days
            )
        if initial_moisture != self.state.configured_initial_soil_moisture:
            self.state.soil_water_mm = capacity * initial_moisture / 100
            self.state.configured_initial_soil_moisture = initial_moisture
        if self.state.soil_water_mm is None:
            self.state.soil_water_mm = capacity * initial_moisture / 100
        self.state.soil_water_mm = min(capacity, self.state.soil_water_mm)

        for setting_key, state_key, configured_key in (
            (CONF_LAST_MOWING, "last_mowing", "configured_last_mowing"),
            (CONF_LAST_WATERING, "last_watering", "configured_last_watering"),
            (
                CONF_LAST_FERTILIZING,
                "last_fertilizing",
                "configured_last_fertilizing",
            ),
        ):
            configured_value = settings.get(setting_key)
            mowing_changed = (
                setting_key == CONF_LAST_MOWING
                and settings.get("last_mowing_revision")
                != self.state.configured_last_mowing_revision
            )
            if (
                configured_value != getattr(self._state, configured_key)
                or mowing_changed
                or (
                    setting_key == CONF_LAST_FERTILIZING
                    and settings.get("last_fertilizing_revision")
                    != self.state.configured_last_fertilizing_revision
                )
                or (
                    setting_key == CONF_LAST_WATERING
                    and settings.get("last_watering_revision")
                    != self.state.configured_last_watering_revision
                )
            ):
                setattr(self._state, state_key, configured_value)
                setattr(self._state, configured_key, configured_value)
                if setting_key == CONF_LAST_FERTILIZING:
                    self.state.configured_last_fertilizing_revision = settings.get(
                        "last_fertilizing_revision"
                    )
                if setting_key == CONF_LAST_WATERING:
                    self.state.configured_last_watering_revision = settings.get(
                        "last_watering_revision"
                    )
                    watering_date = _parse_date(configured_value)
                    self.state.last_watering_at = (
                        (
                            dt_util.now()
                            if watering_date == today
                            else dt_util.as_utc(
                                dt_util.start_of_local_day(watering_date)
                            )
                        ).isoformat()
                        if watering_date
                        else None
                    )
                if setting_key == CONF_LAST_MOWING:
                    self.state.configured_last_mowing_revision = settings.get(
                        "last_mowing_revision"
                    )
                    self.state.last_mowing_at = None
                    self.state.last_mowing_event_id = None
                    self.state.last_mowing_source = (
                        "manual_correction" if configured_value else None
                    )

        if self.state.last_watering and not self.state.last_watering_at:
            watering_date = _parse_date(self.state.last_watering)
            if watering_date is not None:
                self.state.last_watering_at = dt_util.as_utc(
                    dt_util.start_of_local_day(watering_date)
                ).isoformat()

        # Older versions knew only a local date. Preserve that fact and use
        # local midnight as an explicitly estimated time, never the load time.
        mowing_date = _parse_date(self.state.last_mowing)
        if mowing_date is not None and not self.state.last_mowing_at:
            self.state.last_mowing_at = dt_util.as_utc(
                dt_util.start_of_local_day(mowing_date)
            ).isoformat()
            if not self.state.last_mowing_source:
                self.state.last_mowing_source = "legacy_date"

    @staticmethod
    def _reported_at(state):
        """Return the provider report timestamp of a Home Assistant state."""
        return getattr(state, "last_reported", None) or state.last_updated

    @staticmethod
    def _age_minutes(now, timestamp) -> int:
        """Return a non-negative age in full minutes."""
        return max(0, int((now - timestamp).total_seconds() / 60))

    def _pause_mower_when_wet(
        self, now: datetime, mower: dict[str, Any]
    ) -> tuple[datetime | None, str | None]:
        """Defer mowing until the next local day and twelve hours after wetting.

        Combine current leaf wetness, recent rain/watering and live irrigation
        into a conservative mowing pause. This changes recommendations only;
        it does not send mower commands.
        """
        assert self._state is not None
        wet_until: datetime | None = None
        wet_reason: str | None = None
        leaf_id = self.settings.get(CONF_LEAF_WETNESS_ENTITY)
        leaf = self.hass.states.get(leaf_id) if leaf_id else None
        leaf_valid = (
            leaf is not None
            and leaf.state in {"on", "off"}
            and self._soil_sensor_fresh(leaf)
        )
        wet_events = [
            (self.state.last_wet_rain_at, "rain"),
            (self.state.last_watering_at, "watering"),
        ]
        if leaf_valid and leaf is not None:
            wet_events = (
                [(now.isoformat(), "leaf_wetness")] if leaf.state == "on" else []
            )
        if self.state.irrigation_session is not None:
            wet_events.append(
                (
                    now.isoformat(),
                    "irrigation_paused"
                    if self.state.irrigation_session.get("paused_at")
                    else "irrigation_running",
                )
            )
        for timestamp, reason in wet_events:
            event_at = dt_util.parse_datetime(timestamp or "")
            if event_at is None:
                continue
            local_event = dt_util.as_local(event_at)
            next_local_day = dt_util.start_of_local_day(local_event + timedelta(days=1))
            candidate = max(
                dt_util.as_utc(next_local_day), event_at + timedelta(hours=12)
            )
            if wet_until is None or candidate > wet_until:
                wet_until, wet_reason = candidate, reason
        if wet_until is not None and now < wet_until:
            if mower["status"] in {
                "start_mower",
                "mow_regularly",
                "mow_less",
                "reduce_mowing",
                "wait_to_mow",
                "pause_wet",
            }:
                mower["status"] = "pause_wet"
            mower["next_date"] = max(
                mower["next_date"] or dt_util.as_local(now).date(),
                dt_util.as_local(wet_until).date(),
            )
            mower["next_at"] = max(mower.get("next_at") or now, wet_until)
        return (
            (wet_until, wet_reason)
            if wet_until is not None and now < wet_until
            else (None, None)
        )

    def apply_live_irrigation_status(self, data: LawnData) -> None:
        """Publish the wet interlock immediately without fetching weather.

        Overlay the controller state on existing output without a weather
        refresh. Fast safety events can therefore reach entities while the
        slower model update is waiting for a service or storage operation.
        """
        if self.state.irrigation_session is None:
            return
        mower: dict[str, Any] = {
            "status": data.mower_status,
            "next_date": data.next_mowing_date,
            "next_at": dt_util.parse_datetime(data.next_mowing_at or ""),
        }
        until, reason = self._pause_mower_when_wet(dt_util.now(), mower)
        data.mower_status = mower["status"]
        data.mowing_reason = mower["status"]
        data.mower_start_recommended = mower["status"] == "start_mower"
        data.mower_wet_until = until.isoformat() if until else None
        data.mower_wet_reason = reason
        data.next_mowing_date = mower["next_date"]
        data.next_mowing_at = mower["next_at"].isoformat() if mower["next_at"] else None
        data.lawn_status = "lawn_wet"
        data.next_action = "wait_for_irrigation"

    def _read_temperature(self, now) -> tuple[float | None, str, int | None]:
        """Read the selected outdoor sensor, falling back to OpenWeatherMap.

        Prefer the configured outdoor sensor and use the HA weather source as
        fallback. Normalize supported units and reject implausible/non-finite
        observations; return source and age so confidence is not hidden.
        """
        temperature_entity = self.settings.get(CONF_TEMPERATURE_ENTITY)
        state = self.hass.states.get(temperature_entity) if temperature_entity else None
        if state is not None and state.state not in ("unknown", "unavailable"):
            try:
                reported_at = self._reported_at(state)
                if now - reported_at > CURRENT_WEATHER_STALE_AFTER:
                    raise ValueError("selected temperature is stale")
                value = float(state.state)
                if not math.isfinite(value):
                    raise ValueError("temperature is not finite")
                unit = state.attributes.get("unit_of_measurement")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
                if not -90 <= value <= 70:
                    raise ValueError("Implausible temperature")
                assert temperature_entity is not None
                return value, temperature_entity, self._age_minutes(now, reported_at)
            except (TypeError, ValueError, HomeAssistantError):
                pass

        weather = self.hass.states.get(self.settings[CONF_WEATHER_ENTITY])
        if weather is not None and weather.state not in ("unknown", "unavailable"):
            try:
                reported_at = self._reported_at(weather)
                if now - reported_at > CURRENT_WEATHER_STALE_AFTER:
                    return None, "unavailable", self._age_minutes(now, reported_at)
                value = float(weather.attributes["temperature"])
                if not math.isfinite(value):
                    raise ValueError("weather temperature is not finite")
                unit = weather.attributes.get("temperature_unit")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
                if not -90 <= value <= 70:
                    raise ValueError("Implausible temperature")
                return (
                    value,
                    self.settings[CONF_WEATHER_ENTITY],
                    self._age_minutes(now, reported_at),
                )
            except (KeyError, TypeError, ValueError, HomeAssistantError):
                pass
        return None, "unavailable", None

    @staticmethod
    def _number_attribute(state, key: str) -> float | None:
        """Read a finite numeric weather attribute."""
        try:
            value = float(state.attributes[key])
        except (KeyError, TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    def _read_weather_conditions(self, now) -> dict[str, Any]:
        """Read cached meteorological inputs from the selected weather entity.

        Read weather attributes already present in HA and normalize the values
        required by ET and irrigation safety. Missing or stale fields remain
        explicit so callers can choose a fallback or block automation.
        """
        state = self.hass.states.get(self.settings[CONF_WEATHER_ENTITY])
        if state is None or state.state in ("unknown", "unavailable"):
            return {"age_minutes": None, "stale": True, "unavailable": True}
        reported_at = self._reported_at(state)
        age_minutes = self._age_minutes(now, reported_at)
        wind = self._number_attribute(state, "wind_speed")
        if wind is not None:
            try:
                wind = SpeedConverter.convert(
                    wind,
                    state.attributes.get(
                        "wind_speed_unit", UnitOfSpeed.METERS_PER_SECOND
                    ),
                    UnitOfSpeed.METERS_PER_SECOND,
                )
                if wind < 0:
                    wind = None
            except (HomeAssistantError, TypeError, ValueError):
                wind = None
        pressure = self._number_attribute(state, "pressure")
        if pressure is not None:
            try:
                pressure = PressureConverter.convert(
                    pressure,
                    state.attributes.get("pressure_unit", UnitOfPressure.HPA),
                    UnitOfPressure.HPA,
                )
            except (HomeAssistantError, TypeError, ValueError):
                pressure = None
        if pressure is not None and not 300 <= pressure <= 1200:
            pressure = None
        dew_point = self._number_attribute(state, "dew_point")
        temperature_unit = state.attributes.get("temperature_unit")
        if (
            dew_point is not None
            and temperature_unit
            and temperature_unit != UnitOfTemperature.CELSIUS
        ):
            try:
                dew_point = TemperatureConverter.convert(
                    dew_point, temperature_unit, UnitOfTemperature.CELSIUS
                )
            except (HomeAssistantError, TypeError, ValueError):
                dew_point = None
        if dew_point is not None and not -90 <= dew_point <= 70:
            dew_point = None
        humidity = self._number_attribute(state, "humidity")
        if humidity is not None and not 0 <= humidity <= 100:
            humidity = None
        cloud_coverage = self._number_attribute(state, "cloud_coverage")
        if cloud_coverage is not None and not 0 <= cloud_coverage <= 100:
            cloud_coverage = None
        return {
            "reported_at": reported_at.isoformat(),
            "age_minutes": age_minutes,
            "stale": now - reported_at > CURRENT_WEATHER_STALE_AFTER,
            "unavailable": False,
            "humidity": humidity,
            "wind_speed_m_s": wind,
            "cloud_coverage": cloud_coverage,
            "pressure_hpa": pressure,
            "dew_point": dew_point,
        }

    async def _async_forecast(self, forecast_type: str) -> list[dict[str, Any]]:
        """Return a cached daily or hourly forecast from Home Assistant.

        Daily and hourly caches have separate timestamps. On a failed HA weather
        service call, retain the previous data and its age instead of marking
        it fresh. This accesses the existing HA weather integration, not a
        separate HTTP client or additional custom OWM polling loop.
        """
        now = dt_util.now()
        if forecast_type == "hourly":
            cached = self._hourly_forecast_cache
            updated_at = self._hourly_forecast_updated_at
        else:
            cached = self._forecast_cache
            updated_at = self._forecast_updated_at
        if updated_at is not None and now - updated_at < FORECAST_CACHE_INTERVAL:
            return cached
        weather_entity = self.settings[CONF_WEATHER_ENTITY]
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": forecast_type},
                target={"entity_id": weather_entity},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug(
                "%s OpenWeatherMap forecast unavailable: %s", forecast_type, err
            )
            return cached
        if not isinstance(response, dict):
            return cached
        entity_data = response.get(weather_entity, {})
        forecast = (
            entity_data.get("forecast", []) if isinstance(entity_data, dict) else []
        )
        if isinstance(forecast, list):
            normalized_forecast = self._normalize_forecast(forecast, weather_entity)
            if forecast_type == "hourly":
                self._hourly_forecast_cache = normalized_forecast
                self._hourly_forecast_updated_at = now
            else:
                self._forecast_cache = normalized_forecast
                self._forecast_updated_at = now
            return normalized_forecast
        return cached

    def _normalize_forecast(
        self, forecast: list, entity_id: str
    ) -> list[dict[str, Any]]:
        """Normalize HA display units before using forecasts in the model.

        Convert temperatures to Celsius, rain to millimeters and wind to m/s
        exactly once before calculation. Copy provider rows so normalization
        does not mutate HA response data. Reject invalid timestamps,
        probabilities, units and implausible values on a per-row basis.
        """
        state = self.hass.states.get(entity_id)
        attrs = state.attributes if state else {}
        conversions = {
            "temperature": (
                TemperatureConverter,
                attrs.get("temperature_unit", "°C"),
                UnitOfTemperature.CELSIUS,
            ),
            "templow": (
                TemperatureConverter,
                attrs.get("temperature_unit", "°C"),
                UnitOfTemperature.CELSIUS,
            ),
            "dew_point": (
                TemperatureConverter,
                attrs.get("temperature_unit", "°C"),
                UnitOfTemperature.CELSIUS,
            ),
            "precipitation": (
                DistanceConverter,
                attrs.get("precipitation_unit", "mm"),
                UnitOfLength.MILLIMETERS,
            ),
            "wind_speed": (
                SpeedConverter,
                attrs.get("wind_speed_unit", "m/s"),
                UnitOfSpeed.METERS_PER_SECOND,
            ),
        }
        result = []
        for item in forecast:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if normalized.get("datetime") is not None:
                timestamp = dt_util.parse_datetime(str(normalized["datetime"]))
                if timestamp is None:
                    continue
                normalized["datetime"] = dt_util.as_utc(timestamp).isoformat()
            if normalized.get("precipitation_probability") is not None:
                try:
                    probability = float(normalized["precipitation_probability"])
                    if not math.isfinite(probability) or not 0 <= probability <= 100:
                        continue
                    normalized["precipitation_probability"] = probability
                except (TypeError, ValueError):
                    continue
            valid = True
            for key, (converter, source, target) in conversions.items():
                if normalized.get(key) is None:
                    continue
                try:
                    value = float(normalized[key])
                    if not math.isfinite(value):
                        raise ValueError("Non-finite forecast")
                    value = converter.convert(value, source, target)
                    if (
                        key in {"temperature", "templow", "dew_point"}
                        and not -90 <= value <= 70
                    ):
                        raise ValueError("Implausible temperature")
                    if key in {"precipitation", "wind_speed"} and value < 0:
                        raise ValueError("Negative forecast")
                    normalized[key] = value
                except (TypeError, ValueError, HomeAssistantError):
                    valid = False
                    break
            if valid:
                result.append(normalized)
        return result

    def _soil_sensor_fresh(self, state: State | None) -> TypeGuard[State]:
        """Accept physical soil measurements only within the configured age."""
        if state is None or state.state in ("unknown", "unavailable"):
            return False
        age = dt_util.now() - self._reported_at(state)
        return (
            timedelta(0)
            <= age
            <= timedelta(
                minutes=float(
                    self.settings.get(
                        CONF_SOIL_SENSOR_MAX_AGE,
                        DEFAULT_SOIL_SENSOR_MAX_AGE,
                    )
                )
            )
        )

    def input_diagnostics(self) -> dict[str, Any]:
        """Explain why physical measurements are accepted or discarded.

        Report source selection, availability and freshness from current HA
        states. These attributes help explain blockers without requesting
        replacement readings from devices or weather providers.
        """
        result = {}
        for key in (
            CONF_SOIL_MOISTURE_ENTITY,
            CONF_SOIL_TEMPERATURE_ENTITY,
            CONF_LEAF_WETNESS_ENTITY,
        ):
            entity_id = self.settings.get(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            age = (
                max(
                    0,
                    round(
                        (dt_util.now() - self._reported_at(state)).total_seconds() / 60,
                        1,
                    ),
                )
                if state
                else None
            )
            reason = (
                "not_configured"
                if not entity_id
                else "missing"
                if state is None
                else "unavailable"
                if state.state in {"unknown", "unavailable"}
                else "stale"
                if not self._soil_sensor_fresh(state)
                else "accepted"
            )
            if reason == "accepted" and state is not None:
                if key == CONF_LEAF_WETNESS_ENTITY:
                    valid = state.state in {"on", "off"}
                elif key == CONF_SOIL_MOISTURE_ENTITY:
                    valid = self._read_soil_moisture()[0] is not None
                else:
                    valid = self._read_soil_temperature() is not None
                if not valid:
                    reason = "invalid"
            result[key] = {
                "entity_id": entity_id,
                "value": state.state if state else None,
                "unit": state.attributes.get("unit_of_measurement") if state else None,
                "age_minutes": age,
                "maximum_age_minutes": self.settings.get(
                    CONF_SOIL_SENSOR_MAX_AGE, DEFAULT_SOIL_SENSOR_MAX_AGE
                ),
                "reason": reason,
                "reported_at": self._reported_at(state).isoformat() if state else None,
                "normalized_value": (
                    self._read_soil_moisture()[0]
                    if key == CONF_SOIL_MOISTURE_ENTITY
                    else self._read_soil_temperature()
                    if key == CONF_SOIL_TEMPERATURE_ENTITY
                    else state.state == "on"
                    if state and reason == "accepted"
                    else None
                ),
                "normalized_unit": "°C"
                if key == CONF_SOIL_TEMPERATURE_ENTITY
                else "%"
                if key == CONF_SOIL_MOISTURE_ENTITY
                else None,
            }
        now = dt_util.now()
        temperature, selected_temperature_source, _ = self._read_temperature(now)
        weather = self._read_weather_conditions(now)
        rain_id = (
            self.settings.get(CONF_PRECIPITATION_ENTITY)
            or self._find_openweathermap_precipitation_entity()
        )
        sources = {
            CONF_WEATHER_ENTITY: self.settings.get(CONF_WEATHER_ENTITY),
            CONF_TEMPERATURE_ENTITY: self.settings.get(CONF_TEMPERATURE_ENTITY),
            CONF_PRECIPITATION_ENTITY: rain_id,
            "irrigation_flow": self.settings.get("irrigation_flow"),
            "irrigation_valve": self.settings.get("irrigation_valve"),
            "other_valve": self.settings.get("other_valve"),
            "mower_location": self.settings.get("mower_location"),
        }
        for key, entity_id in sources.items():
            state = self.hass.states.get(entity_id) if entity_id else None
            reason = (
                "not_configured"
                if not entity_id
                else "missing"
                if state is None
                else "unavailable"
                if state.state in {"unknown", "unavailable"}
                else "accepted"
            )
            normalized: Any = None
            normalized_unit: str | None = None
            if state and reason == "accepted":
                if key == CONF_WEATHER_ENTITY:
                    normalized = {
                        name: weather.get(name)
                        for name in (
                            "humidity",
                            "wind_speed_m_s",
                            "cloud_coverage",
                            "pressure_hpa",
                            "dew_point",
                        )
                    }
                    reason = "stale" if weather.get("stale", True) else "accepted"
                elif key == CONF_TEMPERATURE_ENTITY:
                    normalized = (
                        temperature
                        if selected_temperature_source == entity_id
                        else None
                    )
                    normalized_unit = "°C"
                    reason = (
                        "accepted" if normalized is not None else "invalid_or_stale"
                    )
                elif key == "irrigation_flow":
                    from .irrigation import _meter_reading

                    reading = _meter_reading(state)
                    normalized = reading[1] if reading else None
                    normalized_unit = (
                        "L"
                        if reading and reading[0] == "volume"
                        else "L/min"
                        if reading
                        else None
                    )
                    reason = "accepted" if reading else "invalid"
                elif key == CONF_PRECIPITATION_ENTITY:
                    try:
                        value = float(state.state)
                        unit = state.attributes.get("unit_of_measurement", "mm")
                        if (
                            not math.isfinite(value)
                            or value < 0
                            or unit not in {"mm", "mm/h", "in", "in/h"}
                        ):
                            raise ValueError("Invalid rain input")
                        normalized = value * 25.4 if unit.startswith("in") else value
                        normalized_unit = "mm/h" if unit.endswith("/h") else "mm"
                        if (
                            unit.endswith("/h")
                            and now - self._reported_at(state)
                            > PRECIPITATION_RATE_STALE_AFTER
                        ):
                            reason = "stale"
                    except (TypeError, ValueError):
                        reason = "invalid"
                else:
                    normalized = state.state
            result[key] = {
                "entity_id": entity_id,
                "value": state.state if state else None,
                "unit": state.attributes.get("unit_of_measurement") if state else None,
                "reported_at": self._reported_at(state).isoformat() if state else None,
                "age_minutes": round(
                    (now - self._reported_at(state)).total_seconds() / 60, 1
                )
                if state
                else None,
                "normalized_value": normalized,
                "normalized_unit": normalized_unit,
                "reason": reason,
            }
        weather_id = sources[CONF_WEATHER_ENTITY]
        weather_state = self.hass.states.get(weather_id) if weather_id else None
        result[CONF_WEATHER_ENTITY]["raw_attributes"] = {
            name: weather_state.attributes.get(name) if weather_state else None
            for name in (
                "temperature",
                "temperature_unit",
                "humidity",
                "wind_speed",
                "wind_speed_unit",
                "cloud_coverage",
                "pressure",
                "pressure_unit",
                "dew_point",
            )
        }
        result[CONF_TEMPERATURE_ENTITY]["effective_source"] = (
            selected_temperature_source
        )
        return result

    def model_diagnostics(self) -> dict[str, Any]:
        """Explain the last soil calculation; never trigger a refresh or write."""
        return {
            "confidence": deepcopy(self._last_model_confidence),
            "last_balance": deepcopy(self._last_soil_trace),
            "moisture_basis": "percentage_of_modeled_plant_available_capacity",
            "field_validated": False,
            "assumptions": [
                "single_root_zone_bucket",
                "profile_based_soil_parameters",
                "estimated_solar_radiation",
                "estimated_day_night_distribution",
            ],
        }

    def update_diagnostics(self) -> dict[str, Any]:
        """Expose process-local refresh outcomes without retaining error text."""
        return {
            "last_success_at": self._last_calculation_success_at,
            "last_failure_at": self._last_calculation_failure_at,
            "last_error_type": self._last_calculation_error_type,
            "last_update_success": self.last_update_success,
        }

    def _read_soil_moisture(self) -> tuple[float | None, str]:
        """Read and validate an optional physical soil-moisture sensor.

        Use configured dry/wet calibration to map a valid fresh sensor reading
        to a bounded percentage. An unavailable observation leaves the model
        as the fallback instead of forcing a false dry/wet measurement.
        """
        entity_id = self.settings.get(CONF_SOIL_MOISTURE_ENTITY)
        if not entity_id:
            return None, "model"
        state = self.hass.states.get(entity_id)
        if not self._soil_sensor_fresh(state):
            return None, "model"
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None, "model"
        if not 0 <= value <= 100:
            return None, "model"
        dry = float(self.settings.get(CONF_SOIL_SENSOR_DRY, DEFAULT_SOIL_SENSOR_DRY))
        wet = float(self.settings.get(CONF_SOIL_SENSOR_WET, DEFAULT_SOIL_SENSOR_WET))
        if wet <= dry:
            return None, "model"
        calibrated = (value - dry) / (wet - dry) * 100
        return round(max(0.0, min(100.0, calibrated)), 1), entity_id

    def _calibrate_soil_model(
        self, now, capacity: float, measured_percent: float | None
    ) -> None:
        """Gently move the modeled reservoir toward a physical sensor value.

        Apply only an eligible new observation to the root-zone water estimate.
        The remembered calibration timestamp prevents repeated application of
        the same sensor report across coordinator updates.
        """
        assert self._state is not None
        if measured_percent is None:
            return
        last_calibrated = dt_util.parse_datetime(
            self.state.soil_sensor_last_calibrated_at or ""
        )
        if (
            last_calibrated is not None
            and now - last_calibrated < SOIL_SENSOR_CALIBRATION_INTERVAL
        ):
            return
        entity_id = self.settings.get(CONF_SOIL_MOISTURE_ENTITY)
        observation = self.hass.states.get(entity_id) if entity_id else None
        if observation is None or (
            last_calibrated is not None
            and self._reported_at(observation) <= last_calibrated
        ):
            # Reusing one report repeatedly would give it more influence than
            # intended. Only a newly reported observation can correct again.
            return
        current = float(self.state.soil_water_mm or 0.0)
        measured_water = capacity * measured_percent / 100
        self.state.soil_water_mm = round(
            current * (1 - SOIL_SENSOR_BLEND_FACTOR)
            + measured_water * SOIL_SENSOR_BLEND_FACTOR,
            2,
        )
        self.state.soil_sensor_last_calibrated_at = now.isoformat()

    def _update_repairs(
        self,
        *,
        temperature_available: bool,
        forecast_available: bool,
        forecast_stale: bool,
        precipitation_available: bool,
        current_weather_available: bool,
    ) -> None:
        """Create and clear actionable Home Assistant repair issues."""
        checks = {
            "temperature_unavailable": temperature_available,
            "forecast_unavailable": forecast_available,
            "forecast_stale": not forecast_stale,
            "observed_precipitation_unavailable": precipitation_available,
            "current_weather_stale": current_weather_available,
        }
        for issue_key, available in checks.items():
            issue_id = f"{self.config_entry.entry_id}_{issue_key}"
            if available:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            else:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=issue_key,
                )

        for config_key in (
            CONF_TEMPERATURE_ENTITY,
            CONF_PRECIPITATION_ENTITY,
            CONF_SOIL_MOISTURE_ENTITY,
            CONF_SOIL_TEMPERATURE_ENTITY,
        ):
            entity_id = self.settings.get(config_key)
            state = self.hass.states.get(entity_id) if entity_id else None
            available = not entity_id or (
                state is not None and state.state not in ("unknown", "unavailable")
            )
            issue_id = f"{self.config_entry.entry_id}_{config_key}_unavailable"
            if available:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            else:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="configured_entity_unavailable",
                    translation_placeholders={"entity_id": str(entity_id)},
                )

    def _find_openweathermap_precipitation_entity(self) -> str | None:
        """Find an enabled rain entity belonging to the selected weather entry.

        Use the entity registry to find a rain sensor associated with the chosen
        weather source. Do not take an unrelated entry's rain sensor simply
        because its name resembles an OpenWeatherMap entity.
        """
        registry = er.async_get(self.hass)
        weather_id = self.settings.get(CONF_WEATHER_ENTITY)
        weather_entry = registry.async_get(weather_id) if weather_id else None
        if weather_entry is None or weather_entry.config_entry_id is None:
            return None
        for entry in registry.entities.values():
            device_class = entry.device_class or entry.original_device_class
            identity = " ".join(
                str(value or "")
                for value in (
                    entry.entity_id,
                    entry.unique_id,
                    entry.original_name,
                    entry.translation_key,
                )
            ).lower()
            if (
                entry.config_entry_id == weather_entry.config_entry_id
                and entry.domain == "sensor"
                and entry.platform == "openweathermap"
                and device_class in {"precipitation", "precipitation_intensity"}
                and ("rain" in identity or "regen" in identity)
                and self.hass.states.get(entry.entity_id) is not None
            ):
                return entry.entity_id
        return None

    def _read_soil_temperature(self) -> float | None:
        """Read an optional soil-temperature sensor in Celsius."""
        entity_id = self.settings.get(CONF_SOIL_TEMPERATURE_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        if not self._soil_sensor_fresh(state):
            return None
        try:
            value = float(state.state)
            if not math.isfinite(value):
                return None
            unit = state.attributes.get("unit_of_measurement")
            if unit and unit != UnitOfTemperature.CELSIUS:
                value = TemperatureConverter.convert(
                    value, unit, UnitOfTemperature.CELSIUS
                )
            if not -90 <= value <= 70:
                return None
            return round(value, 1)
        except (TypeError, ValueError, HomeAssistantError):
            return None

    def _sample_precipitation(self, now) -> tuple[str, float, str, float]:
        """Accumulate measured precipitation and return its latest increment.

        Resolve rate/daily/cumulative semantics and return normalized amounts.
        Baselines prevent counting the same cumulative reading repeatedly.
        Missing data resets the relevant sample and marks the day uncertain;
        it is not interpreted as observed zero rainfall.
        """
        assert self._state is not None
        configured_mode = self.settings.get(
            CONF_PRECIPITATION_MODE, DEFAULT_PRECIPITATION_MODE
        )
        entity_id = (
            self.settings.get(CONF_PRECIPITATION_ENTITY)
            or self._find_openweathermap_precipitation_entity()
        )
        if not entity_id:
            self.state.daily_rain_unknown = True
            self._reset_precipitation_sample()
            return "not_measured", 0.0, configured_mode, 0.0
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            self.state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode, 0.0
        try:
            value = float(state.state)
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid precipitation")
        except (TypeError, ValueError):
            self.state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode, 0.0
        unit = str(state.attributes.get("unit_of_measurement", "mm"))
        if unit not in {"mm", "mm/h", "in", "in/h"}:
            self.state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode, 0.0
        if unit.startswith("in"):
            value *= 25.4
        mode = configured_mode
        if mode == "auto":
            state_class = state.attributes.get("state_class")
            if "/h" in unit:
                mode = "rate"
            elif state_class in {"total", "total_increasing"}:
                mode = "cumulative"
            else:
                mode = "increment"
        if (
            self.state.precipitation_last_source != entity_id
            or self.state.precipitation_last_mode != mode
        ):
            self._reset_precipitation_sample(source=entity_id, mode=mode)
        last_value = self.state.precipitation_last_value
        last_sample = dt_util.parse_datetime(
            self.state.precipitation_last_sample_at or ""
        )
        reported_at = min(now, self._reported_at(state))
        if now - reported_at > PRECIPITATION_RATE_STALE_AFTER:
            self.state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=mode)
            return "unavailable", 0.0, mode, 0.0
        if dt_util.as_local(reported_at).date() != dt_util.as_local(now).date():
            self.state.daily_rain_unknown = True
        if last_sample is not None and reported_at <= last_sample:
            return entity_id, 0.0, mode, value if mode == "rate" else 0.0
        if last_sample is None:
            self.state.daily_rain_unknown = True
        local_midnight = dt_util.as_utc(
            dt_util.start_of_local_day(dt_util.as_local(reported_at))
        )
        increment = 0.0
        daily_increment = 0.0
        intensity = 0.0
        if mode == "rate":
            if last_sample is not None and reported_at - last_sample > timedelta(
                hours=2
            ):
                self.state.daily_rain_unknown = True
            average_rate = (
                (max(0.0, float(last_value)) + value) / 2
                if last_value is not None
                else value
            )
            increment, daily_increment = precipitation_rate_amounts(
                rate_mm_per_hour=average_rate,
                now=reported_at,
                last_sample=last_sample,
                day_start=local_midnight,
            )
            intensity = value
        elif mode == "cumulative" and last_value is not None:
            increment = value - last_value if value >= last_value else value
            daily_increment = increment
            if last_sample is not None:
                elapsed_hours = max(
                    1 / 60, (reported_at - last_sample).total_seconds() / 3600
                )
                intensity = increment / elapsed_hours
            if (
                last_sample is not None
                and dt_util.as_local(last_sample).date()
                != dt_util.as_local(reported_at).date()
            ):
                elapsed_seconds = max(0.0, (reported_at - last_sample).total_seconds())
                current_day_seconds = max(
                    0.0,
                    (reported_at - local_midnight).total_seconds(),
                )
                if elapsed_seconds > 0:
                    daily_increment *= min(1.0, current_day_seconds / elapsed_seconds)
        elif mode == "increment":
            if last_sample is not None:
                increment = value
                daily_increment = (
                    value
                    if dt_util.as_local(reported_at).date()
                    == dt_util.as_local(now).date()
                    else 0.0
                )
                elapsed_hours = max(
                    1 / 60, (reported_at - last_sample).total_seconds() / 3600
                )
                intensity = increment / elapsed_hours
        increment = max(0.0, increment)
        daily_increment = max(0.0, daily_increment)
        self.state.daily_rain_mm += daily_increment
        self.state.precipitation_last_value = value
        self.state.precipitation_last_sample_at = reported_at.isoformat()
        self.state.precipitation_last_source = entity_id
        self.state.precipitation_last_mode = mode
        return entity_id, increment, mode, max(0.0, intensity)

    def _reset_precipitation_sample(
        self, *, source: str | None = None, mode: str | None = None
    ) -> None:
        """Reset a precipitation baseline after a gap or source change.

        Forget the comparison baseline when source, mode or availability
        changes. A later reading cannot safely be subtracted from a baseline
        belonging to another measurement stream.
        """
        assert self._state is not None
        self.state.precipitation_last_value = None
        self.state.precipitation_last_sample_at = None
        self.state.precipitation_last_source = source
        self.state.precipitation_last_mode = mode

    def _finalize_previous_day(self, previous_day: date) -> None:
        """Finalize temperature history and GTS for one completed day.

        Finish a local calendar day's temperature contribution before resetting
        the active sample. Missing temperature days lower GTS completeness.
        """
        assert self._state is not None
        if not self.state.temperature_samples:
            self.state.daily_temperature_history.clear()
            self.state.missing_temperature_days += 1
            return
        mean = self.state.temperature_sum / self.state.temperature_samples
        self.state.gts += grassland_temperature_increment(previous_day, mean)
        self.state.daily_temperature_history.append(round(mean, 2))
        self.state.daily_temperature_history = self.state.daily_temperature_history[
            -14:
        ]

    def _update_soil_model(
        self,
        *,
        now,
        temperature: float | None,
        weather: dict[str, Any],
        precipitation_increment_mm: float,
        precipitation_intensity_mm_h: float,
    ) -> SoilUpdate:
        """Apply measured rain and incremental evapotranspiration.

        Integrate only bounded elapsed time and expose longer gaps explicitly.
        Choose the available ET method, apply rain/interception/runoff and
        drainage, then reconcile eligible sensor calibration. Model water
        remains bounded by the configured root-zone capacity.
        """
        assert self._state is not None
        previous_update = dt_util.parse_datetime(self.state.last_soil_update_at or "")
        self.state.last_soil_update_at = now.isoformat()

        elapsed = now - previous_update if previous_update is not None else None
        elapsed_hours = (
            max(0.0, elapsed.total_seconds() / 3600) if elapsed is not None else 0.0
        )
        maximum_hours = MAX_SOIL_MODEL_INTERVAL.total_seconds() / 3600
        if elapsed_hours > maximum_hours:
            self.state.last_soil_model_gap_at = now.isoformat()
            self.state.last_soil_model_gap_hours = round(
                elapsed_hours - maximum_hours, 2
            )
            elapsed_hours = maximum_hours
        else:
            last_gap = dt_util.parse_datetime(self.state.last_soil_model_gap_at or "")
            if last_gap is not None and now - last_gap >= timedelta(hours=24):
                self.state.last_soil_model_gap_at = None
                self.state.last_soil_model_gap_hours = 0.0

        previous_sample = (
            self.state.weather_samples[-1] if self.state.weather_samples else None
        )

        def _mean_input(key: str) -> float | None:
            current = weather.get(key)
            previous = previous_sample.get(key) if previous_sample else None
            if current is None:
                return previous
            if previous is None:
                return current
            return (float(current) + float(previous)) / 2

        reference_et = 0.0
        daily_reference_et = 0.0
        method = "unavailable"
        local_day = dt_util.as_local(now).date()
        if temperature is not None:
            minimum = self.state.temperature_min
            maximum = self.state.temperature_max
            if minimum is None or maximum is None or maximum - minimum < 2.0:
                minimum, maximum = temperature - 2.0, temperature + 2.0
            humidity = _mean_input("humidity")
            wind = _mean_input("wind_speed_m_s")
            cloud_coverage = _mean_input("cloud_coverage")
            if (
                not weather.get("stale", True)
                and weather.get("humidity") is not None
                and weather.get("wind_speed_m_s") is not None
                and weather.get("cloud_coverage") is not None
            ):
                assert (
                    humidity is not None
                    and wind is not None
                    and cloud_coverage is not None
                )
                daily_reference_et = penman_monteith_evapotranspiration(
                    day=local_day,
                    latitude=self.hass.config.latitude,
                    elevation=float(self.hass.config.elevation or 0.0),
                    temperature_min=minimum,
                    temperature_max=maximum,
                    humidity=humidity,
                    wind_speed_m_s=wind,
                    cloud_coverage=cloud_coverage,
                    pressure_hpa=_mean_input("pressure_hpa"),
                    dew_point=_mean_input("dew_point"),
                )
                method = "penman_monteith_estimated_radiation"
            else:
                daily_reference_et = hargreaves_evapotranspiration(
                    day=local_day,
                    latitude=self.hass.config.latitude,
                    temperature_min=minimum,
                    temperature_max=maximum,
                )
                method = "hargreaves_samani"
        else:
            # Keep the bucket moving during temperature outages, using the
            # latest valid estimate for at most one day, then a seasonal prior.
            for sample in reversed(self.state.weather_samples):
                sampled_at = dt_util.parse_datetime(sample.get("timestamp", ""))
                if sampled_at is None or now - sampled_at > timedelta(hours=24):
                    break
                if sample.get("et_method") in {
                    "penman_monteith_estimated_radiation",
                    "hargreaves_samani",
                }:
                    daily_reference_et = float(sample["reference_et_daily_mm"])
                    break
            if not daily_reference_et:
                daily_reference_et = (
                    0.8
                    if local_day.month in {11, 12, 1, 2}
                    else 3.2
                    if local_day.month in {6, 7, 8}
                    else 1.8
                )
            method = "estimated_fallback"
        reference_et = interval_evapotranspiration(
            daily_et_mm=daily_reference_et,
            end=dt_util.as_local(now),
            interval_hours=elapsed_hours,
            latitude=self.hass.config.latitude,
        )

        soil_type = self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)
        root_depth = float(self.settings.get(CONF_ROOT_DEPTH, DEFAULT_ROOT_DEPTH))
        capacity = soil_capacity(soil_type, root_depth)
        crop_coefficient = 0.35
        if local_day.month in range(3, 11) and (
            temperature is None or temperature >= 5
        ):
            crop_coefficient = 0.8
        crop_coefficient *= {
            "sunny": 1.1,
            "partial_shade": 1.0,
            "shade": 0.8,
        }.get(self.settings.get(CONF_SUN_EXPOSURE, DEFAULT_SUN_EXPOSURE), 1.0)
        last_rain = dt_util.parse_datetime(self.state.last_rain_at or "")
        if last_rain is None or now - last_rain > timedelta(hours=2):
            self.state.canopy_storage_mm = 0.0
        profile = soil_profile(soil_type)
        interception_available = max(
            0.0, profile["interception_mm"] - self.state.canopy_storage_mm
        )
        rain_correction = float(
            self.settings.get(CONF_RAIN_CORRECTION, DEFAULT_RAIN_CORRECTION)
        )
        corrected_precipitation = precipitation_increment_mm * rain_correction
        initial_water = float(self.state.soil_water_mm or 0.0)
        balance = update_soil_water_balance(
            water_mm=float(self.state.soil_water_mm or 0.0),
            soil_type=soil_type,
            precipitation_mm=corrected_precipitation,
            precipitation_intensity_mm_h=(
                precipitation_intensity_mm_h * rain_correction
            ),
            interval_hours=elapsed_hours,
            reference_et_mm=reference_et,
            crop_coefficient=crop_coefficient,
            root_depth_cm=root_depth,
            slope=self.settings.get(CONF_SLOPE, DEFAULT_SLOPE),
            compaction=self.settings.get(CONF_COMPACTION, DEFAULT_COMPACTION),
            interception_available_mm=interception_available,
        )
        if corrected_precipitation > 0:
            self.state.canopy_storage_mm = min(
                profile["interception_mm"],
                self.state.canopy_storage_mm + balance["interception_mm"],
            )
            self.state.last_rain_at = now.isoformat()
            if self.state.daily_rain_mm >= 0.5:
                self.state.last_wet_rain_at = now.isoformat()
        self.state.soil_water_mm = balance["water_mm"]
        self._last_soil_trace = {
            "calculated_at": now.isoformat(),
            "elapsed_hours": max(0.0, elapsed.total_seconds() / 3600)
            if elapsed
            else 0.0,
            "integrated_hours": elapsed_hours,
            "initial_water_mm": initial_water,
            "precipitation_mm": corrected_precipitation,
            "interception_mm": balance["interception_mm"],
            "effective_rain_mm": balance["effective_rain_mm"],
            "runoff_mm": balance["runoff_mm"],
            "drainage_mm": balance["drainage_mm"],
            "actual_et_mm": balance["actual_et_mm"],
            "water_before_sensor_mm": balance["water_mm"],
            "sensor_correction_mm": 0.0,
            "final_water_mm": balance["water_mm"],
            "balance_residual_mm": round(
                initial_water
                + balance["effective_rain_mm"]
                - balance["drainage_mm"]
                - balance["actual_et_mm"]
                - balance["water_mm"],
                4,
            ),
            "method": method,
        }
        local_midnight = dt_util.as_utc(
            dt_util.start_of_local_day(dt_util.as_local(now))
        )
        current_day_hours = min(
            elapsed_hours,
            max(
                0.0,
                (now - local_midnight).total_seconds() / 3600,
            ),
        )
        day_fraction = current_day_hours / elapsed_hours if elapsed_hours else 0.0
        self.state.current_day_evapotranspiration_mm = round(
            self.state.current_day_evapotranspiration_mm
            + balance["actual_et_mm"] * day_fraction,
            2,
        )
        self.state.daily_effective_rain_mm = round(
            self.state.daily_effective_rain_mm
            + balance["effective_rain_mm"] * day_fraction,
            2,
        )
        self.state.daily_runoff_mm = round(
            self.state.daily_runoff_mm + balance["runoff_mm"] * day_fraction, 2
        )
        self.state.daily_drainage_mm = round(
            self.state.daily_drainage_mm + balance["drainage_mm"] * day_fraction,
            2,
        )
        self.state.daily_interception_mm = round(
            self.state.daily_interception_mm
            + balance["interception_mm"] * day_fraction,
            2,
        )
        self.state.weather_samples.append(
            {
                "timestamp": now.isoformat(),
                "temperature": temperature,
                "humidity": weather.get("humidity"),
                "wind_speed_m_s": weather.get("wind_speed_m_s"),
                "cloud_coverage": weather.get("cloud_coverage"),
                "pressure_hpa": weather.get("pressure_hpa"),
                "dew_point": weather.get("dew_point"),
                "reference_et_daily_mm": daily_reference_et,
                "et_method": method,
            }
        )
        self.state.weather_samples = self.state.weather_samples[-96:]
        return {
            **balance,
            "reference_et_daily_mm": round(daily_reference_et, 2),
            "expected_et_24h_mm": round(daily_reference_et * crop_coefficient, 2),
            "method": method,
            "capacity_mm": capacity,
        }

    def _roll_day_and_sample(self, today: date, temperature: float | None) -> None:
        """Finalize a completed day, reset a new year and add one sample.

        Day boundaries follow the HA local timezone. Finish past samples and
        track missed days before adding today's temperature. Annual GTS resets
        and configured baselines are distinct from individual day samples.
        """
        assert self._state is not None
        if self.state.sample_date != today.isoformat():
            previous_day = _parse_date(self.state.sample_date)
            if previous_day:
                self._finalize_previous_day(previous_day)
                self.state.missing_temperature_days += max(
                    0, (today - previous_day).days - 1
                )
            if previous_day and (today - previous_day).days > 1:
                self.state.daily_temperature_history.clear()
            self.state.sample_date = today.isoformat()
            self.state.temperature_sample_at = None
            self.state.temperature_sum = 0.0
            self.state.temperature_samples = 0
            self.state.temperature_min = None
            self.state.temperature_max = None
            self.state.daily_rain_mm = 0.0
            self.state.daily_rain_unknown = False
            self.state.current_day_evapotranspiration_mm = 0.0
            self.state.daily_effective_rain_mm = 0.0
            self.state.daily_runoff_mm = 0.0
            self.state.daily_drainage_mm = 0.0
            self.state.daily_interception_mm = 0.0

        if self.state.year != today.year:
            self.state.year = today.year
            self.state.gts = 0.0
            self.state.mower_started_year = None
            self.state.missing_temperature_days = max(
                0, (today - date(today.year, 1, 1)).days
            )

        if temperature is not None and math.isfinite(temperature):
            now = dt_util.now()
            last_sample = dt_util.parse_datetime(self.state.temperature_sample_at or "")
            if last_sample is not None and now - last_sample < UPDATE_INTERVAL:
                return
            self.state.temperature_sample_at = now.isoformat()
            self.state.temperature_sum += temperature
            self.state.temperature_samples += 1
            self.state.temperature_min = (
                temperature
                if self.state.temperature_min is None
                else min(self.state.temperature_min, temperature)
            )
            self.state.temperature_max = (
                temperature
                if self.state.temperature_max is None
                else max(self.state.temperature_max, temperature)
            )

    async def _async_update_data(self) -> LawnData:
        """Serialize model updates against transactional maintenance writes.

        Every scheduled refresh acquires the model lock before mutating state.
        This prevents maintenance rollback from erasing a simultaneous soil
        update and prevents snapshots from mixing transaction stages.
        """
        async with self._state_lock:
            try:
                data = await self._async_calculate_locked()
            except Exception as err:
                # Record the exception type only, then preserve HA error handling.
                self._last_calculation_failure_at = dt_util.utcnow().isoformat()
                self._last_calculation_error_type = type(err).__name__
                raise
            self._last_calculation_success_at = dt_util.utcnow().isoformat()
            return data

    async def _async_calculate_locked(self) -> LawnData:
        """Calculate all current recommendations.

        The caller owns the model lock throughout sampling and persistence.
        Update observations/model first, obtain normalized cached forecasts,
        derive recommendations and confidence, overlay live irrigation, and
        save the runtime state before returning the calculated LawnData.
        """
        assert self._state is not None
        now = dt_util.now()
        today = dt_util.as_local(now).date()
        settings = self.settings
        temperature, temperature_source, temperature_age_minutes = (
            self._read_temperature(now)
        )
        unavailable = temperature is None
        if unavailable != self._weather_unavailable:
            if unavailable:
                _LOGGER.warning(
                    "Lawn temperature input unavailable; automatic irrigation is blocked"
                )
            else:
                _LOGGER.info("Lawn temperature input available again")
            self._weather_unavailable = unavailable
        weather_conditions = self._read_weather_conditions(now)
        weather_input_ages = [
            value
            for value in (
                temperature_age_minutes,
                weather_conditions.get("age_minutes"),
            )
            if value is not None
        ]
        weather_input_age_minutes = (
            max(weather_input_ages) if weather_input_ages else None
        )
        self._roll_day_and_sample(today, temperature)
        (
            precipitation_source,
            precipitation_increment,
            precipitation_mode,
            precipitation_intensity,
        ) = self._sample_precipitation(now)
        soil_update = self._update_soil_model(
            now=now,
            temperature=temperature,
            weather=weather_conditions,
            precipitation_increment_mm=precipitation_increment,
            precipitation_intensity_mm_h=precipitation_intensity,
        )
        forecast = await self._async_forecast("daily")
        hourly_forecast = await self._async_forecast("hourly")
        weather_state = self.hass.states.get(settings[CONF_WEATHER_ENTITY])
        provider_updated_at = (
            getattr(weather_state, "last_reported", weather_state.last_updated)
            if weather_state
            else None
        )

        def _effective_forecast_update(fetch_time):
            if fetch_time is None:
                return None
            return (
                min(fetch_time, provider_updated_at)
                if provider_updated_at is not None
                else fetch_time
            )

        daily_updated_at = _effective_forecast_update(self._forecast_updated_at)
        hourly_updated_at = _effective_forecast_update(self._hourly_forecast_updated_at)
        daily_stale = bool(forecast) and (
            daily_updated_at is None or now - daily_updated_at > FORECAST_STALE_AFTER
        )
        hourly_stale = bool(hourly_forecast) and (
            hourly_updated_at is None or now - hourly_updated_at > FORECAST_STALE_AFTER
        )
        usable_forecast = [] if daily_stale else forecast
        usable_hourly_forecast = [] if hourly_stale else hourly_forecast
        forecast_stale = daily_stale or hourly_stale
        forecast_updates = [
            value
            for value, available in (
                (daily_updated_at, bool(forecast)),
                (hourly_updated_at, bool(hourly_forecast)),
            )
            if value is not None and available
        ]
        forecast_updated_at = min(forecast_updates) if forecast_updates else None
        forecast_age_minutes = (
            max(0, int((now - forecast_updated_at).total_seconds() / 60))
            if forecast_updated_at is not None
            else None
        )

        last_watering = _parse_date(self.state.last_watering)
        last_fertilizing = _parse_date(self.state.last_fertilizing)
        last_mowing = _parse_date(self.state.last_mowing)
        area = float(settings.get(CONF_AREA, DEFAULT_AREA))
        capacity = soil_capacity(
            settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE),
            float(settings.get(CONF_ROOT_DEPTH, DEFAULT_ROOT_DEPTH)),
        )
        measured_soil_moisture, soil_moisture_source = self._read_soil_moisture()
        soil_temperature = self._read_soil_temperature()
        before_sensor = float(self.state.soil_water_mm or 0.0)
        confidence = assess_soil_confidence(
            modeled_percent=before_sensor / capacity * 100,
            measured_percent=measured_soil_moisture,
            rain_known=not self.state.daily_rain_unknown,
            weather_stale=weather_conditions.get("stale", True),
            model_gap_hours=self.state.last_soil_model_gap_hours,
            method=soil_update["method"],
        )
        self._last_model_confidence = confidence
        self._calibrate_soil_model(now, capacity, measured_soil_moisture)
        if self._last_soil_trace is not None:
            self._last_soil_trace["sensor_correction_mm"] = round(
                float(self.state.soil_water_mm or 0.0) - before_sensor, 4
            )
            self._last_soil_trace["final_water_mm"] = float(
                self.state.soil_water_mm or 0.0
            )
        soil_water = max(0.0, min(capacity, float(self.state.soil_water_mm or 0.0)))
        soil_moisture = round(soil_water / capacity * 100, 1)
        history = self.state.daily_temperature_history[-7:]
        growth_temperature = round(fmean(history), 1) if history else temperature
        effective_growth_temperature = (
            soil_temperature if soil_temperature is not None else growth_temperature
        )
        growth = growth_state(
            today=today,
            gts=self.state.gts,
            growth_temperature=effective_growth_temperature,
            soil_moisture_percent=soil_moisture,
            mower_started_year=self.state.mower_started_year,
            previous_state=self.state.last_growth_state,
        )
        self.state.last_growth_state = growth
        mower = mower_recommendation(
            growth=growth,
            mower_started_year=self.state.mower_started_year,
            year=today.year,
            last_mowing=last_mowing,
            today=today,
            mode=settings.get(CONF_MOWING_MODE, "manual"),
            interval_factor=float(settings.get(CONF_MOWING_INTERVAL_FACTOR, 1.0)),
            last_mowing_at=dt_util.parse_datetime(self.state.last_mowing_at or ""),
            now=now,
        )
        wet_until, wet_reason = self._pause_mower_when_wet(now, mower)
        mowing_confidence = "medium"
        if temperature is None:
            mower["status"] = "collecting_data"
            mowing_confidence = "low"
        elif temperature <= 0 or (
            soil_temperature is not None and soil_temperature <= 0
        ):
            mower["status"] = "pause_frost"
        if mower["status"] in {
            "collecting_data",
            "winter_off",
            "keep_off",
            "pause_drought",
            "pause_frost",
        }:
            mower["next_at"] = None
            mower["next_date"] = None
        if mower.get("next_at"):
            mower["next_date"] = dt_util.as_local(mower["next_at"]).date()

        watering = watering_recommendation(
            today=today,
            area_m2=area,
            sun_exposure=settings.get(CONF_SUN_EXPOSURE, DEFAULT_SUN_EXPOSURE),
            soil_type=settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE),
            current_temperature=temperature,
            forecast=usable_forecast,
            hourly_forecast=usable_hourly_forecast,
            last_watering=last_watering,
            soil_moisture_percent=soil_moisture,
            soil_water_mm=soil_water,
            soil_capacity_mm=capacity,
            growth=growth,
            now=now,
            expected_et_24h_mm=soil_update["expected_et_24h_mm"],
            rain_efficiency={
                "sandy": 0.9,
                "loamy": 0.85,
                "clayey": 0.7,
            }.get(settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE), 0.85),
        )
        watering_window = recommended_watering_window(
            usable_hourly_forecast,
            dt_util.as_local(now),
            wind_speed_unit="m/s",
        )
        if precipitation_source in {"not_measured", "unavailable"}:
            watering["confidence"] = (
                "medium" if watering["confidence"] == "high" else "low"
            )
        fertilizing = fertilizing_recommendation(
            today=today,
            gts=self.state.gts,
            area_m2=area,
            lawn_type=settings.get(CONF_LAWN_TYPE, DEFAULT_LAWN_TYPE),
            last_fertilizing=last_fertilizing,
        )
        watering_attention = watering["status"] in {
            "water_now",
            "water_soon",
            "wait_for_rain",
        }
        if fertilizing["recommended"] and watering_attention:
            fertilizing.update(
                recommended=False,
                status="water_before_fertilizing",
                dose=0.0,
                total_kg=0.0,
            )
            fertilizing["reasons"].insert(0, "avoid_fertilizing_dry_lawn")
        if fertilizing["recommended"] and temperature is not None and temperature >= 28:
            fertilizing.update(
                recommended=False,
                status="postpone_fertilizing_heat",
                dose=0.0,
                total_kg=0.0,
            )
            fertilizing["reasons"].insert(0, "postpone_fertilizing_above_28c")

        data_warnings: list[str] = []
        if temperature is None:
            data_warnings.append("temperature_unavailable")
        if weather_conditions.get("stale", True):
            data_warnings.append("current_weather_stale")
        if soil_update["method"] in {"hargreaves_samani", "estimated_fallback"}:
            data_warnings.append("evapotranspiration_fallback")
        if not forecast and not hourly_forecast:
            data_warnings.append("forecast_unavailable")
        elif forecast_stale:
            data_warnings.append("forecast_stale")
        elif watering["forecast_coverage_hours"] < 24:
            data_warnings.append("forecast_coverage_incomplete")
        if (
            settings.get(CONF_PRECIPITATION_ENTITY)
            and precipitation_source == "unavailable"
        ):
            data_warnings.append("precipitation_sensor_unavailable")
        if settings.get(CONF_SOIL_MOISTURE_ENTITY) and measured_soil_moisture is None:
            data_warnings.append("soil_moisture_sensor_unavailable")
        if settings.get(CONF_SOIL_TEMPERATURE_ENTITY) and soil_temperature is None:
            data_warnings.append("soil_temperature_sensor_unavailable")
        if self.state.daily_rain_unknown:
            data_warnings.append("observed_precipitation_unavailable")
        if len(history) < 7:
            data_warnings.append("temperature_history_incomplete")
        if self.state.last_soil_model_gap_hours > 0:
            data_warnings.append("soil_model_time_gap")
        if self.state.missing_temperature_days > 0:
            data_warnings.append("gts_incomplete")
        if (
            temperature is None
            or (not forecast and not hourly_forecast)
            or forecast_stale
        ):
            data_quality = "insufficient"
        elif data_warnings:
            data_quality = "limited"
        else:
            data_quality = "good"

        action = next_lawn_action(
            watering_status=watering["status"],
            fertilizing_recommended=fertilizing["recommended"],
            mower_status=mower["status"],
        )

        self._update_repairs(
            temperature_available=temperature is not None,
            forecast_available=bool(forecast or hourly_forecast),
            forecast_stale=forecast_stale and bool(forecast or hourly_forecast),
            precipitation_available=(
                not settings.get(CONF_PRECIPITATION_ENTITY)
                or precipitation_source not in {"not_measured", "unavailable"}
            ),
            current_weather_available=(
                not weather_conditions.get("stale", True)
                and not weather_conditions.get("unavailable", False)
            ),
        )

        data = LawnData(
            gts=round(self.state.gts, 1),
            lawn_status=lawn_status(
                growth=growth,
                watering_status=watering["status"],
                fertilizing_due=fertilizing["recommended"],
                mower_status=mower["status"],
            ),
            watering_recommended=watering["recommended"],
            watering_status=watering["status"],
            watering_mm=watering["mm"],
            watering_liters=watering["liters"],
            watering_reasons=watering["reasons"],
            forecast_rain_mm=watering["rain"],
            forecast_rain_24h_mm=watering["rain_24h"],
            forecast_rain_48h_mm=watering["rain_48h"],
            forecast_rain_72h_mm=watering["rain_72h"],
            next_rain_at=watering["next_rain_at"],
            forecast_updated_at=(
                forecast_updated_at.isoformat()
                if forecast_updated_at is not None
                else None
            ),
            observed_rain_today_mm=(
                None
                if self.state.daily_rain_unknown
                else round(self.state.daily_rain_mm, 1)
            ),
            precipitation_source=precipitation_source,
            watering_confidence=watering["confidence"],
            fertilizing_recommended=fertilizing["recommended"],
            fertilizing_status=fertilizing["status"],
            fertilizer_npk=fertilizing["npk"],
            fertilizer_dose_g_m2=fertilizing["dose"],
            fertilizer_total_kg=fertilizing["total_kg"],
            fertilizing_reasons=fertilizing["reasons"],
            next_fertilizing_window=fertilizing["next_window"],
            last_watering=last_watering,
            last_fertilizing=last_fertilizing,
            last_mowing=last_mowing,
            days_since_watering=days_since(last_watering, today),
            days_since_fertilizing=days_since(last_fertilizing, today),
            days_since_mowing=days_since(last_mowing, today),
            current_temperature=temperature,
            temperature_source=temperature_source,
            growth_status=growth,
            mower_status=mower["status"],
            mower_wet_until=(
                wet_until.isoformat() if wet_until and now < wet_until else None
            ),
            mower_wet_reason=(wet_reason if wet_until and now < wet_until else None),
            mower_start_recommended=mower["status"] == "start_mower",
            mower_can_be_switched_off=mower["status"] == "winter_off",
            mowing_interval_days=mower["interval"],
            next_mowing_date=mower["next_date"],
            next_mowing_at=(
                mower["next_at"].isoformat() if mower.get("next_at") else None
            ),
            last_mowing_at=self.state.last_mowing_at,
            mowing_mode=settings.get(CONF_MOWING_MODE, "manual"),
            mowing_reason=mower["status"],
            mowing_confidence=mowing_confidence,
            last_robot_session_started_at=self.state.last_robot_session_started_at,
            last_robot_session_finished_at=self.state.last_robot_session_finished_at,
            last_robot_session_active_seconds=self.state.last_robot_session_active_seconds,
            mowing_record_source=self.state.last_mowing_source,
            growth_temperature_7d=growth_temperature,
            soil_moisture_percent=soil_moisture,
            measured_soil_moisture_percent=measured_soil_moisture,
            soil_moisture_source=soil_moisture_source,
            soil_water_mm=round(soil_water, 1),
            soil_capacity_mm=capacity,
            daily_evapotranspiration_mm=(self.state.current_day_evapotranspiration_mm),
            reference_evapotranspiration_mm=soil_update["reference_et_daily_mm"],
            evapotranspiration_method=soil_update["method"],
            effective_rain_today_mm=self.state.daily_effective_rain_mm,
            runoff_today_mm=self.state.daily_runoff_mm,
            drainage_today_mm=self.state.daily_drainage_mm,
            interception_today_mm=self.state.daily_interception_mm,
            water_stress_factor=soil_update["water_stress_factor"],
            weather_age_minutes=weather_input_age_minutes,
            humidity=weather_conditions.get("humidity"),
            wind_speed_m_s=weather_conditions.get("wind_speed_m_s"),
            cloud_coverage=weather_conditions.get("cloud_coverage"),
            pressure_hpa=weather_conditions.get("pressure_hpa"),
            dew_point=weather_conditions.get("dew_point"),
            hours_until_rain=watering.get("hours_until_rain"),
            expected_et_24h_mm=watering.get("expected_et_24h", 0.0),
            forecast_72h_estimated=watering.get("forecast_72h_estimated", False),
            probability_adjusted_rain_24h_mm=watering.get(
                "probability_adjusted_rain_24h"
            ),
            watering_window_start=watering_window["start"],
            watering_window_end=watering_window["end"],
            watering_window_reason=watering_window["reason"],
            watering_window_temperature=watering_window["temperature"],
            watering_window_wind_speed_m_s=watering_window["wind_speed_m_s"],
            soil_model_confidence=confidence["level"],
            soil_model_confidence_reasons=confidence["reasons"],
            soil_sensor_deviation_percentage_points=confidence[
                "sensor_deviation_percentage_points"
            ],
            next_action=action,
            data_quality=data_quality,
            data_warnings=data_warnings,
            forecast_age_minutes=forecast_age_minutes,
            forecast_coverage_hours=watering["forecast_coverage_hours"],
            forecast_stale=forecast_stale,
            temperature_history_days=len(history),
            last_calculation_at=now.isoformat(),
            last_soil_update_at=self.state.last_soil_update_at,
            soil_model_gap_hours=self.state.last_soil_model_gap_hours,
            precipitation_mode=precipitation_mode,
            soil_temperature=soil_temperature,
            last_maintenance_event=(
                self.state.maintenance_history[-1]
                if self.state.maintenance_history
                else None
            ),
            gts_complete=self.state.missing_temperature_days == 0,
            missing_temperature_days=self.state.missing_temperature_days,
            irrigation_status=(
                "not_configured"
                if self.irrigation is None
                else self.state.irrigation_last_status
            ),
            irrigation_enabled=self.state.irrigation_enabled,
            irrigation_liters=(
                round(self.state.irrigation_session["liters"], 1)
                if self.state.irrigation_session
                and self.state.irrigation_session["meter_kind"] != "timer"
                else self.state.irrigation_last_liters
            ),
            irrigation_reason=self.state.irrigation_last_reason,
        )
        self.apply_live_irrigation_status(data)
        await self._store.async_save(self.state.as_dict())
        return data

    def _append_maintenance_event(
        self, action: str, previous: dict[str, Any], **details: Any
    ) -> None:
        """Append a reversible maintenance event to the local history."""
        assert self._state is not None
        self.state.maintenance_history.append(
            {
                "action": action,
                "timestamp": dt_util.now().isoformat(),
                "details": details,
                "previous": previous,
            }
        )
        self.state.maintenance_history = self.state.maintenance_history[-20:]

    def _is_recent_maintenance_event(self, action: str, within: timedelta) -> bool:
        """Return whether an automatic input recently recorded the same action."""
        assert self._state is not None
        for event in reversed(self.state.maintenance_history):
            if event.get("action") != action:
                continue
            timestamp = dt_util.parse_datetime(str(event.get("timestamp", "")))
            return bool(timestamp and dt_util.now() - timestamp <= within)
        return False

    def record_water_usage(
        self,
        at: datetime,
        liters: float | None,
        *,
        source: str,
        measurement_gap: bool = False,
        allocations: list[dict] | None = None,
        allocation_estimated: bool = False,
        session_id: str | None = None,
        uncertainty_dates: list[str] | None = None,
    ) -> str:
        """Keep a separate one-year ledger; maintenance history remains bounded.

        Keep physical irrigation and manually recorded/estimated water in one
        ledger, with source and measurement quality preserved. Per-date
        allocations must add up to the rounded session amount without negative
        daily shares; uncertainty dates keep budgets conservative.
        """
        identifier = uuid4().hex
        cutoff = (
            dt_util.as_local(dt_util.now()).date() - timedelta(days=366)
        ).isoformat()
        self.state.water_usage = [
            item for item in self.state.water_usage if item.get("date", "") >= cutoff
        ]
        if allocations and liters is not None:
            allocations = [dict(item) for item in allocations]
            remainder = liters - sum(item["liters"] for item in allocations)
            if abs(remainder) < 0.02:
                if remainder >= 0:
                    allocations[-1]["liters"] += remainder
                else:
                    # A tiny final-day share must not become negative when
                    # the session total is rounded down to two decimals.
                    correction = -remainder
                    for item in reversed(allocations):
                        deducted = min(item["liters"], correction)
                        item["liters"] -= deducted
                        correction -= deducted
                        if correction <= 0:
                            break
            elif remainder > 0:
                allocations.append(
                    {
                        "date": dt_util.as_local(at).date().isoformat(),
                        "liters": remainder,
                    }
                )
                allocation_estimated = True
        self.state.water_usage.append(
            {
                "id": identifier,
                "date": dt_util.as_local(at).date().isoformat(),
                "recorded_at": at.isoformat(),
                "liters": liters,
                "source": source,
                "measurement_gap": measurement_gap,
                "allocations": allocations or [],
                "allocation_estimated": allocation_estimated,
                "session_id": session_id,
                "uncertainty_dates": uncertainty_dates or [],
            }
        )
        return identifier

    async def _async_save_maintenance_locked(self) -> None:
        """Resolve a write before cancelling, keeping disk and model consistent.

        The caller already owns the model lock. Save a deep snapshot in a
        shielded task and wait through every caller cancellation before
        releasing that lock. Commit status is true only after a successful
        verified write; propagate cancellation after its outcome is known.
        """
        snapshot = deepcopy(self.state.as_dict())

        async def save() -> OSError | HomeAssistantError | None:
            # Return expected failures to avoid unhandled task exceptions when
            # the caller is cancelled while the shield resolves the write.
            try:
                await self._store.async_save(snapshot)
            except (OSError, HomeAssistantError) as err:
                return err
            return None

        saving = asyncio.create_task(save(), name="lawn_save_maintenance")
        cancelled = False
        while True:
            try:
                error = await asyncio.shield(saving)
                break
            except asyncio.CancelledError:
                if saving.cancelled():
                    raise
                cancelled = True
        self._maintenance_committed = error is None
        if cancelled:
            raise asyncio.CancelledError
        if error is not None:
            raise error

    async def _async_maintenance_transaction(
        self, operation: Callable[[], Awaitable[None]]
    ) -> None:
        """Rollback failed writes without reverting concurrent valve supervision.

        Snapshot only fields affected by maintenance. A failed uncommitted
        operation restores those fields, preserving unrelated valve-safety
        changes that may occur while storage awaits. Refresh happens outside
        this transaction so it cannot deadlock on the same model lock.
        """
        keys = (
            "last_watering",
            "last_watering_at",
            "soil_water_mm",
            "water_usage",
            "maintenance_history",
            "irrigation_last_session",
            "last_fertilizing",
            "last_mowing",
            "last_mowing_at",
            "last_mowing_source",
            "last_mowing_event_id",
            "mower_started_year",
            "last_robot_session_started_at",
            "last_robot_session_finished_at",
            "last_robot_session_active_seconds",
        )
        async with self._state_lock:
            previous = {key: deepcopy(getattr(self._state, key)) for key in keys}
            self._maintenance_committed = False
            try:
                await operation()
            except (OSError, HomeAssistantError, asyncio.CancelledError) as err:
                if not self._maintenance_committed:
                    for key, value in previous.items():
                        setattr(self._state, key, value)
                if isinstance(err, (asyncio.CancelledError, ServiceValidationError)):
                    raise
                raise HomeAssistantError(
                    "Maintenance could not be saved; no changes were applied",
                    translation_domain=DOMAIN,
                    translation_key="maintenance_storage_failed",
                ) from err

    async def async_mark_watered(
        self,
        amount_mm: float | None = None,
        *,
        deduplicate: bool = False,
        was_wet: bool = False,
        refresh: bool = True,
        recorded_at: datetime | None = None,
        usage: bool = True,
    ) -> None:
        """Record water atomically and refresh only after committing."""
        await self._async_maintenance_transaction(
            lambda: self._async_mark_watered_locked(
                amount_mm,
                deduplicate=deduplicate,
                was_wet=was_wet,
                recorded_at=recorded_at,
                usage=usage,
            )
        )
        if refresh:
            await self.async_request_refresh()

    async def async_mark_fertilized(
        self,
        product_npk: str | None = None,
        amount_kg: float | None = None,
        *,
        recorded_at: datetime | None = None,
    ) -> None:
        """Commit fertilizing before publishing it as completed."""
        await self._async_maintenance_transaction(
            lambda: self._async_mark_fertilized_locked(
                product_npk, amount_kg, recorded_at=recorded_at
            )
        )
        await self.async_request_refresh()

    async def async_mark_mowed(
        self,
        *,
        deduplicate: bool = False,
        event_id: str | None = None,
        recorded_at: datetime | None = None,
        source: str = "manual",
        active_seconds: float | None = None,
        session_started_at: datetime | None = None,
    ) -> None:
        """Commit mowing atomically with other maintenance actions."""
        await self._async_maintenance_transaction(
            lambda: self._async_mark_mowed_locked(
                deduplicate=deduplicate,
                event_id=event_id,
                recorded_at=recorded_at,
                source=source,
                active_seconds=active_seconds,
                session_started_at=session_started_at,
            )
        )
        await self.async_request_refresh()

    async def async_undo_last_action(self) -> None:
        """Commit an undo atomically before refreshing entities."""
        await self._async_maintenance_transaction(self._async_undo_last_action_locked)
        await self.async_request_refresh()

    async def _async_mark_watered_locked(
        self,
        amount_mm: float | None = None,
        *,
        deduplicate: bool = False,
        was_wet: bool = False,
        recorded_at: datetime | None = None,
        usage: bool = True,
        completed_at: datetime | None = None,
    ) -> None:
        """Record watering and add the calculated or configured amount.

        Current watering adds efficiency-adjusted water up to soil capacity.
        Historical entries update history/usage without refilling today's
        model. Record the amount actually applied so undo can subtract that
        credit without restoring an obsolete full soil snapshot.
        """
        assert self._state is not None
        if usage and self.irrigation and self.irrigation.active:
            raise ServiceValidationError(
                "Cannot manually record water during a controlled irrigation session",
                translation_domain=DOMAIN,
                translation_key="action_5",
            )
        if deduplicate and self._is_recent_maintenance_event(
            "watering", timedelta(minutes=30)
        ):
            return
        previous = {
            "last_watering": self.state.last_watering,
            "last_watering_at": self.state.last_watering_at,
            "soil_water_mm": self.state.soil_water_mm,
        }
        now = dt_util.now()
        event_at = recorded_at or completed_at or now
        historical = recorded_at is not None
        last_at = dt_util.parse_datetime(self.state.last_watering_at or "")
        last_date = _parse_date(self.state.last_watering)
        event_date = dt_util.as_local(event_at).date()
        advances_date = (last_date is None or event_date >= last_date) and (
            last_at is None or event_at >= last_at
        )
        if advances_date:
            self.state.last_watering = event_date.isoformat()
        capacity = soil_capacity(
            self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE),
            float(self.settings.get(CONF_ROOT_DEPTH, DEFAULT_ROOT_DEPTH)),
        )
        assumed_mm = amount_mm
        if assumed_mm is None:
            assumed_mm = (
                self.data.watering_mm
                if self.data.watering_mm > 0
                else float(
                    self.settings.get(
                        CONF_DEFAULT_WATERING_AMOUNT, DEFAULT_WATERING_AMOUNT
                    )
                )
            )
        assumed_mm = max(0.0, float(assumed_mm))
        if (assumed_mm > 0 or was_wet) and advances_date:
            self.state.last_watering_at = event_at.isoformat()
        old_water = float(self.state.soil_water_mm or 0.0)
        effective_amount = (0.0 if historical else assumed_mm) * float(
            self.settings.get(CONF_IRRIGATION_EFFICIENCY, DEFAULT_IRRIGATION_EFFICIENCY)
        )
        self.state.soil_water_mm = min(capacity, old_water + effective_amount)
        applied_mm = self.state.soil_water_mm - old_water
        usage_id = (
            self.record_water_usage(
                event_at,
                assumed_mm * float(self.settings.get(CONF_AREA, DEFAULT_AREA)),
                source="manual_estimate" if amount_mm is None else "manual_record",
            )
            if usage
            else (self.state.irrigation_last_session or {}).get("usage_id")
        )
        if not usage and self.state.irrigation_last_session:
            self.state.irrigation_last_session["effective_model_mm"] = round(
                applied_mm, 3
            )
        self._append_maintenance_event(
            "watering",
            previous,
            amount_mm=assumed_mm,
            effective_amount_mm=effective_amount,
            applied_mm=applied_mm,
            recorded_at=event_at.isoformat(),
            historical=historical,
            usage_id=usage_id,
        )
        await self._async_save_maintenance_locked()

    async def _async_mark_fertilized_locked(
        self,
        product_npk: str | None = None,
        amount_kg: float | None = None,
        *,
        recorded_at: datetime | None = None,
    ) -> None:
        """Record fertilizing as completed today.

        Store product/amount details in maintenance history. An older recorded
        event remains in history without moving the latest fertilizing date
        backwards. Persistence is handled by the shared maintenance writer.
        """
        assert self._state is not None
        previous = {"last_fertilizing": self.state.last_fertilizing}
        event_at = recorded_at or dt_util.now()
        event_date = dt_util.as_local(event_at).date().isoformat()
        if not self.state.last_fertilizing or event_date >= self.state.last_fertilizing:
            self.state.last_fertilizing = event_date
        self._append_maintenance_event(
            "fertilizing",
            previous,
            product_npk=product_npk,
            amount_kg=amount_kg,
            recorded_at=event_at.isoformat(),
        )
        await self._async_save_maintenance_locked()

    async def _async_mark_mowed_locked(
        self,
        *,
        deduplicate: bool = False,
        event_id: str | None = None,
        recorded_at: datetime | None = None,
        source: str = "manual",
        active_seconds: float | None = None,
        session_started_at: datetime | None = None,
    ) -> None:
        """Record mowing and acknowledge the mowing season for this year.

        Serialize mowing deduplication and date updates inside the model
        transaction. Robot/completion-input event IDs prevent repeated
        processing; historical entries do not replace newer mowing timestamps.
        """
        async with self._mowing_lock:
            assert self._state is not None
            if event_id and event_id == self.state.last_mowing_event_id:
                return
            if (
                deduplicate
                and not event_id
                and self._is_recent_maintenance_event("mowing", timedelta(seconds=60))
            ):
                return
            now = recorded_at or dt_util.now()
            previous_at = dt_util.parse_datetime(self.state.last_mowing_at or "")
            if event_id and previous_at and now <= previous_at:
                return
            previous = {
                "last_mowing": self.state.last_mowing,
                "last_mowing_at": self.state.last_mowing_at,
                "last_mowing_source": self.state.last_mowing_source,
                "last_mowing_event_id": self.state.last_mowing_event_id,
                "mower_started_year": self.state.mower_started_year,
                "last_robot_session_started_at": self.state.last_robot_session_started_at,
                "last_robot_session_finished_at": self.state.last_robot_session_finished_at,
                "last_robot_session_active_seconds": self.state.last_robot_session_active_seconds,
            }
            if previous_at is None or now >= previous_at:
                self.state.last_mowing = dt_util.as_local(now).date().isoformat()
                self.state.last_mowing_at = now.isoformat()
                if source == "robot_estimate":
                    self.state.last_robot_session_started_at = (
                        session_started_at.isoformat() if session_started_at else None
                    )
                    self.state.last_robot_session_finished_at = now.isoformat()
                    self.state.last_robot_session_active_seconds = active_seconds
                self.state.last_mowing_source = source
                self.state.last_mowing_event_id = event_id
                self.state.mower_started_year = dt_util.as_local(now).year
            self._append_maintenance_event(
                "mowing",
                previous,
                source=source,
                active_seconds=active_seconds,
                recorded_at=now.isoformat(),
            )
            await self._async_save_maintenance_locked()

    async def _async_undo_last_action_locked(self) -> None:
        """Undo the latest maintenance event recorded by the integration.

        Reverse the latest maintenance/model credit, preserving physical
        irrigation evidence and the daily automatic safety lock. Undo removes
        manual usage but marks measured irrigation usage as undone because
        physically delivered water cannot be taken back.
        """
        assert self._state is not None
        if self.irrigation and self.irrigation.active:
            raise ServiceValidationError(
                "Stop controlled irrigation before undoing maintenance",
                translation_domain=DOMAIN,
                translation_key="action_7",
            )
        if not self.state.maintenance_history:
            return
        event = self.state.maintenance_history.pop()
        usage_id = event.get("details", {}).get("usage_id")
        if usage_id:
            retained = []
            for item in self.state.water_usage:
                if item.get("id") == usage_id:
                    if item.get("source") != "irrigation":
                        continue
                    item["undone"] = True
                    item["undone_at"] = dt_util.now().isoformat()
                retained.append(item)
            self.state.water_usage = retained
        last_session = self.state.irrigation_last_session
        if usage_id and last_session and last_session.get("usage_id") == usage_id:
            # Retain the physical session for diagnosis, but make its undone
            # ledger and model credit explicit. Keep the daily safety lock.
            last_session["undone"] = True
            last_session["undone_at"] = dt_util.now().isoformat()
            last_session["effective_model_mm"] = 0.0
        if event.get("action") == "watering" and "applied_mm" in event.get(
            "details", {}
        ):
            self.state.last_watering = event.get("previous", {}).get("last_watering")
            self.state.last_watering_at = event.get("previous", {}).get(
                "last_watering_at"
            )
            applied_mm = max(0.0, float(event["details"]["applied_mm"]))
            self.state.soil_water_mm = max(
                0.0, float(self.state.soil_water_mm or 0.0) - applied_mm
            )
        else:
            for key, value in event.get("previous", {}).items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
        await self._async_save_maintenance_locked()

    async def async_mark_mowing_started(self) -> None:
        """Record mowing through the legacy method name."""
        await self.async_mark_mowed()
