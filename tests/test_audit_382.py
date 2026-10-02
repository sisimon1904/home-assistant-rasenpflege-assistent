"""Safety regressions from the follow-up review of version 3.8.2."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from tests.test_irrigation import _controller


@pytest.mark.parametrize("phase", ["start", "resume"])
@pytest.mark.parametrize("changed", ["mower", "frost", "other_valve"])
async def test_changed_interlock_during_save_never_opens_valve(hass, phase, changed):
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    if phase == "resume":
        await controller.async_start(manual=True, target_liters=100)
        hass.states.async_set("switch.other", "on")
        await controller.async_check()
        hass.states.async_set("switch.other", "off")
    opened = AsyncMock()
    hass.services.async_register("switch", "turn_on", opened)
    changed_once = False

    async def save(data):
        nonlocal changed_once
        if changed_once:
            return
        changed_once = True
        if changed == "mower":
            hass.states.async_set("lawn_mower.garden", "mowing")
        elif changed == "frost":
            hass.states.async_set(
                "weather.openweathermap", "sunny", {"temperature": -1}
            )
        else:
            hass.states.async_set("switch.other", "on")

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    try:
        if phase == "start":
            await controller.async_start(manual=True, target_liters=100)
        else:
            await controller._async_maybe_resume()
    except ServiceValidationError:
        pass
    opened.assert_not_awaited()
    assert hass.states.get("switch.garden_water").state == "off"


@pytest.mark.parametrize("phase", ["start", "resume"])
async def test_preopening_shared_meter_changes_do_not_count_as_irrigation(hass, phase):
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    if phase == "resume":
        await controller.async_start(manual=True, target_liters=100)
        hass.states.async_set("switch.other", "on")
        await controller.async_check()
        hass.states.async_set("switch.other", "off")
    changed_once = False

    async def save(data):
        nonlocal changed_once
        if not changed_once:
            changed_once = True
            hass.states.async_set(
                "sensor.garden_water_liters", "50", {"unit_of_measurement": "L"}
            )

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    if phase == "start":
        await controller.async_start(manual=True, target_liters=100)
    else:
        await controller._async_maybe_resume()
    assert controller.state.irrigation_session["liters"] == 0
    assert controller.state.irrigation_session["meter_baseline"] == 50
    await controller.async_stop()


async def test_paused_valve_reopening_closes_before_blocked_save(hass):
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    await controller.async_start(manual=True, target_liters=100)
    hass.states.async_set("switch.other", "on")
    await controller.async_check()
    assert controller.state.irrigation_session["paused_at"]
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
    hass.states.async_set("switch.garden_water", "on")
    check = asyncio.create_task(controller.async_check())
    try:
        await asyncio.wait_for(closed.wait(), 1)
        assert hass.states.get("switch.garden_water").state == "off"
    finally:
        release.set()
        await check


async def test_automatic_resume_rain_arriving_during_save_never_opens(hass):
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    await controller.async_start(manual=True, target_liters=100)
    controller.state.irrigation_enabled = True
    controller.state.irrigation_session["source"] = "auto"
    hass.states.async_set("switch.other", "on")
    await controller.async_check()
    hass.states.async_set("switch.other", "off")
    opened = AsyncMock()
    hass.services.async_register("switch", "turn_on", opened)

    async def save(data):
        hass.states.async_set("weather.openweathermap", "rainy", {"temperature": 20})

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    await controller._async_maybe_resume()
    opened.assert_not_awaited()
    assert hass.states.get("switch.garden_water").state == "off"


async def test_slow_start_does_not_open_after_maximum_runtime(hass, freezer):
    controller = _controller(hass, max_irrigation_minutes=10)
    hass.states.async_set("lawn_mower.garden", "docked")
    opened = AsyncMock()
    hass.services.async_register("switch", "turn_on", opened)
    advanced = False

    async def save(data):
        nonlocal advanced
        if not advanced:
            advanced = True
            freezer.tick(timedelta(minutes=181))

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    try:
        await controller.async_start(manual=True, target_liters=100)
    except ServiceValidationError:
        pass
    opened.assert_not_awaited()


async def test_watchdog_closes_unsafe_valve_before_storage_retry(hass):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    controller._storage_error = True
    hass.states.async_set("lawn_mower.garden", "mowing")
    release = asyncio.Event()
    closed = asyncio.Event()

    async def save(data):
        await release.wait()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    hass.services.async_register("switch", "turn_off", turn_off)
    checking = asyncio.create_task(controller._async_watchdog(None))
    try:
        await asyncio.wait_for(closed.wait(), 1)
    finally:
        release.set()
        await checking


@pytest.mark.parametrize(
    "changed",
    ["mower", "frost", "other_valve", "runtime", "volume", "manual_stop", "shutdown"],
)
async def test_safety_events_close_even_while_controller_save_holds_lock(hass, changed):
    controller = _controller(
        hass, other_valve="switch.other", max_irrigation_liters=100
    )
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    await controller.async_start(manual=True, target_liters=100)
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
    checking = asyncio.create_task(controller.async_check())
    await saving.wait()
    if changed == "mower":
        hass.states.async_set("lawn_mower.garden", "mowing")
    elif changed == "frost":
        hass.states.async_set("weather.openweathermap", "sunny", {"temperature": -1})
    elif changed == "other_valve":
        hass.states.async_set("switch.other", "on")
    elif changed == "runtime":
        controller.state.irrigation_session["started_at"] = (
            dt_util.now() - timedelta(minutes=91)
        ).isoformat()
    elif changed == "volume":
        hass.states.async_set(
            "sensor.garden_water_liters", "100", {"unit_of_measurement": "L"}
        )
    operations = {
        "runtime": lambda: controller._async_watchdog(None),
        "manual_stop": controller.async_stop,
        "shutdown": lambda: controller._async_homeassistant_stopping(None),
    }
    handling = asyncio.create_task(
        operations.get(changed, lambda: controller._async_input_changed(None))()
    )
    try:
        await asyncio.wait_for(closed.wait(), 1)
    finally:
        release.set()
        await asyncio.gather(checking, handling)
    if controller.active:
        await controller.async_stop()
