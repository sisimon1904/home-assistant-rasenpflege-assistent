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


async def test_rate_zero_report_keeps_preceding_water(hass, freezer):
    """A falling rate cannot erase flow delivered before its report edge."""
    freezer.move_to("2026-07-20T10:00:00+00:00")
    c = _controller(hass, irrigation_flow="sensor.flow", min_irrigation_minutes=5)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/min"})
    await c.async_start(manual=True)
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set("sensor.flow", "12", {"unit_of_measurement": "L/min"})
    await c.async_check()
    assert c.state.irrigation_session["liters"] == 0
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/min"})
    await c.async_check()
    assert c.state.irrigation_session["liters"] == pytest.approx(2)


async def test_external_closure_credits_last_preclosure_counter(hass, freezer):
    """An already reported final volume is sampled before finishing."""
    freezer.move_to("2026-07-20T10:00:00+00:00")
    c = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True)
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set("switch.garden_water", "off")
    await c.async_check()
    assert c.state.irrigation_last_liters == 10
    assert c.state.soil_water_mm == pytest.approx(10.085)


async def test_restart_never_credits_shared_counter_gap(hass):
    """Only the previously saved volume is credited across a restart."""
    c = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True)
    c.state.irrigation_session["liters"] = 5
    hass.states.async_set(
        "sensor.garden_water_liters", "25", {"unit_of_measurement": "L"}
    )
    restarted = IrrigationController(hass, c.coordinator)
    await restarted.async_initialize()
    assert restarted.state.irrigation_last_liters == 5
    assert restarted.state.irrigation_last_measurement_gap
    assert restarted.state.soil_water_mm == pytest.approx(10.0425)
    assert await restarted.async_shutdown()


async def test_session_completion_and_water_credit_share_one_save(hass):
    """No persisted completed session can precede its water credit."""
    c = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True)
    c.state.irrigation_session["liters"] = 10
    c.coordinator._store.async_save.reset_mock()
    await c.async_stop()
    completed = [
        call.args[0]
        for call in c.coordinator._store.async_save.call_args_list
        if call.args[0]["irrigation_session"] is None
    ]
    assert len(completed) == 1
    assert completed[0]["soil_water_mm"] == pytest.approx(10.085)
    assert completed[0]["last_watering_at"] is not None


async def test_resumed_valve_receives_new_opening_grace(hass, freezer):
    """A delayed on report after a long pause gets a fresh 30 seconds."""
    freezer.move_to("2026-07-20T10:00:00+00:00")
    c = _controller(hass, other_valve="switch.other", flow_start_grace=600)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    await c.async_start(manual=True)
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("switch.other", "on")
    await c.async_check()
    assert c.state.irrigation_session["paused_at"]
    hass.states.async_set("switch.other", "off")

    async def delayed_open(_call):
        return None

    hass.services.async_register("switch", "turn_on", delayed_open)
    await c._async_maybe_resume()
    assert c.active
    assert c.state.irrigation_session["paused_at"] is None
    freezer.tick(timedelta(seconds=31))
    await c.async_check()
    assert not c.active
    assert c.state.irrigation_last_reason == "valve_did_not_open"


async def test_failed_start_save_never_opens_valve(hass, enable_custom_integrations):
    """A session must be durable before hardware is opened."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    controller.coordinator._store.async_save.side_effect = OSError("disk full")
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=True)
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active
    assert controller.start_blocker() == "storage_error"
    controller.coordinator._store.async_save.side_effect = None
    await controller._async_watchdog(dt_util.now())
    assert controller.start_blocker() is None


async def test_stop_save_failure_closes_and_retries_credit_once(
    hass, enable_custom_integrations
):
    """Failed storage must not leave water running or duplicate a later credit."""
    controller = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    controller.coordinator._store.async_save.side_effect = OSError("disk full")
    await controller.async_stop("stopped_manually")
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.active
    assert controller.state.soil_water_mm == 10
    assert not controller.state.maintenance_history
    # Shared consumption after closure cannot increase the pending lawn credit.
    hass.states.async_set(
        "sensor.garden_water_liters", "50", {"unit_of_measurement": "L"}
    )
    controller.coordinator._store.async_save.side_effect = None
    await controller.async_check()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_liters == 10
    assert controller.state.soil_water_mm == pytest.approx(10.085)
    assert len(controller.state.maintenance_history) == 1


async def test_weather_refresh_failure_does_not_replay_saved_credit(
    hass, enable_custom_integrations
):
    """Weather failure after successful accounting is outside the retry transaction."""
    controller = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    controller.coordinator.async_request_refresh.side_effect = OSError(
        "weather offline"
    )
    with pytest.raises(OSError):
        await controller.async_stop("stopped_manually")
    await controller.async_check()
    assert not controller.active
    assert controller.state.soil_water_mm == pytest.approx(10.085)
    assert len(controller.state.maintenance_history) == 1


async def test_home_assistant_stop_closes_and_blocks_reopening(
    hass, enable_custom_integrations
):
    """An orderly stop closes the owned valve and disables further starts."""
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_initialize()
    await controller.async_start(manual=True)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active
    assert controller.state.irrigation_last_reason == "homeassistant_stopping"
    assert controller.start_blocker() == "homeassistant_stopping"
    assert await controller.async_shutdown()


async def test_old_rate_blocks_start_but_idle_cumulative_meter_does_not(
    hass, enable_custom_integrations
):
    """Rate readings expire; unchanged cumulative totals remain useful baselines."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set(
        "sensor.garden_water_liters", "1", {"unit_of_measurement": "L/min"}
    )
    later = dt_util.now() + timedelta(minutes=10)
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.dt_util.now",
        return_value=later,
    ):
        assert controller.start_blocker() == "meter_stale"
    hass.states.async_set(
        "sensor.garden_water_liters", "100", {"unit_of_measurement": "L"}
    )
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.dt_util.now",
        return_value=later,
    ):
        assert controller.start_blocker() is None


async def test_live_wet_interlock_and_progress_without_weather_fetch(
    hass, enable_custom_integrations
):
    """The current session immediately updates mowing and volume diagnostics."""
    controller = _controller(hass)
    controller.coordinator.async_set_updated_data(
        LawnData(mower_status="mow_regularly")
    )
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True)
    session = controller.state.irrigation_session
    session["target_liters"] = 100
    session["liters"] = 25
    controller.coordinator.async_request_refresh.reset_mock()
    controller._publish_session()
    data = controller.coordinator.data
    assert data.mower_status == "pause_wet"
    assert data.next_action == "wait_for_irrigation"
    assert data.lawn_status == "lawn_wet"
    attrs = controller.diagnostic_attributes()
    assert attrs["session_remaining_liters"] == 75
    assert attrs["session_progress_percent"] == 25
    assert attrs["session_delivered_mm"] == 0.25
    controller.coordinator.async_request_refresh.assert_not_awaited()
    session["paused_at"] = dt_util.now().isoformat()
    controller._publish_session()
    assert data.mower_wet_reason == "irrigation_paused"


async def test_failed_resume_stays_closed_until_storage_recovers(
    hass, enable_custom_integrations
):
    """A paused session needs a durable resume record before reopening."""
    controller = _controller(hass, other_valve="switch.other")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("switch.other", "off")
    await controller.async_start(manual=True)
    hass.states.async_set("switch.other", "on")
    await controller.async_check()
    assert controller.state.irrigation_session["paused_at"]
    hass.states.async_set("switch.other", "off")
    controller.coordinator._store.async_save.side_effect = OSError("disk full")
    await controller._async_maybe_resume()
    assert hass.states.get("switch.garden_water").state == "off"
    assert controller.state.irrigation_session["paused_at"]
    controller.coordinator._store.async_save.side_effect = None
    await controller._async_watchdog(dt_util.now())
    assert hass.states.get("switch.garden_water").state == "on"
    assert controller.state.irrigation_session["paused_at"] is None
    assert hass.states.get("switch.other").state == "off"


@pytest.mark.parametrize("field", ["current_temperature", "soil_temperature"])
async def test_frost_blocks_start_and_stops_running_session(
    hass, enable_custom_integrations, field
):
    """Fresh freezing air or soil temperatures protect starts and active watering."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    controller.coordinator.async_set_updated_data(LawnData(current_temperature=10))
    await controller.async_start(manual=True, target_liters=100)
    setattr(controller.coordinator.data, field, -1)
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "frost"
    with pytest.raises(ServiceValidationError, match="frost"):
        await controller.async_start(manual=True)


async def test_requested_liters_stop_before_manual_minimum(
    hass, enable_custom_integrations
):
    """An explicit volume is honored without an unrelated five-minute minimum."""
    controller = _controller(hass, max_flow_l_min=300)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=10)
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "target_reached"
    assert controller.state.irrigation_last_session["delivered_mm"] == 0.1
    assert controller.state.irrigation_last_session[
        "effective_model_mm"
    ] == pytest.approx(0.085)
    assert len(controller.state.water_usage) == 1
    await controller.coordinator.async_undo_last_action()
    assert not controller.state.water_usage


async def test_requested_mm_convert_to_liters(hass, enable_custom_integrations):
    """One millimeter corresponds to one liter per configured square meter."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_mm=3)
    assert controller.state.irrigation_session["target_liters"] == 300


@pytest.mark.parametrize(
    "arguments",
    [
        {"target_liters": 1, "target_mm": 1},
        {"target_mm": -1},
        {"target_liters": float("nan")},
        {"target_liters": 3000},
    ],
)
async def test_invalid_volume_never_opens(hass, enable_custom_integrations, arguments):
    """Ambiguous, nonfinite and above-limit requests are rejected before opening."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=True, **arguments)
    assert hass.states.get("switch.garden_water").state == "off"


async def test_volume_target_requires_a_meter(hass, enable_custom_integrations):
    """Timer mode cannot pretend to deliver a selected water volume."""
    controller = _controller(hass, irrigation_flow=None, allow_unmetered_manual=True)
    hass.states.async_set("lawn_mower.garden", "docked")
    with pytest.raises(ServiceValidationError):
        await controller.async_start(manual=True, target_liters=10)
    assert not controller.active


async def test_soak_cycle_excludes_shared_consumption_and_requires_safe_resume(
    hass, enable_custom_integrations
):
    """Soaking closes only the owned valve and resets the shared baseline on resume."""
    controller = _controller(
        hass,
        irrigation_cycle_minutes=1,
        irrigation_soak_minutes=2,
        max_flow_l_min=300,
        other_valve="switch.other",
    )
    hass.states.async_set("switch.other", "off")
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    session = controller.state.irrigation_session
    session["segment_started_at"] = (dt_util.now() - timedelta(minutes=1)).isoformat()
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert session["paused_at"]
    assert session["pause_reason"] == "soak_pause"
    assert hass.states.get("switch.garden_water").state == "off"
    await controller._async_maybe_resume()
    assert session["paused_at"]
    hass.states.async_set(
        "sensor.garden_water_liters", "25", {"unit_of_measurement": "L"}
    )
    session["resume_after"] = (dt_util.now() - timedelta(seconds=1)).isoformat()
    hass.states.async_set("switch.other", "on")
    await controller._async_maybe_resume()
    assert hass.states.get("switch.other").state == "on"
    assert hass.states.get("switch.garden_water").state == "off"
    hass.states.async_set("switch.other", "off")
    await controller._async_maybe_resume()
    assert not session["paused_at"]
    assert session["cycle_number"] == 2
    hass.states.async_set(
        "sensor.garden_water_liters", "30", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    assert session["liters"] == 10
    await controller.async_stop()
    assert len(controller.state.water_usage) == 1
    assert controller.state.water_usage[0]["liters"] == 10


async def test_soak_pause_does_not_extend_maximum_duration(
    hass, enable_custom_integrations
):
    """Even an intentionally long soaking pause cannot bypass total-runtime safety."""
    controller = _controller(hass, max_irrigation_minutes=5)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    await controller._async_pause_locked("soak_pause")
    controller.state.irrigation_session["started_at"] = (
        dt_util.now() - timedelta(minutes=6)
    ).isoformat()
    await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "maximum_runtime"


def _automatic_ready(controller):
    now = dt_util.now()
    controller.state.irrigation_enabled = True
    controller.coordinator.async_set_updated_data(
        LawnData(
            current_temperature=20,
            watering_status="water_now",
            watering_recommended=True,
            watering_mm=5,
            watering_confidence="high",
            soil_model_confidence="high",
            observed_rain_today_mm=0,
            watering_window_start=(now - timedelta(minutes=1)).isoformat(),
            watering_window_end=(now + timedelta(minutes=30)).isoformat(),
        )
    )


async def test_automation_hold_expires_without_enabling_master_switch(
    hass, enable_custom_integrations
):
    """A temporary hold is independent of the persistent automation switch."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    until = dt_util.now() + timedelta(minutes=5)
    await controller.async_suspend_automation(until)
    assert controller.automatic_blocker() == "automation_suspended"
    assert not controller.automatic_conditions()["not_suspended"]
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.dt_util.now",
        return_value=until + timedelta(seconds=1),
    ):
        assert controller.automatic_blocker() is None
    await controller.async_suspend_automation(None)
    assert controller.state.irrigation_suspended_until is None
    assert controller.state.irrigation_enabled
    controller.state.irrigation_enabled = False
    assert controller.automatic_blocker() == "automation_disabled"


async def test_suspend_stops_auto_but_allows_manual(hass, enable_custom_integrations):
    """A hold stops automatic watering while preserving voluntary safe watering."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    await controller.async_start(manual=False)
    await controller.async_suspend_automation(dt_util.now() + timedelta(hours=1))
    assert not controller.active
    assert controller.state.irrigation_last_reason == "automation_suspended"
    await controller.async_start(manual=True, target_liters=100)
    assert controller.active


async def test_automation_schedule_enforced_at_start_and_while_running(
    hass, enable_custom_integrations
):
    """Scheduled eligibility is rechecked under the session lock and while open."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    _automatic_ready(controller)
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.schedule_allowed",
        return_value=False,
    ):
        assert controller.automatic_blocker() == "outside_schedule"
        with pytest.raises(ServiceValidationError):
            await controller.async_start(manual=False)
    await controller.async_start(manual=False)
    with patch(
        "custom_components.rasenpflege_assistent.irrigation.schedule_allowed",
        return_value=False,
    ):
        await controller.async_check()
    assert not controller.active
    assert controller.state.irrigation_last_reason == "outside_schedule"


async def test_diagnostics_show_independent_failures_together(
    hass, enable_custom_integrations
):
    """A bad mower, meter and weather are shown simultaneously."""
    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "mowing")
    hass.states.async_set("sensor.garden_water_liters", "unavailable")
    diagnostics = controller.diagnostic_attributes()
    assert {"mower_docked", "meter_available", "weather_available"} <= set(
        diagnostics["automatic_blockers"]
    )


async def test_irrigation_events_are_entry_scoped_and_not_replayed(
    hass, enable_custom_integrations
):
    """A committed completion emits one event; storage retries do not duplicate it."""
    controller = _controller(hass, max_flow_l_min=300)
    events = []
    hass.bus.async_listen(f"{DOMAIN}_irrigation", events.append)
    hass.states.async_set("lawn_mower.garden", "docked")
    await controller.async_start(manual=True, target_liters=100)
    hass.states.async_set(
        "sensor.garden_water_liters", "10", {"unit_of_measurement": "L"}
    )
    await controller.async_check()
    controller.coordinator._store.async_save.side_effect = OSError("disk full")
    await controller.async_stop()
    await hass.async_block_till_done()
    assert [event.data["phase"] for event in events] == ["started"]
    assert not controller.state.water_usage
    controller.coordinator._store.async_save.side_effect = None
    await controller.async_check()
    await controller.async_check()
    await hass.async_block_till_done()
    assert [event.data["phase"] for event in events] == ["started", "stopped"]
    assert (
        events[-1].data["config_entry_id"]
        == controller.coordinator.config_entry.entry_id
    )
    assert len(controller.state.water_usage) == 1
