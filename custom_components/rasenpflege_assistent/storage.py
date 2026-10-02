"""Verify persisted lawn state through Home Assistant's public storage API."""

from copy import deepcopy

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store


class VerifiedStore[T](Store[T]):
    """Confirm state after writes that HA may only log as unsuccessful."""

    async def async_save(self, data: T) -> None:
        """Save a stable snapshot and require matching persisted data."""
        snapshot = deepcopy(data)
        await super().async_save(snapshot)
        if await super().async_load() != snapshot:
            raise HomeAssistantError("Lawn state could not be verified after saving")
