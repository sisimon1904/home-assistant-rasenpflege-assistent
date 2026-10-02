"""Diagnostic export, storage outcomes and sensor correction regressions.

File: tests/test_release_390_diagnostics.py

HA fixtures provide repeatable source states and storage failure injection.
Diagnostic reads must remain local and must not request weather or command
hardware. Exported snapshots must not permit callers to mutate live state.
"""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.storage import VerifiedStore
from tests.test_irrigation import _controller


@pytest.mark.parametrize("configured", [False, True])
async def test_extended_diagnostics_are_serializable_and_read_only(hass, configured):
    c = _controller(
        hass, irrigation_valve="switch.garden_water" if configured else None
    )
    c.coordinator.async_set_updated_data(LawnData())
    c.coordinator.config_entry.runtime_data = c.coordinator
    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as calls:
        result = await async_get_config_entry_diagnostics(
            hass, c.coordinator.config_entry
        )
    calls.assert_not_called()
    c.coordinator._store.async_save.assert_not_called()
    json.dumps(result, allow_nan=False)
    assert set(result) >= {"inputs", "soil_model", "storage", "updates"}
    assert result["soil_model"]["last_balance"] is None
    assert result["soil_model"]["field_validated"] is False
    assert result["storage"]["successful_writes"] == 0


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (1, "in", 25.4),
        (2, "mm/h", 2),
        ("nan", "mm", None),
        (-1, "mm", None),
        (1, "unsupported", None),
    ],
)
async def test_rain_diagnostic_normalization(hass, value, unit, expected):
    c = _controller(hass, precipitation_entity="sensor.rain")
    hass.states.async_set("sensor.rain", str(value), {"unit_of_measurement": unit})
    result = c.coordinator.input_diagnostics()["precipitation_entity"]
    assert result["normalized_value"] == expected
    assert result["reason"] == ("invalid" if expected is None else "accepted")
    assert result["reported_at"] is not None


@pytest.mark.parametrize(
    "state,expected",
    [("0", "accepted"), ("nan", "invalid"), ("unavailable", "unavailable")],
)
async def test_flow_diagnostic_validity(hass, state, expected):
    c = _controller(hass)
    hass.states.async_set(
        "sensor.garden_water_liters", state, {"unit_of_measurement": "L"}
    )
    assert c.coordinator.input_diagnostics()["irrigation_flow"]["reason"] == expected


async def test_weather_diagnostics_keep_raw_and_normalized_units(hass):
    c = _controller(hass)
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {
            "temperature": 68,
            "temperature_unit": "°F",
            "wind_speed": 36,
            "wind_speed_unit": "km/h",
            "humidity": 50,
            "cloud_coverage": 10,
        },
    )
    result = c.coordinator.input_diagnostics()["weather_entity"]
    assert result["raw_attributes"]["wind_speed"] == 36
    assert result["normalized_value"]["wind_speed_m_s"] == 10
    assert result["reason"] == "accepted"


async def test_stale_rain_is_visible_without_sampling_state_changes(hass, freezer):
    c = _controller(hass, precipitation_entity="sensor.rain")
    hass.states.async_set("sensor.rain", "2", {"unit_of_measurement": "mm/h"})
    before = c.state.as_dict()
    freezer.tick(timedelta(hours=3))
    result = c.coordinator.input_diagnostics()["precipitation_entity"]
    assert result["reason"] == "stale"
    assert c.state.as_dict() == before


async def test_sensor_correction_requires_new_report(hass, freezer):
    c = _controller(
        hass, soil_moisture_entity="sensor.soil", soil_sensor_max_age_minutes=1440
    )
    hass.states.async_set("sensor.soil", "50")
    c.coordinator._calibrate_soil_model(dt_util.now(), 40, 50)
    water = c.state.soil_water_mm
    freezer.tick(timedelta(hours=6))
    c.coordinator._calibrate_soil_model(dt_util.now(), 40, 50)
    assert c.state.soil_water_mm == water
    hass.states.async_set("sensor.soil", "51")
    c.coordinator._calibrate_soil_model(dt_util.now(), 40, 51)
    assert c.state.soil_water_mm > water


async def test_last_balance_includes_sensor_correction_and_is_detached(hass, freezer):
    c = _controller(hass, soil_moisture_entity="sensor.soil")
    hass.states.async_set("sensor.soil", "80")
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {
            "temperature": 20,
            "temperature_unit": "°C",
            "humidity": 50,
            "wind_speed": 2,
            "wind_speed_unit": "m/s",
            "cloud_coverage": 20,
        },
    )
    c.coordinator._async_forecast = AsyncMock(return_value=[])
    c.state.last_soil_update_at = (dt_util.now() - timedelta(hours=1)).isoformat()
    data = await c.coordinator._async_update_data()
    result = c.coordinator.model_diagnostics()
    balance = result["last_balance"]
    assert balance["final_water_mm"] == c.state.soil_water_mm
    assert abs(balance["balance_residual_mm"]) <= 0.002
    assert balance["sensor_correction_mm"] > 0
    assert data.soil_model_confidence == "low"
    assert "soil_sensor_model_disagreement" in data.soil_model_confidence_reasons
    balance["final_water_mm"] = -100
    assert c.coordinator.model_diagnostics()["last_balance"]["final_water_mm"] >= 0


@pytest.mark.parametrize("operation", ["save", "verify"])
async def test_storage_failure_health_retains_history_after_recovery(hass, operation):
    store = VerifiedStore(hass, 1, "test390")
    if operation == "save":
        context = patch.object(
            Store, "async_save", side_effect=OSError("private file path")
        )
    else:
        context = patch.object(Store, "async_load", return_value={"old": True})
    with context:
        for _ in range(2):
            with pytest.raises((OSError, HomeAssistantError)):
                await store.async_save({"new": True})
    status = store.diagnostic_status()
    assert status["consecutive_failures"] == 2
    assert status["last_failure_operation"] == operation
    assert not status["pending"]
    assert "private file path" not in json.dumps(status)
    await store.async_save({"new": True})
    recovered = store.diagnostic_status()
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_failure_at"] == status["last_failure_at"]
    assert recovered["last_success_at"] is not None
    status["successful_writes"] = 100
    assert store.diagnostic_status()["successful_writes"] == 1


async def test_storage_pending_status_while_write_is_blocked(hass):
    store = VerifiedStore(hass, 1, "test390pending")
    entered, release = asyncio.Event(), asyncio.Event()
    original = Store.async_save

    async def delayed(self, data):
        entered.set()
        await release.wait()
        await original(self, data)

    with patch.object(Store, "async_save", delayed):
        saving = asyncio.create_task(store.async_save({"value": 1}))
        await entered.wait()
        assert store.diagnostic_status()["pending"]
        release.set()
        await saving
    assert not store.diagnostic_status()["pending"]


@pytest.mark.parametrize("failure", [OSError, HomeAssistantError, ValueError])
async def test_refresh_failure_and_recovery_are_visible(hass, failure):
    c = _controller(hass)
    with (
        patch.object(
            c.coordinator, "_async_calculate_locked", side_effect=failure("fail")
        ),
        pytest.raises(failure),
    ):
        await c.coordinator._async_update_data()
    failed = c.coordinator.update_diagnostics()
    assert failed["last_error_type"] == failure.__name__
    assert failed["last_failure_at"] is not None
    with patch.object(
        c.coordinator, "_async_calculate_locked", return_value=LawnData()
    ):
        await c.coordinator._async_update_data()
    assert c.coordinator.update_diagnostics()["last_success_at"] is not None
    assert (
        c.coordinator.update_diagnostics()["last_failure_at"]
        == failed["last_failure_at"]
    )


@pytest.mark.parametrize("invalid", ["broken", "2026-07-20T12:00:00", 42])
async def test_restored_invalid_session_timing_still_closes_valve(hass, invalid):
    """Malformed durable timing must not prevent closing an owned valve."""
    from custom_components.rasenpflege_assistent.irrigation import IrrigationController

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    controller.state.irrigation_session["started_at"] = invalid
    controller.state.irrigation_session["segment_started_at"] = invalid
    restored = IrrigationController(hass, controller.coordinator)
    await restored.async_initialize()
    assert hass.states.get("switch.garden_water").state == "off"
    assert not restored.active
    assert restored.state.irrigation_last_reason == "interrupted_by_restart"
    assert restored.state.irrigation_last_session["measurement_gap"]
    assert await restored.async_shutdown()
