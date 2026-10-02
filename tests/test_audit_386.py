"""Safety and schedule regressions for version 3.8.6.

File: tests/test_audit_386.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import real_monotonic
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from tests.test_irrigation import _automatic_ready, _controller


@pytest.fixture(autouse=True)
async def real_loop_clock(monkeypatch):
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)


@pytest.mark.parametrize("blocked", ["controller", "model"])
async def test_suspension_closes_before_waiting_for_storage(hass, blocked):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(c)
    await c.async_start(manual=False)
    saving, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def save(data):
        saving.set()
        await release.wait()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    c.coordinator._store.async_save = AsyncMock(side_effect=save)
    hass.services.async_register("switch", "turn_off", turn_off)
    checking = None
    if blocked == "controller":
        checking = asyncio.create_task(c.async_check())
        await saving.wait()
    else:
        await c.coordinator._state_lock.acquire()
    holding = asyncio.create_task(
        c.async_suspend_automation(dt_util.now() + timedelta(hours=2))
    )
    try:
        await asyncio.wait_for(closed.wait(), 0.3)
    finally:
        if blocked == "model":
            c.coordinator._state_lock.release()
        release.set()
        await asyncio.gather(holding, *([checking] if checking else []))
    assert not c.active


async def test_failed_suspension_still_closes_automatic_watering(hass):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(c)
    await c.async_start(manual=False)
    c.coordinator._store.async_save = AsyncMock(side_effect=OSError("disk failure"))
    with pytest.raises(ServiceValidationError):
        await c.async_suspend_automation(dt_util.now() + timedelta(hours=2))
    assert hass.states.get("switch.garden_water").state == "off"


async def test_soak_pause_keeps_consumption_and_time_until_physical_closure(
    hass, freezer
):
    c = _controller(hass, irrigation_cycle_minutes=1)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "1", {"unit_of_measurement": "L"}
    )

    async def turn_off(call):
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(
            "sensor.garden_water_liters", "3", {"unit_of_measurement": "L"}
        )
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await c.async_check()
    session = c.state.irrigation_session
    assert session["paused_at"] is not None
    assert session["liters"] == pytest.approx(3)
    assert session["active_seconds"] == pytest.approx(90)
    await c.async_stop()
    assert c.state.irrigation_last_liters == pytest.approx(3)


async def test_failed_hold_release_keeps_existing_suspension(hass):
    c = _controller(hass)
    hold = (dt_util.now() + timedelta(hours=2)).isoformat()
    c.state.irrigation_suspended_until = hold
    c.coordinator._store.async_save = AsyncMock(side_effect=OSError("disk failure"))
    with pytest.raises(ServiceValidationError):
        await c.async_suspend_automation(None)
    assert c.state.irrigation_suspended_until == hold


async def test_suspending_automation_does_not_stop_manual_watering(hass):
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    await c.async_suspend_automation(dt_util.now() + timedelta(hours=2))
    assert c.active
    assert hass.states.get("switch.garden_water").state == "on"
    await c.async_stop()


@pytest.mark.parametrize("meter", ["timer", "rate"])
async def test_delayed_soak_closure_preserves_other_meter_modes(hass, freezer, meter):
    c = _controller(
        hass,
        irrigation_cycle_minutes=1,
        irrigation_flow=None if meter == "timer" else "sensor.garden_water_liters",
        allow_unmetered_manual=True,
    )
    hass.states.async_set("lawn_mower.garden", "docked")
    if meter == "rate":
        hass.states.async_set(
            "sensor.garden_water_liters", "0", {"unit_of_measurement": "L/min"}
        )
    await c.async_start(
        manual=True, **({"target_liters": 100} if meter == "rate" else {})
    )
    freezer.tick(timedelta(seconds=30))
    if meter == "rate":
        hass.states.async_set(
            "sensor.garden_water_liters", "2", {"unit_of_measurement": "L/min"}
        )
        await c.async_check()
    freezer.tick(timedelta(seconds=30))

    async def turn_off(call):
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await c.async_check()
    session = c.state.irrigation_session
    assert session["paused_at"] is not None
    assert session["active_seconds"] == pytest.approx(90)
    assert session["liters"] == pytest.approx(2 if meter == "rate" else 0)
    await c.async_stop()


async def test_stuck_pause_retry_accounts_active_time_once(hass, freezer):
    c = _controller(hass, irrigation_cycle_minutes=1)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "1", {"unit_of_measurement": "L"}
    )
    hass.services.async_register("switch", "turn_off", AsyncMock())
    await c.async_check()
    assert not c.state.irrigation_session.get("paused_at")
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set(
        "sensor.garden_water_liters", "3", {"unit_of_measurement": "L"}
    )

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await c.async_check()
    session = c.state.irrigation_session
    assert session["active_seconds"] == pytest.approx(90)
    assert session["liters"] == pytest.approx(3)
    await c.async_check()
    assert session["active_seconds"] == pytest.approx(90)
    await c.async_stop()


@pytest.mark.parametrize("overnight", [False, True])
def test_next_schedule_finds_window_reentered_at_autumn_rollback(overnight):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from custom_components.rasenpflege_assistent.planning import next_schedule_time

    zone = ZoneInfo("Europe/Berlin")
    settings = {
        "irrigation_weekdays": ["5"] if overnight else ["6"],
        "irrigation_start_time": "22:00:00" if overnight else "01:00:00",
        "irrigation_end_time": "02:15:00",
    }
    result = next_schedule_time(
        settings,
        datetime(2026, 10, 25, 2, 20, tzinfo=zone, fold=0),
        datetime(2026, 10, 25, 3, tzinfo=zone),
    )
    assert result is not None
    assert result.astimezone(timezone.utc) == datetime(
        2026, 10, 25, 1, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "zone_name,day",
    [
        ("Europe/Berlin", "2026-03-29"),
        ("Europe/Berlin", "2026-10-25"),
        ("Australia/Lord_Howe", "2026-04-05"),
        ("Australia/Lord_Howe", "2026-10-04"),
    ],
)
@pytest.mark.parametrize(
    "window",
    [("01:00:00", "01:45:00"), ("02:15:00", "03:30:00"), ("22:00:00", "02:15:00")],
)
def test_schedule_predictions_match_elapsed_time_oracle(zone_name, day, window):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from custom_components.rasenpflege_assistent.planning import (
        next_schedule_time,
        schedule_allowed,
    )

    zone = ZoneInfo(zone_name)
    first = (
        datetime.fromisoformat(day + "T01:50:00")
        .replace(tzinfo=zone)
        .astimezone(timezone.utc)
    )
    last = first + timedelta(hours=4)
    settings = {
        "irrigation_weekdays": [str(i) for i in range(7)],
        "irrigation_start_time": window[0],
        "irrigation_end_time": window[1],
    }
    expected = None
    cursor = first
    while cursor < last:
        if schedule_allowed(settings, cursor.astimezone(zone)):
            expected = cursor
            break
        cursor += timedelta(minutes=1)
    result = next_schedule_time(settings, first.astimezone(zone), last.astimezone(zone))
    assert (result.astimezone(timezone.utc) if result else None) == expected
