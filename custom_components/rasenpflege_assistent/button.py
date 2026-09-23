"""Button platform for Lawn Care Assistant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
        press_fn=lambda coordinator: (
            coordinator.irrigation.async_start(manual=True)
            if coordinator.irrigation and coordinator.irrigation.configured
            else coordinator.async_mark_watered()
        ),
    ),
    LawnButtonDescription(
        key="stop_irrigation",
        translation_key="stop_irrigation",
        icon="mdi:water-off",
        press_fn=lambda coordinator: coordinator.irrigation.async_stop(),
    ),
    LawnButtonDescription(
        key="mark_fertilized",
        translation_key="mark_fertilized",
        icon="mdi:leaf",
        press_fn=lambda coordinator: coordinator.async_mark_fertilized(),
    ),
    LawnButtonDescription(
        key="undo_last_action",
        translation_key="undo_last_action",
        icon="mdi:undo-variant",
        press_fn=lambda coordinator: coordinator.async_undo_last_action(),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lawn logging buttons."""
    coordinator: LawnCoordinator = entry.runtime_data
    async_add_entities(
        LawnButton(coordinator, description)
        for description in BUTTONS
        if description.key != "stop_irrigation"
        or (coordinator.irrigation and coordinator.irrigation.configured)
    )


class LawnButton(LawnEntity, ButtonEntity):
    """Represent a maintenance logging button."""

    entity_description: LawnButtonDescription

    def __init__(
        self, coordinator: LawnCoordinator, description: LawnButtonDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = (
            replace(description, translation_key="start_irrigation")
            if description.key == "mark_watered"
            and coordinator.irrigation
            and coordinator.irrigation.configured
            else description
        )

    async def async_press(self) -> None:
        """Record a completed maintenance action."""
        await self.entity_description.press_fn(self.coordinator)
