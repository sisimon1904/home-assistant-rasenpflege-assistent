"""Local irrigation schedules and recorded consumption, without network access."""

from datetime import date, datetime, time, timedelta
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
        "week": today - timedelta(days=today.weekday()),
        "month": today.replace(day=1),
    }
    output = {}
    for label, start in periods.items():
        matching = []
        for record in records:
            try:
                day = date.fromisoformat(record["date"])
            except (KeyError, TypeError, ValueError):
                continue
            if start <= day <= today:
                matching.append(record)
        output[f"{label}_liters"] = round(
            sum(
                float(record["liters"])
                for record in matching
                if record.get("liters") is not None
            ),
            2,
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
                    float(record["liters"])
                    for record in matching
                    if record.get("source") == source
                    and record.get("liters") is not None
                ),
                2,
            )
        output[f"{label}_source"] = "recorded_water_only"
    return output
