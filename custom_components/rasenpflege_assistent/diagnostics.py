"""Serializable diagnostic snapshot for one configured lawn entry.

File: custom_components/rasenpflege_assistent/diagnostics.py

Diagnostics combine calculated data, version information and optional
irrigation readiness/session details. Date objects are converted explicitly
so the returned dictionary can be exported by Home Assistant as JSON.

Reading diagnostics does not refresh weather, save state or command valves.
Only the selected config entry is inspected; credentials are not copied from
the external weather integration.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import LawnConfigEntry
from .const import INTEGRATION_VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LawnConfigEntry
) -> dict[str, Any]:
    """Return non-sensitive diagnostic information."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data)
    for key in (
        "last_watering",
        "last_fertilizing",
        "last_mowing",
        "next_mowing_date",
    ):
        if data[key] is not None:
            data[key] = data[key].isoformat()
    return {
        "integration_version": INTEGRATION_VERSION,
        "water_model_version": coordinator.water_model_version,
        "config_entry_version": entry.version,
        "data": data,
        "last_update_success": coordinator.last_update_success,
        "inputs": coordinator.input_diagnostics(),
        "soil_model": coordinator.model_diagnostics(),
        "model_insights": coordinator.insight_diagnostics(include_history=True),
        "storage": coordinator._store.diagnostic_status(),
        "updates": coordinator.update_diagnostics(),
        "irrigation": (
            {
                "readiness": coordinator.irrigation_controller.readiness(),
                **coordinator.irrigation_controller.diagnostic_attributes(),
                "automatic_enabled": coordinator.irrigation_controller.state.irrigation_enabled,
            }
            if coordinator.irrigation and coordinator.irrigation_controller.configured
            else None
        ),
    }
