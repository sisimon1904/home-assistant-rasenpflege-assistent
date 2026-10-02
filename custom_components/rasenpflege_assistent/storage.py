"""Verified Home Assistant storage writes for durable lawn state.

File: custom_components/rasenpflege_assistent/storage.py

VerifiedStore uses HA storage to save an independent snapshot, then reloads
the stored data and compares it with that snapshot. HA can log certain write
failures without raising; readback makes unsuccessful persistence observable.

Callers serialize writes and decide rollback or safe valve closure. A failed
verification raises HomeAssistantError. This wrapper adds a local read per save
and makes no network requests.
"""

from copy import deepcopy

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store


class VerifiedStore[T](Store[T]):
    """Confirm state after writes that HA may only log as unsuccessful."""

    async def async_save(self, data: T) -> None:
        """Save a stable snapshot and require matching persisted data.

        Deep-copy before the first await so concurrent safety changes cannot
        alter the snapshot being verified. Compare via HA's public load API
        because some write failures are logged rather than raised by Store.
        The caller must hold the appropriate model transaction lock.
        """
        snapshot = deepcopy(data)
        await super().async_save(snapshot)
        if await super().async_load() != snapshot:
            raise HomeAssistantError("Lawn state could not be verified after saving")
