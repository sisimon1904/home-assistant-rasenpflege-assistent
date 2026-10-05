"""Continuous mowing durations, alternatives and quality for release 3.13.0.

File: tests/test_release_3130.py

Exercise real weather gaps and local/DST boundaries rather than constructing
an expected copy of the algorithm. HA fixtures check settings persistence,
localized diagnostics and the absence of device or weather commands.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from tests.test_release_390_config import _flow, _payload
from tests.test_release_3120 import NOW, _hour, _live, _window


def test_short_first_window_is_skipped_for_complete_pass():
    hours = [_hour(NOW + timedelta(hours=i)) for i in range(7)]
    hours[1]["wind_speed"] = 9
    result = _window(hourly=hours, duration_minutes=120)
    assert result["start"] == (NOW + timedelta(hours=2)).isoformat()
    assert result["available_minutes"] == 300
    assert "mowing_window_too_short" in result["blockers"]


def test_alternative_is_next_separate_sufficient_window():
    hours = [_hour(NOW + timedelta(hours=i)) for i in range(7)]
    hours[3]["wind_speed"] = 9
    result = _window(hourly=hours, duration_minutes=180)
    assert result["start"] == NOW.isoformat()
    assert result["alternative"]["start"] == (NOW + timedelta(hours=4)).isoformat()
    assert result["alternative"]["available_minutes"] == 180


def test_forecast_gap_cannot_supply_required_duration():
    result = _window(
        hourly=[_hour(NOW), _hour(NOW + timedelta(hours=2))], duration_minutes=90
    )
    assert result["start"] is None
    assert result["alternative"] is None
    assert result["reason"] == "mowing_window_too_short"
    assert result["quality"] == "insufficient"


def test_schedule_end_limits_duration_to_actual_available_minutes():
    result = _window(end_time="10:30:00", duration_minutes=91)
    assert result["start"] is None
    result = _window(end_time="10:30:00", duration_minutes=90)
    assert result["available_minutes"] == 90


def test_due_time_consumes_part_of_first_hour():
    result = _window(
        hourly=[_hour(NOW)], due_at=NOW + timedelta(minutes=30), duration_minutes=31
    )
    assert result["start"] is None


def test_current_observation_cannot_supply_a_multi_hour_pass():
    result = _window(
        hourly=[],
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "sunny",
        },
        duration_minutes=61,
    )
    assert result["start"] is None


@pytest.mark.parametrize(
    "current",
    [
        {"stale": True},
        {
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "sunny",
        },
    ],
)
def test_same_instant_conflict_cannot_be_overwritten_by_current_observation(current):
    result = _window(hourly=[_hour(NOW), _hour(NOW, precipitation=2)], current=current)
    assert result["start"] is None
    assert "forecast_conflict" in result["missing_inputs"]


def test_quality_of_later_window_not_lowered_by_missing_earlier_humidity():
    result = _window(
        hourly=[_hour(NOW, humidity=None), _hour(NOW + timedelta(hours=1))]
    )
    assert result["quality"] == "estimated"
    assert result["quality_reasons"] == ["mowing_quality_estimated"]
    assert "mowing_dew_unknown" in result["missing_inputs"]


@pytest.mark.parametrize("duration", [0, 1, 240, 1440])
async def test_duration_options_preserve_unrelated_configuration(hass, duration):
    flow, _ = _flow(hass, area=123)
    values = await _payload(flow.async_step_mowing)
    values["mowing_duration_minutes"] = duration
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["area"] == 123
    assert result["data"]["mowing_duration_minutes"] == duration


@pytest.mark.parametrize(
    "duration", [-1, 1441, True, None, "60", float("nan"), float("inf")]
)
async def test_invalid_duration_returns_field_error_without_saving(hass, duration):
    flow, entry = _flow(hass, mowing_duration_minutes=60)
    values = await _payload(flow.async_step_mowing)
    values["mowing_duration_minutes"] = duration
    result = await flow.async_step_mowing(values)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["mowing_duration_minutes"] in {
        "mowing_duration_invalid",
        "invalid_number",
    }
    assert entry.options["mowing_duration_minutes"] == 60


async def test_read_only_localized_quality_and_duration(hass):
    c = await _live(
        hass,
        mowing_start_time="00:00:00",
        mowing_end_time="00:00:00",
        mowing_duration_minutes=120,
    )
    with (
        patch.object(
            type(hass.services), "async_call", new_callable=AsyncMock
        ) as calls,
        patch.object(
            c.coordinator, "_async_forecast", new_callable=AsyncMock
        ) as forecast,
    ):
        result = c.coordinator.mowing_plan_details()
    assert result["required_minutes"] == 120
    assert result["available_minutes"] >= 120
    assert result["quality_text"] != "mowing_quality_estimated"
    calls.assert_not_called()
    forecast.assert_not_called()


async def test_uncertain_wet_history_clears_all_recommendations(hass):
    c = await _live(hass, mowing_start_time="00:00:00", mowing_end_time="00:00:00")
    c.state.last_watering_at = "invalid"
    result = c.coordinator.mowing_plan_details()
    assert result["start"] is None and result["alternative"] is None
    assert result["available_minutes"] is None
    assert result["quality"] == "insufficient"


def test_normalized_conflict_survives_current_observation():
    result = _window(
        hourly=[{"datetime": NOW.isoformat(), "forecast_conflict": True}],
        current={
            "stale": False,
            "temperature": 20,
            "humidity": 50,
            "wind_speed_m_s": 2,
            "condition": "sunny",
        },
    )
    assert result["start"] is None
    assert "forecast_conflict" in result["missing_inputs"]


@pytest.mark.parametrize("month,expected", [(3, None), (10, 240)])
def test_required_real_duration_respects_overnight_dst(month, expected):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    now = datetime(
        2026, month, 29 if month == 3 else 25, 1, tzinfo=ZoneInfo("Europe/Berlin")
    )
    utc = now.astimezone(timezone.utc)
    result = _window(
        now=now,
        hourly=[_hour(utc + timedelta(hours=i)) for i in range(5)],
        start_time="22:00:00",
        end_time="04:00:00",
        duration_minutes=180,
    )
    assert result["available_minutes"] == expected
    assert (result["start"] is None) == (expected is None)


@pytest.mark.parametrize("language", ["de", "en"])
async def test_dashboard_renders_actual_alternative_and_quality(
    hass, freezer, language
):
    from pathlib import Path

    import yaml
    from homeassistant.helpers.template import Template

    freezer.move_to(NOW)
    hass.config.language = language
    c = await _live(
        hass,
        mowing_start_time="00:00:00",
        mowing_end_time="00:00:00",
        mowing_duration_minutes=120,
    )
    c.coordinator._hourly_forecast_cache[3]["wind_speed"] = 9
    plan = c.coordinator.mowing_plan_details()
    assert plan["alternative"] is not None
    assert plan["quality"] == "estimated"
    for name in ("mowing", "care-plan"):
        card = yaml.safe_load(
            (
                Path(__file__).parents[1] / f"docs/dashboard/{name}.{language}.yaml"
            ).read_text()
        )
        if name == "care-plan":
            # Locate the mowing detail card independently of other appended cards.
            card = next(
                item
                for item in card["cards"]
                if "alternative" in item.get("secondary", "")
            )
        entity = card["entity"]
        hass.states.async_set(entity, "mow_regularly", {"mowing_window": plan})
        rendered = Template(card["secondary"], hass).async_render(
            {"entity": entity}, parse_result=False
        )
        assert "120" in rendered
        assert plan["quality_text"] in rendered
        assert ("Ausweichtermin:" if language == "de" else "Alternative:") in rendered
