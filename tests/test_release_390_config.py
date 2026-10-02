"""Independent options-page error and clearing regressions for 3.9.0.

File: tests/test_release_390_config.py

Exercise public flow steps with HA entries and schema defaults. Rejected
submissions must preserve saved options; unrelated settings survive edits.
"""

from types import SimpleNamespace

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent.config_flow import LawnCareOptionsFlow
from custom_components.rasenpflege_assistent.const import DOMAIN
from tests.test_config_flow import _input


def _flow(hass, **options):
    entry = MockConfigEntry(
        domain=DOMAIN, data=_input("weather.owm"), options=options, version=9
    )
    entry.add_to_hass(hass)
    flow = LawnCareOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    return flow, entry


async def _payload(step):
    form = await step()
    return {
        marker.schema: marker.default()
        for marker in form["data_schema"].schema
        if callable(marker.default) and marker.default() is not vol.UNDEFINED
    }


@pytest.mark.parametrize(
    "active,done",
    [
        ("idle", "docked"),
        ("unknown", "docked"),
        ("mowing", "paused"),
        ("mowing", "MOWING"),
        (" ", "docked"),
    ],
)
async def test_mowing_invalid_states_preserve_options(hass, active, done):
    flow, entry = _flow(hass, mowing_active_state="mowing", mowing_done_state="docked")
    payload = await _payload(flow.async_step_mowing)
    payload.update(mowing_active_state=active, mowing_done_state=done)
    result = await flow.async_step_mowing(payload)
    assert result["type"] is FlowResultType.FORM
    assert "mowing_states_invalid" in result["errors"].values()
    assert entry.options["mowing_active_state"] == "mowing"


@pytest.mark.parametrize(
    "changes,field,code",
    [
        ({"irrigation_valve": "switch.water"}, "mower_location", "mower_required"),
        (
            {"irrigation_valve": "switch.water", "mower_location": "sensor.mower"},
            "irrigation_flow",
            "flow_required",
        ),
        (
            {"irrigation_valve": "switch.water", "other_valve": "switch.water"},
            "other_valve",
            "other_valve_same",
        ),
        ({"mower_safe_state": " "}, "mower_safe_state", "safe_state_required"),
    ],
)
async def test_irrigation_invalid_configuration(hass, changes, field, code):
    flow, entry = _flow(hass)
    payload = await _payload(flow.async_step_irrigation)
    payload.update(changes)
    result = await flow.async_step_irrigation(payload)
    assert result["errors"][field] == code
    assert entry.options == {}


@pytest.mark.parametrize(
    "field,other",
    [
        ("max_irrigation_minutes", "min_irrigation_minutes"),
        ("max_flow_l_min", "min_flow_l_min"),
    ],
)
async def test_safety_equal_bounds_rejected(hass, field, other):
    flow, _ = _flow(hass)
    payload = await _payload(flow.async_step_safety)
    payload[field] = payload[other]
    result = await flow.async_step_safety(payload)
    assert result["errors"][field] == "maximum_below_minimum"


@pytest.mark.parametrize(
    "step_name",
    ["sensors", "mowing", "irrigation", "safety", "model", "maintenance", "schedule"],
)
async def test_all_options_pages_block_active_irrigation(hass, step_name):
    flow, entry = _flow(hass)
    entry.runtime_data = SimpleNamespace(
        irrigation=SimpleNamespace(active=True), _state=None
    )
    step = getattr(flow, f"async_step_{step_name}")
    payload = await _payload(step)
    payload.setdefault("mowing_active_state", "mowing")
    payload.setdefault("mowing_done_state", "docked")
    result = await step(payload)
    assert result["errors"]["base"] == "irrigation_active"
    assert entry.options == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_nonfinite_hidden_setting_is_reported_on_current_page(hass, value):
    flow, entry = _flow(hass, area=value)
    payload = await _payload(flow.async_step_model)
    result = await flow.async_step_model(payload)
    assert result["errors"]["base"] == "invalid_number"
    assert entry.options["area"] is value


async def test_optional_sensor_clear_keeps_unrelated_options(hass):
    flow, _ = _flow(hass, soil_moisture_entity="sensor.soil", rain_correction=1.2)
    result = await flow.async_step_sensors({})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["soil_moisture_entity"] is None
    assert result["data"]["rain_correction"] == 1.2
