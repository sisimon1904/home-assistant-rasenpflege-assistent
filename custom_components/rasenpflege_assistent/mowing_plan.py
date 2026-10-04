"""Read-only hourly mowing windows and conservative dew-risk estimates.

File: custom_components/rasenpflege_assistent/mowing_plan.py

Use normalized HA weather/forecast data; never request weather or command a
mower. Bolton's vapor-pressure inversion estimates dew point from humidity:
https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.dewpoint.html
Air dew-point spread is only a heuristic: grass surface temperature is unknown.
Risk thresholds and one dry hour after dew are advisory, not field validation.
Collect separate continuous windows, require the configured real mowing
duration, and expose the next sufficient interval as a read-only alternative.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from .insights import aware_time, finite_number
from .planning import next_schedule_time, schedule_allowed


class DewEstimate(TypedDict):
    """Unknown evidence must not appear as low risk or measured lawn dryness."""

    risk: str
    dew_point_c: float | None
    spread_c: float | None
    source: str
    estimated: bool
    surface_dry_confirmed: bool


def dew_risk(temperature: object, humidity: object, dew_point: object) -> DewEstimate:
    """Estimate spread using supplied dew point or relative humidity.

    Spread <=2 C is high risk; <=4 C moderate. Reject impossible/supersaturated
    inputs and zero humidity instead of returning a mathematically invented
    assurance. Both risk and drying remain estimates even with supplied Td.
    """
    t, rh, td = (finite_number(value) for value in (temperature, humidity, dew_point))
    source = "unknown"
    if t is None or not -90 <= t <= 70:
        td = None
    else:
        if td is not None and -90 <= td <= t + 0.5:
            source = "weather_dew_point"
        else:
            td = None
            if rh is not None and 0 < rh <= 100:
                gamma = math.log(rh / 100) + 17.67 * t / (243.5 + t)
                td = 243.5 * gamma / (17.67 - gamma)
                source = "humidity_estimate"
    spread = max(0.0, t - td) if t is not None and td is not None else None
    return {
        "risk": "unknown"
        if spread is None
        else "high"
        if spread <= 2
        else "moderate"
        if spread <= 4
        else "low",
        "dew_point_c": round(td, 2) if td is not None else None,
        "spread_c": round(spread, 2) if spread is not None else None,
        "source": source,
        "estimated": True,
        "surface_dry_confirmed": False,
    }


class WindowOption(TypedDict):
    """A continuous interval with enough real minutes for a complete pass."""

    start: str
    end: str
    available_minutes: float


class MowingWindow(TypedDict):
    """A weather window is a recommendation, with explicit missing evidence."""

    status: str
    start: str | None
    end: str | None
    reason: str
    blockers: list[str]
    missing_inputs: list[str]
    current_dew: DewEstimate
    window_dew: DewEstimate | None
    estimated: bool
    surface_dry_confirmed: bool
    weather_slots_reviewed: int
    leaf_wetness: str
    required_minutes: float
    available_minutes: float | None
    alternative: WindowOption | None
    quality: str
    quality_reasons: list[str]


_RAIN_STATES = {
    "rainy",
    "pouring",
    "lightning-rainy",
    "snowy",
    "snowy-rainy",
    "hail",
    "lightning",
}
_DRY_STATES = {
    "sunny",
    "partlycloudy",
    "cloudy",
    "clear-night",
    "windy",
    "windy-variant",
}


def _hour_reason(row: Mapping[str, object]) -> tuple[str | None, DewEstimate]:
    """Require temperature, precipitation, wind and dew evidence for a slot."""
    estimate = dew_risk(
        row.get("temperature"), row.get("humidity"), row.get("dew_point")
    )
    if row.get("forecast_conflict"):
        return "forecast_conflict", estimate
    t = finite_number(row.get("temperature"))
    rain = finite_number(row.get("precipitation"))
    wind = finite_number(row.get("wind_speed"))
    probability = finite_number(row.get("precipitation_probability"))
    if t is None or not -90 <= t <= 70:
        return "mowing_temperature_unknown", estimate
    if t <= 0:
        return "mowing_frost", estimate
    if t >= 28:
        return "mowing_heat", estimate
    condition = row.get("condition")
    if not isinstance(condition, str):
        condition = None
    if condition == "fog":
        return "mowing_fog", estimate
    if condition == "exceptional":
        return "mowing_weather_unknown", estimate
    if (
        condition in _RAIN_STATES
        or (rain is not None and rain > 0)
        or (probability is not None and probability >= 50)
    ):
        return "mowing_rain", estimate
    if rain is None or rain < 0:
        return "mowing_rain_unknown", estimate
    if wind is None or wind < 0:
        return "mowing_wind_unknown", estimate
    if wind > 8:
        return "mowing_wind", estimate
    if estimate["risk"] == "unknown":
        return "mowing_dew_unknown", estimate
    if estimate["risk"] != "low":
        return "mowing_dew_risk", estimate
    return None, estimate


def mowing_window(
    *,
    now: datetime,
    hourly: list[dict[str, object]],
    current: Mapping[str, object],
    due_at: datetime | None,
    eligible: bool,
    wet_until: datetime | None,
    irrigation_active: bool,
    soil_frost: bool,
    leaf_wetness: str,
    start_time: str = "09:00:00",
    end_time: str = "20:00:00",
    duration_minutes: object = 0,
) -> MowingWindow:
    """Select the earliest suitable hourly window within 48 actual hours.

    UTC arithmetic preserves real duration over DST; scheduling uses HA local
    time. Do not extend one forecast slot through gaps. Known dew requires a
    preceding low-risk dry hour, forecast rain a twelve-hour/next-day hold.
    Current weather can support only the next hour, never tomorrow's humidity.
    Zero required minutes preserves existing installations; a positive value
    excludes short intervals without combining evidence across weather gaps.
    """
    required = finite_number(duration_minutes)
    if required is None or not 0 <= required <= 1440:
        required = 0.0
    utc_now = now.astimezone(timezone.utc)
    estimate = dew_risk(
        current.get("temperature"), current.get("humidity"), current.get("dew_point")
    )
    if current.get("stale", True):
        estimate = dew_risk(None, None, None)
    result: MowingWindow = {
        "status": "no_window",
        "start": None,
        "end": None,
        "reason": "mowing_no_window",
        "blockers": [],
        "missing_inputs": [],
        "current_dew": estimate,
        "window_dew": None,
        "estimated": True,
        "surface_dry_confirmed": False,
        "weather_slots_reviewed": 0,
        "leaf_wetness": leaf_wetness,
        "required_minutes": required,
        "available_minutes": None,
        "alternative": None,
        "quality": "insufficient",
        "quality_reasons": [],
    }
    if not eligible or irrigation_active or soil_frost:
        result["status"] = "blocked"
        result["reason"] = (
            "irrigation_running"
            if irrigation_active
            else "mowing_frost"
            if soil_frost
            else "mowing_not_due"
        )
        result["quality_reasons"] = [result["reason"]]
        return result
    earliest = max(
        utc_now,
        due_at.astimezone(timezone.utc) if due_at else utc_now,
        wet_until.astimezone(timezone.utc) if wet_until else utc_now,
    )
    schedule = {"irrigation_start_time": start_time, "irrigation_end_time": end_time}
    rows: dict[datetime, dict[str, object]] = {}
    for row in hourly:
        at = aware_time(row.get("datetime"))
        if at is not None:
            at = at.astimezone(timezone.utc)
            if utc_now <= at < utc_now + timedelta(hours=48):
                # Identical retries are harmless; conflicting absolute hours
                # cannot become suitable merely through provider ordering.
                if at in rows and rows[at] != row:
                    rows[at] = {"forecast_conflict": True}
                else:
                    rows[at] = row
    # An actual current observation supports this hour only. Do not assert
    # zero rain from a missing/unknown weather condition.
    if not current.get("stale", True):
        condition = current.get("condition")
        if not isinstance(condition, str):
            condition = None
        current_row: dict[str, object] = {
            "temperature": current.get("temperature"),
            "humidity": current.get("humidity"),
            "dew_point": current.get("dew_point"),
            "wind_speed": current.get("wind_speed_m_s"),
            "condition": condition,
            "precipitation": 0.0 if condition in _DRY_STATES else None,
        }
        if condition in _RAIN_STATES:
            current_row["precipitation"] = 1.0
        if leaf_wetness == "dry":
            # A fresh dry binary observation replaces only current dew evidence.
            current_row["dew_point"] = None
            current_row["humidity"] = None
        if not rows.get(utc_now, {}).get("forecast_conflict"):
            rows[utc_now] = current_row
    blockers: set[str] = set()
    missing: set[str] = set()
    drying_needed = leaf_wetness == "wet" or (
        estimate["risk"] in {"high", "moderate"} and leaf_wetness != "dry"
    )
    dry_since: datetime | None = None
    previous: datetime | None = None
    windows: list[tuple[datetime, datetime, DewEstimate]] = []
    rain_hold = earliest
    ordered = sorted(rows.items())
    for index, (at, row) in enumerate(ordered):
        next_at = (
            ordered[index + 1][0]
            if index + 1 < len(ordered)
            else utc_now + timedelta(hours=48)
        )
        slot_end = min(at + timedelta(hours=1), next_at, utc_now + timedelta(hours=48))
        if slot_end <= utc_now:
            continue
        reason, dew = _hour_reason(row)
        if (
            at == utc_now
            and leaf_wetness == "dry"
            and reason in {"mowing_dew_unknown", "mowing_dew_risk"}
        ):
            reason = None
        result["weather_slots_reviewed"] += 1
        if reason:
            blockers.add(reason)
            if reason.endswith("_unknown") or reason == "forecast_conflict":
                missing.add(reason)
            if reason in {"mowing_dew_risk", "mowing_fog", "mowing_frost"}:
                drying_needed = True
            dry_since = None
        elif (
            previous is None or at - previous > timedelta(hours=1) or dry_since is None
        ):
            dry_since = at
        rain = finite_number(row.get("precipitation"))
        probability = finite_number(row.get("precipitation_probability"))
        condition = row.get("condition")
        wet_forecast = (
            (isinstance(condition, str) and condition in _RAIN_STATES)
            or (rain is not None and rain > 0)
            or (probability is not None and probability >= 50)
        )
        if wet_forecast:
            # Rain remains relevant even if frost/heat is the primary blocker.
            local = at.astimezone(now.tzinfo)
            midnight = (local + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            rain_hold = max(
                rain_hold, midnight.astimezone(timezone.utc), at + timedelta(hours=12)
            )
            blockers.add("mowing_rain")
        candidate = max(at, earliest, rain_hold)
        scheduled = next_schedule_time(
            schedule, candidate.astimezone(now.tzinfo), slot_end.astimezone(now.tzinfo)
        )
        if scheduled is not None:
            candidate = scheduled.astimezone(timezone.utc)
        dry_ready = not drying_needed or (
            dry_since is not None and candidate - dry_since >= timedelta(hours=1)
        )
        allowed = schedule_allowed(schedule, candidate.astimezone(now.tzinfo))
        # Find the exact first disallowed instant, including second-valued
        # policies and UTC-offset transitions. Never extend past a slot end.
        end = slot_end
        lower = candidate
        probe = min(
            candidate.replace(second=0, microsecond=0) + timedelta(minutes=1), end
        )
        while candidate < end and probe <= end:
            if not schedule_allowed(schedule, probe.astimezone(now.tzinfo)):
                upper = probe
                while upper - lower > timedelta(microseconds=1):
                    middle = lower + (upper - lower) / 2
                    if schedule_allowed(schedule, middle.astimezone(now.tzinfo)):
                        lower = middle
                    else:
                        upper = middle
                end = upper
                break
            if probe == end:
                break
            lower = probe
            probe = min(probe + timedelta(minutes=1), end)
        if (
            reason is None
            and dry_ready
            and allowed
            and candidate < end
            and at >= utc_now - timedelta(hours=1)
        ):
            # Merge only touching evidence; a gap, blocked hour or daily
            # schedule boundary must split windows even when both sides are dry.
            if windows and candidate <= windows[-1][1]:
                beginning, ending, initial_dew = windows[-1]
                windows[-1] = (beginning, max(ending, end), initial_dew)
            else:
                windows.append((candidate, end, dew))
        elif not allowed:
            blockers.add("mowing_outside_schedule")
        elif reason is None and not dry_ready:
            blockers.add("mowing_drying")
        previous = at
    result["blockers"] = sorted(blockers)
    result["missing_inputs"] = sorted(missing)
    suitable = []
    for beginning, ending, initial_dew in windows:
        minutes = (ending - beginning).total_seconds() / 60
        if minutes >= required:
            suitable.append((beginning, ending, initial_dew, minutes))
        else:
            blockers.add("mowing_window_too_short")
    result["blockers"] = sorted(blockers)
    if suitable:
        beginning, ending, initial_dew, minutes = suitable[0]
        result.update(
            {
                "status": "recommended",
                "start": beginning.astimezone(now.tzinfo).isoformat(),
                "end": ending.astimezone(now.tzinfo).isoformat(),
                "reason": "mowing_window_estimated",
                "window_dew": initial_dew,
                "available_minutes": round(minutes, 2),
                "quality": "estimated",
                "quality_reasons": ["mowing_quality_estimated"],
            }
        )
        if len(suitable) > 1:
            beginning, ending, _, minutes = suitable[1]
            result["alternative"] = {
                "start": beginning.astimezone(now.tzinfo).isoformat(),
                "end": ending.astimezone(now.tzinfo).isoformat(),
                "available_minutes": round(minutes, 2),
            }
    elif not rows:
        result["reason"] = "mowing_hourly_unavailable"
    elif windows:
        result["reason"] = "mowing_window_too_short"
    if not suitable:
        result["quality_reasons"] = sorted(missing) or [result["reason"]]
    return result
