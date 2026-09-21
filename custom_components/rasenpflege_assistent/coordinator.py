"""Coordinator for Lawn Care Assistant."""

from __future__ import annotations

import logging
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
    lawn_status,
    mower_recommendation,
    next_lawn_action,
    precipitation_rate_amounts,
    soil_capacity,
    update_soil_water,
    watering_recommendation,
)
from .const import (
    CONF_AREA,
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_LAST_FERTILIZING,
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_TEMPERATURE_ENTITY,
    CONF_SOIL_TYPE,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_AREA,
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_LAWN_TYPE,
    DEFAULT_PRECIPITATION_MODE,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_EXPOSURE,
    DEFAULT_WATERING_AMOUNT,
    DOMAIN,
    FORECAST_CACHE_INTERVAL,
    FORECAST_STALE_AFTER,
    MAX_SOIL_MODEL_INTERVAL,
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

    @property
    def settings(self) -> dict[str, Any]:
        """Return merged setup data and editable options."""
        return {**self.config_entry.data, **self.config_entry.options}

    async def _async_setup(self) -> None:
        """Load persisted running totals once."""
        today = dt_util.now().date()
        stored = await self._store.async_load()
        settings = self.settings
        initial_gts = float(settings.get(CONF_INITIAL_GTS, DEFAULT_INITIAL_GTS))
        initial_moisture = float(
            settings.get(CONF_INITIAL_SOIL_MOISTURE, DEFAULT_INITIAL_SOIL_MOISTURE)
        )
        capacity = soil_capacity(settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))

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
            )
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
            )

        if initial_gts != self._state.configured_initial_gts:
            self._state.gts = initial_gts
            self._state.configured_initial_gts = initial_gts
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

    def _read_temperature(self) -> tuple[float | None, str]:
        """Read the selected outdoor sensor, falling back to OpenWeatherMap."""
        temperature_entity = self.settings.get(CONF_TEMPERATURE_ENTITY)
        state = self.hass.states.get(temperature_entity) if temperature_entity else None
        if state is not None and state.state not in ("unknown", "unavailable"):
            try:
                value = float(state.state)
                unit = state.attributes.get("unit_of_measurement")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
                return value, temperature_entity
            except (TypeError, ValueError, HomeAssistantError):
                pass

        weather = self.hass.states.get(self.settings[CONF_WEATHER_ENTITY])
        if weather is not None:
            try:
                value = float(weather.attributes["temperature"])
                unit = weather.attributes.get("temperature_unit")
                if unit and unit != UnitOfTemperature.CELSIUS:
                    value = TemperatureConverter.convert(
                        value, unit, UnitOfTemperature.CELSIUS
                    )
                return value, self.settings[CONF_WEATHER_ENTITY]
            except (KeyError, TypeError, ValueError, HomeAssistantError):
                pass
        return None, "unavailable"

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
        return round(value, 1), entity_id

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
    ) -> None:
        """Create and clear actionable Home Assistant repair issues."""
        checks = {
            "temperature_unavailable": temperature_available,
            "forecast_unavailable": forecast_available,
            "forecast_stale": not forecast_stale,
            "observed_precipitation_unavailable": precipitation_available,
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

    def _sample_precipitation(self, now) -> tuple[str, float, str]:
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
            self._reset_precipitation_sample()
            return "not_measured", 0.0, configured_mode
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode
        try:
            value = max(0.0, float(state.state))
        except (TypeError, ValueError):
            self._reset_precipitation_sample(source=entity_id, mode=configured_mode)
            return "unavailable", 0.0, configured_mode
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
        increment = 0.0
        daily_increment = 0.0
        if mode == "rate":
            increment, daily_increment = precipitation_rate_amounts(
                rate_mm_per_hour=value,
                now=now,
                last_sample=last_sample,
            )
        elif mode == "cumulative" and last_value is not None:
            increment = value - last_value if value >= last_value else value
            daily_increment = increment
            if last_sample is not None and last_sample.date() != now.date():
                elapsed_seconds = max(0.0, (now - last_sample).total_seconds())
                current_day_seconds = max(
                    0.0,
                    (
                        now - now.replace(hour=0, minute=0, second=0, microsecond=0)
                    ).total_seconds(),
                )
                if elapsed_seconds > 0:
                    daily_increment *= min(1.0, current_day_seconds / elapsed_seconds)
        elif mode == "increment":
            changed_at = state.last_changed
            if last_sample is not None and changed_at > last_sample:
                increment = value
                daily_increment = value if changed_at.date() == now.date() else 0.0
        increment = max(0.0, increment)
        daily_increment = max(0.0, daily_increment)
        self._state.daily_rain_mm += daily_increment
        self._state.precipitation_last_value = value
        self._state.precipitation_last_sample_at = now.isoformat()
        self._state.precipitation_last_source = entity_id
        self._state.precipitation_last_mode = mode
        return entity_id, increment, mode

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
        precipitation_increment_mm: float,
    ) -> None:
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

        reference_et = 0.0
        if temperature is not None and elapsed_hours > 0:
            minimum = self._state.temperature_min
            maximum = self._state.temperature_max
            if minimum is None or maximum is None or maximum - minimum < 2.0:
                minimum, maximum = temperature - 2.0, temperature + 2.0
            daily_et = hargreaves_evapotranspiration(
                day=now.date(),
                latitude=self.hass.config.latitude,
                temperature_min=minimum,
                temperature_max=maximum,
            )
            reference_et = daily_et * elapsed_hours / 24

        soil_type = self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)
        capacity = soil_capacity(soil_type)
        crop_coefficient = 0.35
        if temperature is not None and temperature >= 5 and now.month in range(3, 11):
            crop_coefficient = 0.8
        crop_coefficient *= {
            "sunny": 1.1,
            "partial_shade": 1.0,
            "shade": 0.8,
        }.get(self.settings.get(CONF_SUN_EXPOSURE), 1.0)
        rain_efficiency = {
            "sandy": 0.9,
            "loamy": 0.85,
            "clayey": 0.7,
        }.get(soil_type, 0.85)
        water, actual_et = update_soil_water(
            water_mm=float(self._state.soil_water_mm or 0.0),
            capacity_mm=capacity,
            precipitation_mm=precipitation_increment_mm,
            reference_et_mm=reference_et,
            crop_coefficient=crop_coefficient,
            rain_efficiency=rain_efficiency,
        )
        self._state.soil_water_mm = water
        self._state.current_day_evapotranspiration_mm = round(
            self._state.current_day_evapotranspiration_mm + actual_et, 2
        )

    def _roll_day_and_sample(self, today: date, temperature: float | None) -> None:
        """Finalize a completed day, reset a new year and add one sample."""
        assert self._state is not None
        if self._state.sample_date != today.isoformat():
            previous_day = _parse_date(self._state.sample_date)
            if previous_day:
                self._finalize_previous_day(previous_day)
            self._state.sample_date = today.isoformat()
            self._state.temperature_sum = 0.0
            self._state.temperature_samples = 0
            self._state.temperature_min = None
            self._state.temperature_max = None
            self._state.daily_rain_mm = 0.0
            self._state.current_day_evapotranspiration_mm = 0.0

        if self._state.year != today.year:
            self._state.year = today.year
            self._state.gts = 0.0
            self._state.mower_started_year = None

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
        today = now.date()
        settings = self.settings
        temperature, temperature_source = self._read_temperature()
        self._roll_day_and_sample(today, temperature)
        (
            precipitation_source,
            precipitation_increment,
            precipitation_mode,
        ) = self._sample_precipitation(now)
        self._update_soil_model(
            now=now,
            temperature=temperature,
            precipitation_increment_mm=precipitation_increment,
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
        capacity = soil_capacity(settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))
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
        if precipitation_source == "not_measured":
            data_warnings.append("observed_precipitation_unavailable")
        if len(history) < 7:
            data_warnings.append("temperature_history_incomplete")
        if self._state.last_soil_model_gap_hours > 0:
            data_warnings.append("soil_model_time_gap")
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
            precipitation_available=precipitation_source
            not in {"not_measured", "unavailable"},
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
            observed_rain_today_mm=round(self._state.daily_rain_mm, 1),
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
            soil_model_confidence=(
                "high"
                if measured_soil_moisture is not None
                else "low"
                if self._state.last_soil_model_gap_hours > 0
                else "high"
                if precipitation_source not in {"not_measured", "unavailable"}
                else "medium"
                if forecast or hourly_forecast
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

    async def async_mark_watered(self, amount_mm: float | None = None) -> None:
        """Record watering and add the calculated or configured amount."""
        assert self._state is not None
        previous = {
            "last_watering": self._state.last_watering,
            "soil_water_mm": self._state.soil_water_mm,
        }
        self._state.last_watering = dt_util.now().date().isoformat()
        capacity = soil_capacity(self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))
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
        self._state.soil_water_mm = min(
            capacity, float(self._state.soil_water_mm or 0.0) + assumed_mm
        )
        self._append_maintenance_event("watering", previous, amount_mm=assumed_mm)
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_fertilized(
        self, product_npk: str | None = None, amount_kg: float | None = None
    ) -> None:
        """Record fertilizing as completed today."""
        assert self._state is not None
        previous = {"last_fertilizing": self._state.last_fertilizing}
        self._state.last_fertilizing = dt_util.now().date().isoformat()
        self._append_maintenance_event(
            "fertilizing",
            previous,
            product_npk=product_npk,
            amount_kg=amount_kg,
        )
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowed(self) -> None:
        """Record mowing and acknowledge the mowing season for this year."""
        assert self._state is not None
        now = dt_util.now()
        previous = {
            "last_mowing": self._state.last_mowing,
            "mower_started_year": self._state.mower_started_year,
        }
        self._state.last_mowing = now.date().isoformat()
        self._state.mower_started_year = now.year
        self._append_maintenance_event("mowing", previous)
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_undo_last_action(self) -> None:
        """Undo the latest maintenance event recorded by the integration."""
        assert self._state is not None
        if not self._state.maintenance_history:
            return
        event = self._state.maintenance_history.pop()
        for key, value in event.get("previous", {}).items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowing_started(self) -> None:
        """Record mowing through the legacy method name."""
        await self.async_mark_mowed()
