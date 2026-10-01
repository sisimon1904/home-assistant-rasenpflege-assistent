"""The Lawn Care Assistant integration."""

from __future__ import annotations

import math
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMPACTION,
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_IRRIGATION_EFFICIENCY,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_MOWED_ENTITY,
    CONF_PRECIPITATION_ENTITY,
    CONF_RAIN_CORRECTION,
    CONF_ROOT_DEPTH,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_SENSOR_DRY,
    CONF_SOIL_SENSOR_WET,
    CONF_SOIL_TEMPERATURE_ENTITY,
    CONF_WATERED_ENTITY,
    DEFAULT_COMPACTION,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_IRRIGATION_EFFICIENCY,
    DEFAULT_RAIN_CORRECTION,
    DEFAULT_ROOT_DEPTH,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_SENSOR_DRY,
    DEFAULT_SOIL_SENSOR_WET,
    DEFAULT_WATERING_AMOUNT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import LawnCoordinator
from .irrigation import IrrigationController
from .mowing import MowingObserver

type LawnConfigEntry = ConfigEntry[LawnCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register maintenance actions once for all lawn entries."""

    def _coordinator(call: ServiceCall) -> LawnCoordinator:
        entry_id = call.data["config_entry_id"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
            raise ServiceValidationError(
                f"Unknown Lawn Care Assistant entry: {entry_id}"
            )
        return entry.runtime_data

    def _recorded_at(call: ServiceCall):
        value = call.data.get("recorded_at")
        if not value:
            return None
        at = dt_util.parse_datetime(value)
        if at is None or at.tzinfo is None or at > dt_util.now():
            raise ServiceValidationError(
                "Use a past ISO timestamp with timezone for recorded_at"
            )
        return at

    async def _start_irrigation(call: ServiceCall) -> None:
        coordinator = _coordinator(call)
        await coordinator.irrigation.async_start(
            manual=True,
            target_liters=call.data.get("target_liters"),
            target_mm=call.data.get("target_mm"),
        )

    async def _stop_irrigation(call: ServiceCall) -> None:
        await _coordinator(call).irrigation.async_stop()

    async def _suspend_irrigation(call: ServiceCall) -> None:
        value = call.data.get("until")
        duration = call.data.get("duration_hours")
        if value and duration is not None:
            raise ServiceValidationError("Choose until or duration_hours")
        until = dt_util.parse_datetime(value) if value else None
        if value and (until is None or until.tzinfo is None):
            raise ServiceValidationError("Use an ISO timestamp with timezone for until")
        if duration is not None:
            until = dt_util.utcnow() + timedelta(hours=duration)
        await _coordinator(call).irrigation.async_suspend_automation(until)

    async def _record_watering(call: ServiceCall) -> None:
        coordinator = _coordinator(call)
        if coordinator.irrigation and coordinator.irrigation.active:
            raise ServiceValidationError(
                "Cannot manually record water during a controlled irrigation session"
            )
        at = _recorded_at(call)
        if at is not None and "amount_mm" not in call.data:
            raise ServiceValidationError(
                "Historical watering requires an explicit amount_mm"
            )
        await coordinator.async_mark_watered(call.data.get("amount_mm"), recorded_at=at)

    async def _record_fertilizing(call: ServiceCall) -> None:
        await _coordinator(call).async_mark_fertilized(
            call.data.get("product_npk"),
            call.data.get("amount_kg"),
            recorded_at=_recorded_at(call),
        )

    async def _record_mowing(call: ServiceCall) -> None:
        await _coordinator(call).async_mark_mowed(recorded_at=_recorded_at(call))

    async def _undo(call: ServiceCall) -> None:
        await _coordinator(call).async_undo_last_action()

    def _finite(value: float) -> float:
        if not math.isfinite(value):
            raise vol.Invalid("A finite quantity is required")
        return value

    entry_schema = {vol.Required("config_entry_id"): cv.string}
    history_schema = {**entry_schema, vol.Optional("recorded_at"): cv.string}
    hass.services.async_register(
        DOMAIN,
        "start_irrigation",
        _start_irrigation,
        schema=vol.Schema(
            {
                **entry_schema,
                vol.Optional("target_liters"): vol.All(
                    vol.Coerce(float), _finite, vol.Range(min=0.1, max=50000)
                ),
                vol.Optional("target_mm"): vol.All(
                    vol.Coerce(float), _finite, vol.Range(min=0.1, max=50)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN, "stop_irrigation", _stop_irrigation, schema=vol.Schema(entry_schema)
    )
    hass.services.async_register(
        DOMAIN,
        "suspend_irrigation",
        _suspend_irrigation,
        schema=vol.Schema(
            {
                **entry_schema,
                vol.Optional("until"): cv.string,
                vol.Optional("duration_hours"): vol.All(
                    vol.Coerce(float), _finite, vol.Range(min=0.25, max=168)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "record_watering",
        _record_watering,
        schema=vol.Schema(
            {
                **history_schema,
                vol.Optional("amount_mm"): vol.All(
                    vol.Coerce(float), _finite, vol.Range(min=0, max=50)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "record_fertilizing",
        _record_fertilizing,
        schema=vol.Schema(
            {
                **history_schema,
                vol.Optional("product_npk"): cv.string,
                vol.Optional("amount_kg"): vol.All(
                    vol.Coerce(float), _finite, vol.Range(min=0, max=100)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN, "record_mowing", _record_mowing, schema=vol.Schema(history_schema)
    )
    hass.services.async_register(
        DOMAIN, "undo_last_action", _undo, schema=vol.Schema(entry_schema)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Set up Lawn Care Assistant from a config entry."""
    coordinator = LawnCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.irrigation = IrrigationController(hass, coordinator)
    if (
        coordinator.irrigation.configured
        or coordinator.irrigation.active
        or coordinator._state.irrigation_recent_valve_id
    ):
        await coordinator.irrigation.async_initialize()
        await coordinator.async_request_refresh()

    registry = er.async_get(hass)
    if not coordinator.irrigation.configured and not coordinator.irrigation.active:
        _remove_unused_irrigation_entities(hass, entry.entry_id)
    for key in (
        "watering_due",
        "fertilizing_due",
        "mower_can_be_switched_off",
        "mower_start_recommended",
    ):
        entity_id = registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{entry.entry_id}_{key}"
        )
        if entity_id:
            registry.async_remove(entity_id)

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
            await coordinator.async_mark_mowed(
                event_id=f"{new_state.entity_id}:{new_state.last_changed.isoformat()}",
                recorded_at=event.time_fired,
                source="completion_input",
            )
        else:
            if coordinator.irrigation and coordinator.irrigation.active:
                return
            await coordinator.async_mark_watered(deduplicate=True)

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

    coordinator.mowing_observer = MowingObserver(coordinator)
    coordinator.mowing_observer.subscribe(entry)
    leaf_id = coordinator.settings.get(CONF_LEAF_WETNESS_ENTITY)
    if leaf_id:

        async def _leaf_changed(_event):
            await coordinator.async_request_refresh()

        entry.async_on_unload(
            async_track_state_change_event(hass, [leaf_id], _leaf_changed)
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LawnConfigEntry) -> bool:
    """Unload a config entry."""
    if (
        entry.runtime_data.irrigation
        and not await entry.runtime_data.irrigation.async_shutdown()
    ):
        return False
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
    if entry.version == 4:
        data = {
            **entry.data,
            CONF_SOIL_MOISTURE_ENTITY: None,
        }
        hass.config_entries.async_update_entry(
            entry, data=data, version=5, minor_version=0
        )
    if entry.version == 5:
        data = {
            **entry.data,
            "precipitation_mode": "auto",
            CONF_SOIL_TEMPERATURE_ENTITY: None,
        }
        hass.config_entries.async_update_entry(
            entry, data=data, version=6, minor_version=0
        )
    if entry.version == 6:
        defaults = {
            CONF_ROOT_DEPTH: DEFAULT_ROOT_DEPTH,
            CONF_SLOPE: DEFAULT_SLOPE,
            CONF_COMPACTION: DEFAULT_COMPACTION,
            CONF_IRRIGATION_EFFICIENCY: DEFAULT_IRRIGATION_EFFICIENCY,
            CONF_RAIN_CORRECTION: DEFAULT_RAIN_CORRECTION,
            CONF_SOIL_SENSOR_DRY: DEFAULT_SOIL_SENSOR_DRY,
            CONF_SOIL_SENSOR_WET: DEFAULT_SOIL_SENSOR_WET,
        }
        data = {
            **entry.data,
            **{key: entry.data.get(key, value) for key, value in defaults.items()},
        }
        options = {
            **entry.options,
            **{
                key: entry.options.get(key, entry.data.get(key, value))
                for key, value in defaults.items()
            },
        }
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            version=7,
            minor_version=0,
            unique_id=entry.entry_id,
        )
    if entry.version == 7:
        hass.config_entries.async_update_entry(entry, version=8, minor_version=0)
    if entry.version == 8:
        hass.config_entries.async_update_entry(entry, version=9, minor_version=0)
    return True


def _remove_unused_irrigation_entities(hass: HomeAssistant, entry_id: str) -> None:
    """Remove only this entry's optional outputs and obsolete valve repair."""
    registry = er.async_get(hass)
    for platform, key in (
        ("sensor", "irrigation_status"),
        ("sensor", "irrigation_readiness"),
        ("sensor", "irrigation_auto_decision"),
        ("sensor", "next_automatic_start"),
        ("sensor", "irrigation_remaining_time"),
        ("button", "stop_irrigation"),
        ("switch", "automatic_irrigation"),
    ):
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry_id}_{key}")
        if entity_id:
            registry.async_remove(entity_id)
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_irrigation_valve_stuck")
