"""Validate dashboard YAML and embedded Home Assistant templates.

File: tests/test_dashboard.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from pathlib import Path

import pytest
import yaml
from homeassistant.helpers.template import Template

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "path", sorted((ROOT / "docs/dashboard").glob("*.yaml")), ids=lambda path: path.name
)
async def test_dashboard_templates_parse_and_render(hass, path):
    """Every embedded template renders against actual Home Assistant helpers."""
    card = yaml.safe_load(path.read_text())
    assert isinstance(card, dict) and ("type" in card or "views" in card)

    def visit(value, entity=None):
        if isinstance(value, dict):
            current = value.get("entity", entity)
            for child in value.values():
                visit(child, current)
        elif isinstance(value, list):
            for child in value:
                visit(child, entity)
        elif isinstance(value, str) and ("{{" in value or "{%" in value):
            Template(value, hass).async_render({"entity": entity}, parse_result=False)

    visit(card)


@pytest.mark.parametrize("language", ["de", "en"])
def test_complete_dashboard_native_cards_and_scoped_actions(language):
    """Full dashboards need no custom cards and route control through the integration."""
    path = ROOT / "docs/dashboard" / f"dashboard.{language}.yaml"
    dashboard = yaml.safe_load(path.read_text())
    assert len(dashboard["views"]) == 5
    assert len({view["path"] for view in dashboard["views"]}) == 5

    actions = []

    def visit(value):
        if isinstance(value, dict):
            assert not value.get("type", "").startswith("custom:")
            if value.get("action") == "perform-action":
                assert value["perform_action"].startswith("rasenpflege_assistent.")
                assert value["data"]["config_entry_id"] == "REPLACE_WITH_ENTRY_ID"
                actions.append(value["perform_action"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(dashboard)
    assert "rasenpflege_assistent.start_irrigation" in actions
    assert "rasenpflege_assistent.stop_irrigation" in actions
    assert "rasenpflege_assistent.suspend_irrigation" in actions


@pytest.mark.parametrize("language", ["de", "en"])
async def test_complete_dashboard_renders_live_diagnostics(hass, language):
    """Render nested real coordinator/controller attributes in native Markdown cards."""
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor
    from tests.test_release_3120 import _live

    hass.config.language = language
    controller = await _live(hass)
    entities = {
        "status": "sensor.rasen_pflegestatus",
        "next_action": "sensor.rasen_nachste_aktion",
        "growth_status": "sensor.rasen_wachstumsstatus",
        "care_plan": "sensor.rasen_pflegeplan",
        "soil_moisture": "sensor.rasen_modellierte_bodenfeuchte",
        "mower_status": "sensor.rasen_mahroboterstatus",
        "watering_recommendation": "sensor.rasen_bewasserungsempfehlung",
        "data_quality": "sensor.rasen_datenqualitat",
        "irrigation_status": "sensor.rasen_bewasserungsstatus",
        "irrigation_readiness": "sensor.rasen_bewasserung_diagnose",
        "water_consumption_day": "sensor.rasen_wasserverbrauch_heute",
    }
    for description in SENSORS:
        if description.key in entities:
            sensor = LawnSensor(controller.coordinator, description)
            hass.states.async_set(
                entities[description.key],
                sensor.native_value if sensor.native_value is not None else "unknown",
                sensor.extra_state_attributes,
            )

    rendered = []

    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and ("{{" in value or "{%" in value):
            rendered.append(Template(value, hass).async_render(parse_result=False))

    path = ROOT / "docs/dashboard" / f"dashboard.{language}.yaml"
    visit(yaml.safe_load(path.read_text()))
    assert len(rendered) >= 20
    assert all("Undefined" not in text for text in rendered)
