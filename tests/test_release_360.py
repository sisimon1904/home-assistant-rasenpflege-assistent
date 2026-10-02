"""Release regressions for optional output cleanup and readable explanations.

File: tests/test_release_360.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.rasenpflege_assistent import _remove_unused_irrigation_entities
from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.explanations import reason_text


async def test_removed_valve_removes_only_owned_outputs(hass):
    """Removing one optional valve must not remove other lawns' entities."""
    registry = er.async_get(hass)
    owned = registry.async_get_or_create("sensor", DOMAIN, "first_irrigation_status")
    other = registry.async_get_or_create("sensor", DOMAIN, "second_irrigation_status")
    soil = registry.async_get_or_create("sensor", DOMAIN, "first_soil_moisture")
    ir.async_create_issue(
        hass,
        DOMAIN,
        "first_irrigation_valve_stuck",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="irrigation_valve_stuck",
    )
    _remove_unused_irrigation_entities(hass, "first")
    assert registry.async_get(owned.entity_id) is None
    assert registry.async_get(other.entity_id) is not None
    assert registry.async_get(soil.entity_id) is not None
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "first_irrigation_valve_stuck")
        is None
    )


def test_readable_reasons_keep_estimates_explicit():
    """German/English explanations retain the uncertainty of robot sessions."""
    assert "geschätzt" in reason_text("modeled_soil_moisture_used", "de")
    assert "incomplete" in reason_text("forecast_precipitation_unavailable", "en")
    assert "keine vollständige" in reason_text("robot_estimate", "de")
    assert "does not confirm" in reason_text("robot_estimate", "en")
    assert reason_text("future_reason", "en") == "future_reason"
