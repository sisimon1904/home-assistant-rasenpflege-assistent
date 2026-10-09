"""v3.20.0 quiet-state observation, independent hints and water-ledger checks.

File: tests/test_release_3200.py

Reproduce the lost returning recommendation during quiet hours. Validate
restart/cooldown/persistence behavior, full authorized ledger export payloads,
and date-based consumption without treating unknown quantities as zero.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.dashboard import websocket_dashboard_data
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.notifications import CareNotifier
from custom_components.rasenpflege_assistent.planning import daily_consumption
from tests.test_release_3180 import notifier
from tests.test_services import _entry
from tests.test_web_dashboard import loaded_entry


async def test_returning_mowing_during_quiet_is_not_lost_after_restart(hass, freezer):
    item = notifier(hass)
    item.coordinator.async_set_updated_data(LawnData(mower_start_recommended=True))
    await item.async_configure(True, 1, changes_only=True)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        with patch.object(item, "quiet_now", return_value=True):
            item.coordinator.async_set_updated_data(LawnData())
            await item.async_check()
            item.coordinator.async_set_updated_data(
                LawnData(mower_start_recommended=True)
            )
            await item.async_check()
        assert create.call_count == 1
        stored = item.store.async_save.call_args.args[0]
        assert stored["care_pending"]
        restored = CareNotifier(item.coordinator)
        restored.store.async_load = AsyncMock(return_value=stored)
        restored.store.async_save = AsyncMock()
        await restored.async_initialize()
        await restored.async_check()
        assert create.call_count == 1
        freezer.tick(timedelta(hours=2))
        await restored.async_check()
        assert create.call_count == 2
        await restored.async_check()
        assert create.call_count == 2


async def test_withdrawn_quiet_recommendation_is_not_published_later(hass, freezer):
    item = notifier(hass)
    await item.async_configure(True, 1, changes_only=True)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        with patch.object(item, "quiet_now", return_value=True):
            await item.async_check()
            item.coordinator.async_set_updated_data(LawnData())
            await item.async_check()
        freezer.tick(timedelta(hours=2))
        await item.async_check()
        create.assert_not_called()


async def test_returning_mowing_while_watering_stays_due_is_a_change(hass, freezer):
    item = notifier(hass)
    item.coordinator.async_set_updated_data(
        LawnData(mower_start_recommended=True, watering_recommended=True)
    )
    await item.async_configure(True, 1, changes_only=True)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        item.coordinator.async_set_updated_data(LawnData(watering_recommended=True))
        await item.async_check()
        item.coordinator.async_set_updated_data(
            LawnData(mower_start_recommended=True, watering_recommended=True)
        )
        await item.async_check()
        freezer.tick(timedelta(hours=1))
        await item.async_check()
        assert create.call_count == 2


async def test_failed_quiet_observation_preserves_retry_state(hass):
    item = notifier(hass)
    await item.async_configure(True, 1, changes_only=True)
    item.store.async_save.side_effect = HomeAssistantError("disk")
    with (
        patch.object(item, "quiet_now", return_value=True),
        pytest.raises(HomeAssistantError),
    ):
        await item.async_check()
    assert item._care_observed == ""
    assert not item._care_pending


@pytest.mark.parametrize(
    "care,irrigation,count",
    [(False, True, 1), (True, False, 1), (False, False, 0), (True, True, 2)],
)
async def test_notification_categories_can_be_enabled_independently(
    hass, care, irrigation, count
):
    item = notifier(hass)
    item.coordinator.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "reason": "no_flow",
    }
    await item.async_configure(
        True, 1, care_enabled=care, irrigation_enabled=irrigation
    )
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        assert create.call_count == count


async def test_independent_category_cooldowns_are_restored(hass, freezer):
    item = notifier(hass)
    item.coordinator.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "reason": "no_flow",
    }
    await item.async_configure(
        True, 24, care_interval_hours=6, irrigation_interval_hours=1
    )
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        stored = item.store.async_save.call_args.args[0]
        restored = CareNotifier(item.coordinator)
        restored.store.async_load = AsyncMock(return_value=stored)
        restored.store.async_save = AsyncMock()
        await restored.async_initialize()
        freezer.tick(timedelta(hours=2))
        item.coordinator.state.irrigation_last_session["finished_at"] = (
            dt_util.now().isoformat()
        )
        await restored.async_check()
        assert create.call_count == 3
        assert restored.care_interval_hours == 6
        assert restored.irrigation_interval_hours == 1


@pytest.mark.parametrize("hours", [1, 6, 24])
async def test_legacy_common_interval_migrates_to_both_categories(hass, hours):
    item = notifier(hass)
    item.store.async_load = AsyncMock(
        return_value={"enabled": True, "interval_hours": hours}
    )
    await item.async_initialize()
    assert item.care_enabled and item.irrigation_enabled
    assert item.care_interval_hours == item.irrigation_interval_hours == hours


@pytest.mark.parametrize(
    "settings",
    [
        {"care_interval_hours": True},
        {"irrigation_interval_hours": 2},
        {"care_enabled": "yes"},
        {"irrigation_enabled": 1},
    ],
)
async def test_invalid_category_preferences_do_not_persist(hass, settings):
    item = notifier(hass)
    with pytest.raises(HomeAssistantError):
        await item.async_configure(True, 1, **settings)
    item.store.async_save.assert_not_called()


def test_daily_quantities_use_allocations_and_keep_unknowns():
    records = [
        {
            "date": "2026-10-26",
            "liters": 100,
            "source": "irrigation",
            "measurement_gap": False,
            "volume_estimated": False,
            "allocations": [
                {"date": "2026-10-25", "liters": 60},
                {"date": "2026-10-26", "liters": 40},
            ],
            "allocation_estimated": True,
        },
        {"date": "2026-10-25", "liters": 20, "source": "manual_estimate"},
        {
            "date": "2026-10-26",
            "liters": None,
            "source": "irrigation",
            "measurement_gap": True,
        },
        {"date": "2026-10-24", "liters": None, "source": "irrigation"},
    ]
    rows = daily_consumption(records, date(2026, 10, 26), 7)
    assert len(rows) == 7
    assert rows[-1]["liters"] == 40
    assert rows[-1]["unknown_sessions"] == rows[-1]["gap_sessions"] == 1
    assert rows[-2]["measured"] == 60
    assert rows[-2]["manual_estimate"] == 20
    assert rows[-2]["liters"] == 80
    assert rows[-3]["liters"] is None
    assert rows[0]["sessions"] == 0
    assert rows[0]["liters"] == 0


def test_daily_periods_are_validated():
    with pytest.raises(ValueError):
        daily_consumption([], date(2026, 10, 9), 366)
    assert len(daily_consumption([], date(2026, 10, 9), 30)) == 30


async def test_full_water_ledger_is_authorized_and_strips_private_context(hass):
    entry = loaded_entry(hass)
    entry.runtime_data = _entry(hass).runtime_data
    entry.runtime_data.state.water_usage = [
        {
            "date": dt_util.now().date().isoformat(),
            "liters": 0.04,
            "source": "irrigation",
            "comparison_context": "private-valve",
            "session_id": "private-session",
            "volume_estimated": False,
            "measurement_gap": False,
        }
        for _ in range(50)
    ]
    connection = Mock()
    connection.user.is_admin = False
    connection.user.permissions.check_entity.return_value = True
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 1, "config_entry_id": entry.entry_id}
    )
    payload = connection.send_result.call_args.args[1]
    assert len(payload["water_records"]) == 50
    assert "private" not in str(payload["water_records"])
    assert len(payload["daily_consumption"]) == 30
    assert payload["notifications"] is None
    connection.send_result.reset_mock()
    connection.user.permissions.check_entity.return_value = False
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 2, "config_entry_id": entry.entry_id}
    )
    connection.send_result.assert_not_called()
