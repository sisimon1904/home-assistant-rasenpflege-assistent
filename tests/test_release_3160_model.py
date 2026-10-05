"""Independent dry-down references, storm cases and soil-sensor outages.

File: tests/test_release_3160_model.py

Analytic stressed ET and literal soil-profile references check numerical
policy across depths and time steps. Water conservation does not prove field
accuracy. Lost sensor observations must never force zero moisture.
"""

import math
from datetime import timedelta

import pytest

from custom_components.rasenpflege_assistent.calculations import (
    update_soil_water_balance,
)
from tests.test_irrigation import _controller
from tests.test_release_3120 import NOW

PROFILES = [
    ("sandy", 22, 0.45, 18, 0.25),
    ("loamy", 40, 0.5, 12, 0.35),
    ("clayey", 46, 0.55, 7, 0.45),
]


@pytest.mark.parametrize("soil,base,fraction,rate,interception", PROFILES)
@pytest.mark.parametrize("depth", [5, 10, 20])
@pytest.mark.parametrize("hours", [1, 6, 24])
def test_thirty_day_dry_down_against_independent_exponential_reference(
    soil, base, fraction, rate, interception, depth, hours
):
    capacity = base * depth / 10
    initial = capacity * 0.3
    expected = initial * math.exp(-(30 * 3 * 0.9) / (capacity * fraction))
    water = initial
    for _ in range(30 * 24 // hours):
        result = update_soil_water_balance(
            water_mm=water,
            soil_type=soil,
            root_depth_cm=depth,
            precipitation_mm=0,
            precipitation_intensity_mm_h=0,
            interval_hours=hours,
            reference_et_mm=3 * hours / 24,
            crop_coefficient=0.9,
        )
        assert 0 <= result["water_mm"] <= water
        assert water - result["water_mm"] == pytest.approx(
            result["actual_et_mm"], abs=0.001
        )
        water = result["water_mm"]
    assert water == pytest.approx(expected, abs=0.10)


@pytest.mark.parametrize("soil,base,fraction,rate,interception", PROFILES)
@pytest.mark.parametrize(
    "slope,factor", [("flat", 1), ("gentle", 0.85), ("steep", 0.6)]
)
@pytest.mark.parametrize("compaction,factor2", [("normal", 1), ("compacted", 0.65)])
def test_storm_reference_infiltration_runoff_and_capacity(
    soil, base, fraction, rate, interception, slope, factor, compaction, factor2
):
    incoming = rate * factor * factor2
    capacity = base / 2
    result = update_soil_water_balance(
        water_mm=5,
        soil_type=soil,
        root_depth_cm=5,
        precipitation_mm=60,
        precipitation_intensity_mm_h=60,
        interval_hours=1,
        irrigation_mm=8,
        reference_et_mm=0,
        crop_coefficient=1,
        slope=slope,
        compaction=compaction,
    )
    assert result["effective_rain_mm"] == pytest.approx(incoming, abs=0.001)
    assert result["runoff_mm"] == pytest.approx(60 - interception - incoming, abs=0.001)
    assert result["water_mm"] == pytest.approx(min(capacity, 13 + incoming), abs=0.001)
    assert result["drainage_mm"] == pytest.approx(
        max(0, 13 + incoming - capacity), abs=0.001
    )
    assert sum(
        result[key]
        for key in (
            "water_mm",
            "interception_mm",
            "runoff_mm",
            "drainage_mm",
            "actual_et_mm",
        )
    ) == pytest.approx(73, abs=0.002)


@pytest.mark.parametrize("soil,base,fraction,rate,interception", PROFILES)
def test_repeated_watering_credits_have_known_storage_and_overflow_totals(
    soil, base, fraction, rate, interception
):
    water = 0
    drainage = 0
    for _ in range(20):
        result = update_soil_water_balance(
            water_mm=water,
            soil_type=soil,
            precipitation_mm=0,
            precipitation_intensity_mm_h=0,
            interval_hours=24,
            irrigation_mm=4,
            reference_et_mm=0,
            crop_coefficient=1,
        )
        water = result["water_mm"]
        drainage += result["drainage_mm"]
    assert water == base
    assert water + drainage == 80


@pytest.mark.parametrize(
    "reading", ["unavailable", "unknown", "nan", "inf", "-1", "101"]
)
async def test_soil_sensor_outage_falls_back_without_zeroing_model(
    hass, freezer, reading
):
    freezer.move_to(NOW)
    c = _controller(hass, soil_moisture_entity="sensor.soil")
    c.state.soil_water_mm = 20
    hass.states.async_set("sensor.soil", reading)
    measured, source = c.coordinator._read_soil_moisture()
    c.coordinator._calibrate_soil_model(NOW, 100, measured)
    assert measured is None and source == "model"
    assert c.state.soil_water_mm == 20
    evidence = c.coordinator.insight_diagnostics()["soil_evidence"]
    assert evidence["basis"] == "soil_model_only" and evidence["model_still_used"]
    assert not evidence["field_accuracy_confirmed"]


async def test_sensor_recovery_blends_once_and_reused_report_does_not_accumulate(
    hass, freezer
):
    freezer.move_to(NOW)
    c = _controller(hass, soil_moisture_entity="sensor.soil")
    c.state.soil_water_mm = 10
    hass.states.async_set("sensor.soil", "50")
    c.coordinator._calibrate_soil_model(NOW, 100, 50)
    assert c.state.soil_water_mm == 20
    freezer.move_to(NOW + timedelta(days=1))
    hass.states.async_set("sensor.soil", "unavailable")
    c.coordinator._calibrate_soil_model(NOW + timedelta(days=1), 100, None)
    assert c.state.soil_water_mm == 20
    hass.states.async_set("sensor.soil", "50")
    c.coordinator._calibrate_soil_model(NOW + timedelta(days=1), 100, 50)
    assert c.state.soil_water_mm == 27.5
    freezer.move_to(NOW + timedelta(days=1, hours=2))
    c.coordinator._calibrate_soil_model(NOW + timedelta(days=1, hours=2), 100, 50)
    assert c.state.soil_water_mm == 27.5
    assert (
        c.coordinator.insight_diagnostics()["soil_evidence"]["basis"]
        == "soil_sensor_supported"
    )
