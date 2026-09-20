"""Sensor platform for Rasenpflege-Assistent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_CONFIDENCE,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_DAILY_EVAPOTRANSPIRATION_MM,
    ATTR_DAYS_SINCE_FERTILIZING,
    ATTR_DAYS_SINCE_MOWING,
    ATTR_DAYS_SINCE_WATERING,
    ATTR_DOSE_G_M2,
    ATTR_FORECAST_RAIN_MM,
    ATTR_FERTILIZING_RECOMMENDED,
    ATTR_FERTILIZER_STATUS,
    ATTR_GROWTH_TEMPERATURE,
    ATTR_ICON_COLOR,
    ATTR_LAST_MOWING,
    ATTR_MODEL_CONFIDENCE,
    ATTR_MOWER_CAN_BE_SWITCHED_OFF,
    ATTR_MOWER_START_RECOMMENDED,
    ATTR_NEXT_WINDOW,
    ATTR_NPK,
    ATTR_REASONS,
    ATTR_RECOMMENDED_LITERS,
    ATTR_RECOMMENDED_MM,
    ATTR_SOIL_CAPACITY_MM,
    ATTR_SOIL_WATER_MM,
    ATTR_TEMPERATURE_SOURCE,
    ATTR_TOTAL_KG,
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
}

STATUS_COLORS = {
    "Winterruhe": "blue",
    "Vorfrühling": "light-green",
    "Bewässerung empfohlen": "light-blue",
    "Düngung empfohlen": "orange",
    "Guter Zustand": "green",
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
        },
    ),
    LawnSensorDescription(
        key="soil_moisture",
        translation_key="soil_moisture",
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.MOISTURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda data: data.soil_moisture_percent,
        attributes_fn=lambda data: {
            ATTR_SOIL_WATER_MM: data.soil_water_mm,
            ATTR_SOIL_CAPACITY_MM: data.soil_capacity_mm,
            ATTR_DAILY_EVAPOTRANSPIRATION_MM: data.daily_evapotranspiration_mm,
            ATTR_MODEL_CONFIDENCE: data.soil_model_confidence,
        },
    ),
    LawnSensorDescription(
        key="gts",
        translation_key="gts",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement="K",
        suggested_display_precision=1,
        value_fn=lambda data: data.gts,
    ),
    LawnSensorDescription(
        key="watering_recommendation",
        translation_key="watering_recommendation",
        icon="mdi:watering-can-outline",
        value_fn=lambda data: data.watering_status,
        attributes_fn=lambda data: {
            ATTR_RECOMMENDED_MM: data.watering_mm,
            ATTR_RECOMMENDED_LITERS: data.watering_liters,
            ATTR_FORECAST_RAIN_MM: data.forecast_rain_mm,
            ATTR_DAYS_SINCE_WATERING: data.days_since_watering,
            ATTR_CONFIDENCE: data.watering_confidence,
            ATTR_REASONS: data.watering_reasons,
        },
    ),
    LawnSensorDescription(
        key="watering_amount",
        translation_key="watering_amount",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=0,
        value_fn=lambda data: data.watering_liters,
        attributes_fn=lambda data: {ATTR_RECOMMENDED_MM: data.watering_mm},
    ),
    LawnSensorDescription(
        key="fertilizer_amount",
        translation_key="fertilizer_amount",
        icon="mdi:weight-kilogram",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=2,
        value_fn=lambda data: data.fertilizer_total_kg,
        attributes_fn=lambda data: {
            ATTR_NPK: data.fertilizer_npk,
            ATTR_DOSE_G_M2: data.fertilizer_dose_g_m2,
        },
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
