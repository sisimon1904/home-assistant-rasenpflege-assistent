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
    ATTR_GTS_COMPLETE,
    ATTR_HOURS_UNTIL_RAIN,
    ATTR_HUMIDITY,
    ATTR_ICON_COLOR,
    ATTR_INTERCEPTION_MM,
    ATTR_LAST_MAINTENANCE_EVENT,
    ATTR_LAST_MOWING,
    ATTR_LAST_SOIL_UPDATE,
    ATTR_MEASURED_SOIL_MOISTURE,
    ATTR_MISSING_TEMPERATURE_DAYS,
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
    ATTR_PROBABILITY_ADJUSTED_RAIN,
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
    ATTR_WATERING_WINDOW_END,
    ATTR_WATERING_WINDOW_REASON,
    ATTR_WATERING_WINDOW_START,
    ATTR_WATERING_WINDOW_TEMPERATURE,
    ATTR_WATERING_WINDOW_WIND_SPEED,
    ATTR_WEATHER_AGE_MINUTES,
    ATTR_WIND_SPEED,
    DOMAIN,
)
from .coordinator import LawnCoordinator
from .entity import LawnEntity
from .explanations import reason_text
from .models import LawnData
from .planning import consumption_summary

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
    "pause_wet": "light-blue",
    "wait_to_mow": "grey",
    "pause_frost": "blue",
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
    "lawn_wet": "light-blue",
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
            "lawn_wet",
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
            "wait_to_mow",
            "winterize_mower",
            "no_action",
            "wait_for_irrigation",
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
            "pause_wet",
            "pause_frost",
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
            "wet_until": data.mower_wet_until,
            "wet_reason": data.mower_wet_reason,
            "mowing_mode": data.mowing_mode,
            "last_mowing_at": data.last_mowing_at,
            "next_mowing_at": data.next_mowing_at,
            "recommendation_reason": data.mowing_reason,
            "recommendation_confidence": data.mowing_confidence,
            "last_robot_session_started_at": data.last_robot_session_started_at,
            "last_robot_session_finished_at": data.last_robot_session_finished_at,
            "last_robot_session_active_minutes": (
                round(data.last_robot_session_active_seconds / 60, 1)
                if data.last_robot_session_active_seconds is not None
                else None
            ),
            "last_mowing_source": data.mowing_record_source,
            "last_mowing_estimated": data.mowing_record_source
            in {"robot_estimate", "legacy_date", "manual_correction"},
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
        attributes_fn=lambda data: {
            ATTR_GTS_COMPLETE: data.gts_complete,
            ATTR_MISSING_TEMPERATURE_DAYS: data.missing_temperature_days,
        },
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
            ATTR_PROBABILITY_ADJUSTED_RAIN: (data.probability_adjusted_rain_24h_mm),
            ATTR_WATERING_WINDOW_START: data.watering_window_start,
            ATTR_WATERING_WINDOW_END: data.watering_window_end,
            ATTR_WATERING_WINDOW_REASON: data.watering_window_reason,
            ATTR_WATERING_WINDOW_TEMPERATURE: data.watering_window_temperature,
            ATTR_WATERING_WINDOW_WIND_SPEED: (data.watering_window_wind_speed_m_s),
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
        key="irrigation_status",
        translation_key="irrigation_status",
        icon="mdi:sprinkler-variant",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "running", "paused", "stopping", "completed", "stopped"],
        value_fn=lambda data: data.irrigation_status,
        attributes_fn=lambda data: {
            "automatic_irrigation_enabled": data.irrigation_enabled,
            "last_irrigation_liters": data.irrigation_liters,
            "reason": data.irrigation_reason,
        },
    ),
    LawnSensorDescription(
        key="irrigation_readiness",
        translation_key="irrigation_readiness",
        icon="mdi:water-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=[
            "ready",
            "running",
            "paused",
            "stopping",
            "completed",
            "stopped",
            "mower_not_docked",
            "valve_not_closed",
            "other_valve_open",
            "other_valve_unavailable",
            "meter_unavailable",
            "meter_stale",
            "storage_error",
            "homeassistant_stopping",
            "frost",
            "not_configured",
        ],
        value_fn=lambda data: "not_configured",
    ),
    LawnSensorDescription(
        key="irrigation_auto_decision",
        translation_key="irrigation_auto_decision",
        icon="mdi:water-clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=[
            "ready",
            "not_configured",
            "automation_disabled",
            "session_active",
            "mower_not_docked",
            "valve_not_closed",
            "other_valve_open",
            "other_valve_unavailable",
            "meter_unavailable",
            "meter_stale",
            "storage_error",
            "homeassistant_stopping",
            "frost",
            "meter_required",
            "waiting_for_weather",
            "rain_unavailable",
            "weather_unavailable",
            "low_confidence",
            "already_watered_today",
            "retry_cooldown",
            "watering_not_due",
            "no_suitable_window",
            "waiting_for_window",
            "window_expired",
            "automation_suspended",
            "outside_schedule",
        ],
        value_fn=lambda data: "not_configured",
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
            ATTR_GTS_COMPLETE: data.gts_complete,
            ATTR_MISSING_TEMPERATURE_DAYS: data.missing_temperature_days,
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
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        state_class=SensorStateClass.TOTAL_INCREASING,
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
            "estimated_fallback",
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


SENSORS += tuple(
    LawnSensorDescription(
        key=key,
        translation_key=key,
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=1,
        value_fn=lambda data: None,
    )
    for key in ("water_consumption_week", "water_consumption_month")
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
    async_add_entities(
        LawnSensor(coordinator, description)
        for description in SENSORS
        if description.key
        not in {"irrigation_status", "irrigation_readiness", "irrigation_auto_decision"}
        or (coordinator.irrigation and coordinator.irrigation.configured)
    )


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
        if self.entity_description.key in {
            "water_consumption_week",
            "water_consumption_month",
        }:
            period = "week" if self.entity_description.key.endswith("week") else "month"
            return consumption_summary(
                self.coordinator._state.water_usage,
                dt_util.as_local(dt_util.now()).date(),
            )[f"{period}_liters"]
        if self.entity_description.key == "irrigation_readiness":
            return self.coordinator.irrigation.readiness()
        if self.entity_description.key == "irrigation_auto_decision":
            return self.coordinator.irrigation.automatic_blocker() or "ready"
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful recommendation details."""
        key = self.entity_description.key
        language = self.coordinator.hass.config.language
        if key in {"water_consumption_week", "water_consumption_month"}:
            return consumption_summary(
                self.coordinator._state.water_usage,
                dt_util.as_local(dt_util.now()).date(),
            )
        if key in {"irrigation_readiness", "irrigation_auto_decision"}:
            details = self.coordinator.irrigation.diagnostic_attributes()
            details["reason_text"] = reason_text(self.native_value, language)
            details["automatic_blockers_text"] = [
                reason_text(code, language) for code in details["automatic_blockers"]
            ]
            return details
        details = self.entity_description.attributes_fn(self.coordinator.data)
        if key == "soil_moisture":
            details["input_diagnostics"] = self.coordinator.input_diagnostics()
        if key == "data_quality":
            details["input_diagnostics"] = self.coordinator.input_diagnostics()
            details["forecast_diagnostics"] = {
                "provider": self.coordinator.settings.get("weather_entity"),
                "daily_updated_at": self.coordinator._forecast_updated_at.isoformat()
                if self.coordinator._forecast_updated_at
                else None,
                "hourly_updated_at": self.coordinator._hourly_forecast_updated_at.isoformat()
                if self.coordinator._hourly_forecast_updated_at
                else None,
                "daily_entries": len(self.coordinator._forecast_cache),
                "hourly_entries": len(self.coordinator._hourly_forecast_cache),
                "daily_missing_rain_values": sum(
                    item.get("precipitation", item.get("native_precipitation")) is None
                    for item in self.coordinator._forecast_cache
                ),
                "hourly_missing_wind_values": sum(
                    item.get("wind_speed") is None
                    for item in self.coordinator._hourly_forecast_cache
                ),
            }
        if key == "mower_status":
            observer = getattr(self.coordinator, "mowing_observer", None)
            details["live_robot_session"] = (
                observer.diagnostic_attributes()
                if observer
                else {"status": "not_configured", "active_minutes": 0}
            )
        if key == "irrigation_status":
            details.update(self.coordinator.irrigation.diagnostic_attributes())
            if details.get("last_session"):
                details["last_session"] = {
                    **details["last_session"],
                    "reason_text": reason_text(
                        details["last_session"]["reason"], language
                    ),
                }
        for code_key in (
            "reason",
            "recommendation_reason",
            "wet_reason",
            "watering_window_reason",
        ):
            if code_key in details:
                details[f"{code_key}_text"] = reason_text(details[code_key], language)
        if ATTR_REASONS in details:
            details["reasons_text"] = [
                reason_text(code, language) for code in details[ATTR_REASONS]
            ]
        if (
            key == "mower_status"
            and details.get("last_mowing_source") == "robot_estimate"
        ):
            details["estimate_note"] = reason_text("robot_estimate", language)
        return details
