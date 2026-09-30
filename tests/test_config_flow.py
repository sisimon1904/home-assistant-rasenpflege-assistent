"""Tests for the Lawn Care Assistant config flow and migration."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent import async_migrate_entry
from custom_components.rasenpflege_assistent.config_flow import (
    GENERAL_FIELDS,
    LawnCareConfigFlow,
    LawnCareOptionsFlow,
    _validate_unique_valve,
)
from custom_components.rasenpflege_assistent.const import DOMAIN


def _input(weather_entity: str) -> dict:
    """Return a complete valid setup payload."""
    return {
        "name": "Back lawn",
        "weather_entity": weather_entity,
        "precipitation_mode": "auto",
        "default_watering_amount": 15,
        "area": 100,
        "sun_exposure": "sunny",
        "lawn_type": "family",
        "soil_type": "loamy",
        "initial_gts": 0,
        "initial_soil_moisture": 70,
        "root_depth_cm": 10,
        "slope": "flat",
        "compaction": "normal",
        "irrigation_efficiency": 0.85,
        "rain_correction": 1.0,
        "soil_sensor_dry": 0,
        "soil_sensor_wet": 100,
    }


async def test_user_flow(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """A valid OpenWeatherMap entity creates a version 9 entry."""
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "weather",
        "openweathermap",
        "test-weather",
        suggested_object_id="openweathermap",
    )
    hass.states.async_set(entity.entity_id, "sunny", {"temperature": 20})

    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": config_entries.SOURCE_USER}
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    assert {key.schema for key in result["data_schema"].schema} == set(GENERAL_FIELDS)
    weather_field = next(
        key for key in result["data_schema"].schema if key.schema == "weather_entity"
    )
    assert weather_field.description["suggested_value"] == entity.entity_id

    with patch(
        "custom_components.rasenpflege_assistent.async_setup_entry",
        return_value=True,
    ):
        result = await flow.async_step_user(_input(entity.entity_id))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Back lawn"
    assert result["version"] == 9
    assert result["data"]["name"] == "Back lawn"
    assert "irrigation_valve" not in result["data"]
    assert flow.context["unique_id"]


async def test_invalid_soil_sensor_calibration(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Wet calibration must be greater than the dry reference."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.openweathermap"), version=9
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    user_input = {
        "soil_sensor_dry": 60,
        "soil_sensor_wet": 40,
        "root_depth_cm": 10,
        "slope": "flat",
        "compaction": "normal",
        "default_watering_amount": 15,
        "irrigation_efficiency": 0.85,
        "rain_correction": 1.0,
    }
    result = await flow.async_step_model(user_input)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"soil_sensor_wet": "soil_sensor_range_invalid"}


async def test_migrate_version_six_entry(hass: HomeAssistant) -> None:
    """Version 6 entries receive model v3 defaults and a stable unique ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Lawn"},
        options={},
        version=6,
        unique_id="lawn",
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 9
    assert entry.unique_id == entry.entry_id
    assert entry.data["root_depth_cm"] == 10
    assert entry.options["rain_correction"] == 1.0


async def test_migrate_version_eight_preserves_valve_and_automation(
    hass: HomeAssistant,
) -> None:
    """Existing users keep the configured valve and automation preference."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"irrigation_valve": "switch.garden_water"},
        options={"irrigation_flow": "sensor.shared_water"},
        version=8,
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 9
    assert entry.data["irrigation_valve"] == "switch.garden_water"
    assert entry.options["irrigation_flow"] == "sensor.shared_water"


async def test_valve_requires_mower_guard(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An irrigator cannot be configured without a verified mower input."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.openweathermap"), version=9
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    payload = {
        "irrigation_valve": "switch.garden_water",
        "irrigation_flow": "sensor.garden_liters",
        "mower_safe_state": "docked",
        "allow_unmetered_manual": False,
    }
    result = await flow.async_step_irrigation(payload)
    assert result["errors"]["mower_location"] == "mower_required"


async def test_same_valve_cannot_be_owned_by_two_lawns(hass: HomeAssistant) -> None:
    """Two independent watchdogs must not compete for one shared valve."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={"irrigation_valve": "switch.shared_valve"},
    )
    existing.add_to_hass(hass)
    settings = {"irrigation_valve": "switch.shared_valve"}
    assert _validate_unique_valve(hass, settings) == {
        "irrigation_valve": "valve_already_used"
    }
    assert not _validate_unique_valve(hass, settings, existing.entry_id)


def test_irrigation_options_hide_recorded_watering_and_show_numeric_values() -> None:
    """A controlled valve has one watering input; numeric options are editable."""
    from homeassistant.helpers.selector import NumberSelectorMode

    from custom_components.rasenpflege_assistent.config_flow import _schema

    full = {key.schema: value for key, value in _schema().schema.items()}
    valve = {
        key.schema: value for key, value in _schema(show_watered=False).schema.items()
    }
    assert "watered_entity" in full
    assert "watered_entity" not in valve
    assert "other_valve" in valve
    for name in (
        "initial_soil_moisture",
        "irrigation_efficiency",
        "rain_correction",
        "min_irrigation_minutes",
        "max_irrigation_minutes",
        "max_irrigation_liters",
        "flow_start_grace_seconds",
        "min_flow_l_min",
        "max_flow_l_min",
    ):
        assert valve[name].config["mode"] == NumberSelectorMode.BOX
    markers = {key.schema: key for key in _schema(show_watered=False).schema}
    assert markers["min_irrigation_minutes"].default() == 5
    assert markers["max_irrigation_minutes"].default() == 90


async def test_options_form_prefills_saved_irrigation_times(
    hass: HomeAssistant,
) -> None:
    """Saved minute values appear in the editable options form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_input("weather.openweathermap"),
        options={
            "irrigation_valve": "switch.garden_water",
            "min_irrigation_minutes": 12,
            "max_irrigation_minutes": 75,
        },
        version=9,
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    menu = await flow.async_step_init()
    assert menu["type"] is FlowResultType.MENU
    assert "safety" in menu["menu_options"]
    result = await flow.async_step_safety()

    assert result["type"] is FlowResultType.FORM
    markers = {key.schema: key for key in result["data_schema"].schema}
    assert markers["min_irrigation_minutes"].description["suggested_value"] == 12
    assert markers["max_irrigation_minutes"].description["suggested_value"] == 75


async def test_saving_one_settings_page_preserves_other_pages(
    hass: HomeAssistant,
) -> None:
    """Editing a model value leaves the configured valve and sensors untouched."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_input("weather.openweathermap"),
        options={
            "irrigation_valve": "switch.garden_water",
            "irrigation_flow": "sensor.shared_meter",
            "mower_location": "lawn_mower.garden",
            "temperature_entity": "sensor.outside",
            "root_depth_cm": 11,
        },
        version=9,
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_model({"root_depth_cm": 12})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["root_depth_cm"] == 12
    assert result["data"]["irrigation_valve"] == "switch.garden_water"
    assert result["data"]["irrigation_flow"] == "sensor.shared_meter"
    assert result["data"]["temperature_entity"] == "sensor.outside"


async def test_saving_settings_while_irrigating_is_rejected(
    hass: HomeAssistant,
) -> None:
    """A settings reload must not interrupt an active valve session."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.openweathermap"), version=9
    )
    entry.add_to_hass(hass)
    entry.runtime_data = type(
        "Runtime", (), {"irrigation": type("Valve", (), {"active": True})()}
    )()
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_maintenance({"last_watering": "2026-09-20"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "irrigation_active"


async def test_clearing_optional_sensor_keeps_irrigation_settings(
    hass: HomeAssistant,
) -> None:
    """Removing a sensor on its page does not erase a saved valve or limits."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_input("weather.openweathermap"),
        options={
            "temperature_entity": "sensor.old_temperature",
            "irrigation_valve": "switch.garden_water",
            "max_irrigation_minutes": 72,
        },
        version=9,
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_sensors({"precipitation_mode": "auto"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["temperature_entity"] is None
    assert result["data"]["irrigation_valve"] == "switch.garden_water"
    assert result["data"]["max_irrigation_minutes"] == 72


async def test_mowing_page_preserves_other_settings(hass: HomeAssistant) -> None:
    """Selecting robot mowing never erases unrelated irrigation configuration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_input("weather.openweathermap"),
        options={"irrigation_valve": "switch.garden", "max_irrigation_minutes": 72},
        version=9,
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    menu = await flow.async_step_init()
    assert "mowing" in menu["menu_options"]
    result = await flow.async_step_mowing(
        {
            "mowing_mode": "robot",
            "mowing_interval_factor": 1,
            "mowing_active_state": "mowing",
            "mowing_done_state": "docked",
            "mowing_min_minutes": 10,
        }
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["irrigation_valve"] == "switch.garden"
    assert result["data"]["max_irrigation_minutes"] == 72
    assert result["data"]["mowing_mode"] == "robot"


async def test_mowing_page_rejects_unsafe_completion_states(
    hass: HomeAssistant,
) -> None:
    """Idle, unknown and error cannot be configured as successful docking."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.openweathermap"), version=9
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    for done in ("mowing", "idle", "unknown", "unavailable", "error"):
        result = await flow.async_step_mowing(
            {
                "mowing_mode": "robot",
                "mowing_interval_factor": 1,
                "mowing_active_state": "mowing",
                "mowing_done_state": done,
                "mowing_min_minutes": 10,
            }
        )
        assert result["errors"]["mowing_done_state"] == "mowing_states_invalid"


async def test_unchanged_mowing_date_preserves_exact_record_on_history_save(hass):
    """Editing another history field leaves the last mowing time untouched."""
    from types import SimpleNamespace

    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.openweathermap"), version=9
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        _state=SimpleNamespace(last_mowing="2026-07-20")
    )
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_maintenance(
        {"last_mowing": "2026-07-20", "initial_gts": 300, "initial_soil_moisture": 70}
    )
    assert "last_mowing_revision" not in result["data"]
    assert "last_mowing" not in result["data"]
