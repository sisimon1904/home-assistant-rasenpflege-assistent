"""Local irrigation windows, water-consumption periods and time allocation.

File: custom_components/rasenpflege_assistent/planning.py

Pure helpers evaluate weekday/time windows, summarize the durable usage
ledger and allocate measured water across local dates. Budget periods are
local calendar days, Monday-based weeks and calendar months.

Overnight windows belong to their starting weekday. DST searches compare
actual UTC instants while applying local schedule rules. Time allocation
preserves measured volume but estimates its distribution between dates.
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any


def schedule_allowed(settings: dict[str, Any], now: datetime) -> bool:
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


def consumption_summary(records: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Sum local calendar periods; keep unknown and partial sessions explicit.

    Prefer explicit date allocations; older records fall back to their
    recorded date. Preserve unknown-volume and measurement-gap counts
    alongside liters, because automatic budgets must not treat incomplete
    totals as proof of remaining water allowance.
    """
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


def consumption_evidence(records: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Split recorded valve quantities by evidence without inventing precision.

    Manual records retain their separate source totals. Only an explicitly
    complete, non-estimated valve record counts as measured. Legacy records,
    gaps and missing quality flags remain uncertain. Calendar allocations and
    unknown-volume counts use the same rules as the existing ledger summary.
    """
    output = consumption_summary(records, today)
    groups: dict[str, list[dict[str, Any]]] = {
        "measured": [],
        "estimated": [],
        "uncertain": [],
    }
    for record in records:
        if record.get("source") != "irrigation":
            continue
        category = (
            "uncertain"
            if record.get("measurement_gap") is not False
            or record.get("liters") is None
            else "measured"
            if record.get("volume_estimated") is False
            else "estimated"
            if record.get("volume_estimated") is True
            else "uncertain"
        )
        groups[category].append(record)
    for category, rows in groups.items():
        totals = consumption_summary(rows, today)
        for period in ("day", "week", "month"):
            output[f"{period}_{category}_liters"] = totals[f"{period}_liters"]
    return output


def daily_consumption(
    records: list[dict[str, Any]], today: date, days: int = 30
) -> list[dict[str, Any]]:
    """Return 7/30 local ledger dates, retaining allocations and unknowns.

    These are recorded amounts, not proof of daily actual consumption. Empty
    days have no record; unknown-only days retain a null volume. Source totals
    and quality counts are carried alongside partial known quantities.
    """
    if days not in {7, 30}:
        raise ValueError("Daily consumption supports 7 or 30 days")
    # Index the ledger once. A live flow update must not scan a year of
    # records thirty times on HA's event loop. Each record belongs at most
    # once to a particular date, even with multiple allocations on that date.
    first = today - timedelta(days=days - 1)
    buckets: dict[date, list[dict[str, Any]]] = {}
    for record in records:
        dates: set[date] = set()
        for allocation in record.get("allocations") or [record]:
            try:
                at = date.fromisoformat(allocation["date"])
            except (KeyError, TypeError, ValueError):
                continue
            if first <= at <= today:
                dates.add(at)
        for raw in record.get("uncertainty_dates") or []:
            try:
                at = date.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if first <= at <= today:
                dates.add(at)
        for at in dates:
            buckets.setdefault(at, []).append(record)
    output = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        totals = consumption_evidence(buckets.get(day, []), day)
        known = totals["day_liters"]
        unknown = totals["day_unmetered_sessions"]
        output.append(
            {
                "date": day.isoformat(),
                "liters": known if known > 0 or not unknown else None,
                "sessions": totals["day_sessions"],
                "unknown_sessions": unknown,
                "gap_sessions": totals["day_measurement_gap_sessions"],
                "allocation_estimated_sessions": totals[
                    "day_allocation_estimated_sessions"
                ],
                **{
                    kind: totals[f"day_{kind}_liters"]
                    for kind in (
                        "measured",
                        "estimated",
                        "uncertain",
                        "manual_record",
                        "manual_estimate",
                    )
                },
            }
        )
    return output


def allocate_volume(
    start: datetime, end: datetime, liters: float
) -> list[dict[str, Any]]:
    """Split a measured interval at local midnight using actual elapsed seconds.

    Advance boundaries in the supplied local timezone, but divide volume
    by real elapsed UTC seconds. A DST day therefore receives its actual
    duration share rather than an assumed fixed 24-hour share.
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
    settings: dict[str, Any], earliest: datetime, latest: datetime
) -> datetime | None:
    """Find an allowed instant in a forecast interval, including DST transitions.

    Enumerate local start times with both DST folds and include offset
    transitions that can re-enter a permitted window. Compare candidates
    in UTC and keep the latest boundary exclusive. A missing overlap
    returns None instead of proposing a start outside the allowed interval.
    """
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
