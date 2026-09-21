"""Button platform for Lawn Care Assistant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MOWED_ENTITY, CONF_WATERED_ENTITY, DOMAIN
from .coordinator import LawnCoordinator
from .entity import LawnEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LawnButtonDescription(ButtonEntityDescription):
    """Describe a lawn logging button."""

    press_fn: Callable[[LawnCoordinator], Awaitable[None]]


BUTTONS: tuple[LawnButtonDescription, ...] = (
    LawnButtonDescription(
        key="mark_mowing_started",
        translation_key="mark_mowing_started",
        icon="mdi:robot-mower",
        press_fn=lambda coordinator: coordinator.async_mark_mowed(),
    ),
    LawnButtonDescription(
        key="mark_watered",
        translation_key="mark_watered",
        icon="mdi:watering-can",
        press_fn=lambda coordinator: coordinator.async_mark_watered(),
    ),
    LawnButtonDescription(
        key="mark_fertilized",
        translation_key="mark_fertilized",
        icon="mdi:leaf",
        press_fn=lambda coordinator: coordinator.async_mark_fertilized(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lawn logging buttons."""
    coordinator: LawnCoordinator = entry.runtime_data
    hidden_keys: set[str] = set()
    if coordinator.settings.get(CONF_MOWED_ENTITY):
        hidden_keys.add("mark_mowing_started")
    if coordinator.settings.get(CONF_WATERED_ENTITY):
        hidden_keys.add("mark_watered")

    registry = er.async_get(hass)
    for key in hidden_keys:
        existing = registry.async_get_entity_id(
            "button", DOMAIN, f"{entry.entry_id}_{key}"
        )
        if existing:
            registry.async_remove(existing)

    async_add_entities(
        LawnButton(coordinator, description)
        for description in BUTTONS
        if description.key not in hidden_keys
    )


class LawnButton(LawnEntity, ButtonEntity):
    """Represent a maintenance logging button."""

    entity_description: LawnButtonDescription

    def __init__(
        self, coordinator: LawnCoordinator, description: LawnButtonDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Record a completed maintenance action."""
        await self.entity_description.press_fn(self.coordinator)
