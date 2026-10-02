"""Local irrigation schedules and recorded consumption, without network access."""

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any


def schedule_allowed(settings: dict, now: datetime) -> bool:
    """Evaluate local weekdays, including windows spanning midnight.

    An overnight window belongs to the weekday on which it starts.
    Equal start/end times permit the entire selected day.
    """
    weekdays = settings.get("irrigation_weekdays", ["0", "1", "2", "3", "4", "5", "6"])
    try:
        start = time.fromisoformat(settings.get("irrigation_start_time", "00:00:00"))
        end = time.fromisoformat(settings.get("irrigation_end_time", "00:00:00"))
    except (TypeError, ValueError):
        return False
    if (
        start.tzinfo is not None
        or end.tzinfo is not None
        or not isinstance(weekdays, (list, tuple, set))
    ):
        return False
    current = now.time().replace(tzinfo=None)
    owner_day = now.date()
    if start == end:
        within = True
    elif start < end:
        within = start <= current < end
    else:
        within = current >= start or current < end
        if current < end:
            owner_day -= timedelta(days=1)
    return within and str(owner_day.weekday()) in weekdays


def consumption_summary(records: list[dict[str, Any]], today: date) -> dict:
    """Sum local calendar periods; keep unknown and partial sessions explicit."""
    periods = {
        "day": today,
        "week": today - timedelta(days=today.weekday()),
        "month": today.replace(day=1),
    }
    output = {}
    for label, start in periods.items():
        matching = []
        amounts = []
        for record in records:
            allocations = record.get("allocations") or [record]
            selected = []
            for allocation in allocations:
                try:
                    day = date.fromisoformat(allocation["date"])
                    liters = allocation.get("liters")
                    if liters is not None:
                        liters = float(liters)
                        if not math.isfinite(liters) or liters < 0:
                            continue
                except (KeyError, TypeError, ValueError):
                    continue
                if start <= day <= today:
                    selected.append(liters)
            if not selected:
                for raw_day in record.get("uncertainty_dates", []):
                    try:
                        day = date.fromisoformat(raw_day)
                    except (TypeError, ValueError):
                        continue
                    if start <= day <= today:
                        selected = [0.0]
                        break
            if selected:
                matching.append(record)
                amounts.append((record, sum(v for v in selected if v is not None)))
        output[f"{label}_liters"] = round(sum(v for _, v in amounts), 2)
        output[f"{label}_allocation_estimated_sessions"] = sum(
            bool(record.get("allocation_estimated")) for record in matching
        )
        output[f"{label}_unmetered_sessions"] = sum(
            record.get("liters") is None for record in matching
        )
        output[f"{label}_measurement_gap_sessions"] = sum(
            bool(record.get("measurement_gap")) for record in matching
        )
        output[f"{label}_sessions"] = len(matching)
        for source in ("irrigation", "manual_record", "manual_estimate"):
            output[f"{label}_{source}_liters"] = round(
                sum(
                    liters
                    for record, liters in amounts
                    if record.get("source") == source
                ),
                2,
            )
        output[f"{label}_source"] = "recorded_water_only"
    return output


def allocate_volume(start: datetime, end: datetime, liters: float) -> list[dict]:
    """Split a measured interval at local midnight using actual elapsed seconds.

    Callers supply the local timezone. Cumulative readings spanning a boundary
    require an estimated temporal allocation, while their total stays measured.
    """
    first = start.astimezone(timezone.utc)
    last = end.astimezone(timezone.utc)
    if not math.isfinite(liters) or liters <= 0:
        return []
    duration = (last - first).total_seconds()
    if duration <= 0:
        return [{"date": end.date().isoformat(), "liters": liters}]
    result = []
    cursor = first
    while cursor < last:
        local = cursor.astimezone(end.tzinfo)
        midnight = datetime.combine(
            local.date() + timedelta(days=1), time(), end.tzinfo
        )
        edge = min(last, midnight.astimezone(timezone.utc))
        result.append(
            {
                "date": local.date().isoformat(),
                "liters": liters * (edge - cursor).total_seconds() / duration,
            }
        )
        cursor = edge
    return result


def next_schedule_time(
    settings: dict, earliest: datetime, latest: datetime
) -> datetime | None:
    """Find an allowed instant in a forecast interval, including DST transitions."""
    if latest.astimezone(timezone.utc) <= earliest.astimezone(timezone.utc):
        return None
    if schedule_allowed(settings, earliest):
        return earliest
    try:
        start = time.fromisoformat(settings.get("irrigation_start_time", "00:00:00"))
        end = time.fromisoformat(settings.get("irrigation_end_time", "00:00:00"))
        if start == end:
            start = time()
    except (TypeError, ValueError):
        return None
    candidates = []
    first = earliest.astimezone(timezone.utc)
    last = latest.astimezone(timezone.utc)
    cursor = first
    while cursor < last:
        probe = min(cursor + timedelta(hours=1), last)
        previous_offset = cursor.astimezone(earliest.tzinfo).utcoffset()
        if probe.astimezone(earliest.tzinfo).utcoffset() != previous_offset:
            # A rollback can re-enter an allowed window at the transition,
            # even when its nominal daily start is already in the past.
            lower, upper = cursor, probe
            while upper - lower > timedelta(microseconds=1):
                middle = lower + (upper - lower) / 2
                if middle.astimezone(earliest.tzinfo).utcoffset() == previous_offset:
                    lower = middle
                else:
                    upper = middle
            candidate = upper.astimezone(earliest.tzinfo)
            if upper < last and schedule_allowed(settings, candidate):
                candidates.append(candidate)
        cursor = probe
    day = earliest.date()
    while day <= latest.date():
        for fold in (0, 1):
            candidate = datetime.combine(day, start, earliest.tzinfo).replace(fold=fold)
            utc = candidate.astimezone(timezone.utc)
            # A start inside the spring gap becomes eligible at the first
            # existing wall time, rather than one full gap later.
            actual = utc.astimezone(earliest.tzinfo)
            if actual.replace(tzinfo=None) != candidate.replace(tzinfo=None):
                wall = candidate.replace(tzinfo=None)
                alternatives = [
                    candidate.replace(fold=value).astimezone(timezone.utc)
                    for value in (0, 1)
                ]
                lower, upper = min(alternatives), max(alternatives)
                while upper - lower > timedelta(microseconds=1):
                    middle = lower + (upper - lower) / 2
                    if middle.astimezone(earliest.tzinfo).replace(tzinfo=None) < wall:
                        lower = middle
                    else:
                        upper = middle
                utc = upper
                candidate = utc.astimezone(earliest.tzinfo)
            if earliest.astimezone(timezone.utc) <= utc < latest.astimezone(
                timezone.utc
            ) and schedule_allowed(settings, candidate):
                candidates.append(candidate)
        day += timedelta(days=1)
    return (
        min(candidates, key=lambda value: value.astimezone(timezone.utc))
        if candidates
        else None
    )
