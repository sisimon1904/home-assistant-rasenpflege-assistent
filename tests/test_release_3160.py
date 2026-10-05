"""Care previews, bounded retrospective counts and quantity comparisons.

File: tests/test_release_3160.py

Cached candidate times remain conditional on unresolved care prerequisites.
Only distinct complete counter sessions support repeated deviation hints.
Legacy and conflicting evidence never becomes a confirmed volume or fault.
"""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.rasenpflege_assistent.outlook import (
    care_outlook,
    irrigation_comparison,
    irrigation_context,
)
from custom_components.rasenpflege_assistent.review import review_advice
from tests.test_release_3120 import NOW, _live
from tests.test_release_3150 import _advice, _samples

CONTEXT = irrigation_context(
    {
        "area": 100,
        "irrigation_valve": "switch.water",
        "irrigation_flow": "sensor.water",
    },
    "total",
    "L",
)


def _step(action, after=None, availability="later"):
    return {"action": action, "after": after, "availability": availability}


def _preview(steps, start=1, end=3, now=NOW):
    window = {
        "start": (now + timedelta(hours=start)).isoformat(),
        "end": (now + timedelta(hours=end)).isoformat(),
    }
    return care_outlook(
        steps,
        window,
        {"at": window["start"], "end": window["end"]},
        "autumn",
        now,
        "de",
    )


def _session(i=0, **changes):
    return {
        "source": "irrigation",
        "session_id": f"run-{i}",
        "target_liters": 100,
        "liters": 100,
        "measurement_gap": False,
        "volume_estimated": False,
        "comparison_context": CONTEXT,
        "reason": "target_reached",
        "finished_at": (NOW - timedelta(days=i)).isoformat(),
        **changes,
    }


def test_preview_preserves_unresolved_watering_drying_mowing_fertilizing_dependencies():
    result = _preview(
        [
            _step("water_lawn"),
            _step("wait_until_dry", "water_lawn"),
            _step("mow_lawn", "wait_until_dry"),
            _step("fertilize_lawn", "mow_lawn"),
        ]
    )
    water, dry, mow, fertilizer = result["steps"]
    assert water["not_before"] and mow["candidate_at"]
    assert dry["not_before"] is mow["not_before"] is fertilizer["not_before"] is None
    assert mow["outlook_reason"] == "outlook_prerequisite"
    assert fertilizer["window_hint"] == "autumn"
    assert result["reservation"] is False


@pytest.mark.parametrize(
    "start,end,reason",
    [
        (49, 50, "outlook_outside_horizon"),
        (-3, -1, "outlook_expired"),
        (2, 1, "outlook_no_time"),
    ],
)
def test_invalid_or_outside_preview_window_has_no_promised_time(start, end, reason):
    step = _preview([_step("mow_lawn")], start, end)["steps"][0]
    assert step["outlook_reason"] == reason
    assert step["candidate_at"] is step["not_before"] is None


@pytest.mark.parametrize("month,day", [(3, 28), (10, 24)])
def test_preview_horizon_is_48_elapsed_hours_over_dst(month, day):
    from datetime import datetime

    from custom_components.rasenpflege_assistent.insights import aware_time

    now = datetime(2026, month, day, 12, tzinfo=ZoneInfo("Europe/Berlin"))
    result = _preview([_step("mow_lawn")], now=now)
    assert (
        aware_time(result["horizon_end"]) - aware_time(result["generated_at"])
    ).total_seconds() == 48 * 3600


@pytest.mark.parametrize("missing", [None, "broken", "2026-10-04T12:00:00"])
def test_no_hour_is_invented_for_missing_or_naive_candidate(missing):
    result = care_outlook([_step("water_lawn")], {}, {"at": missing}, None, NOW, "en")
    assert result["steps"][0]["not_before"] is None


def test_blocked_step_and_expired_water_window_do_not_expire_unrelated_drying_hint():
    result = care_outlook(
        [
            _step("wait_until_dry")
            | {"not_before": (NOW + timedelta(hours=5)).isoformat()},
            _step("mow_lawn", availability="blocked"),
        ],
        {"start": NOW.isoformat(), "end": (NOW + timedelta(hours=1)).isoformat()},
        {"end": (NOW - timedelta(hours=1)).isoformat()},
        None,
        NOW,
        "en",
    )
    assert result["steps"][0]["outlook_reason"] == "outlook_candidate"
    assert result["steps"][1]["not_before"] is None


@pytest.mark.parametrize(
    "precipitation,status",
    [
        (0, "review_suitable_sampled"),
        (1, "review_unsuitable_observed"),
        (None, "review_insufficient"),
    ],
)
def test_review_summary_counts_unique_windows_and_keeps_unknown_separate(
    precipitation, status
):
    samples = _samples()
    for row in samples:
        row["precipitation"] = precipitation
    result = review_advice(_advice() * 3, samples, NOW + timedelta(hours=3), "de")
    assert result["summary"]["reviewed_windows"] == 1
    assert result["summary"]["counts"][status] == 1
    assert result["summary"]["accuracy_score"] is None
    assert not result["surface_dry_confirmed"]


@pytest.mark.parametrize(
    "liters,reason,status",
    [
        (105, "target_reached", "target_met"),
        (106, "target_reached", "over_target"),
        (94, "target_reached", "target_short"),
        (50, "manual_stop", "stopped_short"),
    ],
)
def test_quantity_tolerance_and_early_stop_are_distinct(liters, reason, status):
    result = irrigation_comparison(
        [_session(liters=liters, reason=reason)], CONTEXT, NOW, "en"
    )
    assert result["counts"][status] == 1
    assert result["sessions"][0]["difference_liters"] == liters - 100


@pytest.mark.parametrize(
    "changes,count",
    [
        ({"measurement_gap": True}, "measurement_gaps"),
        ({"volume_estimated": True}, "estimated_sessions"),
        ({"comparison_context": "changed"}, "different_context"),
        ({"target_liters": None}, "unknown_sessions"),
        ({"liters": True}, "unknown_sessions"),
        ({"measurement_gap": None}, "unknown_sessions"),
        ({"volume_estimated": None}, "unknown_sessions"),
    ],
)
def test_incomplete_or_incomparable_quantities_do_not_support_deviation(changes, count):
    result = irrigation_comparison([_session(**changes)], CONTEXT, NOW, "de")
    assert result["comparable_sessions"] == 0 and result["counts"][count] == 1
    assert result["median_difference_liters"] is None


def test_repeated_distinct_deviations_are_a_review_hint_and_duplicates_conflicts_are_not():
    rows = [_session(i, liters=110) for i in range(3)]
    result = irrigation_comparison(rows, CONTEXT, NOW, "en")
    assert result["review_recommended"] and not result["device_fault_confirmed"]
    assert not irrigation_comparison([rows[0]] * 3, CONTEXT, NOW, "en")[
        "review_recommended"
    ]
    result = irrigation_comparison(
        [rows[0], {**rows[0], "liters": 90}], CONTEXT, NOW, "en"
    )
    assert (
        result["comparable_sessions"] == 0 and result["counts"]["unknown_sessions"] == 1
    )


def test_comparison_bounds_clocks_and_manual_records_without_mutating_input():
    rows = [_session(i) for i in range(40)] + [
        _session(source="manual", liters=500),
        _session(finished_at=(NOW + timedelta(hours=1)).isoformat()),
    ]
    before = deepcopy(rows)
    result = irrigation_comparison(rows, CONTEXT, NOW, "en")
    assert result["comparable_sessions"] == 20
    assert rows == before
    assert irrigation_comparison(None, CONTEXT, NOW, "en")["comparable_sessions"] == 0


@pytest.mark.parametrize(
    "setting,value",
    [
        ("area", 200),
        ("irrigation_flow", "sensor.new"),
        ("irrigation_valve", "switch.new"),
    ],
)
def test_source_and_area_change_is_not_comparable(setting, value):
    changed = irrigation_context(
        {
            "area": 100,
            "irrigation_valve": "switch.water",
            "irrigation_flow": "sensor.water",
            setting: value,
        },
        "total",
        "L",
    )
    assert (
        irrigation_comparison([_session()], changed, NOW, "en")["counts"][
            "different_context"
        ]
        == 1
    )


async def test_finished_counter_session_persists_comparison_metadata(hass, freezer):
    from tests.test_irrigation import _controller

    freezer.move_to(NOW)
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.move_to(NOW + timedelta(minutes=2))
    hass.states.async_set(
        "sensor.garden_water_liters", "110", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    result = c.diagnostic_attributes()["quantity_comparison"]
    assert result["counts"]["over_target"] == 1
    saved = c.state.as_dict()
    c.state.water_usage = saved["water_usage"]
    assert c.diagnostic_attributes()["quantity_comparison"] == result


async def test_preview_summary_and_comparison_reads_do_not_write_or_command(
    hass, freezer
):
    freezer.move_to(NOW)
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    before = deepcopy(c.state.as_dict())
    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as commands:
        a = c.coordinator.care_outlook_details()
        b = c.coordinator.care_outlook_details()
        c.diagnostic_attributes()
        c.coordinator.insight_diagnostics()
    assert a == b and c.state.as_dict() == before
    commands.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": 42},
        {"comparison_context": None},
        {"finished_at": "broken"},
        {"finished_at": "2026-10-04T09:00:00"},
    ],
)
def test_malformed_optional_comparison_records_are_not_evidence(changes):
    result = irrigation_comparison([_session(**changes)], CONTEXT, NOW, "en")
    assert result["comparable_sessions"] == 0
    assert not result["review_recommended"]


@pytest.mark.parametrize("language", ["de", "en"])
async def test_populated_outlook_comparison_summary_and_soil_cards_render(
    hass, freezer, language
):
    import json
    from pathlib import Path

    import yaml
    from homeassistant.helpers.template import Template

    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    freezer.move_to(NOW + timedelta(hours=3))
    hass.config.language = language
    c = await _live(
        hass,
        soil_moisture_entity="sensor.soil",
        mowing_start_time="00:00:00",
        mowing_end_time="00:00:00",
    )
    hass.states.async_set("sensor.soil", "60")
    c.state.mowing_advice_history = _advice()
    c.state.weather_samples = _samples()
    meter = hass.states.get("sensor.garden_water_liters")
    ctx = irrigation_context(
        c.coordinator.settings, "total", meter.attributes["unit_of_measurement"]
    )
    c.state.water_usage = [
        _session(i, comparison_context=ctx, liters=110) for i in range(3)
    ]
    attrs = LawnSensor(
        c.coordinator, next(row for row in SENSORS if row.key == "care_plan")
    ).extra_state_attributes
    attrs.update(
        {
            "mowing_window_quality": c.coordinator.mowing_plan_details(),
            "quantity_comparison": c.diagnostic_attributes()["quantity_comparison"],
            "model_insights": c.coordinator.insight_diagnostics(),
        }
    )
    json.dumps(attrs, allow_nan=False)
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

    for name in ("care-plan", "diagnostics"):
        visit(
            yaml.safe_load(
                (
                    Path(__file__).parents[1] / f"docs/dashboard/{name}.{language}.yaml"
                ).read_text()
            )
        )
    output = "\n".join(rendered)
    assert attrs["outlook"]["scope_text"] in output
    assert attrs["quantity_comparison"]["reason_text"] in output
    assert attrs["model_insights"]["soil_evidence"]["basis_text"] in output
    assert (
        attrs["mowing_window_quality"]["retrospective"]["summary"]["scope_text"]
        in output
    )
    assert "outlook_candidate" not in output and "comparison_review" not in output


def test_missing_current_meter_semantics_is_unknown_rather_than_a_source_change():
    result = irrigation_comparison([_session()], None, NOW, "en")
    assert result["counts"]["unknown_sessions"] == 1
    assert result["counts"]["different_context"] == 0
    assert result["current_context_known"] is False
