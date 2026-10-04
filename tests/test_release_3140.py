"""Weekday schedules, observed duration advice and diagnostic integrity.

File: tests/test_release_3140.py

These tests use absolute UTC durations over real local/DST schedules. Restore
and clock regressions test behavior with malformed persisted data. Suggestions
must exclude stale, incomplete or source-changed observations and remain read-only.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.guidance import (
    duration_context,
    duration_suggestion,
    restore_maintenance_history,
    soil_explanation,
)
from tests.test_mowing import _coordinator
from tests.test_release_390_config import _flow, _payload
from tests.test_release_3120 import NOW, _hour, _live, _window

SETTINGS = {"mowing_mode": "robot", "mowing_entity": "lawn_mower.knoxx"}


def _run(at, minutes=60, **changes):
    detail = {
        "source": "robot_estimate",
        "duration_context": duration_context(SETTINGS),
        "session_started_at": (at - timedelta(minutes=minutes)).isoformat(),
        "recorded_at": at.isoformat(),
        "active_seconds": minutes * 60,
        "interruptions": 0,
        **changes,
    }
    return {
        "action": "mowing",
        "timestamp": at.isoformat(),
        "previous": {},
        "details": detail,
    }


def _runs():
    return [
        _run(NOW - timedelta(days=day), minutes)
        for day, minutes in [(1, 60), (2, 62), (3, 58)]
    ]


def test_duration_suggestion_requires_three_comparable_runs():
    result = duration_suggestion(_runs(), SETTINGS, NOW)
    assert result["suggested_minutes"] == 60
    assert result["sample_count"] == 3
    assert result["coverage_confirmed"] is False
    assert result["automatically_applied"] is False
    assert duration_suggestion(_runs()[:2], SETTINGS, NOW)["suggested_minutes"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "manual"},
        {"duration_context": "other"},
        {"active_seconds": True},
        {"active_seconds": float("inf")},
        {"interruptions": 2},
        {"interruptions": None},
        {"session_started_at": None},
        {"session_started_at": "2026-10-04T08:00:00"},
        {"session_started_at": (NOW + timedelta(days=1)).isoformat()},
        {"session_started_at": (NOW - timedelta(days=100)).isoformat()},
        {"active_seconds": 10},
        {"active_seconds": 4000},
    ],
)
def test_incomplete_or_incompatible_duration_evidence_is_excluded(changes):
    history = _runs()
    history[0]["details"].update(changes)
    assert duration_suggestion(history, SETTINGS, NOW)["suggested_minutes"] is None


def test_duplicate_sessions_and_variable_durations_do_not_invent_confidence():
    assert duration_suggestion([_runs()[0]] * 5, SETTINGS, NOW)["sample_count"] == 1
    history = _runs()
    history[0] = _run(NOW - timedelta(days=1), 120)
    assert (
        duration_suggestion(history, SETTINGS, NOW)["reason"]
        == "duration_suggestion_variable"
    )
    assert (
        duration_suggestion(
            _runs(), {**SETTINGS, "mowing_entity": "sensor.other"}, NOW
        )["suggested_minutes"]
        is None
    )
    assert (
        duration_suggestion(_runs(), {**SETTINGS, "mowing_mode": "manual"}, NOW)[
            "suggested_minutes"
        ]
        is None
    )


def test_weekend_times_and_empty_weekdays():
    # NOW is Sunday 09:00 UTC.
    result = _window(
        weekend_start_time="11:00:00", weekend_end_time="12:00:00", duration_minutes=60
    )
    assert result["start"] == (NOW + timedelta(hours=2)).isoformat()
    assert result["available_minutes"] == 60
    assert _window(weekdays=["0"])["start"] is None
    assert _window(weekdays=[])["reason"] == "mowing_days_disabled"


def test_friday_overnight_window_belongs_to_friday_with_different_saturday_times():
    from datetime import datetime, timezone

    now = datetime(2026, 10, 10, 1, tzinfo=timezone.utc)
    result = _window(
        now=now,
        hourly=[_hour(now + timedelta(hours=i)) for i in range(12)],
        weekdays=["4"],
        start_time="22:00:00",
        end_time="03:00:00",
        weekend_start_time="10:00:00",
        weekend_end_time="12:00:00",
    )
    assert result["start"] == now.isoformat()
    assert result["available_minutes"] == 120


@pytest.mark.parametrize("days", [None, "0", [0], ["7"], [["0"]]])
async def test_bad_weekdays_do_not_save(hass, days):
    flow, entry = _flow(hass, mowing_weekdays=["0"])
    values = await _payload(flow.async_step_mowing)
    values["mowing_weekdays"] = days
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["mowing_weekdays"] == "mowing_weekdays_invalid"
    assert entry.options["mowing_weekdays"] == ["0"]


async def test_weekend_settings_preserve_other_settings(hass):
    flow, _ = _flow(hass, area=123)
    values = await _payload(flow.async_step_mowing)
    values.update(
        mowing_weekdays=["0", "5"],
        mowing_weekend_start_time="10:00:00",
        mowing_weekend_end_time="18:00:00",
    )
    result = await flow.async_step_mowing(values)
    assert result["data"]["area"] == 123
    assert result["data"]["mowing_weekend_start_time"] == "10:00:00"


@pytest.mark.parametrize(
    "raw", [None, 42, {}, [42, {"action": "mowing", "details": None}]]
)
async def test_malformed_restored_history_does_not_break_setup(hass, raw):
    c = _coordinator(hass)
    c._store.async_load = AsyncMock(
        return_value={"maintenance_history": raw, "local_day_model": True}
    )
    await c._async_setup()
    assert c.state.maintenance_history == []


async def test_naive_saved_mowing_clock_cannot_break_recording(hass):
    c = _coordinator(hass)
    c.state.last_mowing_at = "2026-10-01T10:00:00"
    await c.async_mark_mowed(recorded_at=NOW, event_id="new")
    assert c.state.last_mowing_at == NOW.isoformat()


def test_history_restore_preserves_valid_events_and_is_independent():
    raw = _runs() + [
        {
            "action": "watering",
            "timestamp": NOW.isoformat(),
            "details": {},
            "previous": {},
        }
    ]
    result = restore_maintenance_history(raw, NOW)
    assert len(result) == 4
    result[0]["details"]["source"] = "changed"
    assert raw[0]["details"]["source"] == "robot_estimate"


def test_soil_terms_are_signed_and_watering_is_not_double_counted():
    trace = {
        "calculated_at": NOW.isoformat(),
        "initial_water_mm": 20,
        "effective_rain_mm": 2,
        "actual_et_mm": 1,
        "drainage_mm": 0.5,
        "sensor_correction_mm": -0.5,
        "final_water_mm": 20,
    }
    history = [
        {
            "action": "watering",
            "timestamp": NOW.isoformat(),
            "previous": {},
            "details": {"recorded_at": NOW.isoformat(), "applied_mm": 5},
        }
    ]
    result = soil_explanation(trace, history, NOW, "de")
    assert sum(term["amount_mm"] for term in result["terms"]) == 0
    assert result["last_watering_credit"]["model_credit_mm"] == 5
    assert result["final_water_mm"] == 20
    assert "Nicht erneut addieren" in result["last_watering_credit"]["text"]
    assert soil_explanation(None, [], NOW, "en")["terms"] == []


async def test_plan_reads_do_not_track_changes_or_write_storage(hass, freezer):
    freezer.move_to(NOW)
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as calls:
        first = c.coordinator.mowing_plan_details()
        second = c.coordinator.mowing_plan_details()
    assert first["change"] == second["change"]
    assert c.coordinator._previous_mowing_advice is None
    assert first["forecast_age_minutes"] == 0
    calls.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()


async def test_recorded_changes_explain_schedule_then_missing_weather(hass, freezer):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(NOW)
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    c.coordinator._record_mowing_advice(c.coordinator.data, dt_util.now())
    c.coordinator.config_entry.add_to_hass(hass)
    # First available forecast starts at 10:00 after current dew drying.
    hass.config_entries.async_update_entry(
        c.coordinator.config_entry,
        options={
            **c.coordinator.config_entry.options,
            "mowing_start_time": "15:00:00",
            "mowing_end_time": "20:00:00",
        },
    )
    c.coordinator._record_mowing_advice(c.coordinator.data, dt_util.now())
    assert (
        c.coordinator.mowing_plan_details()["change"]["reason"]
        == "mowing_change_schedule"
    )
    c.coordinator._hourly_forecast_cache = []
    c.coordinator._record_mowing_advice(c.coordinator.data, dt_util.now())
    assert (
        c.coordinator.mowing_plan_details()["change"]["reason"] == "mowing_change_data"
    )


def test_suggested_window_includes_short_return_time():
    records = _runs()
    for record in records:
        detail = record["details"]
        begin = dt_util.parse_datetime(detail["session_started_at"])
        detail["session_started_at"] = (begin - timedelta(minutes=5)).isoformat()
        detail["interruptions"] = 1
    result = duration_suggestion(records, SETTINGS, NOW)
    assert result["suggested_minutes"] == 65
    assert result["median_active_minutes"] == 60


def test_conflicting_duration_records_are_not_selected_by_input_order():
    records = _runs()
    changed = _run(NOW - timedelta(days=1), 61)
    assert duration_suggestion(records + [changed], SETTINGS, NOW)["sample_count"] == 2
    assert (
        duration_suggestion([changed] + records, SETTINGS, NOW)["suggested_minutes"]
        is None
    )


async def test_observed_duration_metadata_persists_and_undo_removes_sample(
    hass, freezer
):
    freezer.move_to(NOW)
    c = _coordinator(hass)
    for day, minutes in [(3, 58), (2, 62), (1, 60)]:
        end = NOW - timedelta(days=day)
        await c.async_mark_mowed(
            event_id=f"run{day}",
            recorded_at=end,
            source="robot_estimate",
            active_seconds=minutes * 60,
            session_started_at=end - timedelta(minutes=minutes),
            interruptions=0,
        )
    saved = c.state.as_dict()
    assert (
        duration_suggestion(c.state.maintenance_history, c.settings, NOW)[
            "suggested_minutes"
        ]
        == 60
    )
    restored = _coordinator(hass)
    restored._store.async_load = AsyncMock(return_value=saved)
    await restored._async_setup()
    assert (
        duration_suggestion(restored.state.maintenance_history, restored.settings, NOW)[
            "sample_count"
        ]
        == 3
    )
    await restored.async_undo_last_action()
    assert (
        duration_suggestion(restored.state.maintenance_history, restored.settings, NOW)[
            "suggested_minutes"
        ]
        is None
    )


@pytest.mark.parametrize("language", ["de", "en"])
async def test_new_dashboard_fields_render_with_real_data(hass, freezer, language):
    from pathlib import Path

    import yaml
    from homeassistant.helpers.template import Template

    freezer.move_to(NOW)
    hass.config.language = language
    c = await _live(
        hass, **SETTINGS, mowing_start_time="00:00:00", mowing_end_time="00:00:00"
    )
    c.state.maintenance_history = _runs()
    plan = c.coordinator.mowing_plan_details()
    assert plan["duration_suggestion"]["suggested_minutes"] == 60
    attributes = {
        "mowing_window": plan,
        "mowing_window_quality": plan,
        "model_diagnostics": c.coordinator.model_diagnostics(),
    }

    def visit(value, entity=None):
        if isinstance(value, dict):
            entity = value.get("entity", entity)
            if entity:
                hass.states.async_set(entity, "mow_regularly", attributes)
            for child in value.values():
                visit(child, entity)
        elif isinstance(value, list):
            for child in value:
                visit(child, entity)
        elif isinstance(value, str) and ("{{" in value or "{%" in value):
            Template(value, hass).async_render({"entity": entity}, parse_result=False)

    for name in ("mowing", "care-plan", "diagnostics"):
        visit(
            yaml.safe_load(
                (
                    Path(__file__).parents[1] / f"docs/dashboard/{name}.{language}.yaml"
                ).read_text()
            )
        )


@pytest.mark.parametrize("month,expected", [(3, 120), (10, 240)])
def test_weekend_overnight_window_counts_real_dst_minutes(month, expected):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    now = datetime(
        2026, month, 29 if month == 3 else 25, 1, tzinfo=ZoneInfo("Europe/Berlin")
    )
    utc = now.astimezone(timezone.utc)
    plan = _window(
        now=now,
        hourly=[_hour(utc + timedelta(hours=i)) for i in range(5)],
        weekdays=["5"],
        weekend_start_time="22:00:00",
        weekend_end_time="04:00:00",
    )
    assert plan["available_minutes"] == expected


@pytest.mark.parametrize("value", ["25:00:00", "10:00:00+02:00", 42])
async def test_invalid_weekend_time_returns_field_error(hass, value):
    flow, _ = _flow(hass)
    values = await _payload(flow.async_step_mowing)
    values["mowing_weekend_start_time"] = value
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["mowing_weekend_start_time"] == "mowing_time_invalid"


def test_unhashable_restored_action_is_discarded_without_exception():
    assert (
        restore_maintenance_history(
            [
                {
                    "timestamp": NOW.isoformat(),
                    "action": [],
                    "details": {},
                    "previous": {},
                }
            ],
            NOW,
        )
        == []
    )
