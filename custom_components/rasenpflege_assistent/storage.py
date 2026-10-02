"""Verified Home Assistant storage writes for durable lawn state.

File: custom_components/rasenpflege_assistent/storage.py

VerifiedStore uses HA storage to save an independent snapshot, then reloads
the stored data and compares it with that snapshot. HA can log certain write
failures without raising; readback makes unsuccessful persistence observable.

Callers serialize writes and decide rollback or safe valve closure. A failed
verification raises HomeAssistantError. This wrapper adds a local read per save
and makes no network requests.
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .diagnostic_types import StorageStatus


class VerifiedStore[T: Mapping[str, Any] | Sequence[Any]](Store[T]):
    """Confirm state after writes that HA may only log as unsuccessful."""

    def __init__(self, hass: HomeAssistant, version: int, key: str) -> None:
        """Keep write health per entry and only for the current HA process."""
        super().__init__(hass, version, key)
        self._status: StorageStatus = {
            "last_success_at": None,
            "last_failure_at": None,
            "last_failure_operation": None,
            "last_error_type": None,
            "consecutive_failures": 0,
            "successful_writes": 0,
            "pending": False,
        }

    def diagnostic_status(self) -> StorageStatus:
        """Return a detached health snapshot without filesystem access."""
        return self._status.copy()

    async def async_save(self, data: T) -> None:
        """Save a stable snapshot and require matching persisted data.

        Deep-copy before the first await so concurrent safety changes cannot
        alter the snapshot being verified. Compare via HA's public load API
        because some write failures are logged rather than raised by Store.
        The caller must hold the appropriate model transaction lock.
        """
        snapshot = deepcopy(data)
        operation = "save"
        self._status["pending"] = True
        try:
            await super().async_save(snapshot)
            operation = "verify"
            if await super().async_load() != snapshot:
                raise HomeAssistantError(
                    "Lawn state could not be verified after saving"
                )
        except (OSError, HomeAssistantError) as err:
            self._status["last_failure_at"] = dt_util.utcnow().isoformat()
            self._status["last_failure_operation"] = operation
            self._status["last_error_type"] = type(err).__name__
            self._status["consecutive_failures"] += 1
            raise
        else:
            self._status["last_success_at"] = dt_util.utcnow().isoformat()
            self._status["successful_writes"] += 1
            self._status["consecutive_failures"] = 0
        finally:
            self._status["pending"] = False
