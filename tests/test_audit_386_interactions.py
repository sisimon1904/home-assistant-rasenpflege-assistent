"""Cross-check safety limits against delayed pause closure.

File: tests/test_audit_386_interactions.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from tests.test_irrigation import _automatic_ready, _controller


@pytest.mark.parametrize("condition", ["target", "volume", "flow", "meter", "budget"])
async def test_pause_closure_finishes_when_final_reading_reaches_stop_condition(
    hass, freezer, condition
):
    settings = {"irrigation_cycle_minutes": 1, "irrigation_soak_minutes": 1}
    if condition == "volume":
        settings["max_irrigation_liters"] = 10
    elif condition == "flow":
        settings["max_flow_l_min"] = 10
    elif condition == "budget":
        settings["irrigation_daily_limit_liters"] = 10
    c = _controller(hass, **settings)
    hass.states.async_set("lawn_mower.garden", "docked")
    if condition == "budget":
        _automatic_ready(c)
        await c.async_start(manual=False)
    else:
        await c.async_start(
            manual=True, target_liters=10 if condition in {"target", "volume"} else 100
        )
    freezer.tick(timedelta(seconds=60))
    first = 5 if condition in {"flow", "meter"} else 9
    hass.states.async_set(
        "sensor.garden_water_liters", str(first), {"unit_of_measurement": "L"}
    )

    async def turn_off(call):
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(
            "sensor.garden_water_liters",
            "unavailable"
            if condition == "meter"
            else "15"
            if condition == "flow"
            else "11",
            {"unit_of_measurement": "L"},
        )
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await c.async_check()
    assert not c.active
    expected = {
        "target": "target_reached",
        "volume": "maximum_volume",
        "flow": "excessive_flow",
        "meter": "meter_unavailable",
        "budget": "water_budget_exhausted",
    }
    assert c.state.irrigation_last_reason == expected[condition]
    assert c.state.irrigation_last_liters == (
        5 if condition == "meter" else 15 if condition == "flow" else 11
    )
    opening = AsyncMock()
    hass.services.async_register("switch", "turn_on", opening)
    freezer.tick(timedelta(minutes=1))
    await c._async_maybe_resume()
    opening.assert_not_called()


async def test_real_ha_storage_write_failure_prevents_valve_opening(hass):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.util.file import WriteError

    c = _controller(hass)
    del c.coordinator._store.async_save
    hass.states.async_set("lawn_mower.garden", "docked")
    with (
        patch.object(
            c.coordinator._store,
            "_async_write_data",
            side_effect=WriteError("disk full"),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await c.async_start(manual=True, target_liters=100)
    assert hass.states.get("switch.garden_water").state == "off"
    assert not c.active


async def test_real_storage_failure_rolls_back_enable(hass):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.util.file import WriteError

    c = _controller(hass)
    del c.coordinator._store.async_save
    await c.coordinator._store.async_save(c.state.as_dict())
    with (
        patch.object(
            c.coordinator._store,
            "_async_write_data",
            side_effect=WriteError("disk full"),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await c.async_set_auto_enabled(True)
    assert not c.state.irrigation_enabled
    assert not (await c.coordinator._store.async_load())["irrigation_enabled"]


async def test_real_storage_failure_keeps_closed_session_for_credit_retry(
    hass, freezer
):
    from unittest.mock import patch

    from homeassistant.util.file import WriteError

    c = _controller(hass)
    del c.coordinator._store.async_save
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    with patch.object(
        c.coordinator._store, "_async_write_data", side_effect=WriteError("disk full")
    ):
        await c.async_stop()
    assert hass.states.get("switch.garden_water").state == "off"
    assert c.active
    assert c.state.water_usage == []
    assert c.state.soil_water_mm == 10
    await c.async_check()
    assert not c.active
    assert c.state.irrigation_last_liters == 5
    assert len(c.state.water_usage) == 1
    loaded = await c.coordinator._store.async_load()
    assert loaded == c.state.as_dict()


@pytest.mark.parametrize("limit", ["target", "volume"])
async def test_resume_of_previously_paused_completed_session_never_opens(
    hass, freezer, limit
):
    c = _controller(hass, max_irrigation_liters=10 if limit == "volume" else 5000)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=10)
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await c._async_pause_locked("soak_pause")
    session = c.state.irrigation_session
    assert session.get("paused_at")
    # Simulate a paused snapshot produced before final-limit rechecking.
    session["liters"] = 11
    opening = AsyncMock()
    hass.services.async_register("switch", "turn_on", opening)
    await c._async_maybe_resume()
    assert not c.active
    opening.assert_not_called()
    assert c.state.irrigation_last_reason == (
        "maximum_volume" if limit == "volume" else "target_reached"
    )


@pytest.mark.parametrize("condition", ["runtime", "manual_minimum"])
async def test_final_pause_time_limits_finish_without_resume(hass, freezer, condition):
    settings = {"irrigation_cycle_minutes": 1, "min_irrigation_minutes": 1.5}
    if condition == "runtime":
        settings.update(max_irrigation_minutes=1.5, min_irrigation_minutes=1)
    else:
        settings.update(irrigation_flow=None, allow_unmetered_manual=True)
    c = _controller(hass, **settings)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(
        manual=True, **({"target_liters": 100} if condition == "runtime" else {})
    )
    freezer.tick(timedelta(seconds=60))
    if condition == "runtime":
        hass.states.async_set(
            "sensor.garden_water_liters", "1", {"unit_of_measurement": "L"}
        )

    async def turn_off(call):
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set("switch.garden_water", "off")

    hass.services.async_register("switch", "turn_off", turn_off)
    await c.async_check()
    assert not c.active
    assert c.state.irrigation_last_active_seconds == 90
    assert c.state.irrigation_last_reason == (
        "maximum_runtime" if condition == "runtime" else "target_reached"
    )
