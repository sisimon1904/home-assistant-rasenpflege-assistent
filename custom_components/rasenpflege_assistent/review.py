"""Bounded advice review and read-only irrigation evidence.

File: custom_components/rasenpflege_assistent/review.py

Weather samples are point observations, not continuous grass wetness evidence.
Review only recorded advice with adequate later sample coverage. Never create
zero rainfall from missing data or command devices/retry aborted irrigation.
Session area and meter semantics belong to that session, not current settings.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

from .explanations import reason_text
from .insights import aware_time, finite_number
from .mowing_plan import _hour_reason


def program_context(attributes: Mapping[str, Any]) -> dict[str, str | int | bool]:
    """Copy only explicit source metadata; do not infer a full-lawn program.

    Providers may expose none of these fields. Unknown metadata stays empty,
    rather than being synthesized from docking, progress or device names.
    """
    return {
        key: value
        for key in (
            "mowing_mode",
            "work_mode",
            "task_type",
            "area_id",
            "zone_id",
            "map_id",
        )
        if isinstance((value := attributes.get(key)), (str, int, bool))
        and len(str(value)) <= 128
    }


def restore_advice(raw: object, now: datetime) -> list[dict[str, Any]]:
    """Validate twelve recommendations retained for seven days."""
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw[-12:]:
        if not isinstance(item, dict):
            continue
        start, end, issued = (
            aware_time(item.get(key)) for key in ("start", "end", "issued_at")
        )
        if (
            start
            and end
            and issued
            and now - timedelta(days=7) <= issued <= now
            and issued <= start + timedelta(minutes=1)
            and issued < end
            and start < end <= issued + timedelta(hours=48)
        ):
            result.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "issued_at": issued.isoformat(),
                }
            )
    return result


def remember_advice(
    raw: object, plan: Mapping[str, Any], now: datetime
) -> list[dict[str, Any]]:
    """Append a distinct window during refresh; repeated entity reads never call this."""
    history = restore_advice(raw, now)
    start, end = aware_time(plan.get("start")), aware_time(plan.get("end"))
    if (
        start is None
        or end is None
        or not now - timedelta(minutes=1) <= start < end <= now + timedelta(hours=48)
        or end <= now
    ):
        return history
    if any(
        aware_time(item["end"]) == end
        and abs((start - (aware_time(item["start"]) or start)).total_seconds()) < 1800
        for item in history
    ):
        return history
    return (
        history
        + [
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "issued_at": now.isoformat(),
            }
        ]
    )[-12:]


def review_advice(
    raw: object, observations: object, now: datetime, language: str
) -> dict[str, Any]:
    """Evaluate elapsed windows using samples no further than 45 minutes apart.

    Endpoint observations must be within 45 minutes, with at least two unique
    report times. Stale/repeated weather reports cannot fabricate coverage.
    Even adequate point-sample coverage does not confirm continuous dryness.
    """
    results = []
    for window in restore_advice(raw, now):
        start, end = aware_time(window["start"]), aware_time(window["end"])
        if start is None or end is None or end > now:
            continue
        rows: dict[datetime, dict[str, Any]] = {}
        if isinstance(observations, list):
            for row in observations[-96:]:
                if not isinstance(row, dict) or row.get("stale", True):
                    continue
                at = aware_time(row.get("reported_at"))
                if at and start <= at <= end and at <= now:
                    evidence = {
                        key: row.get(key)
                        for key in (
                            "temperature",
                            "humidity",
                            "dew_point",
                            "wind_speed",
                            "precipitation",
                            "condition",
                        )
                    }
                    if at in rows and rows[at] != evidence:
                        rows[at] = {"forecast_conflict": True}
                    else:
                        rows[at] = evidence
        times = sorted(rows)
        coverage = (
            len(times) >= 2
            and times[0] - start <= timedelta(minutes=45)
            and end - times[-1] <= timedelta(minutes=45)
            and all(b - a <= timedelta(minutes=45) for a, b in pairwise(times))
        )
        reasons = sorted(
            {
                reason
                for row in rows.values()
                if (reason := _hour_reason(row)[0]) is not None
            }
        )
        unknown = any(
            reason.endswith("_unknown") or reason == "forecast_conflict"
            for reason in reasons
        )
        status = (
            "review_insufficient"
            if not coverage or unknown
            else "review_unsuitable_observed"
            if reasons
            else "review_suitable_sampled"
        )
        results.append(
            {
                **window,
                "status": status,
                "status_text": reason_text(status, language),
                "sample_count": len(times),
                "sample_coverage": coverage,
                "reasons": reasons,
                "reasons_text": [reason_text(reason, language) for reason in reasons],
                "surface_dry_confirmed": False,
            }
        )
    # Repeated copies of the same saved interval cannot increase review counts.
    unique = {(row["start"], row["end"]): row for row in results}
    counts = {
        code: sum(row["status"] == code for row in unique.values())
        for code in (
            "review_suitable_sampled",
            "review_unsuitable_observed",
            "review_insufficient",
        )
    }
    return {
        "summary": {
            "reviewed_windows": len(unique),
            "counts": counts,
            "counts_text": [
                {"status": code, "text": reason_text(code, language), "count": count}
                for code, count in counts.items()
            ],
            "accuracy_score": None,
            "retention_days": 7,
            "scope_text": reason_text("review_summary_scope", language),
        },
        "windows": results[-12:],
        "continuous_weather_confirmed": False,
        "surface_dry_confirmed": False,
        "scope_text": reason_text("review_sample_scope", language),
    }


def irrigation_balance(raw: object, language: str) -> dict[str, Any]:
    """Keep unknown totals/remainders explicit; no device actions or auto resume."""
    session = raw if isinstance(raw, dict) else {}

    def quantity(key: str) -> float | None:
        value = finite_number(session.get(key))
        return value if value is not None and value >= 0 else None

    target, liters, credit, area = (
        quantity(key)
        for key in ("target_liters", "liters", "effective_model_mm", "area_m2")
    )
    gap = session.get("measurement_gap") is True
    quality = (
        "water_unmetered"
        if liters is None
        else "water_partial"
        if gap
        else "water_recorded"
    )
    remainder = (
        max(0.0, target - liters)
        if target is not None and liters is not None and not gap
        else None
    )
    reason = (
        session.get("reason")
        if isinstance(session.get("reason"), str)
        else "water_reason_unknown"
    )
    return {
        "target_liters": target,
        "recorded_liters": liters,
        "remaining_liters": round(remainder, 2) if remainder is not None else None,
        "delivery_quality": quality,
        "delivery_quality_text": reason_text(quality, language),
        "measurement_gap": gap,
        "volume_estimated": session.get("volume_estimated")
        if isinstance(session.get("volume_estimated"), bool)
        else None,
        "effective_model_mm": credit,
        "effective_model_liters": round(credit * area, 3)
        if credit is not None and area is not None and area > 0
        else None,
        "area_m2": area,
        "reason": reason,
        "reason_text": reason_text(reason, language),
        "finished_at": session.get("finished_at")
        if aware_time(session.get("finished_at"))
        else None,
        "safety_recheck_required": True,
        "automatically_resumed": False,
        "restart_text": reason_text("water_restart_recheck", language),
        "session_present": bool(session),
    }
