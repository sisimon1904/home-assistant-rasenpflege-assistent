"""Tests for the Lawn Care Assistant config flow and migration."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent import async_migrate_entry
from custom_components.rasenpflege_assistent.config_flow import (
    LawnCareConfigFlow,
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
    """A valid OpenWeatherMap entity creates a version 8 entry."""
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

    with patch(
        "custom_components.rasenpflege_assistent.async_setup_entry",
        return_value=True,
    ):
        result = await flow.async_step_user(_input(entity.entity_id))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Back lawn"
    assert result["version"] == 8
    assert result["data"]["name"] == "Back lawn"
    assert flow.context["unique_id"]


async def test_invalid_soil_sensor_calibration(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Wet calibration must be greater than the dry reference."""
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "weather",
        "openweathermap",
        "test-weather-invalid",
        suggested_object_id="openweathermap_invalid",
    )
    hass.states.async_set(entity.entity_id, "sunny", {"temperature": 20})
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": config_entries.SOURCE_USER}
    result = await flow.async_step_user()
    user_input = _input(entity.entity_id)
    user_input["soil_sensor_dry"] = 60
    user_input["soil_sensor_wet"] = 40
    result = await flow.async_step_user(user_input)
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
    assert entry.version == 8
    assert entry.unique_id == entry.entry_id
    assert entry.data["root_depth_cm"] == 10
    assert entry.options["rain_correction"] == 1.0


async def test_valve_requires_mower_guard(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An irrigator cannot be configured without a verified mower input."""
    registry = er.async_get(hass)
    weather = registry.async_get_or_create(
        "weather", "openweathermap", "test-guarded-weather"
    )
    hass.states.async_set(weather.entity_id, "sunny", {"temperature": 20})
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": config_entries.SOURCE_USER}
    payload = {
        **_input(weather.entity_id),
        "irrigation_valve": "switch.garden_water",
        "irrigation_flow": "sensor.garden_liters",
    }
    result = await flow.async_step_user(payload)
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
