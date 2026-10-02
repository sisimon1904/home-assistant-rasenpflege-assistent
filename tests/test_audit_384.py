"""Regressions from the full 3.8.4 maintenance audit."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import real_monotonic
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.const import INTEGRATION_VERSION
from custom_components.rasenpflege_assistent.planning import next_schedule_time
from tests.test_irrigation import _controller


@pytest.fixture(autouse=True)
async def real_loop_clock(monkeypatch):
    # Simulated device time must not freeze timeouts for failed safety checks.
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)


def test_manifest_device_and_diagnostic_versions_match():
    manifest = Path("custom_components/rasenpflege_assistent/manifest.json")
    assert json.loads(manifest.read_text())["version"] == INTEGRATION_VERSION


@pytest.mark.parametrize("action", ["stop", "suspend"])
async def test_actions_during_completion_save_do_not_access_removed_session(
    hass, action
):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    saving, release = asyncio.Event(), asyncio.Event()

    async def save(data):
        saving.set()
        await release.wait()

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    finishing = asyncio.create_task(controller.async_stop())
    await saving.wait()
    assert controller.active and controller.state.irrigation_session is None
    operation = asyncio.create_task(
        controller.async_stop()
        if action == "stop"
        else controller.async_suspend_automation(dt_util.utcnow() + timedelta(hours=1))
    )
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(finishing, operation)
    assert not controller.active
    assert hass.states.get("switch.garden_water").state == "off"


@pytest.mark.parametrize("fault", ["unavailable", "unit", "reset", "stale"])
async def test_meter_faults_mark_consumption_and_budgets_incomplete(
    hass, freezer, fault
):
    controller = _controller(hass, irrigation_daily_limit_liters=100)
    hass.states.async_set("lawn_mower.garden", "docked")
    if fault == "stale":
        hass.states.async_set(
            "sensor.garden_water_liters", "0", {"unit_of_measurement": "L/min"}
        )
    await controller.async_start(manual=True, target_liters=100)
    if fault == "reset":
        freezer.tick(timedelta(seconds=60))
        hass.states.async_set(
            "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
        )
        await controller.async_check()
    freezer.tick(timedelta(seconds=181))
    if fault != "stale":
        hass.states.async_set(
            "sensor.garden_water_liters",
            "unavailable" if fault == "unavailable" else "0",
            {"unit_of_measurement": "m³" if fault == "unit" else "L"},
        )
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_measurement_gap
    assert controller.state.water_usage[-1]["measurement_gap"]
    assert controller.budget_details()["uncertain"]
    assert controller.state.last_watering_at is not None


async def test_excessive_cumulative_flow_retains_reported_volume(hass, freezer):
    controller = _controller(hass, max_flow_l_min=10)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=5))
    hass.states.async_set(
        "sensor.garden_water_liters", "30", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.state.irrigation_last_reason == "excessive_flow"
    assert controller.state.irrigation_last_liters == 30
    assert controller.state.water_usage[-1]["liters"] == 30


async def test_busy_safety_closure_accounts_water_before_shared_meter_changes(
    hass, freezer
):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    saving, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

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
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    stopping = asyncio.create_task(controller.async_stop())
    try:
        await asyncio.wait_for(closed.wait(), 1)
        freezer.tick(timedelta(minutes=10))
        hass.states.async_set(
            "sensor.garden_water_liters", "100", {"unit_of_measurement": "L"}
        )
    finally:
        release.set()
        await asyncio.gather(checking, stopping)
    assert controller.state.irrigation_last_liters == 5
    assert controller.state.irrigation_last_active_seconds == 60


async def test_completion_time_does_not_include_wait_for_model_lock(hass, freezer):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    closed = asyncio.Event()

    async def turn_off(call):
        hass.states.async_set("switch.garden_water", "off")
        closed.set()

    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.coordinator._state_lock.acquire()
    stopping = asyncio.create_task(controller.async_stop())
    try:
        await asyncio.wait_for(closed.wait(), 1)
        physical_end = dt_util.now()
        freezer.tick(timedelta(minutes=10))
    finally:
        controller.coordinator._state_lock.release()
        await stopping
    assert controller.state.irrigation_last_active_seconds == 60
    assert (
        dt_util.parse_datetime(controller.state.irrigation_last_session["finished_at"])
        == physical_end
    )


@pytest.mark.parametrize("end", ["03:10:00", "04:00:00"])
def test_spring_schedule_starts_at_first_existing_allowed_instant(end):
    zone = ZoneInfo("Europe/Berlin")
    at = next_schedule_time(
        {
            "irrigation_weekdays": ["6"],
            "irrigation_start_time": "02:30:00",
            "irrigation_end_time": end,
        },
        datetime(2026, 3, 29, 1, tzinfo=zone),
        datetime(2026, 3, 29, 4, tzinfo=zone),
    )
    assert at == datetime(2026, 3, 29, 3, tzinfo=zone)


@pytest.mark.parametrize("phase", ["start", "resume"])
async def test_automatic_opening_rejects_lost_live_weather_during_save(hass, phase):
    from tests.test_irrigation import _automatic_ready

    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 20})
    _automatic_ready(controller)
    if phase == "resume":
        await controller.async_start(manual=False)
        hass.states.async_set("switch.other", "on")
        await controller.async_check()
        hass.states.async_set("switch.other", "off")

    async def save(data):
        hass.states.async_set("weather.openweathermap", "unavailable")

    controller.coordinator._store.async_save = AsyncMock(side_effect=save)
    from homeassistant.exceptions import ServiceValidationError

    try:
        if phase == "start":
            await controller.async_start(manual=False)
        else:
            await controller._async_maybe_resume()
    except ServiceValidationError:
        pass
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_last_reason == "weather_unavailable"


@pytest.mark.parametrize("fault", ["unavailable", "excessive_rate", "target"])
async def test_meter_safety_closes_valve_while_storage_is_blocked(hass, freezer, fault):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    if fault == "excessive_rate":
        hass.states.async_set(
            "sensor.garden_water_liters", "0", {"unit_of_measurement": "L/min"}
        )
    await controller.async_start(manual=True, target_liters=5)
    saving, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

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
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters",
        "unavailable"
        if fault == "unavailable"
        else "101"
        if fault == "excessive_rate"
        else "5",
        {"unit_of_measurement": "L/min" if fault == "excessive_rate" else "L"},
    )
    handling = asyncio.create_task(controller._async_input_changed(None))
    try:
        await asyncio.wait_for(closed.wait(), 1)
    finally:
        release.set()
        await asyncio.gather(checking, handling)
    assert not controller.active


@pytest.mark.parametrize(
    "attrs,key",
    [
        ({"wind_speed": -1}, "wind_speed_m_s"),
        ({"wind_speed": 5, "wind_speed_unit": "invalid"}, "wind_speed_m_s"),
        ({"humidity": 120}, "humidity"),
        ({"cloud_coverage": -20}, "cloud_coverage"),
        ({"pressure": -5}, "pressure_hpa"),
        ({"pressure": 1013, "pressure_unit": "invalid"}, "pressure_hpa"),
    ],
)
def test_invalid_live_weather_inputs_are_unknown(hass, attrs, key):
    controller = _controller(hass)
    hass.states.async_set("weather.openweathermap", "sunny", attrs)
    assert controller.coordinator._read_weather_conditions(dt_util.now())[key] is None


@pytest.mark.parametrize(
    "unit,value,expected",
    [
        ("Pa", 101300, 1013),
        ("kPa", 101.3, 1013),
        ("bar", 1.013, 1013),
        ("inHg", 29.92, 1013.207),
    ],
)
def test_live_pressure_uses_home_assistant_unit_conversion(hass, unit, value, expected):
    controller = _controller(hass)
    hass.states.async_set(
        "weather.openweathermap", "sunny", {"pressure": value, "pressure_unit": unit}
    )
    assert controller.coordinator._read_weather_conditions(dt_util.now())[
        "pressure_hpa"
    ] == pytest.approx(expected, rel=1e-4)


async def test_ha_stop_closes_valve_and_removes_listener_without_errors(hass, caplog):
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_initialize()
    await controller.async_start(manual=True, target_liters=100)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    controller.detach()
    assert not controller.active
    assert not controller._unsubscribers
    assert hass.states.get("switch.garden_water").state == "off"
    assert "Unable to remove unknown job listener" not in caplog.text


async def test_live_weather_loss_is_visible_before_next_model_poll(hass):
    from tests.test_irrigation import _automatic_ready

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    hass.states.async_set("weather.openweathermap", "unavailable")
    assert controller.automatic_blocker() == "weather_unavailable"
    assert not controller.automatic_conditions()["weather_available"]


async def test_excessive_rate_preserves_preceding_valid_interval(hass, freezer):
    controller = _controller(hass, max_flow_l_min=10)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "0", {"unit_of_measurement": "L/min"}
    )
    await controller.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(
        "sensor.garden_water_liters", "6", {"unit_of_measurement": "L/min"}
    )
    await controller.async_check()
    freezer.tick(timedelta(seconds=20))
    hass.states.async_set(
        "sensor.garden_water_liters", "20", {"unit_of_measurement": "L/min"}
    )
    await controller.async_check()
    assert controller.state.irrigation_last_reason == "excessive_flow"
    assert controller.state.irrigation_last_liters == 2


async def test_meter_updates_during_closing_command_are_accounted(hass, freezer):
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )

    async def turn_off(call):
        freezer.tick(timedelta(seconds=10))
        hass.states.async_set(
            "sensor.garden_water_liters", "6", {"unit_of_measurement": "L"}
        )
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.async_stop()
    assert controller.state.irrigation_last_liters == 6
    assert controller.state.irrigation_last_active_seconds == 70
