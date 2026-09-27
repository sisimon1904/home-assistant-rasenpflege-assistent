"""Ensure Home Assistant actually loads the settings labels and descriptions."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.rasenpflege_assistent.config_flow import (
    GENERAL_FIELDS,
    IRRIGATION_FIELDS,
    MAINTENANCE_FIELDS,
    MODEL_FIELDS,
    SAFETY_FIELDS,
    SENSOR_FIELDS,
)
from custom_components.rasenpflege_assistent.const import DOMAIN


@pytest.mark.parametrize("language", ["de", "en"])
async def test_options_labels_and_descriptions_load(
    hass: HomeAssistant, enable_custom_integrations: None, language: str
) -> None:
    """Every settings section has translated labels in the runtime loader."""
    translations = await async_get_translations(
        hass, language, "options", integrations={DOMAIN}
    )
    for step, fields in {
        "general": GENERAL_FIELDS,
        "sensors": SENSOR_FIELDS,
        "irrigation": IRRIGATION_FIELDS,
        "safety": SAFETY_FIELDS,
        "model": MODEL_FIELDS,
        "maintenance": MAINTENANCE_FIELDS,
    }.items():
        assert translations[f"component.{DOMAIN}.options.step.{step}.title"]
        for field in fields:
            assert translations[f"component.{DOMAIN}.options.step.{step}.data.{field}"]
            assert translations[
                f"component.{DOMAIN}.options.step.{step}.data_description.{field}"
            ]
        assert translations[f"component.{DOMAIN}.options.step.init.menu_options.{step}"]
