"""Evidence review, water balances and comparable mowing runs for 3.15.0.

File: tests/test_release_3150.py

Check bounded persisted advice, unique actual weather report clocks, unknown
water quantities and immutable session area. Exercise attribute-only program
changes through HA events and keep diagnostics independent from commands.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Event, State

from custom_components.rasenpflege_assistent.guidance import (
    duration_context,
    duration_suggestion,
)
from custom_components.rasenpflege_assistent.mowing import MowingObserver
from custom_components.rasenpflege_assistent.review import (
    irrigation_balance,
    program_context,
    remember_advice,
    restore_advice,
    review_advice,
)
from tests.test_mowing import _coordinator
from tests.test_release_3120 import NOW, _live
from tests.test_release_3140 import SETTINGS, _runs


def _advice():
    return [
        {
            "issued_at": NOW.isoformat(),
            "start": (NOW + timedelta(hours=1)).isoformat(),
            "end": (NOW + timedelta(hours=2)).isoformat(),
        }
    ]


def _samples():
    return [
        {
            "reported_at": (NOW + timedelta(minutes=minute)).isoformat(),
            "temperature": 20,
            "humidity": 50,
            "dew_point": None,
            "wind_speed": 2,
            "precipitation": 0,
            "stale": False,
            "condition": "sunny",
        }
        for minute in [60, 90, 120]
    ]


def test_review_uses_later_unique_observations_without_confirming_dryness():
    result = review_advice(_advice(), _samples(), NOW + timedelta(hours=3), "de")
    window = result["windows"][0]
    assert window["status"] == "review_suitable_sampled"
    assert window["surface_dry_confirmed"] is False
    assert window["sample_count"] == 3
    assert review_advice(_advice(), _samples(), NOW, "en")["windows"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"humidity": None},
        {"wind_speed": None},
        {"stale": True},
        {"reported_at": "broken"},
        {"precipitation": None},
    ],
)
def test_review_incomplete_evidence_stays_unknown(changes):
    samples = _samples()
    for row in samples:
        row.update(changes)
    assert (
        review_advice(_advice(), samples, NOW + timedelta(hours=3), "en")["windows"][0][
            "status"
        ]
        == "review_insufficient"
    )


def test_review_reports_bad_weather_and_refuses_conflicting_hours():
    samples = _samples()
    samples[1]["precipitation"] = 1
    result = review_advice(_advice(), samples, NOW + timedelta(hours=3), "en")[
        "windows"
    ][0]
    assert result["status"] == "review_unsuitable_observed"
    assert "mowing_rain" in result["reasons"]
    assert (
        review_advice(
            _advice(), _samples() + [samples[1]], NOW + timedelta(hours=3), "en"
        )["windows"][0]["status"]
        == "review_insufficient"
    )


def test_repeated_weather_reports_cannot_fabricate_time_coverage():
    samples = [
        {**_samples()[0], "timestamp": (NOW + timedelta(minutes=i)).isoformat()}
        for i in [60, 90, 120]
    ]
    result = review_advice(_advice(), samples, NOW + timedelta(hours=3), "en")[
        "windows"
    ][0]
    assert result["sample_count"] == 1 and result["status"] == "review_insufficient"
    # Equal point evidence with different model ticks does not create a conflict.
    result = review_advice(
        _advice(),
        _samples() + [{**_samples()[1], "timestamp": "different"}],
        NOW + timedelta(hours=3),
        "en",
    )["windows"][0]
    assert result["status"] == "review_suitable_sampled"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        42,
        {},
        [42],
        [_advice()[0] | {"start": "2026-10-04T09:00:00"}],
        [_advice()[0] | {"issued_at": (NOW + timedelta(days=2)).isoformat()}],
    ],
)
def test_corrupt_or_future_advice_history_is_rejected(raw):
    assert restore_advice(raw, NOW) == []


def test_duplicate_recommendations_are_bounded_and_detached():
    advice = _advice()
    plan = {"start": advice[0]["start"], "end": advice[0]["end"]}
    assert remember_advice(advice, plan, NOW) == advice
    result = restore_advice(advice, NOW)
    result[0]["start"] = "changed"
    assert advice[0]["start"] != "changed"


@pytest.mark.parametrize(
    "gap,liters,remaining,quality",
    [
        (False, 40, 60, "water_recorded"),
        (True, 40, None, "water_partial"),
        (False, None, None, "water_unmetered"),
    ],
)
def test_water_balance_preserves_unknown_remainder(gap, liters, remaining, quality):
    result = irrigation_balance(
        {
            "target_liters": 100,
            "liters": liters,
            "measurement_gap": gap,
            "effective_model_mm": 0.3,
            "area_m2": 100,
            "reason": "manual_stop",
        },
        "de",
    )
    assert result["remaining_liters"] == remaining
    assert result["delivery_quality"] == quality
    assert result["effective_model_liters"] == 30
    assert (
        result["safety_recheck_required"] is True
        and result["automatically_resumed"] is False
    )


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        42,
        {"liters": True, "target_liters": float("inf"), "effective_model_mm": -1},
    ],
)
def test_malformed_water_balances_are_unknown(raw):
    result = irrigation_balance(raw, "en")
    assert result["recorded_liters"] is None
    assert result["remaining_liters"] is None
    assert result["effective_model_liters"] is None


def test_legacy_water_record_does_not_use_current_area_to_invent_credit_liters():
    result = irrigation_balance({"liters": 40, "effective_model_mm": 0.3}, "en")
    assert (
        result["effective_model_mm"] == 0.3 and result["effective_model_liters"] is None
    )


def test_duration_details_explain_exclusions_and_area_change():
    records = _runs()
    records[0]["details"]["interruptions"] = 2
    result = duration_suggestion(records, SETTINGS, NOW)
    assert result["excluded"]["duration_interrupted"] == 1
    assert result["minimum_minutes"] == 58 and result["maximum_minutes"] == 62
    assert len(result["samples"]) == 2
    result = duration_suggestion(_runs(), SETTINGS | {"area": 200}, NOW)
    assert (
        result["sample_count"] == 0
        and result["excluded"]["duration_context_changed"] == 3
    )
    assert duration_context(SETTINGS | {"area": 100}) == duration_context(
        SETTINGS | {"area": 100.0}
    )


def test_reported_partial_area_program_is_not_mixed_with_other_programs():
    records = _runs()
    for row in records:
        row["details"]["program_context"] = {"area_id": "all"}
    result = duration_suggestion(records, SETTINGS, NOW, {"area_id": "front"})
    assert (
        result["sample_count"] == 0
        and result["excluded"]["duration_program_different"] == 3
    )
    assert program_context({"progress": 100, "name": "front", "area_id": "front"}) == {
        "area_id": "front"
    }
    assert program_context({"progress": 100}) == {}


async def test_attribute_only_program_change_excludes_duration_but_preserves_observed_work(
    hass, freezer
):
    freezer.move_to(NOW)
    c = _coordinator(hass)
    observer = MowingObserver(c)

    def event(old, new, minute, attributes):
        return Event(
            "state_changed",
            {
                "old_state": State("lawn_mower.knoxx", old),
                "new_state": State("lawn_mower.knoxx", new, attributes),
            },
            time_fired_timestamp=(NOW + timedelta(minutes=minute)).timestamp(),
        )

    await observer.async_handle_event(
        event("docked", "mowing", 0, {"area_id": "front"})
    )
    await observer.async_handle_event(event("mowing", "mowing", 5, {"area_id": "back"}))
    await observer.async_handle_event(event("mowing", "docked", 60, {}))
    detail = c.state.maintenance_history[-1]["details"]
    assert (
        detail["program_context"] == {"area_id": "front"}
        and detail["program_stable"] is False
    )
    assert detail["active_seconds"] == 3600
    assert (
        duration_suggestion(
            c.state.maintenance_history, c.settings, NOW + timedelta(hours=1)
        )["sample_count"]
        == 0
    )


@pytest.mark.parametrize("raw", [None, 42, {}, [42]])
async def test_broken_saved_weather_history_does_not_break_setup(hass, raw):
    c = _coordinator(hass)
    c._store.async_load = AsyncMock(
        return_value={"weather_samples": raw, "local_day_model": True}
    )
    await c._async_setup()
    assert c.state.weather_samples == []


@pytest.mark.parametrize("reason", [None, {"bad": "reason"}, 42])
@pytest.mark.parametrize("sensor_key", ["irrigation_status", "irrigation_readiness"])
async def test_missing_finish_reason_does_not_break_irrigation_sensor(
    hass, reason, sensor_key
):
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    c = await _live(hass)
    c.state.irrigation_last_session = {"liters": 10, "reason": reason}
    description = next(item for item in SENSORS if item.key == sensor_key)
    attributes = LawnSensor(c.coordinator, description).extra_state_attributes
    assert attributes["last_session"]["reason_text"] != "water_reason_unknown"


async def test_advice_reads_are_read_only(hass, freezer):
    freezer.move_to(NOW)
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as calls:
        first = c.coordinator.mowing_plan_details()
        second = c.coordinator.mowing_plan_details()
    assert first["retrospective"] == second["retrospective"]
    assert c.state.mowing_advice_history == []
    calls.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()


async def test_finished_water_balance_keeps_original_area_after_settings_change(
    hass, freezer
):
    from tests.test_irrigation import _controller

    freezer.move_to(NOW)
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=50)
    freezer.move_to(NOW + timedelta(minutes=2))
    hass.states.async_set(
        "sensor.garden_water_liters", "20", {"unit_of_measurement": "L"}
    )
    await c.async_stop()
    balance = c.diagnostic_attributes()["water_balance"]
    assert balance["recorded_liters"] == 20 and balance["remaining_liters"] == 30
    assert balance["area_m2"] == 100
    c.coordinator.config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        c.coordinator.config_entry,
        options={**c.coordinator.config_entry.options, "area": 200},
    )
    assert c.diagnostic_attributes()["water_balance"] == balance


@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_persisted_advice_survives_restart_and_failed_save_rolls_back(
    hass, freezer, failure
):
    from tests.test_coordinator import _coordinator as model

    freezer.move_to(NOW)
    c = model(hass)
    c._store.async_load = AsyncMock(
        return_value={"mowing_advice_history": _advice(), "local_day_model": True}
    )
    await c._async_setup()
    assert c.state.mowing_advice_history == _advice()
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": 20, "humidity": 50, "wind_speed": 2},
    )
    c._async_forecast = AsyncMock(return_value=[])
    original = list(c.state.mowing_advice_history)
    c._store.async_save = AsyncMock(side_effect=failure("save interrupted"))
    with (
        patch.object(
            c,
            "mowing_plan_details",
            return_value={
                "start": (NOW + timedelta(hours=3)).isoformat(),
                "end": (NOW + timedelta(hours=4)).isoformat(),
            },
        ),
        pytest.raises(failure),
    ):
        await c._async_update_data()
    assert c.state.mowing_advice_history == original


def test_backdated_program_cannot_replace_latest_observed_program():
    runs = _runs()
    for row in runs:
        row["details"]["program_context"] = {"area_id": "all"}
    old = {
        **runs[0],
        "details": {
            **runs[0]["details"],
            "recorded_at": (NOW - timedelta(days=10)).isoformat(),
            "program_context": {"area_id": "front"},
        },
    }
    result = duration_suggestion(runs + [old], SETTINGS, NOW)
    assert result["program_context"] == {"area_id": "all"}
    assert result["sample_count"] == 3


async def test_gap_diagnostics_do_not_claim_history_recovered_from_new_sensor(hass):
    c = await _live(hass)
    c.state.last_soil_model_gap_at = (NOW - timedelta(days=1)).isoformat()
    c.state.last_soil_model_gap_hours = 0
    result = c.coordinator.insight_diagnostics()["data_gaps"]
    assert result["history_contains_gap"] is True
    assert result["impact_text"]
    assert result["recovery_basis"] == "model_estimate"


@pytest.mark.parametrize("language", ["de", "en"])
async def test_populated_review_balance_summary_and_gap_cards_render(
    hass, freezer, language
):
    from pathlib import Path

    import yaml
    from homeassistant.helpers.template import Template

    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    freezer.move_to(NOW + timedelta(hours=3))
    hass.config.language = language
    c = await _live(hass, **SETTINGS)
    c.state.mowing_advice_history = _advice()
    c.state.weather_samples = _samples()
    c.state.maintenance_history = _runs()
    c.state.irrigation_last_session = {
        "liters": 20,
        "target_liters": 50,
        "effective_model_mm": 0.1,
        "area_m2": 100,
        "measurement_gap": True,
        "reason": "manual_stop",
        "volume_estimated": True,
    }
    c.state.last_soil_model_gap_at = NOW.isoformat()
    care = next(item for item in SENSORS if item.key == "care_plan")
    attrs = LawnSensor(c.coordinator, care).extra_state_attributes
    assert attrs["summary"] == attrs["prioritized_steps"][0]
    plan = c.coordinator.mowing_plan_details()
    attrs.update(
        {
            "mowing_window": plan,
            "mowing_window_quality": plan,
            "water_balance": c.diagnostic_attributes()["water_balance"],
            "data_gaps": c.coordinator.insight_diagnostics()["data_gaps"],
        }
    )
    rendered = []

    def visit(value, entity=None):
        if isinstance(value, dict):
            entity = value.get("entity", entity)
            if entity:
                hass.states.async_set(entity, "mow_regularly", attrs)
            for child in value.values():
                visit(child, entity)
        elif isinstance(value, list):
            for child in value:
                visit(child, entity)
        elif isinstance(value, str) and ("{{" in value or "{%" in value):
            rendered.append(
                Template(value, hass).async_render(
                    {"entity": entity}, parse_result=False
                )
            )

    for name in ("mowing", "care-plan", "diagnostics"):
        visit(
            yaml.safe_load(
                (
                    Path(__file__).parents[1] / f"docs/dashboard/{name}.{language}.yaml"
                ).read_text()
            )
        )
    output = "\n".join(rendered)
    assert attrs["water_balance"]["delivery_quality_text"] in output
    assert plan["retrospective"]["windows"][0]["status_text"] in output
    assert attrs["summary"]["action_text"] in output
    assert attrs["data_gaps"]["impact_text"] in output
    assert "review_suitable_sampled" not in output


@pytest.mark.parametrize("known_current", [False, True])
async def test_program_uncertainty_is_supporting_and_does_not_block_weather_window(
    hass, freezer, known_current
):
    freezer.move_to(NOW)
    c = await _live(
        hass, **SETTINGS, mowing_start_time="00:00:00", mowing_end_time="00:00:00"
    )
    c.state.maintenance_history = _runs()
    for row in c.state.maintenance_history:
        row["details"]["program_context"] = {"area_id": "all"}
    hass.states.async_set(
        SETTINGS["mowing_entity"], "docked", {"area_id": "all"} if known_current else {}
    )
    plan = c.coordinator.mowing_plan_details()
    assert plan["start"]
    assert plan["evidence"]["blocking"] == []
    assert bool(plan["evidence"]["supporting_unknown"]) is not known_current
    assert plan["duration_suggestion"]["current_program_known"] is known_current
    # Missing forecast evidence blocks an actual window without upgrading program metadata.
    c.coordinator._hourly_forecast_cache = []
    blocked = c.coordinator.mowing_plan_details()
    assert blocked["start"] is None
    assert blocked["evidence"]["blocking"]
