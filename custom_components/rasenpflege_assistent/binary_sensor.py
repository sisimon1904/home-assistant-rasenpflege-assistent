"""Binary sensor platform for Rasenpflege-Assistent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LawnCoordinator
from .entity import LawnEntity
from .models import LawnData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LawnBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a lawn binary sensor."""

    value_fn: Callable[[LawnData], bool]


BINARY_SENSORS: tuple[LawnBinarySensorDescription, ...] = (
    LawnBinarySensorDescription(
        key="mower_can_be_switched_off",
        translation_key="mower_can_be_switched_off",
        icon="mdi:snowflake-off",
        value_fn=lambda data: data.mower_can_be_switched_off,
    ),
    LawnBinarySensorDescription(
        key="mower_start_recommended",
        translation_key="mower_start_recommended",
        icon="mdi:robot-mower-outline",
        value_fn=lambda data: data.mower_start_recommended,
    ),
    LawnBinarySensorDescription(
        key="watering_due",
        translation_key="watering_due",
        icon="mdi:water-alert-outline",
        value_fn=lambda data: data.watering_recommended,
    ),
    LawnBinarySensorDescription(
        key="fertilizing_due",
        translation_key="fertilizing_due",
        icon="mdi:leaf-circle",
        value_fn=lambda data: data.fertilizing_recommended,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lawn binary sensors."""
    coordinator: LawnCoordinator = entry.runtime_data
    async_add_entities(
        LawnBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class LawnBinarySensor(LawnEntity, BinarySensorEntity):
    """Represent a lawn recommendation flag."""

    entity_description: LawnBinarySensorDescription

    def __init__(
        self, coordinator: LawnCoordinator, description: LawnBinarySensorDescription
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return whether the recommendation is due."""
        return self.entity_description.value_fn(self.coordinator.data)
