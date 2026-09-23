"""Coordinator for Lawn Care Assistant."""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .calculations import (
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
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_RAIN_CORRECTION,
    CONF_ROOT_DEPTH,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_SENSOR_DRY,
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
from .models import LawnData, RuntimeState

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

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
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
        self._forecast_updated_at = None
        self._hourly_forecast_cache: list[dict[str, Any]] = []
        self._hourly_forecast_updated_at = None
        self.irrigation = None

    @property
    def settings(self) -> dict[str, Any]:
        """Return merged setup data and editable options."""
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def water_model_version(self) -> int:
        """Return the persisted water-balance model version."""
        return self._state.water_model_version if self._state is not None else 3

    async def _async_setup(self) -> None:
        """Load persisted running totals once."""
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
                last_watering=stored.get("last_watering"),
                last_fertilizing=stored.get("last_fertilizing"),
                last_mowing=stored.get("last_mowing"),
                configured_initial_gts=float(
                    stored.get("configured_initial_gts", initial_gts)
                ),
                configured_last_watering=stored.get("configured_last_watering"),
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
                configured_soil_type=stored.get("configured_soil_type"),
                configured_root_depth_cm=float(
                    stored.get("configured_root_depth_cm", root_depth)
                ),
                missing_temperature_days=int(stored.get("missing_temperature_days", 0)),
                irrigation_enabled=bool(stored.get("irrigation_enabled", False)),
                irrigation_session=stored.get("irrigation_session"),
                irrigation_last_auto_date=stored.get("irrigation_last_auto_date"),
                irrigation_last_status=stored.get("irrigation_last_status", "idle"),
                irrigation_last_reason=stored.get("irrigation_last_reason"),
                irrigation_last_liters=stored.get("irrigation_last_liters"),
                irrigation_valve_id=stored.get("irrigation_valve_id"),
            )
            if not stored.get("local_day_model", False):
                # Earlier releases stored UTC-based partial days. They cannot be
                # safely attributed to a local calendar day after migration.
                self._state.sample_date = today.isoformat()
                self._state.temperature_sum = 0.0
                self._state.temperature_samples = 0
                self._state.temperature_min = None
                self._state.temperature_max = None
                self._state.daily_rain_mm = 0.0
                self._state.daily_rain_unknown = True
                self._state.current_day_evapotranspiration_mm = 0.0
                self._state.daily_effective_rain_mm = 0.0
                self._state.daily_runoff_mm = 0.0
                self._state.daily_drainage_mm = 0.0
                self._state.daily_interception_mm = 0.0
                if initial_gts == 0:
                    self._state.missing_temperature_days = max(
                        self._state.missing_temperature_days,
                        (today - date(today.year, 1, 1)).days,
                    )
                self._state.local_day_model = True
        else:
            initial_watering = settings.get(CONF_LAST_WATERING)
            initial_fertilizing = settings.get(CONF_LAST_FERTILIZING)
            self._state = RuntimeState(
                year=today.year,
                gts=initial_gts,
                sample_date=today.isoformat(),
                last_watering=initial_watering,
                last_fertilizing=initial_fertilizing,
                configured_initial_gts=initial_gts,
                configured_last_watering=initial_watering,
                configured_last_fertilizing=initial_fertilizing,
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

        if self._state.configured_soil_type is None:
            self._state.configured_soil_type = soil_type
            self._state.configured_root_depth_cm = root_depth
        elif (
            self._state.configured_soil_type != soil_type
            or self._state.configured_root_depth_cm != root_depth
        ):
            old_capacity = soil_capacity(
                self._state.configured_soil_type,
                self._state.configured_root_depth_cm,
            )
            fill_fraction = min(
                1.0, max(0.0, float(self._state.soil_water_mm or 0.0) / old_capacity)
            )
            self._state.soil_water_mm = capacity * fill_fraction
            self._state.configured_soil_type = soil_type
            self._state.configured_root_depth_cm = root_depth
        self._state.water_model_version = max(self._state.water_model_version, 3)
        if self._state.irrigation_valve_id != settings.get(CONF_IRRIGATION_VALVE):
            self._state.irrigation_enabled = False
            self._state.irrigation_valve_id = settings.get(CONF_IRRIGATION_VALVE)

        if initial_gts != self._state.configured_initial_gts:
            self._state.gts = initial_gts
            self._state.configured_initial_gts = initial_gts
            self._state.missing_temperature_days = (
                0 if initial_gts > 0 else (today - date(today.year, 1, 1)).days
            )
        if initial_moisture != self._state.configured_initial_soil_moisture:
            self._state.soil_water_mm = capacity * initial_moisture / 100
            self._state.configured_initial_soil_moisture = initial_moisture
        if self._state.soil_water_mm is None:
            self._state.soil_water_mm = capacity * initial_moisture / 100
        self._state.soil_water_mm = min(capacity, self._state.soil_water_mm)

        for setting_key, state_key, configured_key in (
            (CONF_LAST_WATERING, "last_watering", "configured_last_watering"),
            (
                CONF_LAST_FERTILIZING,
                "last_fertilizing",
                "configured_last_fertilizing",
            ),
        ):
            configured_value = settings.get(setting_key)
            if configured_value != getattr(self._state, configured_key):
                setattr(self._state, state_key, configured_value)
                setattr(self._state, configured_key, configured_value)

    @staticmethod
    def _reported_at(state):
        """Return the provider report timestamp of a Home Assistant state."""
        return getattr(state, "last_reported", None) or state.last_updated

    @staticmethod
    def _age_minutes(now, timestamp) -> int:
        """Return a non-negative age in full minutes."""
        return max(0, int((now - timestamp).total_seconds() / 60))

    def _read_temperature(self, now) -> tuple[float | None, str, int | None]:
        """Read the selected outdoor sensor, falling back to OpenWeatherMap."""
        temperature_entity = self.settings.get(CONF_TEMPERATURE_ENTITY)
        state = self.hass.states.get(temperature_entity) if temperature_entity else None
        if state is not None and state.state not in ("unknown", "unavailable"):
            try:
                reported_at = self._reported_at(state)
                if now - reported_at > CURRENT_WEATHER_STALE_AFTER:
                    raise ValueError("selected temperature is stale")
                value = float(state.state)
                unit = state.attributes.get("unit_of_measurement")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
                return value, temperature_entity, self._age_minutes(now, reported_at)
            except (TypeError, ValueError, HomeAssistantError):
                pass

        weather = self.hass.states.get(self.settings[CONF_WEATHER_ENTITY])
        if weather is not None:
            try:
                reported_at = self._reported_at(weather)
                if now - reported_at > CURRENT_WEATHER_STALE_AFTER:
                    return None, "unavailable", self._age_minutes(now, reported_at)
                value = float(weather.attributes["temperature"])
                unit = weather.attributes.get("temperature_unit")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
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
        """Read cached meteorological inputs from the selected weather entity."""
        state = self.hass.states.get(self.settings[CONF_WEATHER_ENTITY])
        if state is None or state.state in ("unknown", "unavailable"):
            return {"age_minutes": None, "stale": True, "unavailable": True}
        reported_at = self._reported_at(state)
        age_minutes = self._age_minutes(now, reported_at)
        wind = self._number_attribute(state, "wind_speed")
        wind_unit = str(state.attributes.get("wind_speed_unit", "m/s")).lower()
        if wind is not None:
            if "km/h" in wind_unit or "kmh" in wind_unit:
                wind /= 3.6
            elif "mph" in wind_unit:
                wind *= 0.44704
            elif "kn" in wind_unit:
                wind *= 0.514444
            elif "ft/s" in wind_unit:
                wind *= 0.3048
        pressure = self._number_attribute(state, "pressure")
        pressure_unit = str(state.attributes.get("pressure_unit", "hPa")).lower()
        if pressure is not None:
            if pressure_unit == "pa":
                pressure /= 100
            elif pressure_unit == "kpa":
                pressure *= 10
            elif "inhg" in pressure_unit:
                pressure *= 33.8639
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
            except HomeAssistantError:
                dew_point = None
        return {
            "reported_at": reported_at.isoformat(),
            "age_minutes": age_minutes,
            "stale": now - reported_at > CURRENT_WEATHER_STALE_AFTER,
            "unavailable": False,
            "humidity": self._number_attribute(state, "humidity"),
            "wind_speed_m_s": wind,
            "cloud_coverage": self._number_attribute(state, "cloud_coverage"),
            "pressure_hpa": pressure,
            "dew_point": dew_point,
        }

    async def _async_forecast(self, forecast_type: str) -> list[dict[str, Any]]:
        """Return a cached daily or hourly forecast from Home Assistant."""
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
            if forecast_type == "hourly":
                self._hourly_forecast_cache = forecast
                self._hourly_forecast_updated_at = now
            else:
                self._forecast_cache = forecast
                self._forecast_updated_at = now
            return forecast
        return cached

    def _read_soil_moisture(self) -> tuple[float | None, str]:
        """Read and validate an optional physical soil-moisture sensor."""
        entity_id = self.settings.get(CONF_SOIL_MOISTURE_ENTITY)
        if not entity_id:
            return None, "model"
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
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
        """Gently move the modeled reservoir toward a physical sensor value."""
        assert self._state is not None
        if measured_percent is None:
            return
        last_calibrated = dt_util.parse_datetime(
            self._state.soil_sensor_last_calibrated_at or ""
        )
        if (
            last_calibrated is not None
            and now - last_calibrated < SOIL_SENSOR_CALIBRATION_INTERVAL
        ):
            return
        current = float(self._state.soil_water_mm or 0.0)
        measured_water = capacity * measured_percent / 100
        self._state.soil_water_mm = round(
            current * (1 - SOIL_SENSOR_BLEND_FACTOR)
            + measured_water * SOIL_SENSOR_BLEND_FACTOR,
            2,
        )
        self._state.soil_sensor_last_calibrated_at = now.isoformat()

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
        """Find an enabled rain entity belonging to the selected weather entry."""
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
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
            unit = state.attributes.get("unit_of_measurement")
            if unit and unit != UnitOfTemperature.CELSIUS:
                value = TemperatureConverter.convert(
                    value, unit, UnitOfTemperature.CELSIUS
                )
            return round(value, 1)
        except (TypeError, ValueError, HomeAssistantError):
            return None

    def _sample_precipitation(self, now) -> tuple[str, float, str, float]:
        """Accumulate measured precipitation and return its latest increment."""
        assert self._state is not None
        configured_mode = self.settings.get(
            CONF_PRECIPITATION_MODE, DEFAULT_PRECIPITATION_MODE
        )
        entity_id = (
            self.settings.get(CONF_PRECIPITATION_ENTITY)
            or self._find_openweathermap_precipitation_entity()
        )
        if not entity_id:
            self._state.daily_rain_unknown = True
            self._reset_precipitation_sample()
            return "not_measured", 0.0, configured_mode, 0.0
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            self._state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode, 0.0
        try:
            value = max(0.0, float(state.state))
        except (TypeError, ValueError):
            self._state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode, 0.0
        unit = str(state.attributes.get("unit_of_measurement", "mm"))
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
            self._state.precipitation_last_source != entity_id
            or self._state.precipitation_last_mode != mode
        ):
            self._reset_precipitation_sample(source=entity_id, mode=mode)
        last_value = self._state.precipitation_last_value
        last_sample = dt_util.parse_datetime(
            self._state.precipitation_last_sample_at or ""
        )
        reported_at = min(now, self._reported_at(state))
        if now - reported_at > PRECIPITATION_RATE_STALE_AFTER:
            self._state.daily_rain_unknown = True
            self._reset_precipitation_sample(source=entity_id, mode=mode)
            return "unavailable", 0.0, mode, 0.0
        if dt_util.as_local(reported_at).date() != dt_util.as_local(now).date():
            self._state.daily_rain_unknown = True
        if last_sample is not None and reported_at <= last_sample:
            return entity_id, 0.0, mode, value if mode == "rate" else 0.0
        if last_sample is None:
            self._state.daily_rain_unknown = True
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
                self._state.daily_rain_unknown = True
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
        self._state.daily_rain_mm += daily_increment
        self._state.precipitation_last_value = value
        self._state.precipitation_last_sample_at = reported_at.isoformat()
        self._state.precipitation_last_source = entity_id
        self._state.precipitation_last_mode = mode
        return entity_id, increment, mode, max(0.0, intensity)

    def _reset_precipitation_sample(
        self, *, source: str | None = None, mode: str | None = None
    ) -> None:
        """Reset a precipitation baseline after a gap or source change."""
        assert self._state is not None
        self._state.precipitation_last_value = None
        self._state.precipitation_last_sample_at = None
        self._state.precipitation_last_source = source
        self._state.precipitation_last_mode = mode

    def _finalize_previous_day(self, previous_day: date) -> None:
        """Finalize temperature history and GTS for one completed day."""
        assert self._state is not None
        if not self._state.temperature_samples:
            self._state.missing_temperature_days += 1
            return
        mean = self._state.temperature_sum / self._state.temperature_samples
        self._state.gts += grassland_temperature_increment(previous_day, mean)
        self._state.daily_temperature_history.append(round(mean, 2))
        self._state.daily_temperature_history = self._state.daily_temperature_history[
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
    ) -> dict[str, Any]:
        """Apply measured rain and incremental evapotranspiration."""
        assert self._state is not None
        previous_update = dt_util.parse_datetime(self._state.last_soil_update_at or "")
        self._state.last_soil_update_at = now.isoformat()

        elapsed = now - previous_update if previous_update is not None else None
        elapsed_hours = (
            max(0.0, elapsed.total_seconds() / 3600) if elapsed is not None else 0.0
        )
        maximum_hours = MAX_SOIL_MODEL_INTERVAL.total_seconds() / 3600
        if elapsed_hours > maximum_hours:
            self._state.last_soil_model_gap_at = now.isoformat()
            self._state.last_soil_model_gap_hours = round(
                elapsed_hours - maximum_hours, 2
            )
            elapsed_hours = maximum_hours
        else:
            last_gap = dt_util.parse_datetime(self._state.last_soil_model_gap_at or "")
            if last_gap is not None and now - last_gap >= timedelta(hours=24):
                self._state.last_soil_model_gap_at = None
                self._state.last_soil_model_gap_hours = 0.0

        previous_sample = (
            self._state.weather_samples[-1] if self._state.weather_samples else None
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
            minimum = self._state.temperature_min
            maximum = self._state.temperature_max
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
            for sample in reversed(self._state.weather_samples):
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
        }.get(self.settings.get(CONF_SUN_EXPOSURE), 1.0)
        last_rain = dt_util.parse_datetime(self._state.last_rain_at or "")
        if last_rain is None or now - last_rain > timedelta(hours=2):
            self._state.canopy_storage_mm = 0.0
        profile = soil_profile(soil_type)
        interception_available = max(
            0.0, profile["interception_mm"] - self._state.canopy_storage_mm
        )
        rain_correction = float(
            self.settings.get(CONF_RAIN_CORRECTION, DEFAULT_RAIN_CORRECTION)
        )
        corrected_precipitation = precipitation_increment_mm * rain_correction
        balance = update_soil_water_balance(
            water_mm=float(self._state.soil_water_mm or 0.0),
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
            self._state.canopy_storage_mm = min(
                profile["interception_mm"],
                self._state.canopy_storage_mm + balance["interception_mm"],
            )
            self._state.last_rain_at = now.isoformat()
        self._state.soil_water_mm = balance["water_mm"]
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
        self._state.current_day_evapotranspiration_mm = round(
            self._state.current_day_evapotranspiration_mm
            + balance["actual_et_mm"] * day_fraction,
            2,
        )
        self._state.daily_effective_rain_mm = round(
            self._state.daily_effective_rain_mm
            + balance["effective_rain_mm"] * day_fraction,
            2,
        )
        self._state.daily_runoff_mm = round(
            self._state.daily_runoff_mm + balance["runoff_mm"] * day_fraction, 2
        )
        self._state.daily_drainage_mm = round(
            self._state.daily_drainage_mm + balance["drainage_mm"] * day_fraction,
            2,
        )
        self._state.daily_interception_mm = round(
            self._state.daily_interception_mm
            + balance["interception_mm"] * day_fraction,
            2,
        )
        self._state.weather_samples.append(
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
        self._state.weather_samples = self._state.weather_samples[-96:]
        return {
            **balance,
            "reference_et_daily_mm": round(daily_reference_et, 2),
            "expected_et_24h_mm": round(daily_reference_et * crop_coefficient, 2),
            "method": method,
            "capacity_mm": capacity,
        }

    def _roll_day_and_sample(self, today: date, temperature: float | None) -> None:
        """Finalize a completed day, reset a new year and add one sample."""
        assert self._state is not None
        if self._state.sample_date != today.isoformat():
            previous_day = _parse_date(self._state.sample_date)
            if previous_day:
                self._finalize_previous_day(previous_day)
                self._state.missing_temperature_days += max(
                    0, (today - previous_day).days - 1
                )
            self._state.sample_date = today.isoformat()
            self._state.temperature_sum = 0.0
            self._state.temperature_samples = 0
            self._state.temperature_min = None
            self._state.temperature_max = None
            self._state.daily_rain_mm = 0.0
            self._state.daily_rain_unknown = False
            self._state.current_day_evapotranspiration_mm = 0.0
            self._state.daily_effective_rain_mm = 0.0
            self._state.daily_runoff_mm = 0.0
            self._state.daily_drainage_mm = 0.0
            self._state.daily_interception_mm = 0.0

        if self._state.year != today.year:
            self._state.year = today.year
            self._state.gts = 0.0
            self._state.mower_started_year = None
            self._state.missing_temperature_days = max(
                0, (today - date(today.year, 1, 1)).days
            )

        if temperature is not None:
            self._state.temperature_sum += temperature
            self._state.temperature_samples += 1
            self._state.temperature_min = (
                temperature
                if self._state.temperature_min is None
                else min(self._state.temperature_min, temperature)
            )
            self._state.temperature_max = (
                temperature
                if self._state.temperature_max is None
                else max(self._state.temperature_max, temperature)
            )

    async def _async_update_data(self) -> LawnData:
        """Calculate all current recommendations."""
        assert self._state is not None
        now = dt_util.now()
        today = dt_util.as_local(now).date()
        settings = self.settings
        temperature, temperature_source, temperature_age_minutes = (
            self._read_temperature(now)
        )
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

        last_watering = _parse_date(self._state.last_watering)
        last_fertilizing = _parse_date(self._state.last_fertilizing)
        last_mowing = _parse_date(self._state.last_mowing)
        area = float(settings.get(CONF_AREA, DEFAULT_AREA))
        capacity = soil_capacity(
            settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE),
            float(settings.get(CONF_ROOT_DEPTH, DEFAULT_ROOT_DEPTH)),
        )
        measured_soil_moisture, soil_moisture_source = self._read_soil_moisture()
        soil_temperature = self._read_soil_temperature()
        self._calibrate_soil_model(now, capacity, measured_soil_moisture)
        soil_water = max(0.0, min(capacity, float(self._state.soil_water_mm or 0.0)))
        soil_moisture = round(soil_water / capacity * 100, 1)
        history = self._state.daily_temperature_history[-7:]
        growth_temperature = round(fmean(history), 1) if history else temperature
        effective_growth_temperature = (
            soil_temperature if soil_temperature is not None else growth_temperature
        )
        growth = growth_state(
            today=today,
            gts=self._state.gts,
            growth_temperature=effective_growth_temperature,
            soil_moisture_percent=soil_moisture,
            mower_started_year=self._state.mower_started_year,
            previous_state=self._state.last_growth_state,
        )
        self._state.last_growth_state = growth
        mower = mower_recommendation(
            growth=growth,
            mower_started_year=self._state.mower_started_year,
            year=today.year,
            last_mowing=last_mowing,
            today=today,
        )

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
            }.get(settings.get(CONF_SOIL_TYPE), 0.85),
        )
        weather_state_wind_unit = (
            str(weather_state.attributes.get("wind_speed_unit", "m/s"))
            if weather_state is not None
            else "m/s"
        )
        watering_window = recommended_watering_window(
            usable_hourly_forecast,
            dt_util.as_local(now),
            wind_speed_unit=weather_state_wind_unit,
        )
        if precipitation_source in {"not_measured", "unavailable"}:
            watering["confidence"] = (
                "medium" if watering["confidence"] == "high" else "low"
            )
        fertilizing = fertilizing_recommendation(
            today=today,
            gts=self._state.gts,
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
        if self._state.daily_rain_unknown:
            data_warnings.append("observed_precipitation_unavailable")
        if len(history) < 7:
            data_warnings.append("temperature_history_incomplete")
        if self._state.last_soil_model_gap_hours > 0:
            data_warnings.append("soil_model_time_gap")
        if self._state.missing_temperature_days > 0:
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
            gts=round(self._state.gts, 1),
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
                if self._state.daily_rain_unknown
                else round(self._state.daily_rain_mm, 1)
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
            mower_start_recommended=mower["status"] == "start_mower",
            mower_can_be_switched_off=mower["status"] == "winter_off",
            mowing_interval_days=mower["interval"],
            next_mowing_date=mower["next_date"],
            growth_temperature_7d=growth_temperature,
            soil_moisture_percent=soil_moisture,
            measured_soil_moisture_percent=measured_soil_moisture,
            soil_moisture_source=soil_moisture_source,
            soil_water_mm=round(soil_water, 1),
            soil_capacity_mm=capacity,
            daily_evapotranspiration_mm=(self._state.current_day_evapotranspiration_mm),
            reference_evapotranspiration_mm=soil_update["reference_et_daily_mm"],
            evapotranspiration_method=soil_update["method"],
            effective_rain_today_mm=self._state.daily_effective_rain_mm,
            runoff_today_mm=self._state.daily_runoff_mm,
            drainage_today_mm=self._state.daily_drainage_mm,
            interception_today_mm=self._state.daily_interception_mm,
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
            soil_model_confidence=(
                "high"
                if measured_soil_moisture is not None
                else "low"
                if self._state.last_soil_model_gap_hours > 0
                or self._state.daily_rain_unknown
                or soil_update["method"] == "estimated_fallback"
                or weather_conditions.get("stale", True)
                else "high"
                if precipitation_source not in {"not_measured", "unavailable"}
                and soil_update["method"] == "penman_monteith_estimated_radiation"
                else "medium"
                if temperature is not None
                else "low"
            ),
            next_action=action,
            data_quality=data_quality,
            data_warnings=data_warnings,
            forecast_age_minutes=forecast_age_minutes,
            forecast_coverage_hours=watering["forecast_coverage_hours"],
            forecast_stale=forecast_stale,
            temperature_history_days=len(history),
            last_calculation_at=now.isoformat(),
            last_soil_update_at=self._state.last_soil_update_at,
            soil_model_gap_hours=self._state.last_soil_model_gap_hours,
            precipitation_mode=precipitation_mode,
            soil_temperature=soil_temperature,
            last_maintenance_event=(
                self._state.maintenance_history[-1]
                if self._state.maintenance_history
                else None
            ),
            gts_complete=self._state.missing_temperature_days == 0,
            missing_temperature_days=self._state.missing_temperature_days,
            irrigation_status=(
                "not_configured"
                if self.irrigation is None
                else self._state.irrigation_last_status
            ),
            irrigation_enabled=self._state.irrigation_enabled,
            irrigation_liters=(
                round(self._state.irrigation_session["liters"], 1)
                if self._state.irrigation_session
                and self._state.irrigation_session["meter_kind"] != "timer"
                else self._state.irrigation_last_liters
            ),
            irrigation_reason=self._state.irrigation_last_reason,
        )
        await self._store.async_save(self._state.as_dict())
        return data

    def _append_maintenance_event(
        self, action: str, previous: dict[str, Any], **details: Any
    ) -> None:
        """Append a reversible maintenance event to the local history."""
        assert self._state is not None
        self._state.maintenance_history.append(
            {
                "action": action,
                "timestamp": dt_util.now().isoformat(),
                "details": details,
                "previous": previous,
            }
        )
        self._state.maintenance_history = self._state.maintenance_history[-20:]

    def _is_recent_maintenance_event(self, action: str, within: timedelta) -> bool:
        """Return whether an automatic input recently recorded the same action."""
        assert self._state is not None
        for event in reversed(self._state.maintenance_history):
            if event.get("action") != action:
                continue
            timestamp = dt_util.parse_datetime(str(event.get("timestamp", "")))
            return bool(timestamp and dt_util.now() - timestamp <= within)
        return False

    async def async_mark_watered(
        self, amount_mm: float | None = None, *, deduplicate: bool = False
    ) -> None:
        """Record watering and add the calculated or configured amount."""
        assert self._state is not None
        if deduplicate and self._is_recent_maintenance_event(
            "watering", timedelta(minutes=30)
        ):
            return
        previous = {
            "last_watering": self._state.last_watering,
            "soil_water_mm": self._state.soil_water_mm,
        }
        self._state.last_watering = dt_util.as_local(dt_util.now()).date().isoformat()
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
        old_water = float(self._state.soil_water_mm or 0.0)
        effective_amount = assumed_mm * float(
            self.settings.get(CONF_IRRIGATION_EFFICIENCY, DEFAULT_IRRIGATION_EFFICIENCY)
        )
        self._state.soil_water_mm = min(capacity, old_water + effective_amount)
        applied_mm = self._state.soil_water_mm - old_water
        self._append_maintenance_event(
            "watering",
            previous,
            amount_mm=assumed_mm,
            effective_amount_mm=effective_amount,
            applied_mm=applied_mm,
        )
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_fertilized(
        self, product_npk: str | None = None, amount_kg: float | None = None
    ) -> None:
        """Record fertilizing as completed today."""
        assert self._state is not None
        previous = {"last_fertilizing": self._state.last_fertilizing}
        self._state.last_fertilizing = (
            dt_util.as_local(dt_util.now()).date().isoformat()
        )
        self._append_maintenance_event(
            "fertilizing",
            previous,
            product_npk=product_npk,
            amount_kg=amount_kg,
        )
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowed(self, *, deduplicate: bool = False) -> None:
        """Record mowing and acknowledge the mowing season for this year."""
        assert self._state is not None
        if deduplicate and self._is_recent_maintenance_event(
            "mowing", timedelta(hours=12)
        ):
            return
        now = dt_util.now()
        previous = {
            "last_mowing": self._state.last_mowing,
            "mower_started_year": self._state.mower_started_year,
        }
        self._state.last_mowing = dt_util.as_local(now).date().isoformat()
        self._state.mower_started_year = dt_util.as_local(now).year
        self._append_maintenance_event("mowing", previous)
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_undo_last_action(self) -> None:
        """Undo the latest maintenance event recorded by the integration."""
        assert self._state is not None
        if not self._state.maintenance_history:
            return
        event = self._state.maintenance_history.pop()
        if event.get("action") == "watering" and "applied_mm" in event.get(
            "details", {}
        ):
            self._state.last_watering = event.get("previous", {}).get("last_watering")
            applied_mm = max(0.0, float(event["details"]["applied_mm"]))
            self._state.soil_water_mm = max(
                0.0, float(self._state.soil_water_mm or 0.0) - applied_mm
            )
        else:
            for key, value in event.get("previous", {}).items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowing_started(self) -> None:
        """Record mowing through the legacy method name."""
        await self.async_mark_mowed()
