"""Further cycle-meter and consumption-ledger review regressions.

File: tests/test_audit_386_accounting.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from tests.test_irrigation import _controller


async def test_counter_reset_on_each_cycle_preserves_completed_cycle_volume(
    hass, freezer
):
    c = _controller(hass, irrigation_cycle_minutes=1, irrigation_soak_minutes=1)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    assert c.state.irrigation_session["paused_at"]
    freezer.tick(timedelta(minutes=1))

    async def turn_on(call):
        hass.states.async_set(
            "sensor.garden_water_liters", "0", {"unit_of_measurement": "L"}
        )
        hass.states.async_set("switch.garden_water", "on")

    hass.services.async_register("switch", "turn_on", turn_on)
    await c._async_maybe_resume()
    assert c.active
    assert c.state.irrigation_session["liters"] == 5
    freezer.tick(timedelta(seconds=20))
    hass.states.async_set(
        "sensor.garden_water_liters", "2", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    await c.async_stop()
    assert c.state.irrigation_last_liters == 7
    assert not c.state.irrigation_last_measurement_gap


@pytest.mark.parametrize("late_amount", [0.001, 0.002, 0.004])
def test_rounding_does_not_create_negative_daily_allocations(hass, late_amount):
    c = _controller(hass)
    allocations = [
        {"date": "2026-10-01", "liters": 1.001},
        {"date": "2026-10-02", "liters": late_amount},
    ]
    rounded = round(sum(item["liters"] for item in allocations), 2)
    c.coordinator.record_water_usage(
        dt_util.now(), rounded, source="irrigation", allocations=allocations
    )
    record = c.state.water_usage[-1]
    assert all(item["liters"] >= 0 for item in record["allocations"])
    assert sum(item["liters"] for item in record["allocations"]) == pytest.approx(
        rounded
    )


@pytest.mark.parametrize("delivered", [0, 5])
@pytest.mark.parametrize("cancellations", [1, 2])
async def test_cancelled_completion_resolves_persistence_and_publishes_once(
    hass, freezer, delivered, monkeypatch, cancellations
):
    import asyncio
    from copy import deepcopy
    from unittest.mock import AsyncMock, Mock

    from freezegun.api import real_monotonic

    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set(
        "sensor.garden_water_liters", str(delivered), {"unit_of_measurement": "L"}
    )
    saving, release = asyncio.Event(), asyncio.Event()
    persisted = None

    async def save(data):
        nonlocal persisted
        saving.set()
        await release.wait()
        persisted = deepcopy(data)

    c.coordinator._store.async_save = AsyncMock(side_effect=save)
    c._emit_event = Mock()
    stopping = asyncio.create_task(c.async_stop())
    await asyncio.wait_for(saving.wait(), 1)
    for _ in range(cancellations):
        stopping.cancel()
        await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await stopping
    assert persisted is not None
    assert persisted["irrigation_session"] is None
    assert persisted["irrigation_last_liters"] == delivered
    assert len(persisted["water_usage"]) == 1
    assert not c.active
    c._emit_event.assert_called_once()


@pytest.mark.parametrize("delivered", [0, 5])
async def test_cancelled_failed_completion_retains_retry_without_duplicate_usage(
    hass, freezer, delivered, monkeypatch
):
    import asyncio
    from unittest.mock import AsyncMock, Mock

    from freezegun.api import real_monotonic

    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)
    c = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set(
        "sensor.garden_water_liters", str(delivered), {"unit_of_measurement": "L"}
    )
    saving, release = asyncio.Event(), asyncio.Event()

    async def fail(data):
        saving.set()
        await release.wait()
        raise OSError("disk failure")

    c.coordinator._store.async_save = AsyncMock(side_effect=fail)
    c._emit_event = Mock()
    stopping = asyncio.create_task(c.async_stop())
    await asyncio.wait_for(saving.wait(), 1)
    stopping.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await stopping
    assert c.active
    assert c.state.water_usage == []
    assert c.state.soil_water_mm == 10
    assert hass.states.get("switch.garden_water").state == "off"
    c._emit_event.assert_not_called()
    c.coordinator._store.async_save = AsyncMock()
    await c.async_check()
    assert not c.active
    assert c.state.irrigation_last_liters == delivered
    assert len(c.state.water_usage) == 1
    c._emit_event.assert_called_once()


@pytest.mark.parametrize("fault", ["after_delivery", "after_grace"])
async def test_real_counter_reset_in_resumed_cycle_still_stops(hass, freezer, fault):
    c = _controller(hass, irrigation_cycle_minutes=1, irrigation_soak_minutes=1)
    hass.states.async_set("lawn_mower.garden", "docked")
    await c.async_start(manual=True, target_liters=100)
    freezer.tick(timedelta(seconds=60))
    hass.states.async_set(
        "sensor.garden_water_liters", "5", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    freezer.tick(timedelta(minutes=1))
    await c._async_maybe_resume()
    assert c.active
    if fault == "after_delivery":
        freezer.tick(timedelta(seconds=10))
        hass.states.async_set(
            "sensor.garden_water_liters", "6", {"unit_of_measurement": "L"}
        )
        await c.async_check()
    else:
        freezer.tick(timedelta(seconds=121))
    hass.states.async_set(
        "sensor.garden_water_liters", "0", {"unit_of_measurement": "L"}
    )
    await c.async_check()
    assert not c.active
    assert c.state.irrigation_last_reason == "meter_reset"
    assert c.state.irrigation_last_liters == (6 if fault == "after_delivery" else 5)
    assert c.state.irrigation_last_measurement_gap
