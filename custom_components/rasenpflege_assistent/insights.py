"""Bounded model history and conservative calibration/response evidence.

File: custom_components/rasenpflege_assistent/insights.py

Pure helpers keep hourly snapshots for seven days, validate restored JSON
and deduplicate sensor reports. Percentages refer to calibrated sensor and
model scales; disagreement is not proof that either source is correct.
Advice never changes parameters or makes device/API calls.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from itertools import pairwise
from statistics import median
from typing import TypedDict

HISTORY_LIMIT = 168
HISTORY_DAYS = 7


class ModelObservation(TypedDict):
    """One hourly snapshot and accumulated water-balance terms in millimeters."""

    timestamp: str
    context: str
    modeled_percent: float
    measured_percent: float | None
    sensor_reported_at: str | None
    deviation: float | None
    rain_mm: float
    et_mm: float
    rain_known: bool


class CalibrationAdvice(TypedDict):
    """Independent observations and heuristic guidance, not parameter fitting."""

    status: str
    reasons: list[str]
    independent_observations: int
    observation_span_hours: float
    median_deviation_percentage_points: float | None
    automatic_parameter_changes: bool


def aware_time(raw: object) -> datetime | None:
    """Reject missing, malformed and naive serialized dates."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def finite_number(raw: object) -> float | None:
    """Reject booleans and non-finite JSON quantities."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if math.isfinite(raw) else None


def restore_history(raw: object, now: datetime) -> list[ModelObservation]:
    """Validate optional history without discarding existing care/usage records."""
    rows: dict[str, ModelObservation] = {}
    if not isinstance(raw, list):
        return []
    for item in raw[-HISTORY_LIMIT * 2 :]:
        if not isinstance(item, Mapping):
            continue
        at = aware_time(item.get("timestamp"))
        modeled = finite_number(item.get("modeled_percent"))
        rain = finite_number(item.get("rain_mm"))
        et = finite_number(item.get("et_mm"))
        context = item.get("context")
        if (
            at is None
            or not now - timedelta(days=HISTORY_DAYS) <= at <= now
            or modeled is None
            or not 0 <= modeled <= 100
            or rain is None
            or et is None
            or rain < 0
            or et < 0
            or not isinstance(context, str)
            or len(context) > 512
            or not isinstance(item.get("rain_known"), bool)
        ):
            continue
        measured = finite_number(item.get("measured_percent"))
        reported = aware_time(item.get("sensor_reported_at"))
        if (
            measured is None
            or not 0 <= measured <= 100
            or reported is None
            or reported > at
        ):
            measured, reported = None, None
        row: ModelObservation = {
            "timestamp": at.isoformat(),
            "context": context,
            "modeled_percent": modeled,
            "measured_percent": measured,
            "sensor_reported_at": reported.isoformat() if reported else None,
            "deviation": round(measured - modeled, 2) if measured is not None else None,
            "rain_mm": rain,
            "et_mm": et,
            "rain_known": item["rain_known"],
        }
        rows[at.replace(minute=0, second=0, microsecond=0).isoformat()] = row
    return sorted(rows.values(), key=lambda row: aware_time(row["timestamp"]) or now)[
        -HISTORY_LIMIT:
    ]


def append_observation(
    history: list[ModelObservation], row: ModelObservation
) -> list[ModelObservation]:
    """Aggregate one hourly bucket; reset evidence when calibration/source changes."""
    now = aware_time(row["timestamp"])
    if now is None:
        return history.copy()
    retained = [
        item.copy()
        for item in restore_history(history, now)
        if item["context"] == row["context"]
    ]
    if retained:
        last = retained[-1]
        previous = aware_time(last["timestamp"])
        if previous == now:
            return retained
        if previous and previous.replace(
            minute=0, second=0, microsecond=0
        ) == now.replace(minute=0, second=0, microsecond=0):
            row = row.copy()
            row["rain_mm"] = round(row["rain_mm"] + last["rain_mm"], 4)
            row["et_mm"] = round(row["et_mm"] + last["et_mm"], 4)
            row["rain_known"] = row["rain_known"] and last["rain_known"]
            retained.pop()
    return (retained + [row.copy()])[-HISTORY_LIMIT:]


def calibration_advice(history: list[ModelObservation]) -> CalibrationAdvice:
    """Require independent reports over a day before flagging persistent bias."""
    unique: dict[str, ModelObservation] = {}
    for row in history:
        reported = row["sensor_reported_at"]
        if reported and row["deviation"] is not None:
            unique.setdefault(reported, row)
    rows = list(unique.values())
    times = [
        at for row in rows if (at := aware_time(row["sensor_reported_at"])) is not None
    ]
    span = (max(times) - min(times)).total_seconds() / 3600 if times else 0.0
    deviations = [value for row in rows if (value := row["deviation"]) is not None]
    bias = median(deviations) if deviations else None
    enough = len(rows) >= 6 and span >= 24
    reasons = ["calibration_insufficient_history"] if not enough else []
    if enough and bias is not None and abs(bias) >= 20:
        # Rain and incomplete observation intervals can create transient mismatch.
        reasons.append("calibration_persistent_disagreement")
        if any(not row["rain_known"] for row in rows):
            reasons.append("calibration_check_rain_source")
        reasons.append("calibration_check_references_and_location")
    if enough and all(row["measured_percent"] in {0.0, 100.0} for row in rows):
        reasons.append("calibration_sensor_at_limits")
    return {
        "status": "collecting_data"
        if not enough
        else "review_recommended"
        if reasons
        else "no_persistent_disagreement",
        "reasons": reasons,
        "independent_observations": len(rows),
        "observation_span_hours": round(span, 1),
        "median_deviation_percentage_points": round(bias, 2)
        if bias is not None
        else None,
        "automatic_parameter_changes": False,
    }


def watering_explanation(
    *,
    capacity_mm: float,
    water_mm: float,
    area_m2: float,
    efficiency: float,
    recommended_mm: float,
    expected_et_mm: float,
    forecast_rain_mm: float | None,
) -> dict[str, float | str | None]:
    """Explain the existing gross dose and separately show estimated root-zone credit.

    The recommendation includes forecast, ET, rounding and dose limits. It is
    not the literal deficit divided by efficiency; preserve current dose policy.
    """
    target = capacity_mm * 0.8
    return {
        "amount_basis": "gross_applied_water",
        "current_water_mm": round(water_mm, 3),
        "capacity_mm": capacity_mm,
        "target_percent": 80.0,
        "target_water_mm": round(target, 3),
        "deficit_to_target_mm": round(max(0.0, target - water_mm), 3),
        "expected_et_24h_mm": expected_et_mm,
        "forecast_rain_24h_mm": forecast_rain_mm,
        "area_m2": area_m2,
        "irrigation_efficiency": efficiency,
        "recommended_gross_mm": recommended_mm,
        "recommended_liters": round(recommended_mm * area_m2),
        "estimated_root_zone_credit_mm": round(recommended_mm * efficiency, 3),
        "dose_policy": "forecast_et_rounding_and_limits",
    }


class WateringResponse(TypedDict):
    """Observed post-watering change with explicit attribution limitations."""

    status: str
    sensor_change_percentage_points: float | None
    measured_liters: float | None
    efficiency_estimated: bool
    reasons: list[str]
    observed_rain_mm: float | None


def watering_response(
    history: list[ModelObservation], session: Mapping[str, object] | None
) -> WateringResponse:
    """Compare observed pre/post watering moisture; never infer hardware failure.

    Require two distinct reports, a recent baseline and a post report between
    30 minutes and 24 hours. Rain gaps or rain make attribution uncertain.
    """
    result: WateringResponse = {
        "status": "insufficient_observations",
        "sensor_change_percentage_points": None,
        "measured_liters": None,
        "efficiency_estimated": False,
        "reasons": ["response_insufficient_observations"],
        "observed_rain_mm": None,
    }
    if not isinstance(session, Mapping) or not session:
        return result
    start, end = (
        aware_time(session.get("started_at")),
        aware_time(session.get("finished_at")),
    )
    liters = finite_number(session.get("liters"))
    result["measured_liters"] = liters
    if (
        start is None
        or end is None
        or end < start
        or liters is None
        or liters <= 0
        or session.get("measurement_gap")
        or session.get("undone")
    ):
        result["reasons"] = ["response_incomplete_watering"]
        return result
    before, after = [], []
    for row in history:
        report = aware_time(row["sensor_reported_at"])
        if report is None or row["measured_percent"] is None:
            continue
        if (
            start - timedelta(hours=6) <= report <= start
            and (aware_time(row["timestamp"]) or end) <= start
        ):
            before.append(row)
        if end + timedelta(minutes=30) <= report <= end + timedelta(hours=24) and (
            aware_time(row["timestamp"]) or end
        ) <= end + timedelta(hours=24):
            after.append(row)
    if not before or not after:
        return result
    first, last = before[-1], after[0]
    baseline, observed = first["measured_percent"], last["measured_percent"]
    if baseline is None or observed is None or first["context"] != last["context"]:
        return result
    interval = [
        row
        for row in history
        if (aware_time(first["timestamp"]) or start)
        <= (aware_time(row["timestamp"]) or end)
        <= (aware_time(last["timestamp"]) or end)
    ]
    rain = sum(row["rain_mm"] for row in interval)
    interval_times = [
        at for row in interval if (at := aware_time(row["timestamp"])) is not None
    ]
    history_gap = any(
        right - left > timedelta(minutes=90) for left, right in pairwise(interval_times)
    )
    confounded = (
        history_gap or rain > 0 or any(not row["rain_known"] for row in interval)
    )
    delta = round(observed - baseline, 2)
    result["status"] = (
        "attribution_uncertain"
        if confounded
        else "review_recommended"
        if delta <= 0
        else "response_observed"
    )
    result["sensor_change_percentage_points"] = delta
    result["observed_rain_mm"] = round(rain, 3)
    result["reasons"] = (
        ["response_history_gap"]
        if history_gap
        else ["response_rain_uncertain"]
        if confounded
        else ["response_check_delivery_and_sensor"]
        if delta <= 0
        else ["response_observed"]
    )
    return result
