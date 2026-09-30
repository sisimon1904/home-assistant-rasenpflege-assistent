"""Watering controller safety and volume-accounting regressions."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

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
    session["segment_started_at"] = session["started_at"]
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
    controller.state.irrigation_session["segment_started_at"] = (
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
    controller.state.irrigation_session["segment_started_at"] = (
        dt_util.now() - timedelta(minutes=6)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_liters is None
    assert controller.state.soil_water_mm == 10
    assert (
        controller.state.last_watering
        == dt_util.as_local(dt_util.now()).date().isoformat()
    )
    assert controller.state.last_watering_at is not None


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


async def test_shared_meter_is_ignored_while_valve_closed(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Other consumers can change a shared meter without watering this lawn."""
    controller = _controller(hass)
    hass.states.async_set(
        "sensor.garden_water_liters", "45", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.state.last_watering is None
    assert controller.state.irrigation_last_liters is None
    assert not controller.active


async def test_mower_leaving_before_valve_reports_open_forces_closure(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An asynchronous valve report must not defer the mower safety guard."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")

    async def _no_report(_call):
        pass

    hass.services.async_register("switch", "turn_on", _no_report)
    await controller.async_start(manual=True)
    hass.states.async_set("lawn_mower.garden", "mowing")
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "mower_left_dock"


async def test_other_valve_pauses_and_resumes_without_counting_other_consumption(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Only open lawn-valve segments count shared-meter increments."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "on")
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=True)
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    hass.states.async_set("switch.other_water", "on")
    await controller.async_check()
    assert controller.active
    assert controller.state.irrigation_last_status == "paused"
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_session["liters"] == 5
    hass.states.async_set(
        "sensor.garden_water_liters", "25", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.state.irrigation_session["liters"] == 5
    hass.states.async_set("switch.other_water", "off")
    await controller._async_maybe_resume()
    assert hass.states.get("switch.garden_water").state == "on"
    hass.states.async_set(
        "sensor.garden_water_liters", "30", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.state.irrigation_session["liters"] == 10
    await controller.async_stop()
    assert controller.state.irrigation_last_liters == 10
    assert controller.state.soil_water_mm == pytest.approx(10.085)


async def test_volume_counter_spike_is_averaged_over_actual_counter_interval(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A counter reporting once per minute must not look four times faster."""
    controller = _controller(hass, max_flow_l_min=100)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    session = controller.state.irrigation_session
    session["last_volume_change_at"] = (
        dt_util.now() - timedelta(minutes=1)
    ).isoformat()
    session["last_meter_at"] = (dt_util.now() - timedelta(seconds=15)).isoformat()
    hass.states.async_set(
        "sensor.garden_water_liters", "40", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.active
    assert session["liters"] == 40


async def test_unknown_competing_valve_blocks_water(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Only an explicitly closed configured valve permits watering."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "unavailable")
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=True)
    assert controller.readiness() == "other_valve_unavailable"


async def test_failed_auto_start_can_retry_after_cooldown(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """No-flow failures do not consume the only automatic chance of the day."""
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
            soil_model_confidence="high",
            current_temperature=22,
            observed_rain_today_mm=0,
            watering_window_start=(now - timedelta(minutes=1)).isoformat(),
            watering_window_end=(now + timedelta(hours=1)).isoformat(),
        )
    )
    await controller._async_maybe_auto_start()
    assert controller.active
    session = controller.state.irrigation_session
    session["started_at"] = (now - timedelta(minutes=4)).isoformat()
    session["segment_started_at"] = session["started_at"]
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "no_flow"
    assert controller.state.irrigation_last_auto_date is None
    assert controller.automatic_blocker() == "retry_cooldown"
    controller.state.irrigation_retry_after = (now - timedelta(seconds=1)).isoformat()
    assert controller.automatic_blocker() is None


async def test_old_rate_report_cannot_confirm_flow(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A shared meter's positive idle rate must be reported after opening."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "6", {"unit_of_measurement": "L/min"}
    )
    await controller.async_start(manual=True)
    session = controller.state.irrigation_session
    await controller.async_check()
    assert not session["flow_seen"]
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.dt_util.now",
        return_value=dt_util.now() + timedelta(minutes=3),
    ):
        await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "meter_stale"


async def test_timer_pause_retains_wet_record_and_elapsed_time(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Time-only watering records a wet lawn after a closed-valve pause."""
    controller = _controller(
        hass,
        irrigation_flow=None,
        allow_unmetered_manual=True,
        other_valve="switch.other_water",
    )
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    session = controller.state.irrigation_session
    session["segment_started_at"] = (dt_util.now() - timedelta(minutes=2)).isoformat()
    hass.states.async_set("switch.other_water", "on")
    await controller.async_check()
    assert session["paused_at"]
    await controller.async_stop()
    assert controller.state.irrigation_last_active_seconds >= 120
    assert (
        controller.state.last_watering
        == dt_util.as_local(dt_util.now()).date().isoformat()
    )
    assert controller.state.irrigation_last_liters is None


async def test_pause_does_not_assign_new_shared_meter_reading(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An ambiguous reading after another valve opens marks a model gap."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    hass.states.async_set("switch.other_water", "on")
    hass.states.async_set(
        "sensor.garden_water_liters", "20", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.state.irrigation_session["liters"] == 0
    assert controller.state.irrigation_session["measurement_gap"]
    await controller.async_stop()
    assert controller.state.irrigation_last_measurement_gap


async def test_competing_valve_unknown_while_running_closes_lawn_valve(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A lost configured interlock closes the owned valve without resuming."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    hass.states.async_set("switch.other_water", "unavailable")
    await controller.async_check()
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active
    assert controller.state.irrigation_last_reason == "other_valve_unavailable"


async def test_pause_counts_towards_hard_maximum_runtime(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An open competing valve must never prolong the owned session."""
    controller = _controller(
        hass, other_valve="switch.other_water", max_irrigation_minutes=5
    )
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    hass.states.async_set("switch.other_water", "on")
    await controller.async_check()
    controller.state.irrigation_session["started_at"] = (
        dt_util.now() - timedelta(minutes=6)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "maximum_runtime"


async def test_timer_under_one_minute_does_not_record_wet_lawn(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A short manual abort must not create an unmeasured watering event."""
    controller = _controller(hass, irrigation_flow=None, allow_unmetered_manual=True)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    await controller.async_stop()
    assert controller.state.last_watering_at is None
    assert controller.state.last_watering is None


async def test_live_meter_update_does_not_poll_weather(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Live irrigation telemetry uses coordinator listeners, not OWM refresh."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    controller.coordinator.data = LawnData()
    await controller.async_start(manual=True)
    controller.coordinator.async_request_refresh.reset_mock()
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert controller.coordinator.data.irrigation_liters == 5
    controller.coordinator.async_request_refresh.assert_not_awaited()


async def test_late_old_valve_open_after_reconfigure_is_closed(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Remember original valve ownership across a controller reload."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    entry = controller.coordinator.config_entry
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "irrigation_valve": None}
    )
    await controller.async_stop("integration_unloaded")
    restored = IrrigationController(hass, controller.coordinator)
    await restored.async_initialize()
    hass.states.async_set("switch.garden_water", "on")
    await hass.async_block_till_done()
    assert hass.states.get("switch.garden_water").state == "off"
    assert await restored.async_shutdown()


async def test_failed_valve_closure_retries_and_clears_repair(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A stuck valve stays owned and produces an actionable repair until off."""
    from homeassistant.helpers import issue_registry as ir

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)

    async def _ignore_off(_call):
        return None

    hass.services.async_register("switch", "turn_off", _ignore_off)
    await controller.async_stop()
    issue_id = f"{controller.coordinator.config_entry.entry_id}_irrigation_valve_stuck"
    assert controller.active
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    hass.states.async_set("switch.garden_water", "off")
    await controller.async_check()
    assert not controller.active
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_second_valve_is_never_commanded_during_start_pause_resume_stop(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Every service target is the lawn valve across competing-valve changes."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    commands = []

    async def turn_on(call):
        commands.append(("on", call.data["entity_id"]))
        assert call.data["entity_id"] == "switch.garden_water"
        hass.states.async_set("switch.garden_water", "on")

    async def turn_off(call):
        commands.append(("off", call.data["entity_id"]))
        assert call.data["entity_id"] == "switch.garden_water"
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.async_start(manual=True)
    for _ in range(3):
        hass.states.async_set("switch.other_water", "on")
        await controller.async_check()
        assert controller.state.irrigation_last_status == "paused"
        assert hass.states.get("switch.other_water").state == "on"
        hass.states.async_set("switch.other_water", "off")
        await controller._async_maybe_resume()
    await controller.async_stop()
    assert len(commands) >= 8
    with pytest.raises(ServiceValidationError, match="read-only"):
        await controller._async_command_valve("switch.other_water", open_valve=False)
    assert all(entity == "switch.garden_water" for _, entity in commands)


async def test_other_valve_opening_during_start_is_checked_before_return(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An input change during the service await immediately closes lawn water."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")

    async def turn_on(_call):
        hass.states.async_set("switch.garden_water", "on")
        hass.states.async_set("switch.other_water", "on")

    hass.services.async_register("switch", "turn_on", turn_on)
    await controller.async_start(manual=True)
    assert hass.states.get("switch.garden_water").state == "off"
    assert hass.states.get("switch.other_water").state == "on"
    assert controller.state.irrigation_last_status == "paused"


async def test_meter_unit_change_stops_active_watering(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A provider changing scale mid-session cannot create a huge water dose."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "0.002", {"unit_of_measurement": "m³"}
    )
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "meter_unit_changed"
    assert controller.state.last_watering is None


async def test_restart_during_pause_does_not_resume_or_command_other_valve(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Persisted paused water is ended on restart with the second valve intact."""
    controller = _controller(hass, other_valve="switch.other_water")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other_water", "off")
    await controller.async_start(manual=True)
    hass.states.async_set("switch.other_water", "on")
    await controller.async_check()
    restarted = IrrigationController(hass, controller.coordinator)
    await restarted.async_initialize()
    assert not restarted.active
    assert restarted.state.irrigation_last_reason == "interrupted_by_restart"
    assert hass.states.get("switch.garden_water").state == "off"
    assert hass.states.get("switch.other_water").state == "on"
    assert await restarted.async_shutdown()
