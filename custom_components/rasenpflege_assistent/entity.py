"""Base entity for Rasenpflege-Assistent."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN, INTEGRATION_VERSION
from .coordinator import LawnCoordinator


class LawnEntity(CoordinatorEntity[LawnCoordinator]):
    """Base class shared by all lawn entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LawnCoordinator, key: str) -> None:
        """Initialize a lawn entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        name = coordinator.settings.get(CONF_NAME, DEFAULT_NAME)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Custom Integration",
            model="Rasenpflege-Assistent",
            sw_version=INTEGRATION_VERSION,
        )
