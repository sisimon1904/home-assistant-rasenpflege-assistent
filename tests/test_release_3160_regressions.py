"""Stored clocks and lifecycle failures for the 3.16.0 review.

File: tests/test_release_3160_regressions.py

Exercise malformed calibration state with real HA sensor reports. Unload and
setup failures must retain supervision when physical shutdown is unconfirmed.
"""

import asyncio
from datetime import timedelta

import pytest

from tests.test_irrigation import _controller
from tests.test_release_3120 import NOW


@pytest.mark.parametrize(
    "clock",
    [
        "2026-10-01T10:00:00",
        42,
        {"bad": "clock"},
        (NOW + timedelta(days=2)).isoformat(),
    ],
)
async def test_invalid_calibration_clock_does_not_crash_or_suppress_new_observation(
    hass, freezer, clock
):
    freezer.move_to(NOW)
    c = _controller(hass, soil_moisture_entity="sensor.soil")
    hass.states.async_set("sensor.soil", "50")
    c.state.soil_water_mm = 10
    c.state.soil_sensor_last_calibrated_at = clock
    c.coordinator._calibrate_soil_model(NOW, 100, 50)
    assert c.state.soil_water_mm == 20
    assert c.state.soil_sensor_last_calibrated_at == NOW.isoformat()


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_failed_platform_unload_restores_controller_supervision(hass, failure):
    from unittest.mock import AsyncMock, patch

    from custom_components.rasenpflege_assistent import async_unload_entry

    c = _controller(hass)
    entry = c.coordinator.config_entry
    entry.runtime_data = c.coordinator
    c._shutting_down = True
    with (
        patch.object(type(c), "async_shutdown", AsyncMock(return_value=True)),
        patch.object(
            type(hass.config_entries),
            "async_unload_platforms",
            AsyncMock(side_effect=failure),
        ),
        pytest.raises(failure),
    ):
        await async_unload_entry(hass, entry)
    assert c._shutting_down is False


async def test_expired_soil_reading_is_not_a_fresh_gap_recovery_basis(hass, freezer):
    from custom_components.rasenpflege_assistent.models import LawnData

    freezer.move_to(NOW)
    c = _controller(
        hass, soil_moisture_entity="sensor.soil", soil_sensor_max_age_minutes=30
    )
    hass.states.async_set("sensor.soil", "60")
    c.coordinator.async_set_updated_data(LawnData(measured_soil_moisture_percent=60))
    freezer.move_to(NOW + timedelta(minutes=31))
    assert (
        c.coordinator.insight_diagnostics()["data_gaps"]["recovery_basis"]
        == "model_estimate"
    )


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize("closed", [False, True])
async def test_setup_failure_detaches_only_after_confirmed_shutdown(
    hass, failure, closed
):
    from unittest.mock import AsyncMock, Mock, patch

    from homeassistant import config_entries

    from custom_components.rasenpflege_assistent import async_setup_entry
    from custom_components.rasenpflege_assistent.irrigation import IrrigationController
    from custom_components.rasenpflege_assistent.models import LawnData

    c = _controller(hass)
    coordinator = c.coordinator
    entry = coordinator.config_entry
    entry.add_to_hass(hass)
    entry._async_set_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS, None
    )
    coordinator.async_set_updated_data(LawnData())
    unsubscribe = Mock()

    async def initialize():
        coordinator.irrigation_controller._unsubscribers.append(unsubscribe)

    with (
        patch(
            "custom_components.rasenpflege_assistent.LawnCoordinator",
            return_value=coordinator,
        ),
        patch.object(
            type(coordinator), "async_config_entry_first_refresh", AsyncMock()
        ),
        patch.object(
            IrrigationController, "async_initialize", AsyncMock(side_effect=initialize)
        ),
        patch.object(
            IrrigationController, "async_shutdown", AsyncMock(return_value=closed)
        ),
        patch.object(
            type(hass.config_entries),
            "async_forward_entry_setups",
            AsyncMock(side_effect=failure),
        ),
        pytest.raises(failure),
    ):
        await async_setup_entry(hass, entry)
    try:
        assert unsubscribe.call_count == int(closed)
        assert bool(coordinator.irrigation_controller._unsubscribers) is not closed
    finally:
        coordinator.irrigation_controller.detach()


async def test_unconfirmed_shutdown_refuses_platform_unload(hass):
    from unittest.mock import AsyncMock, patch

    from custom_components.rasenpflege_assistent import async_unload_entry

    c = _controller(hass)
    entry = c.coordinator.config_entry
    entry.runtime_data = c.coordinator
    with (
        patch.object(type(c), "async_shutdown", AsyncMock(return_value=False)),
        patch.object(
            type(hass.config_entries), "async_unload_platforms", AsyncMock()
        ) as platforms,
    ):
        assert not await async_unload_entry(hass, entry)
    platforms.assert_not_called()
