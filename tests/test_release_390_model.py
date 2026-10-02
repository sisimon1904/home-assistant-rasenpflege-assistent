"""Water conservation, update intervals and explainable model confidence.

File: tests/test_release_390_model.py

Reference scenarios use controlled rain and ET inputs, not live weather.
They verify numerical behavior and input-quality rules; real field accuracy
still requires comparison with local soil measurements.
"""

import math

import pytest

from custom_components.rasenpflege_assistent.calculations import (
    assess_soil_confidence,
    soil_capacity,
    update_soil_water_balance,
)


@pytest.mark.parametrize("soil", ["sandy", "loamy", "clayey"])
@pytest.mark.parametrize("scenario", ["dry", "storm", "irrigation", "mixed"])
def test_fourteen_day_water_conservation(soil, scenario):
    """Every interval accounts for incoming water, losses and final storage."""
    capacity = soil_capacity(soil)
    water = capacity * 0.6
    canopy = 0.0
    for hour in range(14 * 24):
        initial = water
        rain = 18.0 if scenario in {"storm", "mixed"} and hour % 96 == 0 else 0.0
        irrigation = (
            12.0 if scenario in {"irrigation", "mixed"} and hour % 120 == 12 else 0.0
        )
        if rain == 0:
            canopy = 0.0
        result = update_soil_water_balance(
            water_mm=water,
            soil_type=soil,
            precipitation_mm=rain,
            precipitation_intensity_mm_h=rain,
            irrigation_mm=irrigation,
            interval_hours=1,
            reference_et_mm=4 / 24,
            crop_coefficient=0.8,
            interception_available_mm=max(0, 0.35 - canopy),
        )
        canopy += result["interception_mm"]
        water = result["water_mm"]
        accounted = sum(
            result[key]
            for key in (
                "water_mm",
                "interception_mm",
                "runoff_mm",
                "drainage_mm",
                "actual_et_mm",
            )
        )
        assert initial + rain + irrigation == pytest.approx(accounted, abs=0.002)
        assert 0 <= water <= capacity
        assert 0 <= result["water_stress_factor"] <= 1
        assert all(math.isfinite(value) and value >= 0 for value in result.values())


@pytest.mark.parametrize("initial", [2.0, 19.0, 30.0])
@pytest.mark.parametrize("step_minutes", [5, 15, 60])
def test_dry_model_is_consistent_across_update_intervals(initial, step_minutes):
    """The same integrated ET demand must not depend materially on call frequency."""
    reference = update_soil_water_balance(
        water_mm=initial,
        soil_type="loamy",
        precipitation_mm=0,
        precipitation_intensity_mm_h=0,
        interval_hours=24,
        reference_et_mm=8,
        crop_coefficient=0.8,
    )["water_mm"]
    water = initial
    for _ in range(24 * 60 // step_minutes):
        water = update_soil_water_balance(
            water_mm=water,
            soil_type="loamy",
            precipitation_mm=0,
            precipitation_intensity_mm_h=0,
            interval_hours=step_minutes / 60,
            reference_et_mm=8 * step_minutes / 1440,
            crop_coefficient=0.8,
        )["water_mm"]
    assert water == pytest.approx(reference, abs=0.15)


@pytest.mark.parametrize("measured", [None, 50.0])
@pytest.mark.parametrize("problem", ["none", "rain", "stale", "gap", "fallback"])
def test_confidence_preserves_missing_input_reasons(measured, problem):
    result = assess_soil_confidence(
        modeled_percent=50,
        measured_percent=measured,
        rain_known=problem != "rain",
        weather_stale=problem == "stale",
        model_gap_hours=2 if problem == "gap" else 0,
        method="estimated_fallback"
        if problem == "fallback"
        else "penman_monteith_estimated_radiation",
    )
    assert result["level"] == (
        "low" if problem != "none" else "medium" if measured is None else "high"
    )
    assert "solar_radiation_estimated" in result["reasons"] or problem == "fallback"
    if problem != "none":
        assert len(result["reasons"]) >= 1


@pytest.mark.parametrize("deviation", [-20, -19.9, 19.9, 20])
def test_sensor_disagreement_threshold_is_explicit(deviation):
    result = assess_soil_confidence(
        modeled_percent=50,
        measured_percent=50 + deviation,
        rain_known=True,
        weather_stale=False,
        model_gap_hours=0,
        method="hargreaves_samani",
    )
    assert result["sensor_deviation_percentage_points"] == deviation
    assert result["level"] == ("low" if abs(deviation) >= 20 else "high")
    assert ("soil_sensor_model_disagreement" in result["reasons"]) == (
        abs(deviation) >= 20
    )
