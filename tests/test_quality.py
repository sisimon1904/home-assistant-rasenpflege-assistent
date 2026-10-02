"""Lifecycle, platform, units and persistence regressions for the quality audit.

File: tests/test_quality.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent import (
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    button,
    sensor,
    switch,
)
from custom_components.rasenpflege_assistent.config_flow import LawnCareConfigFlow
from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.planning import schedule_allowed
from tests.test_coordinator import _coordinator
from tests.test_irrigation import _controller


@pytest.mark.parametrize("configured", [False, True])
async def test_platforms_expose_values_and_actions(hass, configured):
    """Every enabled/disabled sensor is readable and all action routes work."""
    controller = _controller(
        hass, irrigation_valve="switch.garden_water" if configured else None
    )
    coordinator = controller.coordinator
    coordinator.async_set_updated_data(
        LawnData(irrigation_status="idle" if configured else "not_configured")
    )
    entry = coordinator.config_entry
    entry.runtime_data = coordinator
    entities = []
    for platform in (sensor, button, switch):
        await platform.async_setup_entry(
            hass, entry, lambda items: entities.extend(items)
        )
    for entity in entities:
        if isinstance(entity, sensor.LawnSensor):
            value = entity.native_value
            json.dumps(entity.extra_state_attributes, default=str, allow_nan=False)
            if entity.entity_description.options and value is not None:
                assert value in entity.entity_description.options
        elif isinstance(entity, button.LawnButton):
            with (
                patch.object(coordinator, "async_mark_mowed", new=AsyncMock()) as mowed,
                patch.object(
                    coordinator, "async_mark_watered", new=AsyncMock()
                ) as watered,
                patch.object(
                    coordinator, "async_mark_fertilized", new=AsyncMock()
                ) as fertilized,
                patch.object(
                    coordinator, "async_undo_last_action", new=AsyncMock()
                ) as undo,
                patch.object(controller, "async_start", new=AsyncMock()) as start,
                patch.object(controller, "async_stop", new=AsyncMock()) as stop,
            ):
                await entity.async_press()
                assert (
                    sum(
                        mock.await_count
                        for mock in (mowed, watered, fertilized, undo, start, stop)
                    )
                    == 1
                )
        else:
            assert not entity.is_on
            await entity.async_turn_on()
            assert entity.is_on
            await entity.async_turn_off()
            assert not entity.is_on
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert (
        diagnostics["irrigation"] is not None
        if configured
        else diagnostics["irrigation"] is None
    )
    json.dumps(diagnostics, allow_nan=False)


async def test_forecast_display_units_and_invalid_rows(hass):
    """HA imperial forecast rows have the same meaning as metric rows."""
    coordinator = _coordinator(hass)
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {
            "temperature_unit": "°F",
            "precipitation_unit": "in",
            "wind_speed_unit": "mph",
        },
    )
    data = [
        {
            "datetime": dt_util.now().isoformat(),
            "temperature": 68,
            "templow": 50,
            "precipitation": 1,
            "wind_speed": 10,
        },
        "broken",
        {"temperature": "nan"},
        {"temperature": 10000},
        {"precipitation": -2},
    ]

    async def forecast(call):
        return {"weather.openweathermap": {"forecast": data}}

    hass.services.async_register(
        "weather", "get_forecasts", forecast, supports_response=SupportsResponse.ONLY
    )
    for kind in ("hourly", "daily"):
        result = await coordinator._async_forecast(kind)
        assert len(result) == 1
        assert result[0]["temperature"] == 20
        assert result[0]["templow"] == 10
        assert result[0]["precipitation"] == pytest.approx(25.4)
        assert result[0]["wind_speed"] == pytest.approx(4.4704)
        assert await coordinator._async_forecast(kind) is result


@pytest.mark.parametrize(
    "raw,unit", [("nan", "mm"), ("inf", "mm"), ("-1", "mm"), ("1", "cups")]
)
async def test_invalid_rain_is_unknown_not_dry(hass, raw, unit):
    controller = _controller(hass, precipitation_entity="sensor.rain")
    hass.states.async_set("sensor.rain", raw, {"unit_of_measurement": unit})
    source, amount, _, rate = controller.coordinator._sample_precipitation(
        dt_util.now()
    )
    assert source == "unavailable"
    assert amount == rate == 0
    assert controller.state.daily_rain_unknown


async def test_unloaded_action_entry_is_reported(hass):
    """A never-loaded entry does not cause an AttributeError in an action."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            DOMAIN, "record_mowing", {"config_entry_id": entry.entry_id}, blocking=True
        )
    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "action_1"


async def test_master_switch_storage_failure_blocks_enable_and_reports_disable(hass):
    controller = _controller(hass)
    controller.coordinator._store.async_save.side_effect = OSError("disk full")
    with pytest.raises(ServiceValidationError):
        await controller.async_set_auto_enabled(True)
    assert not controller.state.irrigation_enabled
    controller.state.irrigation_enabled = True
    with pytest.raises(ServiceValidationError):
        await controller.async_set_auto_enabled(False)
    assert not controller.state.irrigation_enabled


async def test_failed_platform_unload_keeps_safety_watchdog(hass):
    controller = _controller(hass)
    entry = controller.coordinator.config_entry
    entry.runtime_data = controller.coordinator
    unsubscribe = Mock()
    controller._unsubscribers.append(unsubscribe)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await async_unload_entry(hass, entry)
    unsubscribe.assert_not_called()
    assert not controller._shutting_down
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
        assert await async_unload_entry(hass, entry)
    unsubscribe.assert_called_once()
    controller.detach()
    unsubscribe.assert_called_once()


async def test_setup_failure_removes_installed_controller_listeners(hass):
    controller = _controller(hass)
    coordinator = controller.coordinator
    coordinator.config_entry.add_to_hass(hass)
    coordinator.config_entry._async_set_state(
        hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS, None
    )
    coordinator._store.async_load = AsyncMock(return_value=None)
    coordinator._async_update_data = AsyncMock(return_value=LawnData())
    with (
        patch(
            "custom_components.rasenpflege_assistent.LawnCoordinator",
            return_value=coordinator,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            side_effect=RuntimeError("platform failed"),
        ),
        pytest.raises(RuntimeError, match="platform failed"),
    ):
        await async_setup_entry(hass, coordinator.config_entry)
    assert not coordinator.irrigation._unsubscribers
    assert coordinator.irrigation._shutting_down


async def test_reconfigure_keeps_history_settings_and_clears_old_override(hass):
    registry = er.async_get(hass)
    weather = registry.async_get_or_create("weather", "openweathermap", "new-weather")
    hass.states.async_set(weather.entity_id, "sunny", {"temperature": 20})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"weather_entity": "weather.old", "name": "Lawn", "area": 120},
        options={"weather_entity": "weather.override", "root_depth_cm": 12},
        unique_id="same-lawn",
        version=9,
    )
    entry.add_to_hass(hass)
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": entry.entry_id,
    }
    assert (await flow.async_step_reconfigure())["step_id"] == "reconfigure"
    assert (await flow.async_step_reconfigure({"weather_entity": "weather.missing"}))[
        "errors"
    ]
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await flow.async_step_reconfigure(
            {"weather_entity": weather.entity_id}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["weather_entity"] == weather.entity_id
    assert entry.data["area"] == 120
    assert entry.options == {"root_depth_cm": 12}
    assert entry.unique_id == "same-lawn"


async def test_future_entry_version_cannot_be_downgraded(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=10)
    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 10


@pytest.mark.parametrize(
    "settings",
    [
        {"irrigation_start_time": "22:00+02:00"},
        {"irrigation_weekdays": None},
        {"irrigation_end_time": "bad"},
    ],
)
def test_invalid_imported_schedule_blocks_start(settings):
    assert not schedule_allowed(settings, dt_util.now())


@pytest.mark.parametrize("configured", [False, True])
async def test_real_home_assistant_setup_and_unload(
    hass, enable_custom_integrations, configured
):
    """HA creates actual entities and removes them again through entry unload."""
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import (
        MockModule,
        mock_integration,
    )

    mock_integration(hass, MockModule("openweathermap"))

    hass.states.async_set(
        "weather.openweathermap", "sunny", {"temperature": 20, "temperature_unit": "°C"}
    )
    hass.states.async_set("switch.garden_water", "off")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=9,
        data={
            "name": "Test lawn",
            "weather_entity": "weather.openweathermap",
            "area": 100,
        },
        options={
            "irrigation_valve": "switch.garden_water",
            "irrigation_flow": "sensor.flow",
            "mower_location": "lawn_mower.garden",
        }
        if configured
        else {},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.rasenpflege_assistent.coordinator.Store.async_load",
            return_value=None,
        ),
        patch(
            "custom_components.rasenpflege_assistent.coordinator.Store.async_save",
            new=AsyncMock(),
        ),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.LOADED
        entities = (
            er.async_get(hass).async_entries_for_config_entry(entry.entry_id)
            if hasattr(er.async_get(hass), "async_entries_for_config_entry")
            else er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        )
        assert entities
        assert all(
            hass.states.get(e.entity_id) is not None for e in entities if not e.disabled
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.NOT_LOADED


async def test_normalized_forecast_wind_is_not_converted_twice(hass):
    """A windy km/h forecast never turns into a calm watering window."""
    coordinator = _coordinator(hass)
    coordinator._store.async_load = AsyncMock(return_value=None)
    coordinator._store.async_save = AsyncMock()
    hass.states.async_set(
        "weather.openweathermap",
        "sunny",
        {"temperature": 20, "temperature_unit": "°C", "wind_speed_unit": "km/h"},
    )

    async def forecast(call):
        return {
            "weather.openweathermap": {
                "forecast": [
                    {
                        "datetime": dt_util.now().isoformat(),
                        "temperature": 20,
                        "precipitation": 0,
                        "wind_speed": 40,
                    }
                ]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", forecast, supports_response=SupportsResponse.ONLY
    )
    await coordinator._async_setup()
    data = await coordinator._async_update_data()
    assert data.watering_window_start is None
    assert data.watering_window_reason == "no_suitable_window"


async def test_malformed_forecast_units_dates_and_probabilities_are_rejected(hass):
    coordinator = _coordinator(hass)
    hass.states.async_set(
        "weather.openweathermap", "sunny", {"temperature_unit": "bananas"}
    )
    assert not coordinator._normalize_forecast(
        [{"temperature": 20}], "weather.openweathermap"
    )
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature_unit": "°C"})
    assert not coordinator._normalize_forecast(
        [
            {"datetime": "bad"},
            {"precipitation_probability": "nan"},
            {"precipitation_probability": 101},
            {"precipitation_probability": "bad"},
        ],
        "weather.openweathermap",
    )
    data = coordinator._normalize_forecast(
        [{"datetime": "2026-07-20T12:00:00", "precipitation_probability": 50}],
        "weather.openweathermap",
    )
    assert dt_util.parse_datetime(data[0]["datetime"]).tzinfo is not None


async def test_cancelled_opening_closes_owned_valve(hass):
    """Cancellation after an open command cannot abandon the owned valve."""
    import asyncio

    controller = _controller(hass)
    hass.states.async_set("lawn_mower.garden", "docked")
    opened = asyncio.Event()

    async def turn_on(call):
        hass.states.async_set("switch.garden_water", "on")
        opened.set()
        await asyncio.Event().wait()

    hass.services.async_register("switch", "turn_on", turn_on)
    task = asyncio.create_task(controller.async_start(manual=True))
    await opened.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get("switch.garden_water").state == "off"
    assert not controller.active


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
async def test_configuration_rejects_non_finite_area(hass, value):
    """Invalid selector values must never enter a saved lawn entry."""

    weather = er.async_get(hass).async_get_or_create(
        "weather", "openweathermap", "finite-weather"
    )
    hass.states.async_set(weather.entity_id, "sunny", {"temperature": 20})
    flow = LawnCareConfigFlow()
    flow.hass = hass
    flow.context = {"source": config_entries.SOURCE_USER}
    result = await flow.async_step_user(
        {"name": "Test lawn", "weather_entity": weather.entity_id, "area": value}
    )
    assert result["errors"]["area"] == "invalid_number"
