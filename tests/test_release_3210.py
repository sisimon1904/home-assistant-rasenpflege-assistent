"""v3.21.0 input-driven refresh, cached actions and stale evidence regressions.

File: tests/test_release_3210.py

Real HA state events exercise threshold crossings, failure recovery and unload.
Assert no forecast service calls and an unchanged periodic timer during cached
calculations. WebSocket tests retain administrator and entry scope validation.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.const import DOMAIN
from tests.test_audit_320 import prepare
from tests.test_web_dashboard import loaded_entry, register_commands


@pytest.mark.parametrize("source", ["air", "soil", "weather"])
async def test_state_event_clears_and_restores_frost_using_only_cached_forecasts(
    hass, freezer, source
):
    key = "soil_temperature_entity" if source == "soil" else "temperature_entity"
    entity = "sensor.soil" if source == "soil" else "sensor.air"
    item = prepare(hass, freezer, **({key: entity} if source != "weather" else {}))
    if source == "weather":
        entity = "weather.openweathermap"

    def report(value):
        if source == "weather":
            hass.states.async_set(entity, "sunny", {"temperature": value})
        else:
            hass.states.async_set(entity, str(value), {"unit_of_measurement": "°C"})

    report(-1)
    await item.async_refresh()
    item._async_forecast.reset_mock()
    remove = item.async_add_listener(lambda: None)
    timer = item._unsub_refresh
    item.subscribe_temperature_inputs(item.config_entry)
    try:
        report(9.6)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert item.data.mower_status != "pause_frost"
        assert item._unsub_refresh is timer
        report(-0.04)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert item.data.mower_status == "pause_frost"
        evidence = item.mowing_frost_details()
        assert evidence["active"]
        assert evidence["triggers"][0]["source"] == entity
        assert evidence["triggers"][0]["temperature_c"] == -0.04
        item._async_forecast.assert_not_awaited()
    finally:
        await item.config_entry._async_process_on_unload(hass)
        remove()
        await item.async_shutdown()


async def test_positive_reports_do_not_trigger_extra_calculations(hass, freezer):
    item = prepare(hass, freezer, temperature_entity="sensor.air")
    hass.states.async_set("sensor.air", "9.6", {"unit_of_measurement": "°C"})
    await item.async_refresh()
    item._store.async_save.reset_mock()
    item.subscribe_temperature_inputs(item.config_entry)
    try:
        for value in [9.7, 10, 11, 0.04]:
            hass.states.async_set(
                "sensor.air", str(value), {"unit_of_measurement": "°C"}
            )
            await hass.async_block_till_done(wait_background_tasks=True)
        item._store.async_save.assert_not_awaited()
    finally:
        await item.config_entry._async_process_on_unload(hass)


async def test_changed_input_during_save_is_recalculated_and_unload_detaches(
    hass, freezer
):
    item = prepare(hass, freezer, temperature_entity="sensor.air")
    hass.states.async_set("sensor.air", "-1", {"unit_of_measurement": "°C"})
    await item.async_refresh()
    gate = asyncio.Event()
    entered = asyncio.Event()

    async def slow_save(_data):
        entered.set()
        await gate.wait()

    item._store.async_save.side_effect = slow_save
    item.subscribe_temperature_inputs(item.config_entry)
    hass.states.async_set("sensor.air", "9.6", {"unit_of_measurement": "°C"})
    await entered.wait()
    hass.states.async_set("sensor.air", "-2", {"unit_of_measurement": "°C"})
    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert item.data.current_temperature == -2
    assert item.data.mower_status == "pause_frost"
    assert item._store.async_save.await_count >= 3
    await item.config_entry._async_process_on_unload(hass)
    count = item._store.async_save.await_count
    hass.states.async_set("sensor.air", "10", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert item._store.async_save.await_count == count


async def test_cached_failure_marks_recommendations_stale_and_recovers(hass, freezer):
    item = prepare(hass, freezer)
    await item.async_refresh()
    original = item.update_diagnostics()["calculated_inputs"]
    freezer.tick(timedelta(minutes=1))
    item._store.async_save.side_effect = HomeAssistantError("write failed")
    with pytest.raises(HomeAssistantError):
        await item.async_recalculate_cached()
    details = item.update_diagnostics()
    assert details["recommendations_stale"]
    assert not item.last_update_success
    assert details["calculated_inputs"] == original
    item._store.async_save.side_effect = None
    await item.async_recalculate_cached()
    assert item.last_update_success
    assert not item.update_diagnostics()["recommendations_stale"]


async def test_overdue_calculation_and_manual_cached_refresh(hass, freezer):
    item = prepare(hass, freezer)
    await item.async_refresh()
    item._async_forecast.reset_mock()
    assert not item.update_diagnostics()["recommendations_stale"]
    freezer.tick(timedelta(minutes=33))
    assert item.update_diagnostics()["recommendations_stale"]
    await item.async_recalculate_cached()
    assert not item.update_diagnostics()["recommendations_stale"]
    item._async_forecast.assert_not_awaited()


async def test_unload_cancels_refresh_waiting_for_model_lock(hass, freezer):
    item = prepare(hass, freezer, temperature_entity="sensor.air")
    hass.states.async_set("sensor.air", "-1", {"unit_of_measurement": "°C"})
    await item.async_refresh()
    item.subscribe_temperature_inputs(item.config_entry)
    await item._state_lock.acquire()
    try:
        hass.states.async_set("sensor.air", "10", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
        assert item._input_refresh_task is not None
        await item.config_entry._async_process_on_unload(hass)
    finally:
        item._state_lock.release()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert item._input_refresh_task is None
    assert item.data.mower_status == "pause_frost"


async def test_failed_input_refresh_retries_on_subsequent_report(hass, freezer):
    item = prepare(hass, freezer, temperature_entity="sensor.air")
    hass.states.async_set("sensor.air", "-1", {"unit_of_measurement": "°C"})
    await item.async_refresh()
    item.subscribe_temperature_inputs(item.config_entry)
    try:
        item._store.async_save.side_effect = HomeAssistantError("write failed")
        hass.states.async_set("sensor.air", "10", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done(wait_background_tasks=True)
        assert not item.last_update_success
        assert item.data.mower_status == "pause_frost"
        item._store.async_save.side_effect = None
        hass.states.async_set("sensor.air", "11", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done(wait_background_tasks=True)
        assert item.last_update_success
        assert item.data.mower_status != "pause_frost"
    finally:
        await item.config_entry._async_process_on_unload(hass)


async def test_cached_refresh_does_not_make_stale_forecasts_fresh(hass, freezer):
    item = prepare(hass, freezer)
    await item.async_refresh()
    old = dt_util.now() - timedelta(hours=4)
    item._forecast_updated_at = item._hourly_forecast_updated_at = old
    item._forecast_cache = [{"datetime": dt_util.now().isoformat(), "temperature": 20}]
    item._hourly_forecast_cache = list(item._forecast_cache)
    item._async_forecast.reset_mock()
    await item.async_recalculate_cached()
    assert "forecast_stale" in item.data.data_warnings
    assert item._forecast_updated_at == item._hourly_forecast_updated_at == old
    item._async_forecast.assert_not_awaited()


@pytest.mark.parametrize("extra", [{}, {"refresh_weather": True}])
async def test_recalculate_gateway_validates_empty_payload(hass, hass_ws_client, extra):
    entry = loaded_entry(hass)
    entry.runtime_data.async_recalculate_cached = AsyncMock()
    client = await register_commands(hass, hass_ws_client)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": "recalculate",
            "data": extra,
        }
    )
    result = await client.receive_json()
    assert result["success"] is (not extra)
    assert entry.runtime_data.async_recalculate_cached.await_count == (
        0 if extra else 1
    )


async def test_read_only_user_cannot_recalculate(
    hass, hass_ws_client, hass_read_only_access_token
):
    entry = loaded_entry(hass)
    entry.runtime_data.async_recalculate_cached = AsyncMock()
    client = await register_commands(hass, hass_ws_client, hass_read_only_access_token)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": "recalculate",
            "data": {},
        }
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
    entry.runtime_data.async_recalculate_cached.assert_not_awaited()


async def test_recalculation_failure_is_reported_without_internal_error_text(
    hass, hass_ws_client
):
    entry = loaded_entry(hass)
    entry.runtime_data.async_recalculate_cached = AsyncMock(
        side_effect=RuntimeError("internal private details")
    )
    client = await register_commands(hass, hass_ws_client)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": "recalculate",
            "data": {},
        }
    )
    result = await client.receive_json()
    assert not result["success"]
    assert "internal private details" not in result["error"]["message"]
