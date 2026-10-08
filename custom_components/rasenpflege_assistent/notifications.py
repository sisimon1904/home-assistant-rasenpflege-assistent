"""Optional, rate-limited local Home Assistant care notifications.

File: custom_components/rasenpflege_assistent/notifications.py

Reuse coordinator updates without extra weather requests or device commands.
Opt-in preferences and per-category cooldowns survive restart in a separate
verified store. Notifications appear in HA's own notification drawer; this
feature does not select a phone, email address or external message recipient.
Settings and cooldown writes are serialized independently from valve safety.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import LawnCoordinator
from .explanations import reason_text
from .insights import aware_time
from .storage import VerifiedStore

_LOGGER = logging.getLogger(__name__)


class CareNotifier:
    """One entry's opt-in preferences and bounded persistent cooldowns."""

    def __init__(self, coordinator: LawnCoordinator) -> None:
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.entry = coordinator.config_entry
        self.store: VerifiedStore[dict[str, Any]] = VerifiedStore(
            self.hass, 1, f"{DOMAIN}_notifications_{self.entry.entry_id}"
        )
        self.enabled = False
        self.interval_hours = 24
        self.quiet_start = ""
        self.quiet_end = ""
        self.changes_only = False
        self._signatures: dict[str, str] = {}
        self._sent: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._stopped = False
        self._pending = False

    @property
    def preferences(self) -> dict[str, Any]:
        """Expose only user-editable preferences to the dashboard."""
        return {
            "enabled": self.enabled,
            "interval_hours": self.interval_hours,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "changes_only": self.changes_only,
        }

    @staticmethod
    def valid_quiet(start: object, end: object) -> bool:
        """Require two local HH:MM values or two empty values (disabled)."""
        if not isinstance(start, str) or not isinstance(end, str):
            return False
        if start == end == "":
            return True
        return bool(
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start)
            and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end)
            and start != end
        )

    def quiet_now(self) -> bool:
        """Use HA local wall time; overnight quiet periods also span DST."""
        if not self.quiet_start:
            return False
        clock = dt_util.as_local(dt_util.utcnow()).strftime("%H:%M")
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= clock < self.quiet_end
        return clock >= self.quiet_start or clock < self.quiet_end

    async def async_initialize(self) -> None:
        """Restore valid settings; malformed optional data defaults to disabled."""
        data = await self.store.async_load()
        if isinstance(data, dict):
            self.enabled = data.get("enabled") is True
            interval = data.get("interval_hours")
            self.interval_hours = (
                interval if type(interval) is int and interval in {1, 6, 24} else 24
            )
            start, end = data.get("quiet_start", ""), data.get("quiet_end", "")
            if self.valid_quiet(start, end):
                self.quiet_start, self.quiet_end = str(start), str(end)
            self.changes_only = data.get("changes_only") is True
            signatures = data.get("signatures")
            if isinstance(signatures, dict):
                self._signatures = {
                    key: value
                    for key, value in signatures.items()
                    if key in {"care", "irrigation"}
                    and isinstance(value, str)
                    and len(value) <= 512
                }
            sent = data.get("sent")
            now = dt_util.utcnow()
            if isinstance(sent, dict):
                self._sent = {
                    key: value
                    for key, value in sent.items()
                    if key in {"care", "irrigation"}
                    and (at := aware_time(value)) is not None
                    and at <= now
                }

    async def async_configure(
        self,
        enabled: bool,
        interval_hours: int,
        quiet_start: str = "",
        quiet_end: str = "",
        changes_only: bool = False,
    ) -> None:
        """Persist opt-in before making it effective; failed writes change nothing."""
        if (
            type(enabled) is not bool
            or type(interval_hours) is not int
            or interval_hours not in {1, 6, 24}
            or type(changes_only) is not bool
            or not self.valid_quiet(quiet_start, quiet_end)
        ):
            raise HomeAssistantError("Invalid notification preferences")
        async with self._lock:
            await self.store.async_save(
                {
                    "enabled": enabled,
                    "interval_hours": interval_hours,
                    "sent": dict(self._sent),
                    "quiet_start": quiet_start,
                    "quiet_end": quiet_end,
                    "changes_only": changes_only,
                    "signatures": dict(self._signatures),
                }
            )
            self.enabled, self.interval_hours = enabled, interval_hours
            self.quiet_start, self.quiet_end = quiet_start, quiet_end
            self.changes_only = changes_only

    def stop(self) -> None:
        """Prevent a queued notification from publishing after entry unload."""
        self._stopped = True

    def updated(self) -> None:
        """Coalesce update bursts into one asynchronous local evaluation."""
        if self.enabled and not self._pending and not self._stopped:
            self._pending = True
            self.hass.async_create_task(self._async_updated())

    async def _async_updated(self) -> None:
        try:
            await self.async_check()
        except (OSError, HomeAssistantError):
            _LOGGER.exception("Could not persist lawn notification cooldown")
        finally:
            self._pending = False

    async def async_check(self) -> None:
        """Notify due care and abnormal completed irrigation with separate limits.

        The advice is a recommendation, not proof of overdue maintenance or a
        reserved future action. Restarted abort evidence may be reported once
        if it is still recent; ordinary manual stops are not failures.
        """
        async with self._lock:
            data = self.coordinator.data
            if (
                not self.enabled
                or self._stopped
                or data is None
                or not self.coordinator.last_update_success
                or self.quiet_now()
            ):
                return
            now = dt_util.utcnow()
            language = self.hass.config.language
            de = language.startswith("de")
            due = []
            if data.mower_start_recommended:
                due.append("Mähen" if de else "Mowing")
            if data.watering_recommended:
                due.append("Bewässerung" if de else "Watering")
            if data.fertilizing_recommended:
                due.append("Düngung" if de else "Fertilizing")
            candidates = {}
            # Stable evidence, not shifting forecast timestamps, determines a
            # material change. Repeated alerts for the same abort are suppressed
            # across restarts; new aborts still respect the category cooldown.
            signatures = {
                "care": "|".join(
                    [
                        str(data.mower_start_recommended),
                        str(data.watering_recommended),
                        str(data.fertilizing_recommended),
                        str(data.last_mowing_at),
                        str(data.last_watering),
                        str(data.last_fertilizing),
                    ]
                ),
            }
            if due:
                candidates["care"] = (
                    ("Pflege empfohlen: " if de else "Care recommended: ")
                    + ", ".join(due)
                    + (
                        ". Aktuelle Zeitfenster und Sperrgründe im Rasenpflege-Dashboard prüfen."
                        if de
                        else ". Check current windows and blockers in the lawn care dashboard."
                    )
                )
            session = self.coordinator.state.irrigation_last_session or {}
            if not due and "care" in self._signatures:
                # A recommendation that becomes unavailable and later returns
                # is a new change, even if the care categories match. Preserve
                # its cooldown so a flapping input cannot flood notifications.
                reset_signatures = dict(self._signatures)
                reset_signatures.pop("care")
                await self.store.async_save(
                    {
                        **self.preferences,
                        "sent": dict(self._sent),
                        "signatures": reset_signatures,
                    }
                )
                self._signatures = reset_signatures
            finished = aware_time(session.get("finished_at"))
            reason = session.get("reason")
            if (
                isinstance(reason, str)
                and reason
                and reason
                not in {
                    "target_reached",
                    "stopped_manually",
                    "integration_unloaded",
                    "homeassistant_stopping",
                }
                and finished
                and timedelta(0) <= now - finished <= timedelta(hours=24)
            ):
                candidates["irrigation"] = (
                    "Bewässerung abgebrochen: " if de else "Irrigation interrupted: "
                ) + (reason_text(reason, language) or str(reason))
                signatures["irrigation"] = f"{session.get('finished_at')}|{reason}"
            for category, message in candidates.items():
                signature = signatures[category]
                if (
                    category == "irrigation" or self.changes_only
                ) and self._signatures.get(category) == signature:
                    continue
                previous = aware_time(self._sent.get(category))
                if previous and now - previous < timedelta(hours=self.interval_hours):
                    continue
                sent = {**self._sent, category: now.isoformat()}
                updated_signatures = {**self._signatures, category: signature}
                await self.store.async_save(
                    {
                        **self.preferences,
                        "sent": sent,
                        "signatures": updated_signatures,
                    }
                )
                self._sent = sent
                self._signatures = updated_signatures
                if self._stopped:
                    return
                persistent_notification.async_create(
                    self.hass,
                    message,
                    title=self.entry.title,
                    notification_id=f"{DOMAIN}_{self.entry.entry_id}_{category}",
                )


async def async_setup_notifications(coordinator: LawnCoordinator) -> None:
    """Attach the listener only after entry platforms have been set up."""
    notifier = CareNotifier(coordinator)
    try:
        await notifier.async_initialize()
    except (OSError, HomeAssistantError):
        # This optional feature must not prevent lawn/valve supervision from
        # loading when only its independent preference file cannot be read.
        _LOGGER.exception("Could not load lawn notifications; defaulting to disabled")
    notifiers = coordinator.hass.data.setdefault(f"{DOMAIN}_notifiers", {})
    notifiers[coordinator.config_entry.entry_id] = notifier
    remove_listener = coordinator.async_add_listener(notifier.updated)

    def detach() -> None:
        notifier.stop()
        remove_listener()
        notifiers.pop(coordinator.config_entry.entry_id, None)

    coordinator.config_entry.async_on_unload(detach)
