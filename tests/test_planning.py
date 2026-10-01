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


def test_volume_allocation_crosses_week_and_month_boundaries():
    """A measured interval retains its total and splits the local calendar correctly."""
    from zoneinfo import ZoneInfo

    from custom_components.rasenpflege_assistent.planning import allocate_volume

    zone = ZoneInfo("Europe/Berlin")
    parts = allocate_volume(
        datetime(2026, 9, 30, 23, 30, tzinfo=zone),
        datetime(2026, 10, 1, 0, 30, tzinfo=zone),
        100,
    )
    assert [p["liters"] for p in parts] == [50, 50]
    totals = consumption_summary(
        [{"date": "2026-10-01", "liters": 100, "allocations": parts}], date(2026, 10, 1)
    )
    assert totals["day_liters"] == totals["month_liters"] == 50
    assert totals["week_liters"] == 100
    parts[0]["date"], parts[1]["date"] = "2026-10-04", "2026-10-05"
    assert (
        consumption_summary([{"liters": 100, "allocations": parts}], date(2026, 10, 5))[
            "week_liters"
        ]
        == 50
    )


def test_dst_allocation_uses_elapsed_time():
    """A 25-hour autumn day receives its actual elapsed share."""
    from zoneinfo import ZoneInfo

    from custom_components.rasenpflege_assistent.planning import allocate_volume

    zone = ZoneInfo("Europe/Berlin")
    parts = allocate_volume(
        datetime(2026, 10, 25, tzinfo=zone), datetime(2026, 10, 26, 1, tzinfo=zone), 260
    )
    assert [p["liters"] for p in parts] == [250, 10]


@pytest.mark.parametrize(
    "earliest,latest,expected",
    [
        ("2026-09-28T20:00:00", "2026-09-29T03:00:00", "2026-09-28T22:00:00"),
        ("2026-09-29T01:00:00", "2026-09-29T03:00:00", "2026-09-29T01:00:00"),
        ("2026-09-29T03:00:00", "2026-09-30T03:00:00", None),
    ],
)
def test_next_schedule_intersects_forecast(earliest, latest, expected):
    from custom_components.rasenpflege_assistent.planning import next_schedule_time

    settings = {
        "irrigation_weekdays": ["0"],
        "irrigation_start_time": "22:00:00",
        "irrigation_end_time": "02:00:00",
    }
    value = next_schedule_time(
        settings,
        datetime.fromisoformat(earliest).replace(tzinfo=timezone.utc),
        datetime.fromisoformat(latest).replace(tzinfo=timezone.utc),
    )
    assert (value.replace(tzinfo=None).isoformat() if value else None) == expected


def test_equal_times_allow_next_selected_day_from_midnight():
    from custom_components.rasenpflege_assistent.planning import next_schedule_time

    settings = {
        "irrigation_weekdays": ["3"],
        "irrigation_start_time": "12:00:00",
        "irrigation_end_time": "12:00:00",
    }
    at = next_schedule_time(
        settings,
        datetime(2026, 9, 30, 20, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 5, tzinfo=timezone.utc),
    )
    assert at == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_next_schedule_handles_spring_gap_and_autumn_fold():
    from zoneinfo import ZoneInfo

    from custom_components.rasenpflege_assistent.planning import next_schedule_time

    zone = ZoneInfo("Europe/Berlin")
    settings = {
        "irrigation_weekdays": ["6"],
        "irrigation_start_time": "02:30:00",
        "irrigation_end_time": "04:00:00",
    }
    at = next_schedule_time(
        settings,
        datetime(2026, 3, 29, 1, tzinfo=zone),
        datetime(2026, 3, 29, 4, tzinfo=zone),
    )
    assert at.hour == 3
    at = next_schedule_time(
        settings,
        datetime(2026, 10, 25, 2, 40, tzinfo=zone, fold=0),
        datetime(2026, 10, 25, 3, tzinfo=zone),
    )
    # Already inside the allowed interval; preserve the earlier actual instant.
    assert at.fold == 0 and at.minute == 40


def test_gap_without_known_new_day_volume_still_blocks_budget_period():
    """A zero recorded new-day amount must not make a missing interval complete."""
    result = consumption_summary(
        [
            {
                "date": "2026-10-01",
                "liters": 10,
                "allocations": [{"date": "2026-09-30", "liters": 10}],
                "measurement_gap": True,
                "uncertainty_dates": ["2026-09-30", "2026-10-01"],
            }
        ],
        date(2026, 10, 1),
    )
    assert result["day_liters"] == 0
    assert result["day_measurement_gap_sessions"] == 1
