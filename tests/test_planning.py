"""Local schedule and consumption regressions."""

from datetime import date, datetime, timezone

import pytest

from custom_components.rasenpflege_assistent.planning import (
    consumption_summary,
    schedule_allowed,
)


@pytest.mark.parametrize(
    "timestamp,allowed",
    [
        ("2026-09-28T21:59:00", False),
        ("2026-09-28T22:00:00", True),
        ("2026-09-29T01:59:00", True),
        ("2026-09-29T02:00:00", False),
        ("2026-09-29T22:00:00", False),
    ],
)
def test_overnight_window_belongs_to_start_day(timestamp, allowed):
    """Monday's overnight window ends Tuesday without granting Tuesday night."""
    settings = {
        "irrigation_weekdays": ["0"],
        "irrigation_start_time": "22:00:00",
        "irrigation_end_time": "02:00:00",
    }
    assert schedule_allowed(settings, datetime.fromisoformat(timestamp)) is allowed


def test_default_all_day_and_empty_weekdays():
    """Old configurations preserve all-day scheduling; users can disable every day."""
    now = datetime(2026, 10, 1, 23, tzinfo=timezone.utc)
    assert schedule_allowed({}, now)
    assert not schedule_allowed({"irrigation_weekdays": []}, now)
    assert not schedule_allowed({"irrigation_start_time": "invalid"}, now)


def test_consumption_uses_local_calendar_and_keeps_unknown_sessions_separate():
    """Week and month totals exclude future dates and never invent unmetered liters."""
    records = [
        {"date": "2026-09-28", "liters": 10},
        {"date": "2026-10-01", "liters": 20, "measurement_gap": True},
        {"date": "2026-10-01", "liters": None},
        {"date": "2026-10-02", "liters": 500},
        {"date": "bad", "liters": 400},
    ]
    result = consumption_summary(records, date(2026, 10, 1))
    assert result["week_liters"] == 30
    assert result["month_liters"] == 20
    assert result["month_unmetered_sessions"] == 1
    assert result["month_measurement_gap_sessions"] == 1
