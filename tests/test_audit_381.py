"""Confirmed defects found during the second 3.8.1 review."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.calculations import (
    sum_hourly_forecast_rain,
)
from tests.test_irrigation import _controller


@pytest.mark.parametrize("action", ["watering", "fertilizing", "mowing", "undo"])
async def test_failed_maintenance_save_restores_state(hass, action):
    controller = _controller(hass)
    coordinator = controller.coordinator
    if action == "undo":
        await coordinator.async_mark_watered(2)
    before = deepcopy(controller.state.as_dict())
    coordinator._store.async_save.side_effect = OSError("disk full")
    methods = {
        "watering": lambda: coordinator.async_mark_watered(2),
        "fertilizing": coordinator.async_mark_fertilized,
        "mowing": coordinator.async_mark_mowed,
        "undo": coordinator.async_undo_last_action,
    }
    with pytest.raises(HomeAssistantError):
        await methods[action]()
    assert controller.state.as_dict() == before


async def test_undo_preserves_physical_water_for_weekly_budget(hass, freezer):
    freezer.move_to("2026-10-02T07:00:00+00:00")
    controller = _controller(hass, irrigation_weekly_limit_liters=100)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=20)
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set(
        "sensor.garden_water_liters", "20", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    before = controller.budget_details()
    assert before["week_liters"] == 20
    await controller.coordinator.async_undo_last_action()
    assert controller.budget_details() == before
    assert controller.state.water_usage[0]["undone"]


@pytest.mark.parametrize(
    "start",
    [
        datetime(2026, 3, 29, tzinfo=ZoneInfo("Europe/Berlin")),
        datetime(2026, 10, 25, tzinfo=ZoneInfo("Europe/Berlin")),
    ],
)
def test_rain_horizon_uses_elapsed_hours_across_dst(start):
    forecast = [
        {
            "datetime": (
                start.astimezone(timezone.utc) + timedelta(hours=hour)
            ).isoformat(),
            "precipitation": 1,
        }
        for hour in range(26)
    ]
    assert sum_hourly_forecast_rain(forecast, 24, start) == 24


async def test_failed_fertilizing_does_not_rollback_concurrent_mowing(hass):
    controller = _controller(hass)
    coordinator = controller.coordinator
    saving = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def save(data):
        nonlocal calls
        calls += 1
        if calls == 1:
            saving.set()
            await release.wait()
            raise OSError("disk full")

    coordinator._store.async_save = AsyncMock(side_effect=save)
    first = asyncio.create_task(coordinator.async_mark_fertilized())
    await saving.wait()
    second = asyncio.create_task(coordinator.async_mark_mowed())
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(HomeAssistantError):
        await first
    await second
    assert controller.state.last_fertilizing is None
    assert controller.state.last_mowing == dt_util.now().date().isoformat()
    assert [e["action"] for e in controller.state.maintenance_history] == ["mowing"]


async def test_valve_closes_before_waiting_for_a_slow_maintenance_write(hass):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    saving = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    async def save(data):
        saving.set()
        await release.wait()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    hass.services.async_register("switch", "turn_off", turn_off)
    maintenance = asyncio.create_task(controller.coordinator.async_mark_fertilized())
    await saving.wait()
    stop = asyncio.create_task(controller.async_stop())
    try:
        await asyncio.wait_for(closed.wait(), timeout=2)
        assert hass.states.get("switch.garden_water").state == "off"
    finally:
        release.set()
        await asyncio.gather(maintenance, stop)


async def test_automatic_resume_never_opens_into_current_rain(hass):
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    await controller.async_start(manual=True, target_liters=100)
    controller.state.irrigation_enabled = True
    controller.state.irrigation_session["source"] = "auto"
    hass.states.async_set("switch.other", "on")
    await controller.async_check()
    assert controller.state.irrigation_session["paused_at"]
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "rainy", {"temperature": 20})
    await controller._async_maybe_resume()
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_last_reason == "rain_detected"


@pytest.mark.parametrize("temperature", [None, float("nan"), float("inf"), "broken"])
async def test_initial_setup_rejects_unusable_weather_temperature(hass, temperature):
    from homeassistant.helpers import entity_registry as er

    from custom_components.rasenpflege_assistent.config_flow import LawnCareConfigFlow

    weather = er.async_get(hass).async_get_or_create(
        "weather", "openweathermap", "bad-temp"
    )
    hass.states.async_set(weather.entity_id, "sunny", {"temperature": temperature})
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    result = await flow.async_step_user(
        {"name": "Lawn", "weather_entity": weather.entity_id, "area": 100}
    )
    assert result["errors"]["weather_entity"] == "weather_data_unavailable"


async def test_reconfigure_cannot_change_inputs_during_owned_irrigation(hass):
    from homeassistant.helpers import entity_registry as er

    from custom_components.rasenpflege_assistent.config_flow import LawnCareConfigFlow

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    entry = controller.coordinator.config_entry
    entry.runtime_data = controller.coordinator
    entry.add_to_hass(hass)
    weather = er.async_get(hass).async_get_or_create(
        "weather", "openweathermap", "new-source"
    )
    hass.states.async_set(weather.entity_id, "sunny", {"temperature": 20})
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    before = dict(entry.data)
    result = await flow.async_step_reconfigure({"weather_entity": weather.entity_id})
    assert result["errors"]["base"] == "irrigation_active"
    assert dict(entry.data) == before
    await controller.async_stop()


async def test_cancelled_maintenance_commit_keeps_disk_and_model_consistent(hass):
    controller = _controller(hass)
    coordinator = controller.coordinator
    saving = asyncio.Event()
    release = asyncio.Event()
    persisted = None

    async def save(data):
        nonlocal persisted
        saving.set()
        await release.wait()
        persisted = deepcopy(data)

    coordinator._store.async_save = AsyncMock(side_effect=save)
    task = asyncio.create_task(coordinator.async_mark_fertilized())
    await saving.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert persisted == controller.state.as_dict()
    assert persisted["last_fertilizing"] is not None
