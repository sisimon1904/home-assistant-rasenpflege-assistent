"""Public service validation and actual history/suspension behavior.

File: tests/test_services.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent import async_setup
from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.coordinator import LawnCoordinator
from custom_components.rasenpflege_assistent.irrigation import IrrigationController
from custom_components.rasenpflege_assistent.models import RuntimeState


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"weather_entity": "weather.test", "area": 100}, version=9
    )
    entry.add_to_hass(hass)
    coordinator = LawnCoordinator(hass, entry)
    coordinator._state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        soil_water_mm=10,
    )
    coordinator._store.async_save = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.irrigation = IrrigationController(hass, coordinator)
    entry.runtime_data = coordinator
    return entry


async def test_backdated_service_requires_explicit_quantity_and_keeps_soil(hass):
    """A historical service records user-supplied water without manufacturing a dose."""
    entry = _entry(hass)
    await async_setup(hass, {})
    payload = {
        "config_entry_id": entry.entry_id,
        "recorded_at": (dt_util.now() - timedelta(days=2)).isoformat(),
    }
    with pytest.raises(ServiceValidationError, match="explicit amount"):
        await hass.services.async_call(
            DOMAIN, "record_watering", payload, blocking=True
        )
    await hass.services.async_call(
        DOMAIN, "record_watering", {**payload, "amount_mm": 3}, blocking=True
    )
    assert entry.runtime_data._state.soil_water_mm == 10
    assert entry.runtime_data._state.water_usage[0]["liters"] == 300


@pytest.mark.parametrize("offset", ["future", "naive", "invalid"])
async def test_invalid_record_times_do_not_change_history(hass, offset):
    """Timezone-free, malformed and future history timestamps are rejected."""
    entry = _entry(hass)
    await async_setup(hass, {})
    at = {
        "future": (dt_util.now() + timedelta(days=1)).isoformat(),
        "naive": "2026-01-01T08:00:00",
        "invalid": "not a date",
    }[offset]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "record_mowing",
            {"config_entry_id": entry.entry_id, "recorded_at": at},
            blocking=True,
        )
    assert not entry.runtime_data._state.maintenance_history


async def test_public_hold_service_persists_and_clears(hass):
    """The exposed hold action persists an end time and supports explicit clearing."""
    entry = _entry(hass)
    await async_setup(hass, {})
    until = (dt_util.now() + timedelta(hours=2)).isoformat()
    await hass.services.async_call(
        DOMAIN,
        "suspend_irrigation",
        {"config_entry_id": entry.entry_id, "until": until},
        blocking=True,
    )
    assert entry.runtime_data._state.irrigation_suspended_until == until
    await hass.services.async_call(
        DOMAIN, "suspend_irrigation", {"config_entry_id": entry.entry_id}, blocking=True
    )
    assert entry.runtime_data._state.irrigation_suspended_until is None


async def test_history_is_scoped_to_selected_lawn(hass):
    """Services cannot accidentally change a second configured lawn."""
    first, second = _entry(hass), _entry(hass)
    await async_setup(hass, {})
    await hass.services.async_call(
        DOMAIN,
        "record_fertilizing",
        {
            "config_entry_id": first.entry_id,
            "recorded_at": (dt_util.now() - timedelta(days=1)).isoformat(),
            "amount_kg": 2,
        },
        blocking=True,
    )
    assert first.runtime_data._state.last_fertilizing
    assert not second.runtime_data._state.last_fertilizing


async def test_new_sensor_diagnostics_and_consumption_values(hass):
    """New entities expose real usage and nested diagnostics without API calls."""
    from custom_components.rasenpflege_assistent.models import LawnData
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    entry = _entry(hass)
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(LawnData())
    coordinator.record_water_usage(dt_util.now(), 20, source="irrigation")
    sensors = {
        description.key: LawnSensor(coordinator, description) for description in SENSORS
    }
    assert sensors["water_consumption_week"].native_value == 20
    assert sensors["water_consumption_month"].native_value == 20
    assert (
        sensors["water_consumption_week"].extra_state_attributes[
            "week_irrigation_liters"
        ]
        == 20
    )
    assert "input_diagnostics" in sensors["data_quality"].extra_state_attributes
    assert "forecast_diagnostics" in sensors["data_quality"].extra_state_attributes
    assert "live_robot_session" in sensors["mower_status"].extra_state_attributes


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
async def test_nonfinite_service_amounts_cannot_enter_usage(hass, value):
    """Invalid numeric payloads cannot corrupt persisted consumption totals."""
    import voluptuous as vol

    entry = _entry(hass)
    await async_setup(hass, {})
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "record_watering",
            {"config_entry_id": entry.entry_id, "amount_mm": value},
            blocking=True,
        )
    assert not entry.runtime_data._state.water_usage


async def test_duration_hold_service_and_mutually_exclusive_until(hass, freezer):
    entry = _entry(hass)
    await async_setup(hass, {})
    await hass.services.async_call(
        DOMAIN,
        "suspend_irrigation",
        {"config_entry_id": entry.entry_id, "duration_hours": 2},
        blocking=True,
    )
    assert dt_util.parse_datetime(
        entry.runtime_data._state.irrigation_suspended_until
    ) == dt_util.now() + timedelta(hours=2)
    with pytest.raises(ServiceValidationError, match="Choose"):
        await hass.services.async_call(
            DOMAIN,
            "suspend_irrigation",
            {
                "config_entry_id": entry.entry_id,
                "duration_hours": 2,
                "until": (dt_util.now() + timedelta(hours=1)).isoformat(),
            },
            blocking=True,
        )


async def test_new_daily_care_and_eta_entities_expose_attributes(hass):
    from custom_components.rasenpflege_assistent.models import LawnData
    from custom_components.rasenpflege_assistent.sensor import SENSORS, LawnSensor

    entry = _entry(hass)
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(LawnData(next_action="water_lawn"))
    coordinator.record_water_usage(dt_util.now(), 25, source="irrigation")
    sensors = {item.key: LawnSensor(coordinator, item) for item in SENSORS}
    assert sensors["water_consumption_day"].native_value == 25
    assert (
        sensors["water_consumption_day"].extra_state_attributes["recent_records"][0][
            "liters"
        ]
        == 25
    )
    assert sensors["care_plan"].native_value == "water_lawn"
    assert set(sensors["care_plan"].extra_state_attributes) >= {
        "mowing",
        "watering",
        "fertilizing",
    }
    assert sensors["irrigation_remaining_time"].native_value is None
    assert sensors["next_automatic_start"].native_value is None


async def test_duration_hold_is_elapsed_hours_across_dst(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-25T00:30:00Z")
    entry = _entry(hass)
    await async_setup(hass, {})
    await hass.services.async_call(
        DOMAIN,
        "suspend_irrigation",
        {"config_entry_id": entry.entry_id, "duration_hours": 2},
        blocking=True,
    )
    assert (
        dt_util.parse_datetime(entry.runtime_data._state.irrigation_suspended_until)
        - dt_util.utcnow()
    ).total_seconds() == 7200
