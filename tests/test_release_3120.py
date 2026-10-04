"""Dew estimates, mowing windows, settings and read-only release regressions.

File: tests/test_release_3120.py

Known dew-point references check units and bounds. Time-window tests exercise
real UTC hours over DST, missing evidence, wet holds and configured clocks.
HA fixtures confirm existing entity attributes, localized settings, cache age
and the absence of weather requests, new entities or device commands.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.mowing_plan import dew_risk, mowing_window
from tests.test_irrigation import _controller
from tests.test_release_390_config import _flow, _payload

NOW = datetime(2026, 10, 4, 9, tzinfo=timezone.utc)


def _hour(at, **changes):
    return {
        "datetime": at.isoformat(),
        "temperature": 20,
        "humidity": 50,
        "precipitation": 0,
        "wind_speed": 2,
        **changes,
    }


def _window(**changes):
    values = {
        "now": NOW,
        "hourly": [_hour(NOW + timedelta(hours=i)) for i in range(4)],
        "current": {"stale": True},
        "due_at": None,
        "eligible": True,
        "wet_until": None,
        "irrigation_active": False,
        "soil_frost": False,
        "leaf_wetness": "not_configured",
    }
    values.update(changes)
    return mowing_window(**values)


@pytest.mark.parametrize(
    "temperature,humidity,expected",
    [(20, 50, 9.27), (20, 100, 20), (10, 80, 6.71), (-10, 80, -12.8)],
)
def test_dew_point_reference_values(temperature, humidity, expected):
    result = dew_risk(temperature, humidity, None)
    assert result["dew_point_c"] == pytest.approx(expected, abs=0.05)
    assert result["source"] == "humidity_estimate"
    assert result["surface_dry_confirmed"] is False


@pytest.mark.parametrize(
    "spread,risk",
    [(0, "high"), (2, "high"), (2.01, "moderate"), (4, "moderate"), (4.01, "low")],
)
def test_dew_risk_thresholds_remain_heuristic(spread, risk):
    assert dew_risk(20, None, 20 - spread)["risk"] == risk


@pytest.mark.parametrize(
    "t,rh,td",
    [
        (None, 50, None),
        (True, 50, None),
        (20, True, None),
        (20, 0, None),
        (20, 101, None),
        (20, float("nan"), None),
        (20, None, 21),
        (20, None, float("inf")),
        (-91, 50, None),
    ],
)
def test_invalid_dew_evidence_is_unknown(t, rh, td):
    result = dew_risk(t, rh, td)
    assert result["risk"] == "unknown"
    assert result["dew_point_c"] is None
    json.dumps(result, allow_nan=False)


def test_supplied_dew_point_and_invalid_supplied_value_fallback():
    assert dew_risk(20, 50, 18)["source"] == "weather_dew_point"
    assert dew_risk(20, 50, 25)["source"] == "humidity_estimate"


def test_good_hours_form_one_bounded_window():
    result = _window()
    assert result["start"] == NOW.isoformat()
    assert result["end"] == (NOW + timedelta(hours=4)).isoformat()
    assert result["status"] == "recommended"
    assert not result["surface_dry_confirmed"]


def test_morning_dew_requires_a_known_dry_hour_before_start():
    hours = [
        _hour(NOW, humidity=95),
        _hour(NOW + timedelta(hours=1), humidity=60),
        _hour(NOW + timedelta(hours=2), humidity=50),
    ]
    result = _window(hourly=hours)
    assert result["start"] == (NOW + timedelta(hours=2)).isoformat()
    assert "mowing_dew_risk" in result["blockers"]
    assert "mowing_drying" in result["blockers"]


def test_forecast_gap_cannot_prove_a_drying_hour_or_extend_a_window():
    result = _window(
        hourly=[
            _hour(NOW, humidity=95),
            _hour(NOW + timedelta(hours=2)),
            _hour(NOW + timedelta(hours=4)),
        ]
    )
    assert result["start"] is None
    result = _window(hourly=[_hour(NOW), _hour(NOW + timedelta(hours=3))])
    assert result["end"] == (NOW + timedelta(hours=1)).isoformat()


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"humidity": None}, "mowing_dew_unknown"),
        ({"precipitation": None}, "mowing_rain_unknown"),
        ({"wind_speed": None}, "mowing_wind_unknown"),
        ({"temperature": None}, "mowing_temperature_unknown"),
        ({"temperature": 0}, "mowing_frost"),
        ({"temperature": 28}, "mowing_heat"),
        ({"wind_speed": 9}, "mowing_wind"),
        ({"condition": "fog"}, "mowing_fog"),
    ],
)
def test_incomplete_or_unsafe_forecast_does_not_recommend_start(changes, reason):
    result = _window(hourly=[_hour(NOW, **changes)])
    assert result["start"] is None
    assert reason in result["blockers"]
    if reason.endswith("_unknown"):
        assert reason in result["missing_inputs"]


def test_rain_cannot_be_followed_by_same_day_mowing():
    hours = [_hour(NOW, precipitation=1)] + [
        _hour(NOW + timedelta(hours=i)) for i in range(1, 28)
    ]
    result = _window(hourly=hours)
    assert datetime.fromisoformat(result["start"]).date() > NOW.date()
    assert "mowing_rain" in result["blockers"]


def test_due_time_and_wet_hold_are_both_respected():
    result = _window(
        due_at=NOW + timedelta(hours=1), wet_until=NOW + timedelta(hours=2, minutes=30)
    )
    assert result["start"] == (NOW + timedelta(hours=2, minutes=30)).isoformat()


@pytest.mark.parametrize(
    "changes", [{"eligible": False}, {"irrigation_active": True}, {"soil_frost": True}]
)
def test_interlocks_do_not_advertise_executable_future_start(changes):
    result = _window(**changes)
    assert result["status"] == "blocked"
    assert result["start"] is None


def test_configured_start_and_end_clip_inside_forecast_hour():
    result = _window(start_time="09:30:00", end_time="10:15:00")
    assert result["start"] == NOW.replace(minute=30).isoformat()
    assert result["end"] == NOW.replace(hour=10, minute=15).isoformat()


def test_dry_leaf_reading_overrides_only_current_dew():
    current = {
        "stale": False,
        "temperature": 20,
        "humidity": 95,
        "wind_speed_m_s": 2,
        "condition": "sunny",
    }
    result = _window(current=current, leaf_wetness="dry", hourly=[])
    assert result["start"] == NOW.isoformat()
    assert result["current_dew"]["risk"] == "high"
    result = _window(
        current={**current, "condition": "rainy"}, leaf_wetness="dry", hourly=[]
    )
    assert result["start"] is None


def test_current_rain_replaces_overlapping_dry_forecast():
    now = NOW + timedelta(minutes=30)
    result = _window(
        now=now,
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "rainy",
        },
    )
    assert result["start"] is None


def test_current_weather_window_ends_before_next_forecast_rain():
    now = NOW + timedelta(minutes=30)
    result = _window(
        now=now,
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "sunny",
        },
        hourly=[_hour(NOW + timedelta(hours=1), precipitation=1)],
    )
    assert result["start"] == now.isoformat()
    assert result["end"] == (NOW + timedelta(hours=1)).isoformat()


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 3, 29, 1, tzinfo=ZoneInfo("Europe/Berlin")),
        datetime(2026, 10, 25, 1, tzinfo=ZoneInfo("Europe/Berlin")),
    ],
)
def test_overnight_mowing_window_preserves_real_hours_over_dst(now):
    utc = now.astimezone(timezone.utc)
    result = _window(
        now=now,
        hourly=[_hour(utc + timedelta(hours=i)) for i in range(5)],
        start_time="22:00:00",
        end_time="04:00:00",
    )
    start, end = (
        datetime.fromisoformat(result[key]).astimezone(timezone.utc)
        for key in ("start", "end")
    )
    assert start == utc
    assert end - start == timedelta(hours=2 if now.month == 3 else 4)


def test_no_forecast_does_not_extrapolate_current_humidity_into_tomorrow():
    result = _window(
        hourly=[],
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "sunny",
        },
        due_at=NOW + timedelta(days=1),
    )
    assert result["start"] is None


async def _live(hass, **options):
    c = _controller(hass, **options)
    now = dt_util.now()
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": 20, "humidity": 95, "wind_speed": 2},
    )
    c.coordinator._hourly_forecast_cache = [
        _hour(now + timedelta(hours=i)) for i in range(1, 8)
    ]
    c.coordinator._hourly_forecast_updated_at = now
    c.coordinator.async_set_updated_data(LawnData(mower_status="mow_regularly"))
    return c


async def test_new_plan_is_localized_json_safe_and_read_only(hass):
    from custom_components.rasenpflege_assistent.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    c.coordinator.config_entry.runtime_data = c.coordinator
    with (
        patch.object(
            type(hass.services), "async_call", new_callable=AsyncMock
        ) as calls,
        patch.object(
            c.coordinator, "_async_forecast", new_callable=AsyncMock
        ) as forecast,
    ):
        entities = {desc.key: LawnSensor(c.coordinator, desc) for desc in SENSORS}
        plan = entities["mower_status"].extra_state_attributes["mowing_window"]
        assert entities["care_plan"].extra_state_attributes["mowing_window"]["start"]
        assert (
            entities["data_quality"].extra_state_attributes["mowing_window_quality"][
                "current_dew"
            ]["risk"]
            == "high"
        )
        json.dumps(
            await async_get_config_entry_diagnostics(hass, c.coordinator.config_entry),
            allow_nan=False,
        )
    calls.assert_not_called()
    forecast.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()
    assert plan["reason_text"] != plan["reason"]
    assert plan["current_dew_risk_text"] != "dew_risk_high"
    assert "mowing_window" not in entities


@pytest.mark.parametrize("age", [timedelta(hours=4), timedelta(hours=-1)])
async def test_stale_or_future_cached_forecast_does_not_supply_a_window(hass, age):
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    c.coordinator._hourly_forecast_updated_at = dt_util.now() - age
    hass.states.get(
        "weather.openweathermap"
    ).last_reported = c.coordinator._hourly_forecast_updated_at
    result = c.coordinator.mowing_plan_details()
    assert result["start"] is None
    assert result["forecast_stale"]


async def test_zero_soil_temperature_blocks_the_window(hass):
    c = await _live(hass, soil_temperature_entity="sensor.soil_temp")
    hass.states.async_set("sensor.soil_temp", "0", {"unit_of_measurement": "°C"})
    assert c.coordinator.mowing_plan_details()["reason"] == "mowing_frost"


async def test_date_only_due_time_stays_on_local_calendar_day(hass):
    previous_zone = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Berlin"))
    try:
        c = await _live(hass)
        tomorrow = dt_util.now().date() + timedelta(days=1)
        c.coordinator.data.next_mowing_date = tomorrow
        result = c.coordinator.mowing_plan_details()
        due = datetime.fromisoformat(result["earliest_due_at"])
        assert (
            due.date() == tomorrow
            and due.hour == 0
            and due.utcoffset() == timedelta(hours=2)
        )
    finally:
        dt_util.set_default_time_zone(previous_zone)


async def test_mowing_time_options_preserve_other_settings(hass):
    flow, _entry = _flow(
        hass, area=123, mowing_start_time="10:00:00", mowing_end_time="19:00:00"
    )
    values = await _payload(flow.async_step_mowing)
    values.update(mowing_start_time="09:30:00", mowing_end_time="18:00:00")
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["mowing_start_time"] == "09:30:00"
    assert result["data"]["area"] == 123


@pytest.mark.parametrize("value", ["invalid", "25:00:00", "10:00:00+02:00", 42])
async def test_bad_mowing_time_returns_field_error_and_preserves_options(hass, value):
    flow, entry = _flow(hass, mowing_start_time="10:00:00")
    values = await _payload(flow.async_step_mowing)
    values["mowing_start_time"] = value
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["mowing_start_time"] == "mowing_time_invalid"
    assert entry.options["mowing_start_time"] == "10:00:00"


@pytest.mark.parametrize(
    "first,active,cycles,pauses", [(1, 6, 3, 10), (0, 6, 2, 10), (4, 8, 2, 5)]
)
def test_cycle_remaining_phase_changes_pause_count(first, active, cycles, pauses):
    from custom_components.rasenpflege_assistent.everyday import cycle_guidance

    result = cycle_guidance(
        liters=active * 10,
        area_m2=100,
        flow_l_min=10,
        infiltration_mm_h=10,
        cycle_minutes=4,
        soak_minutes=5,
        maximum_minutes=60,
        first_cycle_remaining_minutes=first,
    )
    assert result["cycles"] == cycles
    assert result["pause_minutes"] == pauses
    assert result["total_minutes"] == active + pauses


def test_cycle_current_soak_and_manual_minimum_are_included():
    from custom_components.rasenpflege_assistent.everyday import cycle_guidance

    result = cycle_guidance(
        liters=0,
        area_m2=100,
        flow_l_min=10,
        infiltration_mm_h=10,
        cycle_minutes=4,
        soak_minutes=5,
        maximum_minutes=60,
        current_soak_remaining_minutes=2,
        minimum_active_minutes=6,
    )
    assert result["active_minutes"] == 6
    assert result["pause_minutes"] == 7
    assert result["total_minutes"] == 13


async def test_shared_valve_pause_leaves_cycle_total_unknown(hass):
    c = _controller(hass)
    c.state.irrigation_session = {
        "started_at": dt_util.now().isoformat(),
        "target_liters": 100,
        "liters": 10,
        "paused_at": dt_util.now().isoformat(),
        "pause_reason": "other_valve_open",
    }
    c.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "liters": 50,
        "active_seconds": 300,
    }
    result = c.cycle_plan_details()
    assert result["total_minutes"] is None
    assert result["resume_time_unknown"]
    assert result["active_minutes"] == 9
    c.state.irrigation_session = None


def test_weekly_differences_require_matching_evidence_quality():
    from custom_components.rasenpflege_assistent.everyday import weekly_comparison
    from tests.test_release_3110 import _history

    result = weekly_comparison(_history(NOW), [], NOW)
    assert result["changes"]["observed_rain_mm"] == 42
    assert result["changes"]["estimated_et_mm"] == 0
    assert result["changes"]["recorded_liters"] == 0
    result = weekly_comparison(
        [], [{"date": NOW.date().isoformat(), "liters": None}], NOW
    )
    assert result["changes"]["observed_rain_mm"] is None
    assert result["changes"]["estimated_et_mm"] is None
    assert result["changes"]["recorded_liters"] is None


async def test_care_mowing_step_exposes_weather_time_or_blocker(hass):
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    mowing = next(
        step
        for step in c.coordinator.care_priority_details()
        if step["action"] == "mow_lawn"
    )
    assert mowing["availability"] == "later" and mowing["not_before"]
    c.coordinator._hourly_forecast_cache = []
    mowing = next(
        step
        for step in c.coordinator.care_priority_details()
        if step["action"] == "mow_lawn"
    )
    assert mowing["availability"] == "blocked" and mowing["blocker_text"]


async def test_live_manual_minimum_uses_owned_active_segment_clock(hass):
    c = _controller(hass, min_irrigation_minutes=10, irrigation_cycle_minutes=0)
    now = dt_util.now()
    c.state.irrigation_session = {
        "started_at": (now - timedelta(minutes=8)).isoformat(),
        "segment_started_at": (now - timedelta(minutes=3)).isoformat(),
        "target_liters": 20,
        "liters": 20,
        "active_seconds": 300,
        "source": "manual",
        "flow_seen": True,
        "measured_flow_l_min": 10,
    }
    hass.states.async_set("switch.garden_water", "on")
    result = c.cycle_plan_details()
    assert result["active_minutes"] == pytest.approx(2, abs=0.1)
    c.state.irrigation_session["explicit_target"] = True
    assert c.cycle_plan_details()["active_minutes"] is None
    c.state.irrigation_session = None


@pytest.mark.parametrize("condition", [[], {}, 42])
def test_optional_malformed_condition_cannot_break_diagnostics(condition):
    result = _window(hourly=[_hour(NOW, condition=condition)])
    json.dumps(result, allow_nan=False)
    assert result["status"] == "recommended"


async def test_forecast_conflict_keeps_automatic_confidence_low_even_with_daily_fallback(
    hass,
):
    c = _controller(hass)
    now = dt_util.now()
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": 20, "humidity": 50, "wind_speed": 2},
    )
    conflict = {
        "datetime": now.isoformat(),
        "forecast_conflict": True,
        "temperature": None,
        "precipitation": None,
    }
    c.coordinator._forecast_updated_at = c.coordinator._hourly_forecast_updated_at = now
    with patch.object(
        c.coordinator,
        "_async_forecast",
        AsyncMock(
            side_effect=[[_hour(now)], [conflict, _hour(now + timedelta(hours=1))]]
        ),
    ):
        data = await c.coordinator._async_update_data()
    assert data.watering_confidence == "low"
    assert "forecast_conflict" in data.data_warnings
    c.coordinator.async_set_updated_data(data)
    assert not c.automatic_conditions()["confidence_sufficient"]


@pytest.mark.parametrize("end", ["09:15:30", "09:59:30"])
def test_second_valued_policy_end_is_exact(end):
    result = _window(end_time=end)
    assert datetime.fromisoformat(result["end"]).time().isoformat() == end


def test_fresh_dry_leaf_cannot_override_fog_or_missing_wind():
    result = _window(
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "condition": "fog",
            "wind_speed_m_s": None,
        },
        leaf_wetness="dry",
        hourly=[],
    )
    assert result["start"] is None and "mowing_fog" in result["blockers"]


def test_rain_during_frost_still_requires_wet_hold_after_warming():
    hours = [_hour(NOW, temperature=0, precipitation=1)] + [
        _hour(NOW + timedelta(hours=i)) for i in range(1, 28)
    ]
    result = _window(hourly=hours)
    assert datetime.fromisoformat(result["start"]).date() > NOW.date()


def test_exceptional_weather_is_unknown_not_a_good_mowing_slot():
    result = _window(hourly=[_hour(NOW, condition="exceptional")])
    assert (
        result["start"] is None and "mowing_weather_unknown" in result["missing_inputs"]
    )


@pytest.mark.parametrize("language", ["de", "en"])
async def test_populated_mowing_and_care_dashboards_render_actual_window(
    hass, language
):
    from pathlib import Path

    import yaml
    from homeassistant.helpers.template import Template

    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    plan = c.coordinator.mowing_plan_details()
    assert plan["start"] and plan["end"]
    attributes = {
        "mowing_window": plan,
        "mowing_window_quality": plan,
        "prioritized_steps": c.coordinator.care_priority_details(),
    }

    def visit(value, entity=None):
        if isinstance(value, dict):
            entity = value.get("entity", entity)
            if entity:
                hass.states.async_set(entity, "mow_regularly", attributes)
            for item in value.values():
                visit(item, entity)
        elif isinstance(value, list):
            for item in value:
                visit(item, entity)
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
