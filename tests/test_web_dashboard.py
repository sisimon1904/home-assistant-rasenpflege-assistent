"""Web dashboard authentication, routing, permission and lifecycle regressions.

File: tests/test_web_dashboard.py

Exercise real HA WebSocket authentication and service validation. Static panel
registration is isolated from the optional frontend package; this suite does
not claim real physical valve behavior or external network availability.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components import frontend, websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent import async_setup
from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.dashboard import (
    PANEL_PATH,
    async_setup_dashboard,
    async_unload_dashboard,
    websocket_dashboard,
    websocket_dashboard_action,
)


def loaded_entry(hass, name="Lawn"):
    """Create a loaded lawn with an actual registry identity."""
    entry = MockConfigEntry(domain=DOMAIN, title=name)
    entry.add_to_hass(hass)
    entry.runtime_data = Mock()
    entry.runtime_data.irrigation_controller.async_set_auto_enabled = AsyncMock()
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_status", config_entry=entry
    )
    return entry


async def register_commands(hass, hass_ws_client, access_token=None):
    """Initialize the actual HA WebSocket endpoint before custom commands."""
    client = (
        await hass_ws_client(hass)
        if access_token is None
        else await hass_ws_client(hass, access_token=access_token)
    )
    websocket_api.async_register_command(hass, websocket_dashboard)
    websocket_api.async_register_command(hass, websocket_dashboard_action)
    return client


async def test_dashboard_discovery_uses_registry_ids_and_excludes_unloaded(
    hass, hass_ws_client
):
    loaded = loaded_entry(hass, "<b>Garden</b>")
    unloaded = loaded_entry(hass, "Hidden")
    unloaded._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
    client = await register_commands(hass, hass_ws_client)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/dashboard"})
    result = await client.receive_json()
    assert result["success"]
    lawns = result["result"]["lawns"]
    assert len(lawns) == 1
    assert lawns[0]["entry_id"] == loaded.entry_id
    assert lawns[0]["name"] == "<b>Garden</b>"
    assert lawns[0]["entities"]["status"].startswith("sensor.")
    assert not lawns[0]["irrigation_configured"]


async def test_read_only_user_cannot_execute_dashboard_actions(
    hass, hass_ws_client, hass_read_only_access_token
):
    entry = loaded_entry(hass)
    client = await register_commands(hass, hass_ws_client, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/dashboard"})
    result = await client.receive_json()
    assert not result["result"]["can_control"]
    await client.send_json(
        {
            "id": 2,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": "enable_automatic",
        }
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
    entry.runtime_data.irrigation_controller.async_set_auto_enabled.assert_not_called()


async def test_discovery_filters_entities_without_read_permission(
    hass, hass_admin_user
):
    loaded_entry(hass)
    connection = Mock()
    connection.user = Mock(is_admin=False)
    connection.user.permissions.check_entity.return_value = False
    websocket_dashboard(hass, connection, {"id": 1})
    assert connection.send_result.call_args.args[1]["lawns"] == []


@pytest.mark.parametrize("action", ["enable_automatic", "disable_automatic"])
async def test_automatic_toggle_delegates_to_safety_controller(
    hass, hass_ws_client, action
):
    entry = loaded_entry(hass)
    client = await register_commands(hass, hass_ws_client)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": action,
        }
    )
    assert (await client.receive_json())["success"]
    entry.runtime_data.irrigation_controller.async_set_auto_enabled.assert_awaited_once_with(
        action == "enable_automatic"
    )


@pytest.mark.parametrize(
    "data",
    [
        {"config_entry_id": "other"},
        {"target_mm": -1},
        {"target_mm": "inf"},
        {"unknown": True},
    ],
)
async def test_dashboard_action_rejects_overrides_and_invalid_doses(
    hass, hass_ws_client, data
):
    entry = loaded_entry(hass)
    await async_setup(hass, {})
    client = await register_commands(hass, hass_ws_client)
    with patch.object(
        entry.runtime_data.irrigation_controller, "async_start", new=AsyncMock()
    ) as start:
        await client.send_json(
            {
                "id": 1,
                "type": f"{DOMAIN}/dashboard_action",
                "config_entry_id": entry.entry_id,
                "action": "start_irrigation",
                "data": data,
            }
        )
        assert not (await client.receive_json())["success"]
        start.assert_not_called()


async def test_action_keeps_context_and_selected_lawn(
    hass, hass_ws_client, hass_admin_user
):
    entry = loaded_entry(hass)
    client = await register_commands(hass, hass_ws_client)
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await client.send_json(
            {
                "id": 1,
                "type": f"{DOMAIN}/dashboard_action",
                "config_entry_id": entry.entry_id,
                "action": "stop_irrigation",
            }
        )
        assert (await client.receive_json())["success"]
        args = service.call_args
        assert args.args == (
            DOMAIN,
            "stop_irrigation",
            {"config_entry_id": entry.entry_id},
        )
        assert args.kwargs["blocking"]
        assert args.kwargs["context"].user_id == hass_admin_user.id


@pytest.mark.parametrize(
    "state", [ConfigEntryState.NOT_LOADED, ConfigEntryState.SETUP_ERROR]
)
async def test_unloaded_lawn_cannot_execute_actions(hass, hass_ws_client, state):
    entry = loaded_entry(hass)
    entry._async_set_state(hass, state, None)
    client = await register_commands(hass, hass_ws_client)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/dashboard_action",
            "config_entry_id": entry.entry_id,
            "action": "enable_automatic",
        }
    )
    assert not (await client.receive_json())["success"]
    entry.runtime_data.irrigation_controller.async_set_auto_enabled.assert_not_called()


async def test_panel_registration_and_last_unload_are_idempotent(hass):
    first, second = loaded_entry(hass), loaded_entry(hass, "Other lawn")
    http = Mock(async_register_static_paths=AsyncMock())
    with patch.object(hass, "http", http, create=True):
        await async_setup_dashboard(hass)
        await async_setup_dashboard(hass)
        http.async_register_static_paths.assert_awaited_once()
        assert frontend.async_panel_exists(hass, PANEL_PATH)
        async_unload_dashboard(hass, first.entry_id)
        assert frontend.async_panel_exists(hass, PANEL_PATH)
        first._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
        async_unload_dashboard(hass, second.entry_id)
        assert not frontend.async_panel_exists(hass, PANEL_PATH)
        await async_setup_dashboard(hass)
        assert frontend.async_panel_exists(hass, PANEL_PATH)
        http.async_register_static_paths.assert_awaited_once()
