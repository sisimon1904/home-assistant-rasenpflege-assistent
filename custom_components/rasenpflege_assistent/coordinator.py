"""Coordinator for Rasenpflege-Assistent."""

from __future__ import annotations

import logging
from datetime import date
from statistics import fmean
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    soil_capacity,
    sum_forecast_rain,
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
    CONF_SOIL_TYPE,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_AREA,
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_LAWN_TYPE,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_EXPOSURE,
    DEFAULT_WATERING_AMOUNT,
    DOMAIN,
    FORECAST_CACHE_INTERVAL,
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
                forecast_today_rain_mm=stored.get("forecast_today_rain_mm"),
                soil_water_mm=stored.get("soil_water_mm"),
                last_evapotranspiration_mm=float(
                    stored.get("last_evapotranspiration_mm", 0.0)
                ),
                daily_temperature_history=[
                    float(value)
                    for value in stored.get("daily_temperature_history", [])[-14:]
                ],
                mower_started_year=stored.get("mower_started_year"),
                last_sample_at=stored.get("last_sample_at"),
                configured_initial_soil_moisture=float(
                    stored.get("configured_initial_soil_moisture", initial_moisture)
                ),
                precipitation_last_value=stored.get("precipitation_last_value"),
                precipitation_last_sample_at=stored.get("precipitation_last_sample_at"),
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

    async def _async_forecast(self) -> list[dict[str, Any]]:
        """Return a cached daily forecast from Home Assistant."""
        now = dt_util.now()
        if (
            self._forecast_updated_at is not None
            and now - self._forecast_updated_at < FORECAST_CACHE_INTERVAL
        ):
            return self._forecast_cache
        weather_entity = self.settings[CONF_WEATHER_ENTITY]
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "daily"},
                target={"entity_id": weather_entity},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Daily OpenWeatherMap forecast unavailable: %s", err)
            return self._forecast_cache
        if not isinstance(response, dict):
            return self._forecast_cache
        entity_data = response.get(weather_entity, {})
        forecast = (
            entity_data.get("forecast", []) if isinstance(entity_data, dict) else []
        )
        if isinstance(forecast, list):
            self._forecast_cache = forecast
            self._forecast_updated_at = now
        return self._forecast_cache

    def _sample_precipitation(self, now) -> str:
        """Accumulate an optional precipitation depth or intensity sensor."""
        assert self._state is not None
        entity_id = self.settings.get(CONF_PRECIPITATION_ENTITY)
        if not entity_id:
            return "forecast_estimate"
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "forecast_estimate"
        try:
            value = max(0.0, float(state.state))
        except (TypeError, ValueError):
            return "forecast_estimate"
        unit = str(state.attributes.get("unit_of_measurement", "mm"))
        if unit.startswith("in"):
            value *= 25.4
        last_value = self._state.precipitation_last_value
        last_sample = dt_util.parse_datetime(
            self._state.precipitation_last_sample_at or ""
        )
        if "/h" in unit:
            elapsed_hours = 0.0
            if last_sample is not None:
                elapsed_hours = min(
                    2.0, max(0.0, (now - last_sample).total_seconds() / 3600)
                )
            self._state.daily_rain_mm += value * elapsed_hours
        elif last_value is not None:
            self._state.daily_rain_mm += (
                value - last_value if value >= last_value else value
            )
        self._state.precipitation_last_value = value
        self._state.precipitation_last_sample_at = now.isoformat()
        return entity_id

    def _finalize_previous_day(self, previous_day: date) -> None:
        """Finalize GTS, evapotranspiration and soil water for one day."""
        assert self._state is not None
        if not self._state.temperature_samples:
            return
        mean = self._state.temperature_sum / self._state.temperature_samples
        self._state.gts += grassland_temperature_increment(previous_day, mean)
        self._state.daily_temperature_history.append(round(mean, 2))
        self._state.daily_temperature_history = self._state.daily_temperature_history[
            -14:
        ]

        minimum = self._state.temperature_min
        maximum = self._state.temperature_max
        if minimum is None or maximum is None:
            minimum, maximum = mean - 2.0, mean + 2.0
        et0 = hargreaves_evapotranspiration(
            day=previous_day,
            latitude=self.hass.config.latitude,
            temperature_min=minimum,
            temperature_max=maximum,
        )
        precipitation_entity = self.settings.get(CONF_PRECIPITATION_ENTITY)
        precipitation = (
            self._state.daily_rain_mm
            if precipitation_entity and self._state.precipitation_last_value is not None
            else float(self._state.forecast_today_rain_mm or 0.0)
        )
        soil_type = self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)
        capacity = soil_capacity(soil_type)
        crop_coefficient = (
            0.8 if mean >= 5 and previous_day.month in range(3, 11) else 0.35
        )
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
            precipitation_mm=precipitation,
            reference_et_mm=et0,
            crop_coefficient=crop_coefficient,
            rain_efficiency=rain_efficiency,
        )
        self._state.soil_water_mm = water
        self._state.last_evapotranspiration_mm = actual_et

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
        precipitation_source = self._sample_precipitation(now)
        forecast = await self._async_forecast()
        self._state.forecast_today_rain_mm = sum_forecast_rain(forecast, 1)

        last_watering = _parse_date(self._state.last_watering)
        last_fertilizing = _parse_date(self._state.last_fertilizing)
        last_mowing = _parse_date(self._state.last_mowing)
        area = float(settings.get(CONF_AREA, DEFAULT_AREA))
        capacity = soil_capacity(settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))
        soil_water = max(0.0, min(capacity, float(self._state.soil_water_mm or 0.0)))
        soil_moisture = round(soil_water / capacity * 100, 1)
        history = self._state.daily_temperature_history[-7:]
        growth_temperature = round(fmean(history), 1) if history else temperature
        growth = growth_state(
            today=today,
            gts=self._state.gts,
            growth_temperature=growth_temperature,
            soil_moisture_percent=soil_moisture,
            mower_started_year=self._state.mower_started_year,
        )
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
            forecast=forecast,
            last_watering=last_watering,
            soil_moisture_percent=soil_moisture,
            soil_water_mm=soil_water,
            soil_capacity_mm=capacity,
        )
        fertilizing = fertilizing_recommendation(
            today=today,
            gts=self._state.gts,
            area_m2=area,
            lawn_type=settings.get(CONF_LAWN_TYPE, DEFAULT_LAWN_TYPE),
            last_fertilizing=last_fertilizing,
        )
        if fertilizing["recommended"] and watering["recommended"]:
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

        data = LawnData(
            gts=round(self._state.gts, 1),
            lawn_status=lawn_status(
                today=today,
                gts=self._state.gts,
                watering_due=watering["recommended"],
                fertilizing_due=fertilizing["recommended"],
            ),
            watering_recommended=watering["recommended"],
            watering_status=watering["status"],
            watering_mm=watering["mm"],
            watering_liters=watering["liters"],
            watering_reasons=watering["reasons"],
            forecast_rain_mm=watering["rain"],
            forecast_updated_at=(
                self._forecast_updated_at.isoformat()
                if self._forecast_updated_at is not None
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
            soil_water_mm=round(soil_water, 1),
            soil_capacity_mm=capacity,
            daily_evapotranspiration_mm=self._state.last_evapotranspiration_mm,
            soil_model_confidence=(
                "high"
                if precipitation_source != "forecast_estimate"
                else "medium"
                if forecast
                else "low"
            ),
        )
        await self._store.async_save(self._state.as_dict())
        return data

    async def async_mark_watered(self) -> None:
        """Record watering and add an assumed 15 mm to the soil model."""
        assert self._state is not None
        self._state.last_watering = dt_util.now().date().isoformat()
        capacity = soil_capacity(self.settings.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))
        assumed_mm = (
            self.data.watering_mm
            if self.data.watering_mm > 0
            else float(
                self.settings.get(CONF_DEFAULT_WATERING_AMOUNT, DEFAULT_WATERING_AMOUNT)
            )
        )
        self._state.soil_water_mm = min(
            capacity, float(self._state.soil_water_mm or 0.0) + assumed_mm
        )
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_fertilized(self) -> None:
        """Record fertilizing as completed today."""
        assert self._state is not None
        self._state.last_fertilizing = dt_util.now().date().isoformat()
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowed(self) -> None:
        """Record mowing and acknowledge the mowing season for this year."""
        assert self._state is not None
        now = dt_util.now()
        self._state.last_mowing = now.date().isoformat()
        self._state.mower_started_year = now.year
        await self._store.async_save(self._state.as_dict())
        await self.async_request_refresh()

    async def async_mark_mowing_started(self) -> None:
        """Record mowing through the legacy method name."""
        await self.async_mark_mowed()
