"""Diagnostics support for Rasenpflege-Assistent."""

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
        "config_entry_version": entry.version,
        "data": data,
        "last_update_success": coordinator.last_update_success,
    }
