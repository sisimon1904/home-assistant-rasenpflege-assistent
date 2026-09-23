"""User toggle for optional automatic irrigation."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LawnCoordinator
from .entity import LawnEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Only add a toggle if valve control is configured."""
    coordinator: LawnCoordinator = entry.runtime_data
    if coordinator.irrigation and coordinator.irrigation.configured:
        async_add_entities([AutomaticIrrigationSwitch(coordinator)])


class AutomaticIrrigationSwitch(LawnEntity, SwitchEntity):
    """Enable or suspend automatic watering without changing manual controls."""

    _attr_icon = "mdi:sprinkler-variant"
    _attr_translation_key = "automatic_irrigation"

    def __init__(self, coordinator: LawnCoordinator) -> None:
        super().__init__(coordinator, "automatic_irrigation")

    @property
    def is_on(self) -> bool:
        """Return the persisted automation state."""
        return bool(self.coordinator._state.irrigation_enabled)

    async def async_turn_on(self, **kwargs) -> None:
        """Allow one qualified watering session per day."""
        await self.coordinator.irrigation.async_set_auto_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Suspend automation and close an automatically opened valve."""
        await self.coordinator.irrigation.async_set_auto_enabled(False)
