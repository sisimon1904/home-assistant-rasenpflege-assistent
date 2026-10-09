"""v3.18.0 dashboard ownership, care history and notification regressions.

File: tests/test_release_3180.py

Exercise server-side safeguards with HA fixtures, including stale journal
identity, physical/automatic records, read permissions and failed persistence.
Browser DOM behavior is covered separately by tests/browser/test-panel.mjs.
"""

import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components import frontend, websocket_api
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.dashboard import (
    PANEL_PATH,
    async_setup_dashboard,
    async_unload_dashboard,
    websocket_dashboard_action,
    websocket_dashboard_data,
)
from custom_components.rasenpflege_assistent.models import LawnData
from custom_components.rasenpflege_assistent.notifications import (
    CareNotifier,
    async_setup_notifications,
)
from tests.test_services import _entry
from tests.test_web_dashboard import loaded_entry


async def test_existing_foreign_panel_survives_unload(hass):
    entry = loaded_entry(hass)
    frontend.async_register_built_in_panel(hass, "map", frontend_url_path=PANEL_PATH)
    owned = hass.data[frontend.DATA_PANELS][PANEL_PATH]
    with patch.object(
        hass, "http", Mock(async_register_static_paths=AsyncMock()), create=True
    ):
        await async_setup_dashboard(hass)
        async_unload_dashboard(hass, entry.entry_id)
    assert hass.data[frontend.DATA_PANELS][PANEL_PATH] is owned


async def test_concurrent_lawn_setup_registers_assets_once(hass):
    async def yield_registration(_paths):
        await asyncio.sleep(0)

    http = Mock(async_register_static_paths=AsyncMock(side_effect=yield_registration))
    with patch.object(hass, "http", http, create=True):
        await asyncio.gather(async_setup_dashboard(hass), async_setup_dashboard(hass))
    http.async_register_static_paths.assert_awaited_once()
    assert frontend.async_panel_exists(hass, PANEL_PATH)


async def test_replaced_panel_survives_unload(hass):
    entry = loaded_entry(hass)
    with patch.object(
        hass, "http", Mock(async_register_static_paths=AsyncMock()), create=True
    ):
        await async_setup_dashboard(hass)
    frontend.async_remove_panel(hass, PANEL_PATH)
    frontend.async_register_built_in_panel(hass, "map", frontend_url_path=PANEL_PATH)
    async_unload_dashboard(hass, entry.entry_id)
    assert frontend.async_panel_exists(hass, PANEL_PATH)


@pytest.mark.parametrize("action", ["mowing", "watering", "fertilizing"])
async def test_latest_manual_record_can_be_undone(hass, action):
    entry = _entry(hass)
    coordinator = entry.runtime_data
    if action == "mowing":
        await coordinator.async_mark_mowed()
    elif action == "watering":
        await coordinator.async_mark_watered(3)
    else:
        await coordinator.async_mark_fertilized("10-5-5", 1)
    event = coordinator.state.maintenance_history[-1]
    await coordinator.async_undo_last_manual(event["timestamp"])
    assert not coordinator.state.maintenance_history
    assert not coordinator.state.water_usage


@pytest.mark.parametrize("source", ["robot_estimate", "completion_input"])
async def test_automatic_mowing_cannot_be_removed_by_dashboard(hass, source):
    coordinator = _entry(hass).runtime_data
    await coordinator.async_mark_mowed(source=source)
    event = coordinator.state.maintenance_history[-1]
    with pytest.raises(ServiceValidationError, match="manual"):
        await coordinator.async_undo_last_manual(event["timestamp"])
    assert len(coordinator.state.maintenance_history) == 1


async def test_stale_journal_identity_does_not_undo_new_event(hass, freezer):
    coordinator = _entry(hass).runtime_data
    await coordinator.async_mark_mowed()
    timestamp = coordinator.state.maintenance_history[-1]["timestamp"]
    freezer.tick(timedelta(seconds=1))
    await coordinator.async_mark_fertilized()
    with pytest.raises(ServiceValidationError, match="changed"):
        await coordinator.async_undo_last_manual(timestamp)
    assert len(coordinator.state.maintenance_history) == 2


async def test_physical_water_cannot_be_removed_by_dashboard(hass):
    coordinator = _entry(hass).runtime_data
    await coordinator.async_mark_watered(2)
    coordinator.state.water_usage[-1]["source"] = "irrigation"
    event = coordinator.state.maintenance_history[-1]
    with pytest.raises(ServiceValidationError, match="Physical"):
        await coordinator.async_undo_last_manual(event["timestamp"])
    assert len(coordinator.state.water_usage) == 1


async def test_failed_manual_undo_rolls_back(hass):
    coordinator = _entry(hass).runtime_data
    await coordinator.async_mark_watered(2)
    before = deepcopy(coordinator.state.as_dict())
    coordinator._store.async_save.side_effect = HomeAssistantError("disk")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_undo_last_manual(
            coordinator.state.maintenance_history[-1]["timestamp"]
        )
    assert coordinator.state.as_dict() == before


async def test_dashboard_history_strips_snapshots_and_blocks_partial_read(hass):
    entry = loaded_entry(hass)
    real = _entry(hass).runtime_data
    await real.async_mark_mowed()
    entry.runtime_data = real
    connection = Mock()
    connection.user.is_admin = True
    connection.user.permissions.check_entity.return_value = True
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 1, "config_entry_id": entry.entry_id}
    )
    payload = connection.send_result.call_args.args[1]
    assert "previous" not in payload["journal"][0]
    assert payload["journal"][0]["can_undo"]
    connection.user.permissions.check_entity.return_value = False
    connection.send_result.reset_mock()
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 2, "config_entry_id": entry.entry_id}
    )
    connection.send_result.assert_not_called()
    assert connection.send_error.call_args.args[1] == "unauthorized"


@pytest.mark.parametrize(
    "action,data",
    [
        ("undo_last_manual", {"timestamp": "x"}),
        ("notification_settings", {"enabled": True, "interval_hours": 1}),
    ],
)
async def test_read_only_cannot_change_history_or_notifications(
    hass, hass_ws_client, hass_read_only_access_token, action, data
):
    entry = loaded_entry(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    websocket_api.async_register_command(hass, websocket_dashboard_action)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": action,
            "data": data,
        }
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"


def notifier(hass):
    coordinator = _entry(hass).runtime_data
    coordinator.async_set_updated_data(LawnData(watering_recommended=True))
    result = CareNotifier(coordinator)
    result.store.async_save = AsyncMock()
    return result


async def test_notifications_opt_in_and_persistent_cooldown(hass, freezer):
    first = notifier(hass)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await first.async_check()
        create.assert_not_called()
        await first.async_configure(True, 6)
        await first.async_check()
        create.assert_called_once()
        await first.async_check()
        create.assert_called_once()
        stored = first.store.async_save.call_args.args[0]
        second = notifier(hass)
        second.store.async_load = AsyncMock(return_value=stored)
        await second.async_initialize()
        await second.async_check()
        create.assert_called_once()
        freezer.tick(timedelta(hours=6))
        await second.async_check()
        assert create.call_count == 2


async def test_failed_notification_settings_and_cooldown_do_not_publish(hass):
    item = notifier(hass)
    item.store.async_save.side_effect = HomeAssistantError("disk")
    with pytest.raises(HomeAssistantError):
        await item.async_configure(True, 1)
    assert not item.enabled
    item.enabled = True
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        with pytest.raises(HomeAssistantError):
            await item.async_check()
        create.assert_not_called()
        assert not item._sent


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("target_reached", 0),
        ("stopped_manually", 0),
        ("no_flow", 1),
        (None, 0),
        (True, 0),
        (["bad"], 0),
        ({"bad": 1}, 0),
    ],
)
async def test_aborted_irrigation_notification(hass, reason, expected):
    item = notifier(hass)
    item.coordinator.async_set_updated_data(LawnData())
    item.coordinator.state.irrigation_last_session = {
        "finished_at": dt_util.now().isoformat(),
        "reason": reason,
    }
    await item.async_configure(True, 24)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        assert create.call_count == expected


@pytest.mark.parametrize(
    "bad",
    [None, [], {"enabled": "yes", "interval_hours": True, "sent": {"care": "invalid"}}],
)
async def test_malformed_optional_notification_data(hass, bad):
    item = notifier(hass)
    item.store.async_load = AsyncMock(return_value=bad)
    await item.async_initialize()
    assert item.preferences == {
        "enabled": False,
        "interval_hours": 24,
        "quiet_start": "",
        "quiet_end": "",
        "changes_only": False,
        "care_enabled": True,
        "irrigation_enabled": True,
        "care_interval_hours": 24,
        "irrigation_interval_hours": 24,
    }


async def test_notification_stops_after_unload(hass):
    item = notifier(hass)
    await item.async_configure(True, 1)
    item.stop()
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        await item.async_check()
        create.assert_not_called()


async def test_optional_notification_read_failure_keeps_entry_listener_safe(hass):
    item = notifier(hass)
    with (
        patch.object(
            CareNotifier,
            "async_initialize",
            new=AsyncMock(side_effect=HomeAssistantError("disk")),
        ),
        patch.object(type(item.entry), "async_on_unload") as on_unload,
    ):
        await async_setup_notifications(item.coordinator)
    manager = hass.data[f"{DOMAIN}_notifiers"][item.entry.entry_id]
    assert not manager.enabled
    on_unload.call_args.args[0]()
    assert manager._stopped
    assert not hass.data[f"{DOMAIN}_notifiers"]


async def test_coalesced_notifications_do_not_spam_on_update_burst(hass):
    item = notifier(hass)
    await item.async_configure(True, 1)
    with patch(
        "custom_components.rasenpflege_assistent.notifications.persistent_notification.async_create"
    ) as create:
        item.updated()
        item.updated()
        await hass.async_block_till_done()
        assert create.call_count == 1
        assert not item._pending


async def test_saved_observation_response_retains_measurement_clock_not_context(hass):
    entry = loaded_entry(hass)
    real = _entry(hass).runtime_data
    entry.runtime_data = real
    now = dt_util.now()
    row = {
        "timestamp": now.isoformat(),
        "context": "private_entity_identity",
        "modeled_percent": 60,
        "measured_percent": 55,
        "sensor_reported_at": (now - timedelta(minutes=10)).isoformat(),
        "rain_mm": 2,
        "rain_known": True,
        "et_mm": 1,
    }
    real.state.model_observations = [row]
    connection = Mock()
    connection.user.is_admin = False
    connection.user.permissions.check_entity.return_value = True
    await websocket_dashboard_data.__wrapped__(
        hass, connection, {"id": 1, "config_entry_id": entry.entry_id}
    )
    data = connection.send_result.call_args.args[1]
    assert data["observations"][0]["sensor_reported_at"] == row["sensor_reported_at"]
    assert "context" not in data["observations"][0]
    assert data["notifications"] is None


@pytest.mark.parametrize(
    "action,data",
    [
        ("notification_settings", {"enabled": True, "interval_hours": 6}),
        ("undo_last_manual", {"timestamp": "shown"}),
    ],
)
async def test_admin_actions_use_selected_entry_manager(
    hass, hass_ws_client, action, data
):
    entry = loaded_entry(hass)
    other = loaded_entry(hass)
    selected, unrelated = (
        Mock(async_configure=AsyncMock()),
        Mock(async_configure=AsyncMock()),
    )
    entry.runtime_data.async_undo_last_manual = AsyncMock()
    hass.data[f"{DOMAIN}_notifiers"] = {
        entry.entry_id: selected,
        other.entry_id: unrelated,
    }
    client = await hass_ws_client(hass)
    websocket_api.async_register_command(hass, websocket_dashboard_action)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": action,
            "data": data,
        }
    )
    assert (await client.receive_json())["success"]
    unrelated.async_configure.assert_not_called()
    if action == "notification_settings":
        selected.async_configure.assert_awaited_once_with(
            enabled=True, interval_hours=6
        )
    else:
        entry.runtime_data.async_undo_last_manual.assert_awaited_once_with("shown")
