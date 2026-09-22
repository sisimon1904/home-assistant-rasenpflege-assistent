"""Sensor platform for Lawn Care Assistant."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfMass,
    UnitOfPrecipitationDepth,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CLOUD_COVERAGE,
    ATTR_CONFIDENCE,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_DAILY_EVAPOTRANSPIRATION_MM,
    ATTR_DATA_WARNINGS,
    ATTR_DAYS_SINCE_FERTILIZING,
    ATTR_DAYS_SINCE_MOWING,
    ATTR_DAYS_SINCE_WATERING,
    ATTR_DEW_POINT,
    ATTR_DOSE_G_M2,
    ATTR_DRAINAGE_MM,
    ATTR_EFFECTIVE_RAIN_MM,
    ATTR_EVAPOTRANSPIRATION_METHOD,
    ATTR_EXPECTED_ET_24H,
    ATTR_FERTILIZER_STATUS,
    ATTR_FERTILIZING_RECOMMENDED,
    ATTR_FORECAST_72H_ESTIMATED,
    ATTR_FORECAST_AGE_MINUTES,
    ATTR_FORECAST_COVERAGE_HOURS,
    ATTR_FORECAST_PERIOD_DAYS,
    ATTR_FORECAST_RAIN_24H_MM,
    ATTR_FORECAST_RAIN_48H_MM,
    ATTR_FORECAST_RAIN_72H_MM,
    ATTR_FORECAST_RAIN_MM,
    ATTR_FORECAST_STALE,
    ATTR_FORECAST_UPDATED_AT,
    ATTR_GROWTH_TEMPERATURE,
    ATTR_HOURS_UNTIL_RAIN,
    ATTR_HUMIDITY,
    ATTR_ICON_COLOR,
    ATTR_INTERCEPTION_MM,
    ATTR_LAST_MAINTENANCE_EVENT,
    ATTR_LAST_MOWING,
    ATTR_LAST_SOIL_UPDATE,
    ATTR_MEASURED_SOIL_MOISTURE,
    ATTR_MODEL_CONFIDENCE,
    ATTR_MOWER_CAN_BE_SWITCHED_OFF,
    ATTR_MOWER_START_RECOMMENDED,
    ATTR_MOWING_INTERVAL_DAYS,
    ATTR_NEXT_MOWING_DATE,
    ATTR_NEXT_RAIN_AT,
    ATTR_NEXT_WINDOW,
    ATTR_NPK,
    ATTR_OBSERVED_RAIN_MM,
    ATTR_PRECIPITATION_MODE,
    ATTR_PRECIPITATION_SOURCE,
    ATTR_PRESSURE,
    ATTR_REASONS,
    ATTR_RECOMMENDED_LITERS,
    ATTR_RECOMMENDED_MM,
    ATTR_REFERENCE_EVAPOTRANSPIRATION_MM,
    ATTR_RUNOFF_MM,
    ATTR_SOIL_CAPACITY_MM,
    ATTR_SOIL_MODEL_GAP_HOURS,
    ATTR_SOIL_MOISTURE_PERCENT,
    ATTR_SOIL_MOISTURE_SOURCE,
    ATTR_SOIL_TEMPERATURE,
    ATTR_SOIL_WATER_MM,
    ATTR_TEMPERATURE_HISTORY_DAYS,
    ATTR_TEMPERATURE_SOURCE,
    ATTR_TOTAL_KG,
    ATTR_WATER_STRESS_FACTOR,
    ATTR_WATERING_RECOMMENDED,
    ATTR_WEATHER_AGE_MINUTES,
    ATTR_WIND_SPEED,
    DOMAIN,
)
from .coordinator import LawnCoordinator
from .entity import LawnEntity
from .models import LawnData

PARALLEL_UPDATES = 0

ValueFn = Callable[[LawnData], Any]
AttributesFn = Callable[[LawnData], dict[str, Any]]


GROWTH_COLORS = {
    "collecting_data": "grey",
    "winter_dormancy": "blue",
    "first_awakening": "light-green",
    "sustained_growth_start": "green",
    "active_growth": "green",
    "slow_growth": "orange",
    "autumn_slowdown": "orange",
    "heat_drought_stress": "red",
}

MOWER_COLORS = {
    "collecting_data": "grey",
    "winter_off": "blue",
    "keep_off": "blue",
    "start_mower": "light-green",
    "mow_regularly": "green",
    "mow_less": "orange",
    "reduce_mowing": "orange",
    "pause_drought": "red",
    "wait_to_mow": "grey",
}

STATUS_COLORS = {
    "collecting_data": "grey",
    "winter_dormancy": "blue",
    "early_spring": "light-green",
    "drought_stress": "red",
    "water_now": "red",
    "water_soon": "orange",
    "wait_for_rain": "light-blue",
    "fertilizing_recommended": "orange",
    "mowing_recommended": "green",
    "good_condition": "green",
}

WATERING_COLORS = {
    "season_pause": "blue",
    "not_due": "green",
    "water_soon": "orange",
    "water_now": "red",
    "wait_for_rain": "light-blue",
}


@dataclass(frozen=True, kw_only=True)
class LawnSensorDescription(SensorEntityDescription):
    """Describe a lawn sensor."""

    value_fn: ValueFn
    attributes_fn: AttributesFn = lambda data: {}


SENSORS: tuple[LawnSensorDescription, ...] = (
    LawnSensorDescription(
        key="status",
        translation_key="status",
        icon="mdi:leaf-circle-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "collecting_data",
            "winter_dormancy",
            "early_spring",
            "drought_stress",
            "water_now",
            "water_soon",
            "wait_for_rain",
            "fertilizing_recommended",
            "mowing_recommended",
            "good_condition",
        ],
        value_fn=lambda data: data.lawn_status,
        attributes_fn=lambda data: {
            ATTR_ICON_COLOR: STATUS_COLORS.get(data.lawn_status, "grey"),
            ATTR_FERTILIZING_RECOMMENDED: data.fertilizing_recommended,
            ATTR_FERTILIZER_STATUS: data.fertilizing_status,
            ATTR_NPK: data.fertilizer_npk,
            ATTR_DOSE_G_M2: data.fertilizer_dose_g_m2,
            ATTR_TOTAL_KG: data.fertilizer_total_kg,
            ATTR_DAYS_SINCE_FERTILIZING: data.days_since_fertilizing,
            ATTR_NEXT_WINDOW: data.next_fertilizing_window,
            ATTR_REASONS: data.fertilizing_reasons,
            ATTR_LAST_MAINTENANCE_EVENT: data.last_maintenance_event,
        },
    ),
    LawnSensorDescription(
        key="next_action",
        translation_key="next_action",
        icon="mdi:clipboard-check-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "collecting_data",
            "water_lawn",
            "prepare_watering",
            "wait_for_rain",
            "fertilize_lawn",
            "start_mower",
            "mow_lawn",
            "winterize_mower",
            "no_action",
        ],
        value_fn=lambda data: data.next_action,
        attributes_fn=lambda data: {
            ATTR_RECOMMENDED_MM: data.watering_mm,
            ATTR_RECOMMENDED_LITERS: data.watering_liters,
            ATTR_NPK: data.fertilizer_npk,
            ATTR_TOTAL_KG: data.fertilizer_total_kg,
            ATTR_NEXT_MOWING_DATE: (
                data.next_mowing_date.isoformat() if data.next_mowing_date else None
            ),
        },
    ),
    LawnSensorDescription(
        key="growth_status",
        translation_key="growth_status",
        icon="mdi:grass",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "collecting_data",
            "winter_dormancy",
            "first_awakening",
            "sustained_growth_start",
            "active_growth",
            "slow_growth",
            "autumn_slowdown",
            "heat_drought_stress",
        ],
        value_fn=lambda data: data.growth_status,
        attributes_fn=lambda data: {
            ATTR_ICON_COLOR: GROWTH_COLORS.get(data.growth_status, "grey"),
            ATTR_GROWTH_TEMPERATURE: data.growth_temperature_7d,
            ATTR_CURRENT_TEMPERATURE: data.current_temperature,
            ATTR_TEMPERATURE_SOURCE: data.temperature_source,
        },
    ),
    LawnSensorDescription(
        key="mower_status",
        translation_key="mower_status",
        icon="mdi:robot-mower-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "collecting_data",
            "winter_off",
            "keep_off",
            "start_mower",
            "mow_regularly",
            "mow_less",
            "reduce_mowing",
            "pause_drought",
            "wait_to_mow",
        ],
        value_fn=lambda data: data.mower_status,
        attributes_fn=lambda data: {
            ATTR_ICON_COLOR: MOWER_COLORS.get(data.mower_status, "grey"),
            ATTR_MOWER_START_RECOMMENDED: data.mower_start_recommended,
            ATTR_MOWER_CAN_BE_SWITCHED_OFF: data.mower_can_be_switched_off,
            ATTR_LAST_MOWING: (
                data.last_mowing.isoformat() if data.last_mowing else None
            ),
            ATTR_DAYS_SINCE_MOWING: data.days_since_mowing,
            ATTR_GROWTH_TEMPERATURE: data.growth_temperature_7d,
            ATTR_TEMPERATURE_SOURCE: data.temperature_source,
            ATTR_MOWING_INTERVAL_DAYS: data.mowing_interval_days,
            ATTR_NEXT_MOWING_DATE: (
                data.next_mowing_date.isoformat() if data.next_mowing_date else None
            ),
        },
    ),
    LawnSensorDescription(
        key="soil_moisture",
        translation_key="soil_moisture",
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.MOISTURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda data: data.soil_moisture_percent,
        attributes_fn=lambda data: {
            ATTR_SOIL_WATER_MM: data.soil_water_mm,
            ATTR_SOIL_CAPACITY_MM: data.soil_capacity_mm,
            ATTR_MEASURED_SOIL_MOISTURE: data.measured_soil_moisture_percent,
            ATTR_SOIL_MOISTURE_SOURCE: data.soil_moisture_source,
            ATTR_DAILY_EVAPOTRANSPIRATION_MM: data.daily_evapotranspiration_mm,
            ATTR_REFERENCE_EVAPOTRANSPIRATION_MM: (
                data.reference_evapotranspiration_mm
            ),
            ATTR_EVAPOTRANSPIRATION_METHOD: data.evapotranspiration_method,
            ATTR_EFFECTIVE_RAIN_MM: data.effective_rain_today_mm,
            ATTR_RUNOFF_MM: data.runoff_today_mm,
            ATTR_DRAINAGE_MM: data.drainage_today_mm,
            ATTR_INTERCEPTION_MM: data.interception_today_mm,
            ATTR_WATER_STRESS_FACTOR: data.water_stress_factor,
            ATTR_MODEL_CONFIDENCE: data.soil_model_confidence,
            ATTR_SOIL_TEMPERATURE: data.soil_temperature,
        },
    ),
    LawnSensorDescription(
        key="gts",
        translation_key="gts",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement="°C·d",
        suggested_display_precision=1,
        value_fn=lambda data: data.gts,
    ),
    LawnSensorDescription(
        key="watering_recommendation",
        translation_key="watering_recommendation",
        icon="mdi:watering-can-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "season_pause",
            "not_due",
            "water_soon",
            "water_now",
            "wait_for_rain",
        ],
        value_fn=lambda data: data.watering_status,
        attributes_fn=lambda data: {
            ATTR_ICON_COLOR: WATERING_COLORS.get(data.watering_status, "grey"),
            ATTR_WATERING_RECOMMENDED: data.watering_recommended,
            ATTR_RECOMMENDED_MM: data.watering_mm,
            ATTR_RECOMMENDED_LITERS: data.watering_liters,
            ATTR_SOIL_MOISTURE_PERCENT: data.soil_moisture_percent,
            ATTR_FORECAST_RAIN_MM: data.forecast_rain_mm,
            ATTR_FORECAST_RAIN_24H_MM: data.forecast_rain_24h_mm,
            ATTR_FORECAST_RAIN_48H_MM: data.forecast_rain_48h_mm,
            ATTR_FORECAST_RAIN_72H_MM: data.forecast_rain_72h_mm,
            ATTR_NEXT_RAIN_AT: data.next_rain_at,
            ATTR_HOURS_UNTIL_RAIN: data.hours_until_rain,
            ATTR_EXPECTED_ET_24H: data.expected_et_24h_mm,
            ATTR_FORECAST_72H_ESTIMATED: data.forecast_72h_estimated,
            ATTR_FORECAST_PERIOD_DAYS: 3,
            ATTR_FORECAST_UPDATED_AT: data.forecast_updated_at,
            ATTR_FORECAST_COVERAGE_HOURS: data.forecast_coverage_hours,
            ATTR_FORECAST_STALE: data.forecast_stale,
            ATTR_OBSERVED_RAIN_MM: data.observed_rain_today_mm,
            ATTR_PRECIPITATION_SOURCE: data.precipitation_source,
            ATTR_PRECIPITATION_MODE: data.precipitation_mode,
            ATTR_DAYS_SINCE_WATERING: data.days_since_watering,
            ATTR_CONFIDENCE: data.watering_confidence,
            ATTR_REASONS: data.watering_reasons,
            ATTR_LAST_SOIL_UPDATE: data.last_soil_update_at,
            ATTR_SOIL_MODEL_GAP_HOURS: data.soil_model_gap_hours,
            ATTR_EFFECTIVE_RAIN_MM: data.effective_rain_today_mm,
        },
    ),
    LawnSensorDescription(
        key="watering_amount",
        translation_key="watering_amount",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.watering_liters,
        attributes_fn=lambda data: {ATTR_RECOMMENDED_MM: data.watering_mm},
    ),
    LawnSensorDescription(
        key="fertilizer_amount",
        translation_key="fertilizer_amount",
        icon="mdi:weight-kilogram",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.fertilizer_total_kg,
        attributes_fn=lambda data: {
            ATTR_NPK: data.fertilizer_npk,
            ATTR_DOSE_G_M2: data.fertilizer_dose_g_m2,
        },
    ),
    LawnSensorDescription(
        key="data_quality",
        translation_key="data_quality",
        icon="mdi:database-check-outline",
        device_class=SensorDeviceClass.ENUM,
        options=["good", "limited", "insufficient"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.data_quality,
        attributes_fn=lambda data: {
            ATTR_DATA_WARNINGS: data.data_warnings,
            ATTR_TEMPERATURE_HISTORY_DAYS: data.temperature_history_days,
            ATTR_FORECAST_AGE_MINUTES: data.forecast_age_minutes,
            ATTR_FORECAST_COVERAGE_HOURS: data.forecast_coverage_hours,
            ATTR_SOIL_MODEL_GAP_HOURS: data.soil_model_gap_hours,
            ATTR_WEATHER_AGE_MINUTES: data.weather_age_minutes,
            ATTR_EVAPOTRANSPIRATION_METHOD: data.evapotranspiration_method,
            ATTR_HUMIDITY: data.humidity,
            ATTR_WIND_SPEED: data.wind_speed_m_s,
            ATTR_CLOUD_COVERAGE: data.cloud_coverage,
            ATTR_PRESSURE: data.pressure_hpa,
            ATTR_DEW_POINT: data.dew_point,
        },
    ),
    LawnSensorDescription(
        key="forecast_coverage",
        translation_key="forecast_coverage",
        icon="mdi:timeline-clock-outline",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.forecast_coverage_hours,
    ),
    LawnSensorDescription(
        key="soil_model_confidence",
        translation_key="soil_model_confidence",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.ENUM,
        options=["high", "medium", "low"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.soil_model_confidence,
    ),
    LawnSensorDescription(
        key="watering_confidence",
        translation_key="watering_confidence",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.ENUM,
        options=["high", "medium", "low"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.watering_confidence,
    ),
    LawnSensorDescription(
        key="forecast_age",
        translation_key="forecast_age",
        icon="mdi:clock-outline",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.forecast_age_minutes,
    ),
    LawnSensorDescription(
        key="forecast_rain_24h",
        translation_key="forecast_rain_24h",
        icon="mdi:weather-rainy",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.forecast_rain_24h_mm,
    ),
    LawnSensorDescription(
        key="forecast_rain_72h",
        translation_key="forecast_rain_72h",
        icon="mdi:weather-pouring",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.forecast_rain_72h_mm,
    ),
    LawnSensorDescription(
        key="observed_rain_today",
        translation_key="observed_rain_today",
        icon="mdi:weather-rainy",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.observed_rain_today_mm,
    ),
    LawnSensorDescription(
        key="temperature_source",
        translation_key="temperature_source",
        icon="mdi:thermometer-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.temperature_source,
    ),
    LawnSensorDescription(
        key="precipitation_source",
        translation_key="precipitation_source",
        icon="mdi:water-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.precipitation_source,
    ),
    LawnSensorDescription(
        key="soil_water",
        translation_key="soil_water",
        icon="mdi:cup-water",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.soil_water_mm,
        attributes_fn=lambda data: {ATTR_SOIL_CAPACITY_MM: data.soil_capacity_mm},
    ),
    LawnSensorDescription(
        key="daily_evapotranspiration",
        translation_key="daily_evapotranspiration",
        icon="mdi:weather-sunny-alert",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.daily_evapotranspiration_mm,
    ),
    LawnSensorDescription(
        key="evapotranspiration_method",
        translation_key="evapotranspiration_method",
        icon="mdi:weather-sunny",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "penman_monteith_estimated_radiation",
            "hargreaves_samani",
            "unavailable",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.evapotranspiration_method,
        attributes_fn=lambda data: {
            ATTR_REFERENCE_EVAPOTRANSPIRATION_MM: (
                data.reference_evapotranspiration_mm
            ),
            ATTR_HUMIDITY: data.humidity,
            ATTR_WIND_SPEED: data.wind_speed_m_s,
            ATTR_CLOUD_COVERAGE: data.cloud_coverage,
            ATTR_PRESSURE: data.pressure_hpa,
            ATTR_DEW_POINT: data.dew_point,
            ATTR_WEATHER_AGE_MINUTES: data.weather_age_minutes,
        },
    ),
    LawnSensorDescription(
        key="last_soil_update",
        translation_key="last_soil_update",
        icon="mdi:water-sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: dt_util.parse_datetime(data.last_soil_update_at or ""),
        attributes_fn=lambda data: {
            ATTR_SOIL_MODEL_GAP_HOURS: data.soil_model_gap_hours
        },
    ),
    LawnSensorDescription(
        key="last_calculation",
        translation_key="last_calculation",
        icon="mdi:calculator-variant-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: dt_util.parse_datetime(data.last_calculation_at or ""),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lawn sensors."""
    coordinator: LawnCoordinator = entry.runtime_data
    registry = er.async_get(hass)
    deprecated = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_fertilizer_recommendation"
    )
    if deprecated:
        registry.async_remove(deprecated)
    async_add_entities(LawnSensor(coordinator, description) for description in SENSORS)


class LawnSensor(LawnEntity, SensorEntity):
    """Represent a calculated lawn sensor."""

    entity_description: LawnSensorDescription

    def __init__(
        self, coordinator: LawnCoordinator, description: LawnSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful recommendation details."""
        return self.entity_description.attributes_fn(self.coordinator.data)
