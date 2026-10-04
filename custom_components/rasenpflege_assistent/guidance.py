"""Read-only duration suggestions, bounded history and soil explanations.

File: custom_components/rasenpflege_assistent/guidance.py

Docking is not proof of full coverage. Suggest a typical elapsed duration only
from at least three recent, comparable, mostly continuous robot observations.
Never apply that suggestion automatically. Legacy records without sufficient
source/clock metadata cannot be upgraded into complete observations.
Soil explanations distinguish the last calculation from a previous watering
credit, which may already be included in that calculation's initial water.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from .const import DEFAULT_MOWING_MIN_MINUTES
from .explanations import reason_text
from .insights import aware_time, finite_number


def restore_maintenance_history(raw: object, now: datetime) -> list[dict[str, Any]]:
    """Keep bounded valid events, including older records without undo details."""
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw[-20:]:
        if not isinstance(item, dict):
            continue
        at = aware_time(item.get("timestamp"))
        if (
            at is None
            or at > now
            or not isinstance(item.get("action"), str)
            or item.get("action") not in {"watering", "mowing", "fertilizing"}
            or not isinstance(item.get("details", {}), dict)
            or not isinstance(item.get("previous", {}), dict)
        ):
            continue
        result.append(deepcopy(item))
    return result


def duration_context(settings: Mapping[str, Any]) -> str:
    """Entity and observation semantics must match across sensor changes."""
    return repr(
        (
            settings.get("mowing_entity"),
            settings.get("mowed_entity"),
            settings.get("mowing_active_state", "mowing"),
            settings.get("mowing_done_state", "docked"),
            settings.get("mowing_min_minutes", DEFAULT_MOWING_MIN_MINUTES),
        )
    )


def duration_suggestion(
    history: object, settings: Mapping[str, Any], now: datetime
) -> dict[str, Any]:
    """Median elapsed minutes from 3–10 comparable observations, not coverage.

    Require at least 85% active time and no more than one interruption (normal
    return). A 25% spread around the median withholds unstable suggestions.
    Future, duplicated, old, source-changed and incomplete records are ignored.
    """
    samples: dict[datetime, tuple[float, float]] = {}
    conflicts: set[datetime] = set()
    context = duration_context(settings)
    minimum = (
        finite_number(settings.get("mowing_min_minutes", DEFAULT_MOWING_MIN_MINUTES))
        or DEFAULT_MOWING_MIN_MINUTES
    )
    if settings.get("mowing_mode", "manual") == "robot" and settings.get(
        "mowing_entity"
    ):
        for event in restore_maintenance_history(history, now):
            detail = event.get("details", {})
            begin = aware_time(detail.get("session_started_at"))
            end = aware_time(detail.get("recorded_at"))
            seconds = finite_number(detail.get("active_seconds"))
            interruptions = finite_number(detail.get("interruptions"))
            if (
                event["action"] != "mowing"
                or detail.get("source") != "robot_estimate"
                or detail.get("duration_context") != context
                or begin is None
                or end is None
                or seconds is None
                or interruptions is None
                or not interruptions.is_integer()
                or not 0 <= interruptions <= 1
                or not now - timedelta(days=90) <= begin < end <= now
            ):
                continue
            elapsed = (
                end.astimezone(timezone.utc) - begin.astimezone(timezone.utc)
            ).total_seconds()
            if (
                minimum * 60 <= seconds <= elapsed <= 12 * 3600
                and seconds / elapsed >= 0.85
            ):
                sample = (seconds / 60, elapsed / 60)
                if end in samples and samples[end] != sample:
                    conflicts.add(end)
                samples[end] = sample
    # Elapsed time includes the short normal return/pause, so the proposed
    # weather window does not underestimate time by using active seconds only.
    chosen = [value for at, value in sorted(samples.items()) if at not in conflicts][
        -10:
    ]
    values = [elapsed for _, elapsed in chosen]
    typical = median(values) if len(values) >= 3 else None
    stable = typical is not None and all(
        abs(value - typical) <= typical * 0.25 for value in values
    )
    reason = (
        "duration_suggestion_estimated"
        if stable
        else "duration_suggestion_variable"
        if typical
        else "duration_suggestion_insufficient"
    )
    return {
        "suggested_minutes": math.ceil(typical)
        if stable and typical is not None
        else None,
        "sample_count": len(values),
        "basis": "elapsed_observation",
        "median_active_minutes": round(median([active for active, _ in chosen]), 1)
        if chosen
        else None,
        "minimum_samples": 3,
        "reason": reason,
        "estimated": True,
        "coverage_confirmed": False,
        "automatically_applied": False,
    }


def soil_explanation(
    trace: Mapping[str, Any] | None, history: object, now: datetime, language: str
) -> dict[str, Any]:
    """Explain signed last-step water terms; watering credits are separate."""
    terms = []
    if trace:
        for field, sign in (
            ("effective_rain_mm", 1),
            ("actual_et_mm", -1),
            ("drainage_mm", -1),
            ("sensor_correction_mm", 1),
        ):
            amount = finite_number(trace.get(field))
            terms.append(
                {
                    "term": field,
                    "amount_mm": round(amount * sign, 4)
                    if amount is not None
                    else None,
                    "text": reason_text("soil_term_" + field, language),
                }
            )
    watering = None
    for event in reversed(restore_maintenance_history(history, now)):
        if event["action"] == "watering":
            detail = event.get("details", {})
            credit = finite_number(detail.get("applied_mm"))
            watering = {
                "recorded_at": detail.get("recorded_at"),
                "model_credit_mm": credit,
                "historical": bool(detail.get("historical")),
                "text": reason_text("soil_watering_separate", language),
            }
            break
    return {
        "calculated_at": trace.get("calculated_at") if trace else None,
        "initial_water_mm": trace.get("initial_water_mm") if trace else None,
        "final_water_mm": trace.get("final_water_mm") if trace else None,
        "terms": terms,
        "last_watering_credit": watering,
        "scope_text": reason_text("soil_last_step", language),
        "field_validated": False,
    }
