"""Read-only care outlook and comparable completed irrigation evidence.

File: custom_components/rasenpflege_assistent/outlook.py

Combine cached candidate times with existing priorities. A future prerequisite
has no known completion time; never turn a candidate into a reservation. Only
complete targeted counter sessions can support repeated quantity deviations.
Legacy, estimated, changed-source and interrupted evidence remains separate.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from .explanations import reason_text
from .insights import aware_time, finite_number


def care_outlook(
    steps: list[dict[str, Any]],
    mowing: Mapping[str, Any],
    watering: Mapping[str, Any],
    fertilizing_hint: str | None,
    now: datetime,
    language: str,
) -> dict[str, Any]:
    """A bounded 48 elapsed-hour preview without simulating future soil states."""
    reference = now.astimezone(timezone.utc)
    horizon = reference + timedelta(hours=48)
    rows: list[dict[str, Any]] = []
    for step in steps:
        action = step["action"]
        raw = (
            mowing.get("start")
            if action == "mow_lawn"
            else watering.get("at")
            if action in {"water_lawn", "prepare_watering"}
            else step.get("not_before")
        )
        candidate = aware_time(raw)
        window = (
            mowing
            if action == "mow_lawn"
            else watering
            if action in {"water_lawn", "prepare_watering"}
            else {}
        )
        end = aware_time(window.get("end"))
        if candidate is not None:
            candidate = candidate.astimezone(timezone.utc)
        if end is not None:
            end = end.astimezone(timezone.utc)
        dependency = step.get("after")
        window_invalid = bool(window) and (
            end is None or candidate is None or end <= max(reference, candidate)
        )
        reason = (
            "outlook_outside_horizon"
            if candidate and candidate > horizon
            else "outlook_expired"
            if end and end <= reference
            else "outlook_prerequisite"
            if dependency
            else "outlook_blocked"
            if step.get("availability") == "blocked"
            else "outlook_no_time"
            if candidate is None or window_invalid
            else "outlook_candidate"
        )
        valid = (
            candidate is not None
            and candidate <= horizon
            and not window_invalid
            and (end is None or reference < end)
        )
        rows.append(
            {
                **step,
                "candidate_at": max(reference, candidate).isoformat()
                if valid and candidate
                else None,
                "candidate_end": min(horizon, end).isoformat()
                if valid and end
                else None,
                "not_before": max(reference, candidate).isoformat()
                if valid
                and candidate
                and not dependency
                and step.get("availability") != "blocked"
                else None,
                "dependency": dependency,
                "dependency_text": reason_text(dependency, language),
                "window_reason": window.get("reason"),
                "window_reason_text": reason_text(window.get("reason"), language),
                "outlook_reason": reason,
                "outlook_reason_text": reason_text(reason, language),
                "window_hint": fertilizing_hint if action == "fertilize_lawn" else None,
                "requires_recheck": action != "no_action",
            }
        )
    return {
        "generated_at": reference.isoformat(),
        "horizon_end": horizon.isoformat(),
        "horizon_hours": 48,
        "steps": rows,
        "reservation": False,
        "scope_text": reason_text("outlook_scope", language),
    }


def irrigation_context(settings: Mapping[str, Any], kind: object, unit: object) -> str:
    """Area, owned valve and meter semantics belong to the completed session."""
    return repr(
        (
            settings.get("irrigation_valve"),
            settings.get("irrigation_flow"),
            finite_number(settings.get("area", 100)),
            kind,
            unit,
        )
    )


def irrigation_comparison(
    raw: object, context: str | None, now: datetime, language: str
) -> dict[str, Any]:
    """Review up to twenty comparable sessions in thirty days; never calibrate.

    Use a descriptive 5% or 1 liter tolerance, whichever is larger. A complete
    shortfall from a stopped session is not a meter fault or systematic underdose.
    """
    rows: list[dict[str, Any]] = []
    counts = {
        key: 0
        for key in (
            "measurement_gaps",
            "estimated_sessions",
            "unknown_sessions",
            "different_context",
            "stopped_short",
            "target_short",
            "target_met",
            "over_target",
        )
    }
    seen: set[str] = set()
    source = raw[-100:] if isinstance(raw, list) else []
    records = []
    for item in source:
        if not isinstance(item, dict) or item.get("source") != "irrigation":
            continue
        at = aware_time(item.get("finished_at"))
        if at and now - timedelta(days=30) <= at <= now:
            records.append((at, item))
    by_id: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    for _, item in records:
        key = item.get("session_id")
        if isinstance(key, str):
            if key in by_id and by_id[key] != item:
                conflicts.add(key)
            by_id[key] = item
    for at, item in sorted(records, key=lambda pair: pair[0])[-20:]:
        identity = item.get("session_id")
        if not isinstance(identity, str) or not identity or identity in seen:
            counts["unknown_sessions"] += int(
                not isinstance(identity, str) or not identity
            )
            continue
        seen.add(identity)
        if identity in conflicts:
            counts["unknown_sessions"] += 1
            continue
        target, liters = (
            finite_number(item.get("target_liters")),
            finite_number(item.get("liters")),
        )
        if item.get("measurement_gap") is True:
            counts["measurement_gaps"] += 1
        elif item.get("measurement_gap") is not False:
            counts["unknown_sessions"] += 1
        elif item.get("volume_estimated") is True:
            counts["estimated_sessions"] += 1
        elif context is None or not isinstance(item.get("comparison_context"), str):
            counts["unknown_sessions"] += 1
        elif item.get("comparison_context") != context:
            counts["different_context"] += 1
        elif (
            item.get("volume_estimated") is not False
            or target is None
            or target <= 0
            or liters is None
            or liters < 0
        ):
            counts["unknown_sessions"] += 1
        else:
            difference = liters - target
            tolerance = max(1.0, target * 0.05)
            status = (
                "over_target"
                if difference > tolerance
                else "target_short"
                if difference < -tolerance and item.get("reason") == "target_reached"
                else "stopped_short"
                if difference < -tolerance
                else "target_met"
            )
            counts[status] += 1
            rows.append(
                {
                    "finished_at": at.isoformat(),
                    "target_liters": target,
                    "recorded_liters": liters,
                    "difference_liters": round(difference, 2),
                    "difference_percent": round(difference / target * 100, 2),
                    "status": status,
                    "status_text": reason_text("comparison_" + status, language),
                }
            )
    repeated = counts["over_target"] >= 3 or counts["target_short"] >= 3
    reason = (
        "comparison_review"
        if repeated
        else "comparison_available"
        if rows
        else "comparison_insufficient"
    )
    return {
        "sessions": rows,
        "counts": counts,
        "comparable_sessions": len(rows),
        "median_difference_liters": round(
            median([row["difference_liters"] for row in rows]), 2
        )
        if rows
        else None,
        "review_recommended": repeated,
        "device_fault_confirmed": False,
        "reason": reason,
        "reason_text": reason_text(reason, language),
        "scope_text": reason_text("comparison_scope", language),
        "period_days": 30,
        "maximum_sessions": 20,
        "settings_changed": False,
        "current_context_known": context is not None,
    }
