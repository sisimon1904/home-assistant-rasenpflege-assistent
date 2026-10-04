"""Release 3.10.0 history, advisory, safety and upgrade regressions.

File: tests/test_release_3100.py

Pure reference cases check evidence thresholds and bounded persistence.
HA fixtures exercise live freshness, restart closure, read-only diagnostics
and preservation of older user settings, maintenance and measured consumption.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.insights import (
    append_observation,
    calibration_advice,
    restore_history,
    watering_explanation,
    watering_response,
)
from custom_components.rasenpflege_assistent.irrigation import IrrigationController
from custom_components.rasenpflege_assistent.models import LawnData
from tests.test_coordinator import _coordinator
from tests.test_irrigation import _controller

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


def _row(at=NOW, measured=70.0, modeled=40.0, **changes):
    return {
        "timestamp": at.isoformat(),
        "context": "sensor.soil:0:100:loamy:10",
        "modeled_percent": modeled,
        "measured_percent": measured,
        "sensor_reported_at": at.isoformat() if measured is not None else None,
        "deviation": measured - modeled if measured is not None else None,
        "rain_mm": 0.0,
        "et_mm": 0.1,
        "rain_known": True,
        **changes,
    }


def test_bounded_history_aggregates_hourly_water_terms():
    history = []
    for i in range(24 * 60 * 21 // 30):
        at = NOW - timedelta(days=21) + timedelta(minutes=30 * i)
        history = append_observation(history, _row(at, rain_mm=0.2))
    assert len(history) == 336
    assert history[-1]["rain_mm"] == pytest.approx(0.4)
    assert history[-1]["et_mm"] == pytest.approx(0.2)
    assert restore_history(history, NOW + timedelta(days=15)) == []


@pytest.mark.parametrize("raw", [None, "broken", {}, [None], ["broken"]])
def test_malformed_optional_history_does_not_break_upgrade(raw):
    assert restore_history(raw, NOW) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp": "broken"},
        {"timestamp": "2026-10-04T12:00:00"},
        {"timestamp": (NOW + timedelta(hours=1)).isoformat()},
        {"modeled_percent": float("nan")},
        {"modeled_percent": -1},
        {"modeled_percent": True},
        {"rain_mm": -1},
        {"et_mm": float("inf")},
        {"context": 12},
        {"rain_known": "yes"},
    ],
)
def test_invalid_history_rows_are_rejected(changes):
    assert restore_history([_row(**changes)], NOW) == []


def test_duplicate_refresh_does_not_duplicate_water_and_context_edit_resets_evidence():
    row = _row()
    history = append_observation([row], row)
    assert history == [row]
    changed = _row(NOW + timedelta(hours=1), context="new-calibration")
    assert append_observation(history, changed) == [changed]
    assert row["context"] != changed["context"]


def test_repeated_sensor_report_does_not_prove_persistent_bias():
    history = [
        _row(
            NOW - timedelta(hours=i),
            sensor_reported_at=(NOW - timedelta(days=3)).isoformat(),
        )
        for i in reversed(range(48))
    ]
    result = calibration_advice(history)
    assert result["independent_observations"] == 1
    assert result["status"] == "collecting_data"


@pytest.mark.parametrize(
    "bias,status",
    [
        (-30, "review_recommended"),
        (-19, "no_persistent_disagreement"),
        (19, "no_persistent_disagreement"),
        (20, "review_recommended"),
    ],
)
def test_calibration_uses_independent_day_span_and_signed_median(bias, status):
    history = [
        _row(NOW - timedelta(hours=6 * i), modeled=40, measured=40 + bias)
        for i in reversed(range(6))
    ]
    result = calibration_advice(history)
    assert result["status"] == status
    assert result["median_deviation_percentage_points"] == bias
    assert result["automatic_parameter_changes"] is False


def test_rain_gap_and_saturated_sensor_produce_conservative_advice():
    history = [
        _row(NOW - timedelta(hours=6 * i), measured=100, rain_known=False)
        for i in reversed(range(6))
    ]
    reasons = calibration_advice(history)["reasons"]
    assert "calibration_sensor_at_limits" in reasons
    assert "calibration_check_rain_source" in reasons


@pytest.mark.parametrize(
    "area,efficiency,dose", [(100, 0.85, 15), (25, 0.5, 5), (80, 1, 0)]
)
def test_amount_explanation_separates_gross_liters_from_model_credit(
    area, efficiency, dose
):
    result = watering_explanation(
        capacity_mm=40,
        water_mm=10,
        area_m2=area,
        efficiency=efficiency,
        recommended_mm=dose,
        expected_et_mm=4,
        forecast_rain_mm=None,
    )
    assert result["deficit_to_target_mm"] == 22
    assert result["recommended_liters"] == area * dose
    assert result["estimated_root_zone_credit_mm"] == dose * efficiency
    assert result["amount_basis"] == "gross_applied_water"


@pytest.mark.parametrize(
    "delta,rain,known,status",
    [
        (5, 0, True, "response_observed"),
        (0, 0, True, "review_recommended"),
        (-5, 0, True, "review_recommended"),
        (5, 2, True, "attribution_uncertain"),
        (5, 0, False, "attribution_uncertain"),
    ],
)
def test_watering_response_never_infers_efficiency_or_proves_device_fault(
    delta, rain, known, status
):
    history = [
        _row(NOW - timedelta(hours=1), measured=40),
        _row(NOW, measured=None),
        _row(NOW + timedelta(hours=1), measured=None),
        _row(
            NOW + timedelta(hours=2),
            measured=40 + delta,
            rain_mm=rain,
            rain_known=known,
        ),
    ]
    session = {
        "started_at": NOW.isoformat(),
        "finished_at": (NOW + timedelta(minutes=30)).isoformat(),
        "liters": 50,
        "measurement_gap": False,
    }
    result = watering_response(history, session)
    assert result["status"] == status
    assert result["sensor_change_percentage_points"] == delta
    assert result["efficiency_estimated"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"measurement_gap": True},
        {"undone": True},
        {"liters": None},
        {"liters": float("nan")},
        {"started_at": "broken"},
    ],
)
def test_incomplete_watering_cannot_support_response_advice(changes):
    session = {
        "started_at": NOW.isoformat(),
        "finished_at": NOW.isoformat(),
        "liters": 50,
        **changes,
    }
    assert watering_response([], session)["status"] == "insufficient_observations"


@pytest.mark.parametrize(
    "unit,age,grace,expected",
    [
        ("L/min", 600, 180, "stale"),
        ("L/min", 150, 180, "accepted"),
        ("L/min", 150, 120, "stale"),
        ("L/min", 600, 900, "accepted"),
        ("L", 600, 120, "accepted"),
    ],
)
async def test_flow_freshness_is_identical_in_diagnostics_and_controller(
    hass, unit, age, grace, expected
):
    c = _controller(hass, flow_start_grace_seconds=grace)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": unit}
    )
    hass.states.get("sensor.garden_water_liters").last_reported = (
        dt_util.utcnow() - timedelta(seconds=age)
    )
    assert c.coordinator.input_diagnostics()["irrigation_flow"]["reason"] == expected
    assert c.automatic_conditions()["meter_fresh"] is (expected == "accepted")
    assert c.readiness() == ("meter_stale" if expected == "stale" else "ready")


@pytest.mark.parametrize("missing", [None, "absent", "invalid", 42, "naive", "future"])
async def test_missing_or_corrupt_session_start_is_closed_and_finalized(hass, missing):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True)
    if missing == "absent":
        c.state.irrigation_session.pop("started_at")
    else:
        c.state.irrigation_session["started_at"] = (
            "2026-10-01T12:00:00"
            if missing == "naive"
            else (dt_util.utcnow() + timedelta(days=1)).isoformat()
            if missing == "future"
            else missing
        )
    restored = IrrigationController(hass, c.coordinator)
    await restored.async_initialize()
    assert hass.states.get("switch.garden_water").state == "off"
    assert not restored.active
    assert "started_at" in restored.state.irrigation_last_session["timing_repaired"]
    assert restored.state.irrigation_last_session["measurement_gap"]
    assert await restored.async_shutdown()


@pytest.mark.parametrize("optional_history", [None, "broken", [_row(dt_util.now())]])
async def test_upgrade_preserves_user_options_care_and_consumption(
    hass, optional_history
):
    c = _coordinator(hass, area=123, irrigation_efficiency=0.75)
    today = dt_util.now().date().isoformat()
    stored = {
        "year": dt_util.now().year,
        "sample_date": today,
        "local_day_model": True,
        "configured_initial_gts": 0,
        "soil_water_mm": 12,
        "last_fertilizing": today,
        "last_watering": today,
        "water_usage": [{"date": today, "liters": 55, "source": "irrigation"}],
        "maintenance_history": [
            {"action": "watering", "timestamp": dt_util.now().isoformat()}
        ],
        "model_observations": optional_history,
    }
    with patch.object(c._store, "async_load", AsyncMock(return_value=stored)):
        await c._async_setup()
    assert c.settings["area"] == 123
    assert c.settings["irrigation_efficiency"] == 0.75
    assert c.state.water_usage == stored["water_usage"]
    assert c.state.maintenance_history == stored["maintenance_history"]
    assert c.state.last_fertilizing == today
    assert c.state.model_initialized_at is None
    assert c.state.diagnostic_recording_since is not None
    assert (
        restore_history(c.state.as_dict()["model_observations"], dt_util.now())
        == c.state.model_observations
    )


async def test_insights_and_recheck_reads_are_detached_and_do_not_call_services(hass):
    c = _controller(hass)
    c.coordinator.async_set_updated_data(LawnData())
    c.coordinator.state.model_observations = [_row(dt_util.now())]
    c.state.irrigation_suspended_until = (
        dt_util.now() + timedelta(hours=2)
    ).isoformat()
    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as calls:
        result = c.coordinator.insight_diagnostics(include_history=True)
        check = c.next_check_details()
    calls.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()
    json.dumps({"insights": result, "check": check}, allow_nan=False)
    assert check["local_check_within_seconds"] == 15
    assert check["boundaries"][0]["reason"] == "automation_suspended"
    result["history"][0]["modeled_percent"] = -1
    assert c.state.model_observations[0]["modeled_percent"] == 40


async def test_model_update_persists_pre_correction_history_and_amount_explanation(
    hass,
):
    """Exercise the complete calculation/save rather than only helper construction."""
    c = _controller(hass, soil_moisture_entity="sensor.soil")
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {
            "temperature": 20,
            "humidity": 50,
            "cloud_coverage": 10,
            "wind_speed": 5,
            "wind_speed_unit": "m/s",
        },
    )
    hass.states.async_set("sensor.soil", "80", {"unit_of_measurement": "%"})
    with patch.object(c.coordinator, "_async_forecast", AsyncMock(return_value=[])):
        data = await c.coordinator._async_update_data()
    row = c.state.model_observations[-1]
    assert row["measured_percent"] == 80
    assert row["modeled_percent"] < data.soil_moisture_percent
    assert data.watering_explanation["recommended_liters"] == data.watering_liters
    saved = c.coordinator._store.async_save.call_args.args[0]
    assert saved["model_observations"] == c.state.model_observations
    json.dumps(saved, allow_nan=False)


async def test_sensor_attributes_expose_localized_advice_and_initialization(hass):
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    c = _controller(hass)
    c.coordinator.async_set_updated_data(
        LawnData(watering_explanation={"recommended_liters": 50})
    )
    sensors = {item.key: LawnSensor(c.coordinator, item) for item in SENSORS}
    assert (
        sensors["watering_recommendation"].extra_state_attributes[
            "watering_explanation"
        ]["recommended_liters"]
        == 50
    )
    model = sensors["soil_moisture"].extra_state_attributes["model_insights"]
    assert model["calibration"]["reasons_text"][0] != "calibration_insufficient_history"
    assert (
        "creation_time_known"
        in sensors["data_quality"].extra_state_attributes["model_initialization"]
    )


async def test_new_model_creation_time_survives_reload(hass):
    c = _coordinator(hass)
    with patch.object(c._store, "async_load", AsyncMock(return_value=None)):
        await c._async_setup()
    initial = c.state.model_initialized_at
    assert initial is not None
    stored = c.state.as_dict()
    restored = _coordinator(hass)
    with patch.object(restored._store, "async_load", AsyncMock(return_value=stored)):
        await restored._async_setup()
    assert restored.state.model_initialized_at == initial
    assert (
        restored.state.diagnostic_recording_since == c.state.diagnostic_recording_since
    )


@pytest.mark.parametrize("soil_type", ["sandy", "loamy", "clayey"])
def test_drought_then_rewetting_reference_preserves_water_and_capacity(soil_type):
    from custom_components.rasenpflege_assistent.calculations import (
        soil_capacity,
        update_soil_water_balance,
    )

    capacity = soil_capacity(soil_type, 10)
    water = capacity
    for _ in range(14):
        dry = update_soil_water_balance(
            water_mm=water,
            soil_type=soil_type,
            reference_et_mm=8,
            crop_coefficient=1,
            precipitation_mm=0,
            precipitation_intensity_mm_h=0,
            interval_hours=24,
        )
        assert dry["water_mm"] + dry["actual_et_mm"] == pytest.approx(water, abs=0.002)
        water = dry["water_mm"]
    assert water < capacity * 0.1
    wet = update_soil_water_balance(
        water_mm=water,
        soil_type=soil_type,
        reference_et_mm=0,
        crop_coefficient=1,
        precipitation_mm=0,
        precipitation_intensity_mm_h=0,
        irrigation_mm=capacity * 2,
        interval_hours=1,
    )
    assert wet["water_mm"] == capacity
    assert wet["drainage_mm"] == pytest.approx(capacity + water, abs=0.002)


async def test_next_check_explains_cooldown_without_promising_a_start(hass):
    c = _controller(hass)
    now = dt_util.now()
    c.state.irrigation_retry_after = (now + timedelta(minutes=20)).isoformat()
    c.coordinator._last_calculation_success_at = now.isoformat()
    c.coordinator.async_set_updated_data(LawnData())
    result = c.next_check_details()
    assert result["estimated"]
    assert result["boundaries"][0]["reason"] == "retry_cooldown"
    assert dt_util.parse_datetime(result["model_refresh_at"]) == now + timedelta(
        minutes=30
    )


@pytest.mark.parametrize("invalid", [42, "bad", [1], {"started_at": False}])
def test_response_rejects_corrupt_session_shape(invalid):
    assert watering_response([], invalid)["status"] == "insufficient_observations"


def test_sparse_history_cannot_attribute_sensor_increase_to_watering():
    rows = [
        _row(NOW - timedelta(hours=1), measured=40),
        _row(NOW + timedelta(hours=5), measured=60),
    ]
    session = {
        "started_at": NOW.isoformat(),
        "finished_at": NOW.isoformat(),
        "liters": 50,
    }
    assert watering_response(rows, session)["status"] == "attribution_uncertain"
    assert watering_response(rows, session)["reasons"] == ["response_history_gap"]
