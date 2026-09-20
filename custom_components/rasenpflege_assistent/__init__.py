"""The Rasenpflege-Assistent integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INITIAL_SOIL_MOISTURE,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    PLATFORMS,
)
from .coordinator import LawnCoordinator

type LawnConfigEntry = ConfigEntry[LawnCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Set up Rasenpflege-Assistent from a config entry."""
    coordinator = LawnCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, entry: LawnConfigEntry
) -> bool:
    """Migrate older configuration entries without losing user settings."""
    if entry.version == 1:
        data = {
            **entry.data,
            CONF_INITIAL_SOIL_MOISTURE: DEFAULT_INITIAL_SOIL_MOISTURE,
        }
        hass.config_entries.async_update_entry(
            entry, data=data, version=2, minor_version=0
        )
    return True
