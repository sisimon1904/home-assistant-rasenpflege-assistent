"""The Lawn Care Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_MOWED_ENTITY,
    CONF_PRECIPITATION_ENTITY,
    CONF_WATERED_ENTITY,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_WATERING_AMOUNT,
    PLATFORMS,
)
from .coordinator import LawnCoordinator

type LawnConfigEntry = ConfigEntry[LawnCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Set up Lawn Care Assistant from a config entry."""
    coordinator = LawnCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    async def _async_record_event(event: Event, action: str) -> None:
        """Record a maintenance event only for a real off-to-on transition."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if (
            old_state is None
            or new_state is None
            or old_state.state != STATE_OFF
            or new_state.state != STATE_ON
        ):
            return
        if action == "mowed":
            await coordinator.async_mark_mowed()
        else:
            await coordinator.async_mark_watered()

    for config_key, action in (
        (CONF_MOWED_ENTITY, "mowed"),
        (CONF_WATERED_ENTITY, "watered"),
    ):
        entity_id = coordinator.settings.get(config_key)
        if entity_id:

            async def _async_handle_event(
                event: Event, selected_action: str = action
            ) -> None:
                await _async_record_event(event, selected_action)

            entry.async_on_unload(
                async_track_state_change_event(
                    hass,
                    [entity_id],
                    _async_handle_event,
                )
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Migrate older configuration entries without losing user settings."""
    if entry.version == 1:
        data = {
            **entry.data,
            CONF_INITIAL_SOIL_MOISTURE: DEFAULT_INITIAL_SOIL_MOISTURE,
        }
        hass.config_entries.async_update_entry(
            entry, data=data, version=2, minor_version=0
        )
    if entry.version == 2:
        data = dict(entry.data)
        options = dict(entry.options)
        data.pop("rain_entity", None)
        options.pop("rain_entity", None)
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            version=3,
            minor_version=0,
        )
    if entry.version == 3:
        data = {
            **entry.data,
            CONF_DEFAULT_WATERING_AMOUNT: DEFAULT_WATERING_AMOUNT,
            CONF_PRECIPITATION_ENTITY: None,
        }
        hass.config_entries.async_update_entry(
            entry, data=data, version=4, minor_version=0
        )
    return True
