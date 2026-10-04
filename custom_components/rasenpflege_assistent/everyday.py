"""Read-only daily care priorities, weekly comparisons and cycle estimates.

File: custom_components/rasenpflege_assistent/everyday.py

Helpers explain existing recommendations and configured irrigation cycles.
Two rolling seven-day periods use recorded observations, never forecasts as
observed rain. Missing evidence remains explicit. No settings, valves, mower
or weather requests are changed by these advisory calculations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from statistics import fmean
from typing import NotRequired, TypedDict

from .insights import ModelObservation, aware_time, finite_number


class CareStep(TypedDict):
    """An ordered suggestion with a prerequisite, not an execution command."""

    action: str
    reason: str
    after: str | None


def care_priorities(
    *,
    watering_status: str,
    mower_status: str,
    fertilizing: bool,
    irrigation_active: bool,
    wet_until: str | None,
    temperature_available: bool,
    frost: bool,
) -> list[CareStep]:
    """Order safety, watering, drying, mowing and optional fertilizing."""
    steps: list[CareStep] = []
    if not temperature_available:
        return [
            {"action": "check_inputs", "reason": "care_check_inputs", "after": None}
        ]
    if frost:
        return [
            {
                "action": "wait_for_frost_free",
                "reason": "care_wait_frost",
                "after": None,
            }
        ]
    if irrigation_active:
        steps.append(
            {
                "action": "wait_for_irrigation",
                "reason": "irrigation_running",
                "after": None,
            }
        )
    elif watering_status in {"water_now", "water_soon", "wait_for_rain"}:
        action = (
            "wait_for_rain"
            if watering_status == "wait_for_rain"
            else "water_lawn"
            if watering_status == "water_now"
            else "prepare_watering"
        )
        steps.append(
            {"action": action, "reason": "care_water_before_mowing", "after": None}
        )
    if (
        wet_until
        or irrigation_active
        or watering_status in {"water_now", "wait_for_rain"}
    ):
        steps.append(
            {
                "action": "wait_until_dry",
                "reason": "care_wait_dry",
                "after": steps[-1]["action"] if steps else None,
            }
        )
    if mower_status in {
        "mow_regularly",
        "mow_less",
        "reduce_mowing",
        "start_mower",
        "pause_wet",
        "wait_to_mow",
    }:
        steps.append(
            {
                "action": "mow_lawn",
                "reason": "care_follow_mowing_schedule",
                "after": steps[-1]["action"] if steps else None,
            }
        )
    if fertilizing:
        steps.append(
            {
                "action": "fertilize_lawn",
                "reason": "care_follow_fertilizing_window",
                "after": steps[-1]["action"] if steps else None,
            }
        )
    return steps or [{"action": "no_action", "reason": "no_action", "after": None}]


class WeeklyPeriod(TypedDict):
    """Partial evidence stays labeled; totals do not imply full weather coverage."""

    start: str
    end: str
    hourly_snapshots: int
    recording_sufficient: bool
    recorded_rain_mm: float
    observed_rain_mm: float | None
    estimated_et_mm: float
    mean_modeled_percent: float | None
    recorded_liters: float
    unknown_volume_records: int
    estimated_volume_records: int


def weekly_comparison(
    history: list[ModelObservation], usage: object, now: datetime
) -> dict[str, object]:
    """Compare rolling 168-hour windows; date-only usage allocation is approximate."""
    reference = now.astimezone(timezone.utc)
    periods: list[WeeklyPeriod] = []
    for start, end in (
        (reference - timedelta(days=7), reference),
        (reference - timedelta(days=14), reference - timedelta(days=7)),
    ):
        rows = [
            row
            for row in history
            if (at := aware_time(row["timestamp"])) is not None and start < at <= end
        ]
        hours = {
            at.timestamp() // 3600
            for row in rows
            if (at := aware_time(row["timestamp"])) is not None
        }
        # Counts and gaps are evidence completeness, not weather accuracy.
        times = [at for row in rows if (at := aware_time(row["timestamp"])) is not None]
        enough = (
            len(hours) >= 160
            and bool(times)
            and min(times) <= start + timedelta(minutes=90)
            and max(times) >= end - timedelta(minutes=90)
            and all(
                timedelta(0) < right - left <= timedelta(minutes=90)
                for left, right in pairwise(sorted(times))
            )
        )
        rain = round(sum(row["rain_mm"] for row in rows), 3)
        liters, unknown, estimated = 0.0, 0, 0
        if isinstance(usage, list):
            for item in usage:
                if not isinstance(item, Mapping):
                    continue
                allocations = item.get("allocations") or [item]
                if not isinstance(allocations, list):
                    continue
                record_unknown = False
                record_in_period = False
                for allocation in allocations:
                    if not isinstance(allocation, Mapping):
                        continue
                    try:
                        day = date.fromisoformat(str(allocation.get("date")))
                    except ValueError:
                        continue
                    # Ledger dates are local: keep the windows disjoint and say
                    # that the first/last date cannot be split at the clock hour.
                    if (
                        start.astimezone(now.tzinfo).date()
                        < day
                        <= end.astimezone(now.tzinfo).date()
                    ):
                        record_in_period = True
                        value = finite_number(allocation.get("liters"))
                        if value is None or value < 0:
                            record_unknown = True
                        else:
                            liters += value
                            if item.get("measurement_gap"):
                                record_unknown = True
                # A gap can belong to a date with no measured allocation.
                uncertainty_dates = item.get("uncertainty_dates")
                if isinstance(uncertainty_dates, list):
                    for raw_day in uncertainty_dates:
                        try:
                            day = date.fromisoformat(str(raw_day))
                        except ValueError:
                            continue
                        if (
                            start.astimezone(now.tzinfo).date()
                            < day
                            <= end.astimezone(now.tzinfo).date()
                        ):
                            record_unknown = True
                unknown += int(record_unknown)
                if record_in_period and (
                    item.get("allocation_estimated")
                    or item.get("source") == "manual_estimate"
                ):
                    estimated += 1
        period: WeeklyPeriod = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "hourly_snapshots": len(hours),
            "recording_sufficient": enough,
            "recorded_rain_mm": rain,
            "observed_rain_mm": rain
            if enough and all(row["rain_known"] for row in rows)
            else None,
            "estimated_et_mm": round(sum(row["et_mm"] for row in rows), 3),
            "mean_modeled_percent": round(
                fmean(row["modeled_percent"] for row in rows), 2
            )
            if rows
            else None,
            "recorded_liters": round(liters, 2),
            "unknown_volume_records": unknown,
            "estimated_volume_records": estimated,
        }
        periods.append(period)
    current, previous = periods
    comparable = current["recording_sufficient"] and previous["recording_sufficient"]
    current_moisture, previous_moisture = (
        current["mean_modeled_percent"],
        previous["mean_modeled_percent"],
    )
    return {
        "current": current,
        "previous": previous,
        "status": "recording_available" if comparable else "partial_history",
        "moisture_change_percentage_points": round(
            current_moisture - previous_moisture, 2
        )
        if comparable and current_moisture is not None and previous_moisture is not None
        else None,
        "changes": {
            "observed_rain_mm": round(
                current["observed_rain_mm"] - previous["observed_rain_mm"], 3
            )
            if current["observed_rain_mm"] is not None
            and previous["observed_rain_mm"] is not None
            else None,
            "estimated_et_mm": round(
                current["estimated_et_mm"] - previous["estimated_et_mm"], 3
            )
            if comparable
            else None,
            "recorded_liters": round(
                current["recorded_liters"] - previous["recorded_liters"], 2
            )
            if current["unknown_volume_records"]
            == previous["unknown_volume_records"]
            == 0
            else None,
            "volume_includes_estimates": bool(
                current["estimated_volume_records"]
                or previous["estimated_volume_records"]
            ),
        },
        "consumption_date_allocation_estimated": True,
        "rain_is_observed": True,
        "period_hours": 168,
    }


class SensorReview(TypedDict):
    """Hints retain a distinction between observations and a proven fault."""

    status: str
    reasons: list[str]
    device_fault_confirmed: bool
    independent_reports: NotRequired[int]
    outage_transitions: NotRequired[int]


def sensor_review(history: list[ModelObservation], configured: bool) -> SensorReview:
    """Flag flat-but-reported moisture and repeated outages conservatively."""
    if not configured:
        return {
            "status": "not_configured",
            "reasons": [],
            "device_fault_confirmed": False,
        }
    rows = history[-48:]
    unique = {
        row["sensor_reported_at"]: row
        for row in rows
        if row["sensor_reported_at"] and row["measured_percent"] is not None
    }
    values = [
        value
        for row in unique.values()
        if (value := row["measured_percent"]) is not None
    ]
    reports = [
        at
        for row in unique.values()
        if (at := aware_time(row["sensor_reported_at"])) is not None
    ]
    span = (max(reports) - min(reports)).total_seconds() / 3600 if reports else 0.0
    reasons = []
    if values and len(values) >= 6 and span >= 24 and max(values) - min(values) <= 0.1:
        modeled = [row["modeled_percent"] for row in rows]
        if modeled and max(modeled) - min(modeled) >= 10:
            reasons.append("sensor_flat_review")
    outages = sum(
        left["measured_percent"] is not None and right["measured_percent"] is None
        for left, right in pairwise(rows)
    )
    if outages >= 3:
        reasons.append("sensor_repeated_outages")
    return {
        "status": "review_recommended" if reasons else "no_pattern_detected",
        "reasons": reasons,
        "independent_reports": len(values),
        "outage_transitions": outages,
        "device_fault_confirmed": False,
    }


class CycleGuidance(TypedDict):
    """Typed estimates and manual suggestions; unavailable values stay null."""

    estimated: bool
    settings_changed: bool
    active_minutes: float | None
    cycles: int | None
    pause_minutes: float | None
    total_minutes: float | None
    review_reasons: list[str]
    suggested_cycle_minutes: int | None
    suggested_soak_minutes: int | None
    application_rate_mm_h: NotRequired[float]
    profile_infiltration_mm_h: NotRequired[float]


def cycle_guidance(
    *,
    liters: float,
    area_m2: float,
    flow_l_min: float | None,
    infiltration_mm_h: float,
    cycle_minutes: float,
    soak_minutes: float,
    maximum_minutes: float,
    first_cycle_remaining_minutes: float | None = None,
    current_soak_remaining_minutes: float = 0.0,
    minimum_active_minutes: float = 0.0,
) -> CycleGuidance:
    """Explain configured cycles and suggest a manual review when applying too fast.

    Flow must originate from an owned session, never another shared-meter user.
    Soil infiltration is profile-based. Recommendations do not alter settings.
    """
    result: CycleGuidance = {
        "estimated": True,
        "settings_changed": False,
        "active_minutes": None,
        "cycles": None,
        "pause_minutes": None,
        "total_minutes": None,
        "review_reasons": [],
        "suggested_cycle_minutes": None,
        "suggested_soak_minutes": None,
    }
    if liters <= 0 and minimum_active_minutes <= 0:
        return result
    if (
        flow_l_min is None
        or not math.isfinite(flow_l_min)
        or flow_l_min <= 0
        or area_m2 <= 0
    ):
        result["review_reasons"] = ["cycle_flow_unknown"]
        return result
    active = max(0.0, liters / flow_l_min, minimum_active_minutes)
    if cycle_minutes > 0:
        first = (
            cycle_minutes
            if first_cycle_remaining_minutes is None
            else max(0.0, min(cycle_minutes, first_cycle_remaining_minutes))
        )
        count = (
            1 + max(0, math.ceil((active - first) / cycle_minutes))
            if first > 0
            else max(1, math.ceil(active / cycle_minutes))
        )
        # At an already exhausted active segment, a pause is due immediately.
        intermediate = max(0, count - 1) + int(first <= 0)
        pause = intermediate * max(0.0, soak_minutes) + max(
            0.0, current_soak_remaining_minutes
        )
    else:
        count, pause = 1, max(0.0, current_soak_remaining_minutes)
    rate = flow_l_min / area_m2 * 60
    reasons = []
    if rate > infiltration_mm_h:
        reasons.append("cycle_infiltration_review")
        # Bound a suggested per-cycle depth to 1..5 mm; this is a heuristic.
        depth = max(1.0, min(5.0, infiltration_mm_h / 4))
        result["suggested_cycle_minutes"] = max(
            1, min(30, math.floor(depth / rate * 60))
        )
        result["suggested_soak_minutes"] = 15 if infiltration_mm_h >= 5 else 30
    if active + pause > maximum_minutes:
        reasons.append("maximum_runtime_before_target")
    result.update(
        {
            "active_minutes": round(active, 1),
            "cycles": count,
            "pause_minutes": round(pause, 1),
            "total_minutes": round(active + pause, 1),
            "application_rate_mm_h": round(rate, 2),
            "profile_infiltration_mm_h": infiltration_mm_h,
            "review_reasons": reasons,
        }
    )
    return result
