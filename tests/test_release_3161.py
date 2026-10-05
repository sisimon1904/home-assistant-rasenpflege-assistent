"""Attribute localization and stable automation data for release 3.16.1.

File: tests/test_release_3161.py

Exercise HA's actual entity translation loader in both supported languages.
Check every emitted top-level attribute, conditional robot hints, enum labels,
localized nested care statuses and regional-language fallback. Reading sensor
attributes must preserve codes and perform no service or forecast requests.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.translation import async_get_translations

from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.explanations import (
    EXPLANATIONS,
    reason_text,
)
from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor
from tests.test_release_3120 import _live

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN


@pytest.mark.parametrize("language", ["de", "en"])
@pytest.mark.parametrize("record_source", ["manual", "robot_estimate"])
async def test_all_emitted_attribute_labels_load_in_home_assistant(
    hass, enable_custom_integrations, language, record_source
):
    hass.config.language = language
    c = await _live(hass)
    c.coordinator.data.mowing_record_source = record_source
    translations = await async_get_translations(
        hass, language, "entity", integrations={DOMAIN}
    )
    for description in SENSORS:
        sensor = LawnSensor(c.coordinator, description)
        for attribute in sensor.extra_state_attributes:
            key = f"component.{DOMAIN}.entity.sensor.{description.translation_key}.state_attributes.{attribute}.name"
            assert translations.get(key), (description.key, attribute)


@pytest.mark.parametrize("language", ["de", "en"])
async def test_native_sensor_enum_values_have_loaded_translations(
    hass, enable_custom_integrations, language
):
    translations = await async_get_translations(
        hass, language, "entity", integrations={DOMAIN}
    )
    for description in SENSORS:
        for option in description.options or []:
            assert translations[
                f"component.{DOMAIN}.entity.sensor.{description.translation_key}.state.{option}"
            ]
    prefix = f"component.{DOMAIN}.entity.sensor.irrigation_status.state_attributes"
    assert (
        translations[f"{prefix}.reason.state.target_reached"]
        == EXPLANATIONS[language]["target_reached"]
    )
    assert translations[f"{prefix}.valve_state.state.on"] == (
        "Offen" if language == "de" else "Open"
    )
    assert translations[f"{prefix}.session_source.state.auto"] == (
        "Automatisch" if language == "de" else "Automatic"
    )


def _leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        return {
            path
            for key, child in value.items()
            for path in _leaf_paths(child, (*prefix, key))
        }
    return {prefix}


def test_both_languages_and_source_strings_have_identical_translation_keys():
    german = json.loads((ROOT / "translations/de.json").read_text())
    english = json.loads((ROOT / "translations/en.json").read_text())
    assert _leaf_paths(german) == _leaf_paths(english)
    assert json.loads((ROOT / "strings.json").read_text()) == english


@pytest.mark.parametrize(
    "language,expected",
    [
        ("de", "Hoch"),
        ("de-DE", "Hoch"),
        ("de_AT", "Hoch"),
        ("DE-ch", "Hoch"),
        ("en", "High"),
        ("en-GB", "High"),
        ("fr", "High"),
    ],
)
def test_reason_text_supports_regional_languages_and_english_fallback(
    language, expected
):
    assert reason_text("high", language) == expected
    assert reason_text("new_unknown_code", language) == "new_unknown_code"
    assert reason_text(None, language) is None


@pytest.mark.parametrize("language", ["de", "en"])
@pytest.mark.parametrize(
    "status",
    [
        "not_due",
        "wait_for_growth",
        "spring_fertilizing_recommended",
        "spring_fertilizing_recorded",
        "summer_fertilizing_recommended",
        "fertilizing_not_due_yet",
        "fertilize_only_if_needed",
        "autumn_fertilizing_recommended",
        "autumn_fertilizing_recorded",
    ],
)
async def test_nested_care_statuses_are_translated_without_changing_codes(
    hass, language, status
):
    hass.config.language = language
    c = await _live(hass)
    c.coordinator.data.fertilizing_status = status
    c.coordinator.data.watering_status = "water_now"
    c.coordinator.data.mower_status = "mow_regularly"
    sensor = LawnSensor(c.coordinator, next(d for d in SENSORS if d.key == "care_plan"))
    attrs = sensor.extra_state_attributes
    for key, code in [
        ("fertilizing", status),
        ("watering", "water_now"),
        ("mowing", "mow_regularly"),
    ]:
        assert attrs[key]["status"] == code
        assert (
            attrs[key]["status_text"]
            == EXPLANATIONS[language][
                "fertilizing_not_due"
                if key == "fertilizing" and code == "not_due"
                else code
            ]
        )
        assert attrs[key]["status_text"] != code


@pytest.mark.parametrize("language", ["de-DE", "en-GB"])
async def test_localized_attributes_are_read_only_and_keep_machine_values(
    hass, language
):
    hass.config.language = language
    c = await _live(hass)
    c.coordinator.state.irrigation_last_reason = "target_reached"
    c.coordinator.data.irrigation_reason = "target_reached"
    state_before = deepcopy(c.coordinator.state.as_dict())
    with (
        patch.object(
            type(hass.services), "async_call", new_callable=AsyncMock
        ) as calls,
        patch.object(
            c.coordinator, "_async_forecast", new_callable=AsyncMock
        ) as forecast,
    ):
        for description in SENSORS:
            attrs = LawnSensor(c.coordinator, description).extra_state_attributes
            json.dumps(attrs, allow_nan=False)
            if description.key == "irrigation_status":
                assert attrs["reason"] == "target_reached"
                assert attrs["reason_text"] == reason_text("target_reached", language)
                assert attrs["automatic_blockers_text"] == [
                    reason_text(code, language) for code in attrs["automatic_blockers"]
                ]
        calls.assert_not_called()
        forecast.assert_not_called()
    assert c.coordinator.state.as_dict() == state_before
    assert c.action_hint(language) == c.action_hint(language.split("-")[0])
