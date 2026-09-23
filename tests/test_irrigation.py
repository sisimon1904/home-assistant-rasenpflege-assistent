"""Watering controller safety and volume-accounting regressions."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.coordinator import LawnCoordinator
from custom_components.rasenpflege_assistent.irrigation import (
    IrrigationController,
    _meter_reading,
)
from custom_components.rasenpflege_assistent.models import LawnData, RuntimeState


def _controller(hass: HomeAssistant, **options) -> IrrigationController:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"weather_entity": "weather.openweathermap", "area": 100},
        options={
            "irrigation_valve": "switch.garden_water",
            "irrigation_flow": "sensor.garden_water_liters",
            "mower_location": "lawn_mower.garden",
            **options,
        },
    )
    coordinator = LawnCoordinator(hass, entry)
    coordinator._state = RuntimeState(
        year=2026, gts=100, sample_date="2026-07-20", soil_water_mm=10
    )
    coordinator._store.async_save = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    controller = IrrigationController(hass, coordinator)
    coordinator.irrigation = controller
    hass.states.async_set("switch.garden_water", "off")
    hass.states.async_set(
        "sensor.garden_water_liters", "0", {"unit_of_measurement": "L"}
    )

    async def _turn_on(_call):
        hass.states.async_set("switch.garden_water", "on")

    async def _turn_off(_call):
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_on", _turn_on)
    hass.services.async_register("switch", "turn_off", _turn_off)
    return controller


async def test_mower_must_be_docked_for_manual_start(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Paused or unknown mower positions must not open the valve."""
    controller = _controller(hass)
    for position in ("mowing", "returning", "paused", "unknown"):
        hass.states.async_set("lawn_mower.garden", position)
        with pytest.raises(ServiceValidationError):
            await controller.async_start(manual=True)
        assert hass.states.get("switch.garden_water").state == "off"
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    assert hass.states.get("switch.garden_water").state == "on"


async def test_mower_dock_gate_accepts_generic_home_assistant_inputs(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Standard mower states, dock binary sensors and custom statuses work."""
    mower = _controller(hass, mower_safe_state="mowing")
    hass.states.async_set("lawn_mower.garden", "mowing")
    assert not mower._mower_is_docked()
    hass.states.async_set("lawn_mower.garden", "docked")
    assert mower._mower_is_docked()

    dock_sensor = _controller(hass, mower_location="binary_sensor.mower_docked")
    hass.states.async_set("binary_sensor.mower_docked", "on")
    assert dock_sensor._mower_is_docked()
    hass.states.async_set("binary_sensor.mower_docked", "off")
    assert not dock_sensor._mower_is_docked()

    custom = _controller(
        hass, mower_location="sensor.mower_status", mower_safe_state="charging"
    )
    hass.states.async_set("sensor.mower_status", "charging")
    assert custom._mower_is_docked()


async def test_mower_departure_overrides_minimum_runtime(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An active mower closes a new irrigation session immediately."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    hass.states.async_set("lawn_mower.garden", "mowing")
    await controller.async_check()
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_last_reason == "mower_left_dock"


async def test_mower_departure_event_closes_owned_valve(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A mower state change triggers immediate closure without weather polling."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_initialize()
    await controller.async_start(manual=True)
    hass.states.async_set("lawn_mower.garden", "returning")
    await hass.async_block_till_done()
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_last_reason == "mower_left_dock"
    assert await controller.async_shutdown()


async def test_no_flow_stops_without_adding_assumed_water(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A meter stuck at zero must close and leave the soil model unchanged."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    session = controller.state.irrigation_session
    session["started_at"] = (dt_util.now() - timedelta(minutes=4)).isoformat()
    await controller.async_check()
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_last_reason == "no_flow"
    assert controller.state.soil_water_mm == 10


async def test_target_volume_waits_for_minimum_runtime_and_records_once(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """The manual minimum holds the valve; measured liters drive accounting."""
    controller = _controller(hass, min_irrigation_minutes=5, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.active
    assert controller.state.irrigation_session["liters"] == 10
    assert controller.state.irrigation_session["target_liters"] == 0
    controller.state.irrigation_session["started_at"] = (
        dt_util.now() - timedelta(minutes=6)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_liters == 10
    assert controller.state.soil_water_mm == pytest.approx(10.085)


async def test_rate_and_volume_sensor_units_are_distinct(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A volume in L must not be mistaken for an instantaneous rate."""
    hass.states.async_set("sensor.flow", "120", {"unit_of_measurement": "L/h"})
    assert _meter_reading(hass.states.get("sensor.flow")) == ("rate", 2.0)
    hass.states.async_set("sensor.flow", "0.03", {"unit_of_measurement": "m³"})
    assert _meter_reading(hass.states.get("sensor.flow")) == ("volume", 30.0)


async def test_unmetered_automatic_start_is_rejected(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """The optional manual timer mode cannot bypass metering for automation."""
    controller = _controller(hass, irrigation_flow=None, allow_unmetered_manual=True)
    hass.states.async_set("lawn_mower.garden", "docked")
    controller.state.irrigation_enabled = True
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=False)


async def test_manual_timer_without_meter_never_credits_unmeasured_water(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Explicit time-only mode ends at minimum duration without inventing liters."""
    controller = _controller(hass, irrigation_flow=None, allow_unmetered_manual=True)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    controller.state.irrigation_session["started_at"] = (
        dt_util.now() - timedelta(minutes=6)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_liters is None
    assert controller.state.soil_water_mm == 10
    assert controller.state.last_watering is None


async def test_automatic_start_requires_reliable_inputs_and_runs_once(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An enabled auto switch only opens for a high-confidence watering window."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    now = dt_util.now()
    controller.state.irrigation_enabled = True
    controller.coordinator.async_set_updated_data(
        LawnData(
            watering_status="water_now",
            watering_recommended=True,
            watering_mm=5,
            watering_confidence="high",
            soil_model_confidence="medium",
            current_temperature=25,
            observed_rain_today_mm=None,
            watering_window_start=(now - timedelta(minutes=1)).isoformat(),
            watering_window_end=(now + timedelta(minutes=30)).isoformat(),
        )
    )
    await controller._async_maybe_auto_start()
    assert not controller.active
    controller.coordinator.data.observed_rain_today_mm = 0
    await controller._async_maybe_auto_start()
    assert controller.active
    assert controller.state.irrigation_session["source"] == "auto"
    await controller.async_stop()
    await controller._async_maybe_auto_start()
    assert not controller.active


async def test_restart_closes_instead_of_resuming_an_owned_valve(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A persisted session never restarts its elapsed timer after a HA reboot."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    restored = IrrigationController(hass, controller.coordinator)
    await restored.async_initialize()
    assert hass.states.get("switch.garden_water").state == "off"
    assert not restored.active
    assert restored.state.irrigation_last_reason == "interrupted_by_restart"
    assert await restored.async_shutdown()


async def test_changing_valve_options_closes_the_original_valve(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A settings reload must not send the stop command to a new switch."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    entry = controller.coordinator.config_entry
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "irrigation_valve": None}
    )
    await controller.async_stop("integration_unloaded")
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active


async def test_delayed_valve_open_is_closed_after_failed_start(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A delayed on state after a timed-out start cannot run uncontrolled."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")

    async def _no_state_report(_call):
        return None

    hass.services.async_register("switch", "turn_on", _no_state_report)
    await controller.async_start(manual=True)
    await controller.async_check()
    assert controller.active  # An asynchronous Zigbee report has 30 s to arrive.
    controller.state.irrigation_session["started_at"] = (
        dt_util.now() - timedelta(seconds=31)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "valve_did_not_open"
    hass.states.async_set("switch.garden_water", "on")
    await controller._async_close_late_open()
    assert hass.states.get("switch.garden_water").state == "off"
