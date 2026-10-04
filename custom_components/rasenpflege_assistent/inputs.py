"""Shared meter normalization and freshness for safety and diagnostics.

File: custom_components/rasenpflege_assistent/inputs.py

Rate readings require recent reports; cumulative meters may remain unchanged.
Reading observations never calls services or mutates sampling baselines.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.core import State


def meter_reading(state: State | None) -> tuple[str, float] | None:
    """Normalize supported flow and volume sensors to L/min or L.

    Return a normalized (kind, value) pair: cumulative volume in liters
    or instantaneous rate in liters/minute. Invalid state, unsupported units,
    non-finite values and negative quantities are unusable observations.
    """
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        raw = float(state.state)
    except (TypeError, ValueError):
        return None
    if not 0 <= raw < 1e9:
        return None
    unit = str(state.attributes.get("unit_of_measurement", "")).strip()
    rates = {
        "L/min": 1.0,
        "L/h": 1 / 60,
        "L/s": 60.0,
        "m³/h": 1000 / 60,
        "m³/min": 1000.0,
        "m³/s": 60000.0,
    }
    volumes = {"L": 1.0, "m³": 1000.0, "gal": 3.785411784}
    if unit in rates:
        return "rate", raw * rates[unit]
    if unit in volumes:
        return "volume", raw * volumes[unit]
    return None


@dataclass(frozen=True, slots=True)
class MeterObservation:
    """Normalized measurement plus the same acceptance rule used by safety."""

    reading: tuple[str, float] | None
    reason: str
    maximum_age_seconds: int


def meter_observation(
    state: State | None, now: datetime, grace_seconds: int
) -> MeterObservation:
    """Accept volume counters or fresh rates; preserve stale values for diagnosis."""
    maximum_age = max(120, grace_seconds)
    reading = meter_reading(state)
    reason = (
        "missing"
        if state is None
        else "unavailable"
        if state.state in {"unknown", "unavailable"}
        else "invalid"
        if reading is None
        else "accepted"
    )
    if (
        state
        and reading
        and reading[0] == "rate"
        and now - (state.last_reported or state.last_updated)
        > timedelta(seconds=maximum_age)
    ):
        reason = "stale"
    return MeterObservation(reading, reason, maximum_age)
