"""Safety and time-accounting regressions for version 3.8.5."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import real_monotonic
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.calculations import (
    recommended_watering_window,
)
from tests.test_irrigation import _automatic_ready, _controller


@pytest.fixture(autouse=True)
async def real_loop_clock(monkeypatch):
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)


@pytest.mark.parametrize("blocked", ["controller", "model"])
async def test_disabling_auto_closes_before_waiting_for_storage(hass, blocked):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    await controller.async_start(manual=False)
    saving, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def save(data):
        saving.set()
        await release.wait()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    hass.services.async_register("switch", "turn_off", turn_off)
    checking = None
    if blocked == "controller":
        checking = asyncio.create_task(controller.async_check())
        await saving.wait()
    else:
        await controller.coordinator._state_lock.acquire()
    disabling = asyncio.create_task(controller.async_set_auto_enabled(False))
    try:
        await asyncio.wait_for(closed.wait(), 1)
    finally:
        if blocked == "model":
            controller.coordinator._state_lock.release()
        release.set()
        await asyncio.gather(disabling, *([checking] if checking else []))
    assert not controller.active
    assert not controller.state.irrigation_enabled


async def test_expired_late_open_guard_does_not_delay_active_safety_event(hass):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    controller._recent_owned_until = dt_util.utcnow() - timedelta(seconds=1)
    controller._recent_owned_valve_id = "switch.garden_water"
    closed = asyncio.Event()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.coordinator._state_lock.acquire()
    hass.states.async_set("lawn_mower.garden", "mowing")
    handling = asyncio.create_task(controller._async_input_changed(None))
    try:
        await asyncio.wait_for(closed.wait(), 1)
    finally:
        controller.coordinator._state_lock.release()
        await handling
    assert not controller.active


@pytest.mark.parametrize("change", ["expired", "demand"])
async def test_delayed_auto_start_rechecks_forecast_window_and_demand(
    hass, freezer, change
):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    changed = False

    async def save(data):
        nonlocal changed
        if changed:
            return
        changed = True
        if change == "expired":
            freezer.tick(timedelta(minutes=35))
        else:
            controller.coordinator.data.watering_recommended = False
            controller.coordinator.data.watering_status = "not_due"

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=False)
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active


@pytest.mark.parametrize("season", ["spring", "autumn"])
def test_forecast_window_has_one_elapsed_hour_across_dst(season):
    zone = ZoneInfo("Europe/Berlin")
    if season == "spring":
        start = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)
        now = datetime(2026, 3, 29, 3, tzinfo=zone)
    else:
        start = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
        now = datetime(2026, 10, 25, 2, 15, tzinfo=zone, fold=1)
    result = recommended_watering_window(
        [
            {
                "datetime": start.isoformat(),
                "temperature": 20,
                "wind_speed": 1,
                "precipitation": 0,
            }
        ],
        now,
    )
    assert result["start"] is not None
    first = datetime.fromisoformat(result["start"])
    last = datetime.fromisoformat(result["end"])
    assert (last - first).total_seconds() == 3600
    assert first <= now < last


@pytest.mark.parametrize("value,unit", [("-91", "°C"), ("71", "°C"), ("212", "°F")])
def test_implausible_soil_temperature_is_rejected(hass, value, unit):
    controller = _controller(hass, soil_temperature_entity="sensor.soil_temperature")
    hass.states.async_set(
        "sensor.soil_temperature", value, {"unit_of_measurement": unit}
    )
    assert controller.coordinator._read_soil_temperature() is None
    assert (
        controller.coordinator.input_diagnostics()["soil_temperature_entity"]["reason"]
        == "invalid"
    )


async def test_physical_watering_date_survives_completion_wait_across_midnight(
    hass, freezer
):
    previous_zone = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Berlin"))
    try:
        freezer.move_to("2026-10-02T21:59:00+00:00")
        controller = _controller(hass)
        hass.states.async_set("lawn_mower.garden", "docked")
        _automatic_ready(controller)
        await controller.async_start(manual=False)
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(
            "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
        )
        closed = asyncio.Event()

        async def turn_off(call):
            hass.states.async_set("switch.garden_water", "off")
            closed.set()

        hass.services.async_register("switch", "turn_off", turn_off)
        await controller.coordinator._state_lock.acquire()
        stopping = asyncio.create_task(controller.async_stop())
        try:
            await asyncio.wait_for(closed.wait(), 1)
            ended_at = dt_util.now()
            freezer.tick(timedelta(minutes=3))
        finally:
            controller.coordinator._state_lock.release()
            await stopping
        assert controller.state.last_watering == "2026-10-02"
        assert controller.state.irrigation_last_auto_date == "2026-10-02"
        assert dt_util.parse_datetime(controller.state.last_watering_at) == ended_at
        assert controller.state.soil_water_mm == pytest.approx(10.0425)
    finally:
        dt_util.set_default_time_zone(previous_zone)


@pytest.mark.parametrize(
    "change", ["missing_data", "stale", "rain", "confidence", "future_window"]
)
async def test_delayed_auto_start_rejects_changed_eligibility(hass, change):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    changed = False

    async def save(data):
        nonlocal changed
        if changed:
            return
        changed = True
        current = controller.coordinator.data
        if change == "missing_data":
            controller.coordinator.data = None
        elif change == "stale":
            current.forecast_stale = True
        elif change == "rain":
            current.observed_rain_today_mm = None
        elif change == "confidence":
            current.soil_model_confidence = "low"
        else:
            current.watering_window_start = (
                dt_util.now() + timedelta(minutes=10)
            ).isoformat()

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=False)
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active


async def test_disabling_auto_with_failed_storage_still_closes_owned_valve(hass):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    await controller.async_start(manual=False)
    controller.coordinator._store.async_save = AsyncMock(
        side_effect=OSError("disk failure")
    )
    with pytest.raises(ServiceValidationError):
        await controller.async_set_auto_enabled(False)
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.state.irrigation_enabled
    controller.coordinator._store.async_save = AsyncMock()
    await controller.async_check()
    assert not controller.active
    assert not controller.state.irrigation_enabled


async def test_disabling_auto_preserves_owned_manual_session(hass):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    controller.state.irrigation_enabled = True
    await controller.async_start(manual=True, target_liters=100)
    await controller.async_set_auto_enabled(False)
    assert hass.states.get("switch.garden_water").state == "on"
    assert controller.active
    assert not controller.state.irrigation_enabled
    await controller.async_stop()
