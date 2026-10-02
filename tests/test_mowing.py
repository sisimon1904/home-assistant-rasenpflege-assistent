"""Mowing intervals, completion observations and migration regressions.

File: tests/test_mowing.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Event, HomeAssistant, State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent.calculations import (
    growth_state,
    mower_recommendation,
)
from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.coordinator import LawnCoordinator
from custom_components.rasenpflege_assistent.models import RuntimeState
from custom_components.rasenpflege_assistent.mowing import MowingObserver

NOW = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)


def _coordinator(hass, **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"weather_entity": "weather.openweathermap"},
        options={
            "mowing_mode": "robot",
            "mowing_entity": "lawn_mower.knoxx",
            **options,
        },
    )
    coordinator = LawnCoordinator(hass, entry)
    coordinator._state = RuntimeState(year=2026, gts=300, sample_date="2026-07-20")
    coordinator._store.async_save = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _event(old, new, minutes):
    return Event(
        "state_changed",
        {
            "old_state": State("lawn_mower.knoxx", old) if old is not None else None,
            "new_state": State("lawn_mower.knoxx", new) if new is not None else None,
        },
        time_fired_timestamp=(NOW + timedelta(minutes=minutes)).timestamp(),
    )


@pytest.mark.parametrize(
    "growth,manual,robot",
    [
        ("active_growth", 4, 1),
        ("slow_growth", 7, 3),
        ("autumn_slowdown", 10, 5),
        ("first_awakening", 10, 5),
    ],
)
def test_robot_intervals_are_shorter(growth, manual, robot):
    """Robot and manual schedules use different growth-dependent intervals."""
    args = {
        "growth": growth,
        "mower_started_year": 2026,
        "year": 2026,
        "last_mowing": date(2026, 7, 1),
        "today": NOW.date(),
    }
    assert mower_recommendation(**args)["interval"] == manual
    assert mower_recommendation(**args, mode="robot")["interval"] == robot


def test_fractional_interval_uses_elapsed_time_across_midnight():
    """A half-day interval does not expire just because the date changes."""
    last = NOW.replace(hour=23)
    args = {
        "growth": "active_growth",
        "mower_started_year": 2026,
        "year": 2026,
        "last_mowing": last.date(),
        "last_mowing_at": last,
        "mode": "robot",
        "interval_factor": 0.5,
        "today": date(2026, 7, 21),
    }
    result = mower_recommendation(**args, now=last + timedelta(hours=1))
    assert result["status"] == "wait_to_mow"
    assert result["next_at"] == last + timedelta(hours=12)
    assert (
        mower_recommendation(**args, now=result["next_at"])["status"] == "mow_regularly"
    )


def test_autumn_hysteresis_avoids_temperature_chatter():
    """Autumn slowdown ends above a different threshold from its entry."""
    args = {
        "today": date(2026, 9, 30),
        "gts": 900,
        "growth_temperature": 10.5,
        "soil_moisture_percent": 60,
        "mower_started_year": 2026,
    }
    assert growth_state(**args, previous_state="autumn_slowdown") == "autumn_slowdown"
    assert growth_state(**args, previous_state="active_growth") == "active_growth"


async def test_observer_records_work_and_excludes_pause_and_return(hass: HomeAssistant):
    """Ten real mowing minutes count, not the much longer pause and return."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    for old, new, minute in [
        ("docked", "mowing", 0),
        ("mowing", "paused", 6),
        ("paused", "mowing", 60),
        ("mowing", "returning", 65),
        ("returning", "docked", 70),
    ]:
        await observer.async_handle_event(_event(old, new, minute))
    assert (
        coordinator._state.last_mowing_at == (NOW + timedelta(minutes=70)).isoformat()
    )
    assert coordinator._state.last_mowing_source == "robot_estimate"
    assert (
        coordinator._state.maintenance_history[-1]["details"]["active_seconds"] == 660
    )


@pytest.mark.parametrize("interruption", ["error", "unknown", "unavailable", "idle"])
async def test_interrupted_robot_does_not_confirm_mowing(hass, interruption):
    """A fault or missing state breaks the chain even after sufficient work."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    await observer.async_handle_event(_event("docked", "mowing", 0))
    await observer.async_handle_event(_event("mowing", interruption, 30))
    await observer.async_handle_event(_event(interruption, "docked", 40))
    assert coordinator._state.last_mowing is None


async def test_short_start_and_startup_state_do_not_confirm_mowing(hass):
    """Short work and a restored mowing state provide no completion proof."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    await observer.async_handle_event(_event("docked", "mowing", 0))
    await observer.async_handle_event(_event("mowing", "docked", 1))
    await observer.async_handle_event(_event(None, "mowing", 20))
    await observer.async_handle_event(_event("mowing", "docked", 50))
    assert coordinator._state.last_mowing is None


async def test_attribute_reports_do_not_restart_active_time(hass):
    """Progress and battery attribute changes preserve the active segment."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    await observer.async_handle_event(_event("docked", "mowing", 0))
    await observer.async_handle_event(_event("mowing", "mowing", 9))
    await observer.async_handle_event(_event("mowing", "docked", 10))
    assert coordinator._state.last_mowing is not None


async def test_completion_input_disables_robot_estimation(hass):
    """Authoritative input and robot status do not double-record sessions."""
    coordinator = _coordinator(hass, mowed_entity="binary_sensor.knoxx_done")
    with patch(
        "custom_components.rasenpflege_assistent.mowing.async_track_state_change_event"
    ) as subscribe:
        MowingObserver(coordinator).subscribe(coordinator.config_entry)
    subscribe.assert_not_called()


async def test_distinct_sessions_same_day_and_duplicate_event(hass):
    """Two runs within twelve hours count; replaying an event does not."""
    coordinator = _coordinator(hass)
    await coordinator.async_mark_mowed(
        event_id="run1", recorded_at=NOW, source="completion_input"
    )
    await coordinator.async_mark_mowed(
        event_id="run1", recorded_at=NOW, source="completion_input"
    )
    await coordinator.async_mark_mowed(
        event_id="run2", recorded_at=NOW + timedelta(hours=1), source="completion_input"
    )
    assert len(coordinator._state.maintenance_history) == 2
    await coordinator.async_undo_last_action()
    assert coordinator._state.last_mowing_at == NOW.isoformat()
    assert coordinator._state.last_mowing_event_id == "run1"


async def test_legacy_mowing_date_migrates_to_local_midnight(hass):
    """Upgrade keeps the day and explicitly marks its time as estimated."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    coordinator = _coordinator(hass)
    with patch.object(
        coordinator._store,
        "async_load",
        new=AsyncMock(
            return_value={
                "last_mowing": "2026-07-20",
                "local_day_model": True,
            }
        ),
    ):
        await coordinator._async_setup()
    assert coordinator._state.last_mowing == "2026-07-20"
    assert coordinator._state.last_mowing_at == "2026-07-19T22:00:00+00:00"
    assert coordinator._state.last_mowing_source == "legacy_date"


async def test_clearing_mowing_date_after_manual_record(hass):
    """Clearing works even if no previous configured date ever existed."""
    coordinator = _coordinator(hass, last_mowing=None, last_mowing_revision="changed")
    with patch.object(
        coordinator._store,
        "async_load",
        new=AsyncMock(
            return_value={
                "last_mowing": "2026-07-20",
                "last_mowing_at": NOW.isoformat(),
                "local_day_model": True,
            }
        ),
    ):
        await coordinator._async_setup()
    assert coordinator._state.last_mowing is None
    assert coordinator._state.last_mowing_at is None


async def test_wet_wait_extends_timestamp_without_resetting_last_mow(hass):
    """Nässe and interval are combined and no fictional mowing is recorded."""
    coordinator = _coordinator(hass)
    coordinator._state.last_watering_at = NOW.isoformat()
    interval_end = NOW + timedelta(hours=2)
    mower = {"status": "wait_to_mow", "next_date": NOW.date(), "next_at": interval_end}
    until, _ = coordinator._pause_mower_when_wet(NOW, mower)
    assert mower["status"] == "pause_wet"
    assert mower["next_at"] == max(until, interval_end)
    assert coordinator._state.last_mowing is None


async def test_real_state_subscription_records_robot_session(hass, freezer):
    """The HA event subscription records observed work without device commands."""
    freezer.move_to(NOW)
    coordinator = _coordinator(hass)
    entry = coordinator.config_entry
    entry.add_to_hass(hass)
    hass.states.async_set("lawn_mower.knoxx", "docked")
    observer = MowingObserver(coordinator)
    observer.subscribe(entry)
    hass.states.async_set("lawn_mower.knoxx", "mowing")
    await hass.async_block_till_done()
    freezer.move_to(NOW + timedelta(minutes=11))
    hass.states.async_set("lawn_mower.knoxx", "docked")
    await hass.async_block_till_done()
    assert coordinator._state.last_mowing_source == "robot_estimate"
    assert len(coordinator._state.maintenance_history) == 1


@pytest.mark.parametrize(
    "temperature,status", [(None, "collecting_data"), (-1, "pause_frost")]
)
async def test_old_growth_history_cannot_override_missing_temperature_or_frost(
    hass, freezer, temperature, status
):
    """Warm historical samples cannot create a current unsafe recommendation."""
    freezer.move_to(NOW)
    coordinator = _coordinator(hass)
    coordinator._state.daily_temperature_history = [20] * 7
    coordinator._state.soil_water_mm = 30
    coordinator._state.last_mowing = "2026-07-01"
    coordinator._state.last_mowing_at = "2026-07-01T10:00:00+00:00"
    coordinator._async_forecast = AsyncMock(return_value=[])
    if temperature is not None:
        hass.states.async_set(
            "weather.openweathermap",
            "sunny",
            {"temperature": temperature, "temperature_unit": "°C"},
        )
    data = await coordinator._async_update_data()
    assert data.mower_status == status
    assert data.next_mowing_at is None
    assert data.next_mowing_date is None
    if temperature is None:
        assert data.mowing_confidence == "low"


async def test_completed_robot_session_persists_active_duration(
    hass, enable_custom_integrations
):
    """Pause and return travel do not inflate the published mowing estimate."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    for old, new, minute in [
        ("docked", "mowing", 0),
        ("mowing", "paused", 10),
        ("paused", "mowing", 20),
        ("mowing", "returning", 30),
        ("returning", "docked", 40),
    ]:
        await observer.async_handle_event(_event(old, new, minute))
    state = coordinator._state
    assert state.last_robot_session_started_at == NOW.isoformat()
    assert (
        state.last_robot_session_finished_at
        == (NOW + timedelta(minutes=40)).isoformat()
    )
    assert state.last_robot_session_active_seconds == 1200
    assert state.as_dict()["last_robot_session_active_seconds"] == 1200


async def test_undo_robot_session_restores_previous_session_details(hass):
    """Undo must keep the mowing date and corresponding robot session consistent."""
    coordinator = _coordinator(hass)
    first = NOW - timedelta(days=2)
    await coordinator.async_mark_mowed(
        recorded_at=first,
        source="robot_estimate",
        active_seconds=600,
        session_started_at=first - timedelta(minutes=10),
    )
    await coordinator.async_mark_mowed(
        recorded_at=NOW,
        source="robot_estimate",
        active_seconds=1200,
        session_started_at=NOW - timedelta(minutes=20),
    )
    await coordinator.async_undo_last_action()
    assert coordinator._state.last_robot_session_finished_at == first.isoformat()
    assert coordinator._state.last_robot_session_active_seconds == 600


async def test_backdated_mowing_keeps_newer_last_mowing(hass):
    """A late-entered historical event does not move the next mowing schedule backwards."""
    coordinator = _coordinator(hass)
    await coordinator.async_mark_mowed(recorded_at=NOW)
    await coordinator.async_mark_mowed(recorded_at=NOW - timedelta(days=3))
    assert coordinator._state.last_mowing_at == NOW.isoformat()
    assert len(coordinator._state.maintenance_history) == 2
    await coordinator.async_undo_last_action()
    assert coordinator._state.last_mowing_at == NOW.isoformat()


async def test_live_robot_minutes_update_without_weather_request(hass):
    """The local observer tick updates active duration without forecast polling."""
    coordinator = _coordinator(hass)
    observer = MowingObserver(coordinator)
    await observer.async_handle_event(_event("docked", "mowing", 0))
    with patch(
        "custom_components.rasenpflege_assistent.mowing.dt_util.now",
        return_value=NOW + timedelta(minutes=5),
    ):
        assert observer.diagnostic_attributes()["active_minutes"] == 5
        observer._tick(NOW + timedelta(minutes=5))
    coordinator.async_request_refresh.assert_not_awaited()
    await observer.async_handle_event(_event("mowing", "paused", 10))
    with patch(
        "custom_components.rasenpflege_assistent.mowing.dt_util.now",
        return_value=NOW + timedelta(minutes=20),
    ):
        assert observer.diagnostic_attributes()["active_minutes"] == 10
        assert observer.diagnostic_attributes()["status"] == "waiting_for_dock"
