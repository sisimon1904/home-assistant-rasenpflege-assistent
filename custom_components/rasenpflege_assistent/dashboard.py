"""Authenticated web dashboard registration, entity discovery and action gateway.

File: custom_components/rasenpflege_assistent/dashboard.py

Serve a local custom panel through Home Assistant's existing HTTP/frontend stack.
The HA shell owns login and the WebSocket connection; no token, password, extra
port, external asset or weather polling is introduced. Entity discovery filters
each result using the current user's read permissions. Mutations require an
administrator on the server and delegate to the existing safety/service paths.
Static JavaScript contains no user data and is registered once per HA process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, INTEGRATION_VERSION

PANEL_PATH = "rasenpflege-assistent"
ASSET_PATH = "/rasenpflege_assistent_static"
_REGISTERED = f"{DOMAIN}_dashboard_registered"
ACTIONS = (
    "start_irrigation",
    "stop_irrigation",
    "suspend_irrigation",
    "record_mowing",
    "record_watering",
    "record_fertilizing",
    "enable_automatic",
    "disable_automatic",
)


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Register assets and the HA sidebar panel once; support headless installs.

    The manifest waits for configured frontend setup through after_dependencies.
    A headless instance has no HTTP server and simply keeps the integration's
    existing entities and actions. Static registrations are process-scoped, so
    config-entry reloads never add duplicate routes or replace another panel.
    """
    if getattr(hass, "http", None) is None:
        return
    if not hass.data.get(_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    ASSET_PATH,
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                )
            ]
        )
        websocket_api.async_register_command(hass, websocket_dashboard)
        websocket_api.async_register_command(hass, websocket_dashboard_action)
        hass.data[_REGISTERED] = True
    if frontend.async_panel_exists(hass, PANEL_PATH):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="lawn-care-dashboard",
        sidebar_title="Rasenpflege"
        if hass.config.language.startswith("de")
        else "Lawn care",
        sidebar_icon="mdi:grass",
        module_url=f"{ASSET_PATH}/panel.js?v={INTEGRATION_VERSION}",
        embed_iframe=False,
        trust_external=False,
    )


@callback
def async_unload_dashboard(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the navigation panel after the last successful entry unload.

    Assets/WebSocket handlers remain process-scoped for safe subsequent reloads.
    A failed physical shutdown or platform unload never reaches this callback.
    """
    if not any(
        entry.entry_id != entry_id and entry.state is ConfigEntryState.LOADED
        for entry in hass.config_entries.async_entries(DOMAIN)
    ):
        frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)


@callback
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/dashboard"})
def websocket_dashboard(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Discover actual entity IDs across loaded lawns, respecting read access.

    States and diagnostics travel over HA's already-authenticated state channel.
    Disabled or unreadable entities are not advertised; a user cannot discover
    an unrelated lawn merely by opening this panel. Names are returned as data
    and the frontend inserts them with textContent rather than executable HTML.
    """
    registry = er.async_get(hass)
    lawns = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        entities = {}
        prefix = f"{entry.entry_id}_"
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                entity.platform == DOMAIN
                and not entity.disabled
                and entity.unique_id.startswith(prefix)
                and connection.user.permissions.check_entity(
                    entity.entity_id, POLICY_READ
                )
            ):
                entities[entity.unique_id[len(prefix) :]] = entity.entity_id
        if not entities:
            continue
        lawns.append(
            {
                "entry_id": entry.entry_id,
                "name": entry.title,
                "entities": entities,
                "irrigation_configured": "irrigation_status" in entities,
            }
        )
    connection.send_result(
        msg["id"],
        {
            "lawns": lawns,
            "can_control": connection.user.is_admin,
            "version": INTEGRATION_VERSION,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/dashboard_action",
        vol.Required("config_entry_id"): str,
        vol.Required("action"): vol.In(ACTIONS),
        vol.Optional("data", default=dict): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_dashboard_action(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Authorize writes before delegating to the established safety controller.

    Never accept a caller-supplied service domain or overriding entry ID. The
    integration's service schemas still validate doses, dates and durations.
    Waiting for completion exposes controller/storage errors to the browser.
    """
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
    ):
        raise ServiceValidationError("This lawn is not loaded. Refresh the dashboard.")
    data = dict(msg["data"])
    if "config_entry_id" in data:
        raise ServiceValidationError("The selected lawn cannot be overridden.")
    action = msg["action"]
    if action in {"enable_automatic", "disable_automatic"}:
        if data:
            raise ServiceValidationError(
                "Automatic permission accepts no extra parameters."
            )
        await entry.runtime_data.irrigation_controller.async_set_auto_enabled(
            action == "enable_automatic"
        )
    else:
        await hass.services.async_call(
            DOMAIN,
            action,
            {**data, "config_entry_id": entry.entry_id},
            blocking=True,
            context=Context(user_id=connection.user.id),
        )
    connection.send_result(msg["id"])
