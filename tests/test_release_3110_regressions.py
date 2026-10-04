"""Reproduced chronology and evidence regressions for release 3.11.0.

File: tests/test_release_3110_regressions.py

Inputs with future timestamps must not authorize safety decisions. Hourly
evidence must preserve its original pre-correction comparison and normalize
equivalent UTC hours. Replayed robot transitions must not add mowing time.
"""

from datetime import timedelta, timezone

from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.insights import (
    append_observation,
    restore_history,
)
from custom_components.rasenpflege_assistent.mowing import MowingObserver
from tests.test_irrigation import _controller
from tests.test_mowing import NOW, _coordinator, _event
from tests.test_release_3100 import _row


async def test_future_flow_report_does_not_authorize_start(hass):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L/min"}
    )
    hass.states.get("sensor.garden_water_liters").last_reported = (
        dt_util.utcnow() + timedelta(hours=1)
    )
    assert c.readiness() == "meter_stale"
    assert not c.automatic_conditions()["meter_fresh"]


async def test_future_weather_report_does_not_validate_temperature(hass):
    c = _controller(hass)
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    hass.states.get("weather.openweathermap").last_reported = (
        dt_util.utcnow() + timedelta(hours=1)
    )
    assert c.coordinator._read_temperature(dt_util.now())[0] is None
    assert c.coordinator._read_weather_conditions(dt_util.now())["stale"]


async def test_future_rain_report_is_unknown_instead_of_clamped_to_now(hass):
    c = _controller(hass, precipitation_entity="sensor.rain")
    hass.states.async_set("sensor.rain", "2", {"unit_of_measurement": "mm/h"})
    hass.states.get("sensor.rain").last_reported = dt_util.utcnow() + timedelta(hours=1)
    assert c.coordinator._sample_precipitation(dt_util.now())[0] == "unavailable"
    assert c.state.daily_rain_unknown


def test_reused_sensor_report_preserves_first_pre_correction_disagreement():
    first = _row(NOW, modeled=40, measured=70)
    later = _row(
        NOW + timedelta(minutes=30),
        modeled=60,
        measured=70,
        sensor_reported_at=NOW.isoformat(),
    )
    result = append_observation([first], later)
    assert result[-1]["deviation"] == 30
    assert restore_history(result, NOW + timedelta(hours=1))[-1]["deviation"] == 30


def test_equivalent_timezone_hours_are_one_history_bucket():
    first = _row(NOW.replace(minute=10))
    later = _row(
        NOW.replace(minute=30),
        timestamp=NOW.replace(minute=30)
        .astimezone(timezone(timedelta(hours=1)))
        .isoformat(),
    )
    assert len(restore_history([first, later], NOW + timedelta(hours=1))) == 1


async def test_out_of_order_robot_transition_cannot_inflate_active_duration(hass):
    c = _coordinator(hass)
    observer = MowingObserver(c)
    for old, new, minute in [
        ("docked", "mowing", 0),
        ("mowing", "paused", 20),
        ("paused", "mowing", 10),
        ("paused", "docked", 21),
    ]:
        await observer.async_handle_event(_event(old, new, minute))
    assert c.state.last_robot_session_active_seconds == 1200


async def test_future_flow_report_does_not_create_a_completion_estimate(hass):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "0", {"unit_of_measurement": "L/min"}
    )
    await c.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L/min"}
    )
    hass.states.get("sensor.garden_water_liters").last_reported = (
        dt_util.utcnow() + timedelta(hours=1)
    )
    result = c.remaining_time_details()
    assert result["session_eta_reason"] == "meter_stale"
    assert result["session_estimated_end"] is None
    await c.async_stop()
