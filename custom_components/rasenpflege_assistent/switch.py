"""Persisted master switch for optional automatic lawn irrigation.

File: custom_components/rasenpflege_assistent/switch.py

The entity reflects RuntimeState.irrigation_enabled and delegates changes
to the controller, which persists them and enforces immediate closure of an
automatically owned session when automation is disabled.

Manual session controls remain separate. This switch does not command a
valve directly; controller safety checks and storage handling apply to every
state change.
"""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LawnCoordinator
from .entity import LawnEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[LawnCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Only add a toggle if valve control is configured."""
    coordinator: LawnCoordinator = entry.runtime_data
    if coordinator.irrigation and coordinator.irrigation_controller.configured:
        async_add_entities([AutomaticIrrigationSwitch(coordinator)])


class AutomaticIrrigationSwitch(LawnEntity, SwitchEntity):
    """Enable or suspend automatic watering without changing manual controls."""

    _attr_translation_key = "automatic_irrigation"

    def __init__(self, coordinator: LawnCoordinator) -> None:
        super().__init__(coordinator, "automatic_irrigation")

    @property
    def is_on(self) -> bool:
        """Return the persisted automation state."""
        return bool(self.coordinator.state.irrigation_enabled)

    async def async_turn_on(self, **kwargs) -> None:
        """Allow one qualified watering session per day."""
        await self.coordinator.irrigation_controller.async_set_auto_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Suspend automation and close an automatically opened valve."""
        await self.coordinator.irrigation_controller.async_set_auto_enabled(False)
