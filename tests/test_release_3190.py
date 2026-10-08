"""v3.19.0 notification policies and permission-filtered usage regressions.

File: tests/test_release_3190.py

Check quiet-hour boundaries, legacy preference migration, atomic persistence,
deduplication after restart and calendar allocation of recorded quantities.
No fixture controls actual irrigation hardware.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.dashboard import websocket_dashboard_data
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.notifications import CareNotifier
from custom_components.rasenpflege_assistent.planning import consumption_evidence
from tests.test_release_3180 import notifier
from tests.test_services import _entry
from tests.test_web_dashboard import loaded_entry


def test_consumption_separates_estimates_gaps_and_legacy_records():
    today = dt_util.parse_date("2026-10-08")
    records = [
        {
            "date": "2026-10-08",
            "liters": 100,
            "source": "irrigation",
            "volume_estimated": False,
            "measurement_gap": False,
        },
        {
            "date": "2026-10-08",
            "liters": 40,
            "source": "irrigation",
            "volume_estimated": True,
            "measurement_gap": False,
        },
        {
            "date": "2026-10-08",
            "liters": 20,
            "source": "irrigation",
            "volume_estimated": False,
            "measurement_gap": True,
        },
        {"date": "2026-10-08", "liters": 30, "source": "irrigation"},
        {"date": "2026-10-08", "liters": 10, "source": "manual_record"},
        {"date": "2026-10-08", "liters": None, "source": "irrigation"},
    ]
    totals = consumption_evidence(records, today)
    assert totals["week_liters"] == 200
    assert totals["week_measured_liters"] == 100
    assert totals["week_estimated_liters"] == 40
    assert totals["week_uncertain_liters"] == 50
    assert totals["week_manual_record_liters"] == 10
    assert totals["week_unmetered_sessions"] == 1


async def test_change_only_notifies_returning_mowing_window(hass, freezer):
    item = notifier(hass)
    item.coordinator.async_set_updated_data(LawnData(mower_start_recommended=True))
    await item.async_configure(True, 1, changes_only=True)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        item.coordinator.async_set_updated_data(LawnData())
        await item.async_check()
        item.coordinator.async_set_updated_data(LawnData(mower_start_recommended=True))
        await item.async_check()
        assert create.call_count == 1
        freezer.tick(timedelta(hours=1))
        await item.async_check()
        assert create.call_count == 2


@pytest.mark.parametrize(
    "clock,quiet", [("2026-10-08T07:00:00Z", True), ("2026-10-08T15:00:00Z", False)]
)
async def test_daytime_quiet_boundaries(hass, freezer, clock, quiet):
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to(clock)
    item = notifier(hass)
    await item.async_configure(True, 1, "09:00", "17:00")
    assert item.quiet_now() == quiet


@pytest.mark.parametrize(
    "start,end",
    [
        ("24:00", "07:00"),
        ("22:00", ""),
        ("", "07:00"),
        ("22:00", "22:00"),
        ("bad", "07:00"),
        (None, "07:00"),
    ],
)
async def test_invalid_quiet_settings_never_persist(hass, start, end):
    item = notifier(hass)
    with pytest.raises(HomeAssistantError):
        await item.async_configure(True, 6, start, end, True)
    item.store.async_save.assert_not_called()
    assert not item.enabled


@pytest.mark.parametrize(
    "clock,quiet",
    [
        ("2026-10-08T19:59:00Z", False),
        ("2026-10-08T20:00:00Z", True),
        ("2026-10-09T04:59:00Z", True),
        ("2026-10-09T05:00:00Z", False),
        ("2026-10-25T00:30:00Z", True),
        ("2026-10-25T01:30:00Z", True),
    ],
)
async def test_overnight_quiet_hours_use_ha_timezone(hass, freezer, clock, quiet):
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to(clock)
    item = notifier(hass)
    await item.async_configure(True, 1, "22:00", "07:00")
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        assert create.call_count == (0 if quiet else 1)


async def test_change_only_retains_cooldown_and_recognizes_new_care(hass, freezer):
    item = notifier(hass)
    await item.async_configure(True, 1, changes_only=True)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        stored = item.store.async_save.call_args.args[0]
        restored = notifier(hass)
        restored.store.async_load = AsyncMock(return_value=stored)
        await restored.async_initialize()
        freezer.tick(timedelta(hours=2))
        await restored.async_check()
        assert create.call_count == 1
        restored.coordinator.async_set_updated_data(
            LawnData(mower_start_recommended=True)
        )
        await restored.async_check()
        assert create.call_count == 2
        restored.coordinator.async_set_updated_data(
            LawnData(fertilizing_recommended=True)
        )
        await restored.async_check()
        assert create.call_count == 2


async def test_identical_irrigation_abort_not_repeated_after_restart(hass, freezer):
    item = notifier(hass)
    item.coordinator.async_set_updated_data(LawnData())
    item.coordinator.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "reason": "no_flow",
    }
    await item.async_configure(True, 1)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        stored = item.store.async_save.call_args.args[0]
        restored = CareNotifier(item.coordinator)
        restored.store.async_save = AsyncMock()
        restored.store.async_load = AsyncMock(return_value=stored)
        await restored.async_initialize()
        freezer.tick(timedelta(hours=2))
        await restored.async_check()
        assert create.call_count == 1
        restored.coordinator.state.irrigation_last_session["finished_at"] = (
            dt_util.now().isoformat()
        )
        await restored.async_check()
        assert create.call_count == 2


async def test_failed_new_preferences_preserve_previous_values(hass):
    item = notifier(hass)
    await item.async_configure(True, 6, "22:00", "07:00", True)
    before = item.preferences.copy()
    item.store.async_save.side_effect = HomeAssistantError("disk")
    with pytest.raises(HomeAssistantError):
        await item.async_configure(False, 1, "09:00", "17:00", False)
    assert item.preferences == before


async def test_malformed_new_preferences_fall_back_safely(hass):
    item = notifier(hass)
    item.store.async_load = AsyncMock(
        return_value={
            "enabled": True,
            "quiet_start": [],
            "quiet_end": "07:00",
            "changes_only": "yes",
            "signatures": {"care": [], "other": "x"},
        }
    )
    await item.async_initialize()
    assert item.quiet_start == item.quiet_end == ""
    assert not item.changes_only
    assert not item._signatures


async def test_dashboard_usage_respects_calendar_allocations_and_unknown_amount(
    hass, freezer
):
    freezer.move_to("2026-10-08T12:00:00Z")
    entry = loaded_entry(hass)
    entry.runtime_data = _entry(hass).runtime_data
    entry.runtime_data.state.water_usage = [
        {
            "date": "2026-10-06",
            "liters": 100,
            "source": "irrigation",
            "allocations": [
                {"date": "2026-10-05", "liters": 60},
                {"date": "2026-10-06", "liters": 40},
            ],
        },
        {"date": "2026-10-07", "liters": 50, "source": "manual_estimate"},
        {
            "date": "2026-10-08",
            "liters": None,
            "source": "irrigation",
            "measurement_gap": True,
        },
        {"date": "2026-09-30", "liters": 1000, "source": "manual_record"},
    ]
    connection = Mock()
    connection.user.is_admin = False
    connection.user.permissions.check_entity.return_value = True
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 1, "config_entry_id": entry.entry_id}
    )
    data = connection.send_result.call_args.args[1]
    assert data["consumption"]["week_liters"] == 150
    assert data["consumption"]["month_liters"] == 150
    assert data["consumption"]["week_unmetered_sessions"] == 1
    assert data["consumption"]["week_measurement_gap_sessions"] == 1
    assert data["notifications"] is None
