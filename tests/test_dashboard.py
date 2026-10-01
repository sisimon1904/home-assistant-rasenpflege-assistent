"""Validate dashboard YAML and embedded Home Assistant templates."""

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
    assert isinstance(card, dict) and "type" in card

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
