"""Home Assistant buttons for maintenance and optional irrigation.

File: custom_components/rasenpflege_assistent/button.py

Button descriptions map stable entity keys to asynchronous coordinator or
controller actions. The watering button records maintenance without a valve,
but starts a supervised manual session when valve control is configured.

Entities delegate all writes and safety decisions to the shared model.
The stop button exists only for configured irrigation; undo is disabled in
the entity registry by default because it changes recorded history.
"""

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


# All writes go through model/controller transactions. In particular, starting
# watering must not prematurely record its target as physically delivered water.
BUTTONS: tuple[LawnButtonDescription, ...] = (
    LawnButtonDescription(
        key="mark_mowing_started",
        translation_key="mark_mowing_started",
        press_fn=lambda coordinator: coordinator.async_mark_mowed(),
    ),
    LawnButtonDescription(
        key="mark_watered",
        translation_key="mark_watered",
        press_fn=lambda coordinator: (
            coordinator.irrigation_controller.async_start(manual=True)
            if coordinator.irrigation and coordinator.irrigation_controller.configured
            else coordinator.async_mark_watered()
        ),
    ),
    LawnButtonDescription(
        key="stop_irrigation",
        translation_key="stop_irrigation",
        press_fn=lambda coordinator: coordinator.irrigation_controller.async_stop(),
    ),
    LawnButtonDescription(
        key="mark_fertilized",
        translation_key="mark_fertilized",
        press_fn=lambda coordinator: coordinator.async_mark_fertilized(),
    ),
    LawnButtonDescription(
        key="undo_last_action",
        translation_key="undo_last_action",
        press_fn=lambda coordinator: coordinator.async_undo_last_action(),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[LawnCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lawn logging buttons."""
    coordinator: LawnCoordinator = entry.runtime_data
    async_add_entities(
        LawnButton(coordinator, description)
        for description in BUTTONS
        if description.key != "stop_irrigation"
        or (coordinator.irrigation and coordinator.irrigation_controller.configured)
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
            and coordinator.irrigation_controller.configured
            else description
        )

    async def async_press(self) -> None:
        """Record a completed maintenance action.

        Dispatch the configured action and await its persistence/safety result.
        The watering action may start a supervised session rather than record
        a completed watering event; the button itself does not credit water.
        """
        await self.entity_description.press_fn(self.coordinator)
