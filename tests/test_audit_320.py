"""Frost recovery, clock changes and legacy water-source regressions.

File: tests/test_audit_320.py

Exercise real coordinator calculations with HA states. Distinguish recorded
calculation inputs from live diagnostics; never infer a frozen root zone from
rounded display values or discard known water with legacy source metadata.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.rasenpflege_assistent.irrigation import IrrigationController
from custom_components.rasenpflege_assistent.planning import (
    consumption_summary,
    daily_consumption,
)
from tests.test_mowing import NOW, _coordinator


def prepare(hass, freezer, **options):
    """Keep growth eligible so frost and wetness alone control the pause."""
    freezer.move_to(NOW)
    item = _coordinator(hass, **options)
    item.state.daily_temperature_history = [20] * 7
    item.state.soil_water_mm = 30
    item.state.last_mowing = "2026-07-01"
    item._async_forecast = AsyncMock(return_value=[])
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 9.1})
    return item


@pytest.mark.parametrize("temperature", [0.04, -0.04, 0.0])
async def test_frost_uses_unrounded_soil_temperature(hass, freezer, temperature):
    item = prepare(hass, freezer, soil_temperature_entity="sensor.soil")
    hass.states.async_set(
        "sensor.soil", str(temperature), {"unit_of_measurement": "°C"}
    )
    assert item._read_soil_temperature() == temperature
    data = await item._async_update_data()
    item.data = data
    assert (data.mower_status == "pause_frost") == (temperature <= 0)
    assert IrrigationController(hass, item)._frost_detected() == (temperature <= 0)


@pytest.mark.parametrize("wet", [False, True])
async def test_frost_clears_on_next_calculation_without_restart(hass, freezer, wet):
    item = prepare(hass, freezer, temperature_entity="sensor.outdoor")
    hass.states.async_set("sensor.outdoor", "-1", {"unit_of_measurement": "°C"})
    frozen = await item._async_update_data()
    item.data = frozen
    assert frozen.mower_status == "pause_frost"
    freezer.tick(timedelta(minutes=24))
    hass.states.async_set("sensor.outdoor", "9.6", {"unit_of_measurement": "°C"})
    if wet:
        item.state.last_wet_rain_at = dt_util.now().isoformat()
    # Live evidence changes independently of the previously calculated status.
    assert item.input_diagnostics()["temperature_entity"]["normalized_value"] == 9.6
    snapshot = item.update_diagnostics()["calculated_inputs"]
    assert snapshot["air_temperature_c"] == -1
    assert snapshot["mower_status"] == "pause_frost"
    recovered = await item._async_update_data()
    item.data = recovered
    assert recovered.current_temperature == 9.6
    assert recovered.mower_status == ("pause_wet" if wet else "mow_regularly")
    assert item.update_diagnostics()["calculated_inputs"]["air_temperature_c"] == 9.6


@pytest.mark.parametrize("kind", ["daily", "hourly"])
async def test_future_forecast_cache_is_not_treated_as_fresh(hass, freezer, kind):
    from custom_components.rasenpflege_assistent.coordinator import LawnCoordinator

    item = prepare(hass, freezer)
    item._async_forecast = LawnCoordinator._async_forecast.__get__(item)
    if kind == "hourly":
        item._hourly_forecast_updated_at = dt_util.now() + timedelta(hours=1)
        item._hourly_forecast_cache = [{"temperature": -5}]
    else:
        item._forecast_updated_at = dt_util.now() + timedelta(hours=1)
        item._forecast_cache = [{"temperature": -5}]
    with patch.object(
        type(hass.services),
        "async_call",
        AsyncMock(return_value={"weather.openweathermap": {"forecast": []}}),
    ) as request:
        assert await item._async_forecast(kind) == []
        request.assert_awaited_once()


@pytest.mark.parametrize("source", [None, "legacy"])
def test_unknown_ledger_source_remains_visible_as_uncertain(source):
    rows = daily_consumption(
        [{"date": "2026-07-20", "liters": 4, "source": source}],
        date(2026, 7, 20),
        7,
    )
    assert rows[-1]["liters"] == rows[-1]["uncertain"] == 4


def test_empty_legacy_uncertainty_dates_do_not_break_consumption():
    records = [{"date": "2026-06-01", "liters": 4, "uncertainty_dates": None}]
    assert consumption_summary(records, date(2026, 7, 20))["day_liters"] == 0
    rows = daily_consumption(
        records,
        date(2026, 7, 20),
    )
    assert all(row["liters"] == 0 for row in rows)


async def test_scheduled_refresh_clears_frost_despite_live_device_updates(
    hass, freezer
):
    item = prepare(hass, freezer, temperature_entity="sensor.outdoor")
    item.irrigation = IrrigationController(hass, item)
    hass.states.async_set("sensor.outdoor", "-1", {"unit_of_measurement": "°C"})
    await item.async_refresh()
    assert item.data.mower_status == "pause_frost"
    remove = item.async_add_listener(lambda: None)
    try:
        hass.states.async_set("sensor.outdoor", "9.6", {"unit_of_measurement": "°C"})
        # Frequent controller reports must not move the scheduled model timer.
        for _ in range(3):
            freezer.tick(timedelta(minutes=10))
            item.irrigation._publish_session()
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done(wait_background_tasks=True)
        assert item.data.mower_status == "mow_regularly"
        assert item.data.current_temperature == 9.6
    finally:
        remove()
        await item.async_shutdown()


async def test_calculation_evidence_survives_mutation_and_failed_refresh(hass, freezer):
    item = prepare(hass, freezer)
    item.data = await item._async_update_data()
    original = item.update_diagnostics()["calculated_inputs"]
    item.data.mower_status = "pause_wet"
    returned = item.update_diagnostics()["calculated_inputs"]
    returned["air_temperature_c"] = -10
    item._async_forecast = AsyncMock(side_effect=RuntimeError("forecast test"))
    with pytest.raises(RuntimeError):
        await item._async_update_data()
    details = item.update_diagnostics()
    assert details["calculated_inputs"] == original
    assert details["last_error_type"] == "RuntimeError"
