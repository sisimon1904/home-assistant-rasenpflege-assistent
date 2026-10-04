"""Read-only care, weekly evidence and cycle diagnostics for release 3.11.0.

File: tests/test_release_3110.py

Reference totals exercise independent periods, local dates and missing evidence.
HA tests verify live sensor attributes, owned-meter estimates, persistence and
rollback. Neither diagnostic reads nor advisory suggestions command devices.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.everyday import (
    care_priorities,
    cycle_guidance,
    sensor_review,
    weekly_comparison,
)
from custom_components.rasenpflege_assistent.explanations import reason_text
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.mowing import MowingObserver
from tests.test_irrigation import _controller
from tests.test_mowing import NOW as ROBOT_NOW
from tests.test_mowing import _coordinator, _event
from tests.test_release_3100 import NOW, _row


def _history(now=NOW):
    return [
        _row(
            now - timedelta(hours=i),
            modeled=60 if i < 168 else 40,
            rain_mm=0.5 if i < 168 else 0.25,
            et_mm=0.1,
        )
        for i in reversed(range(336))
    ]


def _care():
    return care_priorities(
        watering_status="water_now",
        mower_status="mow_regularly",
        fertilizing=True,
        irrigation_active=False,
        wet_until=None,
        temperature_available=True,
        frost=False,
    )


def test_care_sequence_has_explicit_dependencies():
    result = _care()
    assert [s["action"] for s in result] == [
        "water_lawn",
        "wait_until_dry",
        "mow_lawn",
        "fertilize_lawn",
    ]
    assert [s["after"] for s in result] == [
        None,
        "water_lawn",
        "wait_until_dry",
        "mow_lawn",
    ]


@pytest.mark.parametrize(
    "changes,action",
    [
        ({"temperature_available": False}, "check_inputs"),
        ({"frost": True}, "wait_for_frost_free"),
        ({"irrigation_active": True}, "wait_for_irrigation"),
        ({"watering_status": "wait_for_rain"}, "wait_for_rain"),
    ],
)
def test_care_respects_missing_inputs_frost_active_watering_and_rain(changes, action):
    settings = {
        "watering_status": "water_now",
        "mower_status": "mow_regularly",
        "fertilizing": True,
        "irrigation_active": False,
        "wet_until": None,
        "temperature_available": True,
        "frost": False,
    }
    settings.update(changes)
    result = care_priorities(**settings)
    assert result[0]["action"] == action
    if action in {"check_inputs", "wait_for_frost_free"}:
        assert len(result) == 1


def test_no_care_does_not_invent_an_action():
    settings = {
        "watering_status": "no_watering",
        "mower_status": "keep_off",
        "fertilizing": False,
        "irrigation_active": False,
        "wet_until": None,
        "temperature_available": True,
        "frost": False,
    }
    assert care_priorities(**settings) == [
        {"action": "no_action", "reason": "no_action", "after": None}
    ]


def test_weekly_periods_use_disjoint_evidence_and_do_not_change_it():
    history = _history()
    before = json.dumps(history)
    usage = [
        {"date": NOW.date().isoformat(), "liters": 10},
        {"date": (NOW - timedelta(days=7)).date().isoformat(), "liters": 20},
    ]
    result = weekly_comparison(history, usage, NOW)
    assert result["status"] == "recording_available"
    assert (
        result["current"]["hourly_snapshots"]
        == result["previous"]["hourly_snapshots"]
        == 168
    )
    assert result["current"]["observed_rain_mm"] == 84
    assert result["previous"]["observed_rain_mm"] == 42
    assert result["current"]["estimated_et_mm"] == 16.8
    assert result["moisture_change_percentage_points"] == 20
    assert result["current"]["recorded_liters"] == 10
    assert result["previous"]["recorded_liters"] == 20
    assert json.dumps(history) == before


@pytest.mark.parametrize("kind", ["missing", "gap", "unknown_rain"])
def test_weekly_missing_evidence_never_becomes_full_observed_rain(kind):
    history = _history()
    if kind == "missing":
        history = history[-5:]
    elif kind == "gap":
        history = history[:150] + history[155:]
    else:
        history[-1]["rain_known"] = False
    result = weekly_comparison(history, [], NOW)
    if kind == "gap":
        assert result["previous"]["observed_rain_mm"] is None
    else:
        assert result["current"]["observed_rain_mm"] is None
    if kind != "unknown_rain":
        assert result["status"] == "partial_history"
        assert result["moisture_change_percentage_points"] is None


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 3, 30, 12, tzinfo=ZoneInfo("Europe/Berlin")),
        datetime(2026, 10, 26, 12, tzinfo=ZoneInfo("Europe/Berlin")),
    ],
)
def test_weekly_windows_use_real_168_hours_over_dst(now):
    utc = now.astimezone(timezone.utc)
    result = weekly_comparison(_history(utc), [], now)
    for period in (result["current"], result["previous"]):
        assert datetime.fromisoformat(period["end"]) - datetime.fromisoformat(
            period["start"]
        ) == timedelta(hours=168)
        assert period["hourly_snapshots"] == 168
        assert period["recording_sufficient"]


def test_weekly_volume_keeps_unknown_dates_and_estimates_visible():
    today = NOW.date().isoformat()
    usage = [
        {
            "date": today,
            "liters": 5,
            "measurement_gap": True,
            "allocations": [{"date": today, "liters": 5}],
            "uncertainty_dates": [(NOW - timedelta(days=8)).date().isoformat()],
        },
        {"date": today, "liters": 2, "source": "manual_estimate"},
        {"date": today, "liters": None},
    ]
    result = weekly_comparison(_history(), usage, NOW)
    assert result["current"]["recorded_liters"] == 7
    assert result["current"]["unknown_volume_records"] == 2
    assert result["current"]["estimated_volume_records"] == 1
    assert result["previous"]["unknown_volume_records"] == 1
    assert result["consumption_date_allocation_estimated"]


def test_flat_sensor_requires_independent_reports_and_model_change():
    rows = [
        _row(NOW - timedelta(hours=i * 6), measured=50, modeled=30 + i * 3)
        for i in reversed(range(6))
    ]
    assert sensor_review(rows, True)["reasons"] == ["sensor_flat_review"]
    assert not sensor_review(rows, True)["device_fault_confirmed"]
    for row in rows:
        row["modeled_percent"] = 50
    assert not sensor_review(rows, True)["reasons"]
    for row in rows:
        row["sensor_reported_at"] = rows[0]["sensor_reported_at"]
    assert not sensor_review(rows, True)["reasons"]


def test_repeated_outages_are_hints_and_absent_sensor_is_normal():
    rows = [
        _row(NOW - timedelta(hours=i), measured=None if i % 2 else 50)
        for i in reversed(range(8))
    ]
    assert "sensor_repeated_outages" in sensor_review(rows, True)["reasons"]
    assert sensor_review(rows, False)["status"] == "not_configured"
    assert not sensor_review(rows[:2], True)["reasons"]


def _cycle(**changes):
    settings = {
        "liters": 100,
        "area_m2": 100,
        "flow_l_min": 10,
        "infiltration_mm_h": 10,
        "cycle_minutes": 4,
        "soak_minutes": 5,
        "maximum_minutes": 30,
    }
    settings.update(changes)
    return cycle_guidance(**settings)


def test_cycle_duration_includes_only_intermediate_pauses():
    result = _cycle()
    assert (
        result["active_minutes"],
        result["cycles"],
        result["pause_minutes"],
        result["total_minutes"],
    ) == (10, 3, 10, 20)
    assert result["settings_changed"] is False
    assert _cycle(liters=80)["cycles"] == 2
    assert _cycle(cycle_minutes=0)["pause_minutes"] == 0
    assert (
        "maximum_runtime_before_target" in _cycle(maximum_minutes=19)["review_reasons"]
    )


@pytest.mark.parametrize("flow", [None, 0, -1, float("nan"), float("inf")])
def test_cycle_time_is_unknown_without_valid_flow(flow):
    result = _cycle(flow_l_min=flow)
    assert result["total_minutes"] is None
    assert result["review_reasons"] == ["cycle_flow_unknown"]


def test_fast_application_produces_bounded_manual_suggestions():
    result = _cycle(area_m2=20, infiltration_mm_h=3)
    assert result["application_rate_mm_h"] == 30
    assert result["review_reasons"] == ["cycle_infiltration_review"]
    assert result["suggested_cycle_minutes"] == 2
    assert result["suggested_soak_minutes"] == 30
    assert _cycle(liters=0)["cycles"] is None


async def test_idle_shared_meter_does_not_supply_a_cycle_estimate(hass):
    c = _controller(hass)
    c.coordinator.async_set_updated_data(LawnData(watering_liters=100))
    hass.states.async_set(
        "sensor.garden_water_liters", "20", {"unit_of_measurement": "L/min"}
    )
    assert c.cycle_plan_details()["flow_source"] == "unknown"
    assert c.cycle_plan_details()["total_minutes"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"measurement_gap": True},
        {"undone": True},
        {"active_seconds": 30},
        {"finished_at": "invalid"},
    ],
)
async def test_cycle_recent_complete_measurement_is_required(hass, changes):
    c = _controller(hass, irrigation_cycle_minutes=4, irrigation_soak_minutes=5)
    c.coordinator.async_set_updated_data(LawnData(watering_liters=100))
    c.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "liters": 50,
        "active_seconds": 300,
        **changes,
    }
    result = c.cycle_plan_details()
    assert (result["flow_source"] == "recent_complete_session") is (not changes)
    assert (result["total_minutes"] == 20) is (not changes)


async def test_cycle_running_estimate_uses_remaining_target_and_safety_time(hass):
    c = _controller(hass, max_irrigation_minutes=30)
    c.state.irrigation_session = {
        "started_at": (dt_util.now() - timedelta(minutes=25)).isoformat(),
        "target_liters": 100,
        "liters": 20,
        "measured_flow_l_min": 10,
        "flow_seen": True,
    }
    hass.states.async_set("switch.garden_water", "on")
    result = c.cycle_plan_details()
    assert result["active_minutes"] == 8
    assert result["remaining_runtime_minutes"] == pytest.approx(5, abs=0.1)
    assert "maximum_runtime_before_target" in result["review_reasons"]
    c.state.irrigation_session = None


async def test_robot_pause_evidence_persists_and_undo_restores_it(hass):
    c = _coordinator(hass)
    observer = MowingObserver(c)
    for old, new, minute in [
        ("docked", "mowing", 0),
        ("mowing", "paused", 10),
        ("paused", "mowing", 20),
        ("mowing", "docked", 40),
    ]:
        await observer.async_handle_event(_event(old, new, minute))
    result = observer.diagnostic_attributes()["last_observation"]
    assert result["active_minutes"] == 30
    assert result["inactive_minutes"] == 10
    assert result["interruptions"] == 1
    assert not result["coverage_confirmed"]
    assert c.state.as_dict()["last_robot_session_interruptions"] == 1
    await c.async_undo_last_action()
    assert c.state.last_robot_session_interruptions is None


async def test_failed_robot_write_rolls_back_interruption_metadata(hass):
    c = _coordinator(hass)
    c.state.last_robot_session_interruptions = 2
    c._store.async_save.side_effect = OSError("failure")
    with pytest.raises(HomeAssistantError):
        await c.async_mark_mowed(
            source="robot_estimate",
            active_seconds=1800,
            session_started_at=ROBOT_NOW,
            interruptions=4,
        )
    assert c.state.last_robot_session_interruptions == 2


@pytest.mark.parametrize(
    "start,finish,seconds",
    [
        ("invalid", None, 10),
        ("2026-01-01T00:00:00", "2026-01-01T01:00:00", 10),
        (NOW.isoformat(), NOW.isoformat(), float("nan")),
    ],
)
async def test_optional_corrupt_robot_evidence_does_not_break_diagnostics(
    hass, start, finish, seconds
):
    c = _coordinator(hass)
    c.state.last_robot_session_started_at = start
    c.state.last_robot_session_finished_at = finish
    c.state.last_robot_session_active_seconds = seconds
    json.dumps(MowingObserver(c).diagnostic_attributes(), allow_nan=False)


async def test_new_advisory_attributes_are_json_safe_localized_and_read_only(hass):
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    c = _controller(hass, soil_moisture_entity="sensor.soil")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    c.coordinator.async_set_updated_data(
        LawnData(watering_status="water_now", mower_status="mow_regularly")
    )
    with (
        patch.object(
            type(hass.services), "async_call", new_callable=AsyncMock
        ) as calls,
        patch.object(
            c.coordinator, "_async_forecast", new_callable=AsyncMock
        ) as weather,
    ):
        sensors = {item.key: LawnSensor(c.coordinator, item) for item in SENSORS}
        care = sensors["care_plan"].extra_state_attributes["prioritized_steps"]
        quality = sensors["data_quality"].extra_state_attributes["sensor_review"]
        insights = c.coordinator.insight_diagnostics(include_history=True)
        cycles = c.diagnostic_attributes()["cycle_plan"]
        json.dumps(
            {"care": care, "quality": quality, "insights": insights, "cycles": cycles},
            allow_nan=False,
        )
    calls.assert_not_called()
    weather.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()
    assert care[0]["action_text"] != care[0]["action"]
    assert insights["initialization"]["history_limit"] == 336
    assert insights["initialization"]["history_retention_days"] == 14


@pytest.mark.parametrize("language", ["de", "en", "fr"])
def test_new_explanations_never_fall_back_to_raw_codes(language):
    for code in [
        "care_check_inputs",
        "care_wait_frost",
        "care_wait_dry",
        "sensor_flat_review",
        "sensor_repeated_outages",
        "cycle_flow_unknown",
        "cycle_infiltration_review",
        "robot_observing",
        "robot_old_event_ignored",
    ]:
        assert reason_text(code, language) != code


@pytest.mark.parametrize("kind", ["volume", "rate"])
async def test_live_owned_meter_supports_cycle_plan_for_both_meter_kinds(hass, kind):
    c = _controller(hass)
    c.state.irrigation_session = {
        "started_at": dt_util.now().isoformat(),
        "target_liters": 100,
        "liters": 20,
        "flow_seen": True,
        "meter_kind": kind,
        "meter_rate_l_min": 10 if kind == "rate" else 0,
        "measured_flow_l_min": 10 if kind == "volume" else None,
    }
    hass.states.async_set("switch.garden_water", "on")
    hass.states.async_set(
        "sensor.garden_water_liters",
        "10",
        {
            "unit_of_measurement": "L/min" if kind == "rate" else "L",
        },
    )
    result = c.cycle_plan_details()
    assert result["flow_source"] == "owned_session"
    assert result["active_minutes"] == 8
    hass.states.get("sensor.garden_water_liters").last_reported = (
        dt_util.utcnow() + timedelta(hours=1)
    )
    assert c.cycle_plan_details()["flow_source"] == "unknown"
    c.state.irrigation_session = None


async def test_current_diagnostic_export_includes_advisory_and_robot_evidence(hass):
    from custom_components.rasenpflege_assistent.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    c = _controller(hass)
    c.coordinator.async_set_updated_data(LawnData())
    c.coordinator.config_entry.runtime_data = c.coordinator
    c.coordinator.mowing_observer = MowingObserver(c.coordinator)
    result = await async_get_config_entry_diagnostics(hass, c.coordinator.config_entry)
    json.dumps(result, allow_nan=False)
    assert result["model_insights"]["weekly_comparison"]["status"] == "partial_history"
    assert result["mowing_observation"]["coverage_confirmed"] is False
    assert result["care_priorities"][0]["action"] == "check_inputs"
    assert result["irrigation"]["cycle_plan"]["flow_source"] == "unknown"


@pytest.mark.parametrize("invalid", [float("nan"), -1, "bad", 1.5])
async def test_corrupt_optional_interruption_count_remains_unknown(hass, invalid):
    c = _coordinator(hass)
    c.state.last_robot_session_interruptions = invalid
    result = MowingObserver(c).diagnostic_attributes()
    assert result["last_observation"]["interruptions"] is None
    json.dumps(result, allow_nan=False)
