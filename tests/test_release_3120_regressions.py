"""Forecast evidence regressions reproduced before release 3.12.0 fixes.

File: tests/test_release_3120_regressions.py

Malformed provider clocks and duplicate absolute hours must not produce
invented time windows or double-count rainfall. Invalid optional humidity
must remain unknown rather than become apparent dew evidence.
"""

from homeassistant.util import dt as dt_util

from tests.test_irrigation import _controller


async def test_naive_provider_timestamp_is_not_invented_as_utc(hass):
    c = _controller(hass)
    assert (
        c.coordinator._normalize_forecast(
            [
                {
                    "datetime": "2026-10-04T12:00:00",
                    "temperature": 20,
                    "precipitation": 0,
                }
            ],
            "weather.openweathermap",
        )
        == []
    )


async def test_equivalent_provider_hours_do_not_double_count_rain(hass):
    c = _controller(hass)
    result = c.coordinator._normalize_forecast(
        [
            {
                "datetime": "2026-10-04T12:00:00+00:00",
                "temperature": 20,
                "precipitation": 2,
            },
            {
                "datetime": "2026-10-04T14:00:00+02:00",
                "temperature": 20,
                "precipitation": 2,
            },
        ],
        "weather.openweathermap",
    )
    assert len(result) == 1
    assert sum(row["precipitation"] for row in result) == 2


async def test_invalid_forecast_humidity_is_unknown_not_dew_evidence(hass):
    c = _controller(hass)
    result = c.coordinator._normalize_forecast(
        [
            {
                "datetime": "2026-10-04T12:00:00+00:00",
                "temperature": 20,
                "humidity": True,
            }
        ],
        "weather.openweathermap",
    )
    assert result[0]["humidity"] is None


async def test_conflicting_duplicate_hours_do_not_claim_known_rain(hass):
    from custom_components.rasenpflege_assistent.calculations import (
        sum_hourly_forecast_rain,
    )

    c = _controller(hass)
    result = c.coordinator._normalize_forecast(
        [
            {
                "datetime": "2026-10-04T12:00:00+00:00",
                "temperature": 20,
                "precipitation": 2,
            },
            {
                "datetime": "2026-10-04T14:00:00+02:00",
                "temperature": 20,
                "precipitation": 0,
            },
        ],
        "weather.openweathermap",
    )
    assert len(result) == 1
    assert result[0]["forecast_conflict"]
    assert result[0]["precipitation"] is None
    assert (
        sum_hourly_forecast_rain(
            result, 24, dt_util.parse_datetime(result[0]["datetime"])
        )
        is None
    )


async def test_boolean_weather_attributes_do_not_become_numbers(hass):
    c = _controller(hass)
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": True, "humidity": True, "wind_speed": False},
    )
    assert c.coordinator._read_temperature(dt_util.now())[0] is None
    assert c.coordinator._read_weather_conditions(dt_util.now())["humidity"] is None


async def test_boolean_rain_forecast_does_not_become_known_zero(hass):
    c = _controller(hass)
    assert (
        c.coordinator._normalize_forecast(
            [
                {
                    "datetime": "2026-10-04T12:00:00+00:00",
                    "temperature": 20,
                    "precipitation": False,
                }
            ],
            "weather.openweathermap",
        )
        == []
    )


async def test_expired_wet_time_does_not_add_another_care_wait(hass):
    from datetime import timedelta

    from custom_components.rasenpflege_assistent.models import LawnData

    c = _controller(hass)
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    c.coordinator.async_set_updated_data(
        LawnData(
            mower_status="mow_regularly",
            mower_wet_until=(dt_util.now() - timedelta(hours=1)).isoformat(),
        )
    )
    assert "wait_until_dry" not in [
        step["action"] for step in c.coordinator.care_priority_details()
    ]


async def test_naive_saved_wet_timestamp_cannot_crash_mowing_diagnostics(hass):
    from custom_components.rasenpflege_assistent.models import LawnData

    c = _controller(hass)
    c.state.last_watering_at = "2026-10-04T12:00:00"
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": 20, "humidity": 50, "wind_speed": 2},
    )
    c.coordinator.async_set_updated_data(LawnData(mower_status="mow_regularly"))
    result = c.coordinator.mowing_plan_details()
    assert result["start"] is None
    assert result["wet_history_uncertain"]
