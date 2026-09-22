"""Tests for the pure lawn-care calculations."""

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "lawn_calculations",
    Path(__file__).parents[1]
    / "custom_components"
    / "rasenpflege_assistent"
    / "calculations.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_CALCULATIONS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CALCULATIONS)

fertilizing_recommendation = _CALCULATIONS.fertilizing_recommendation
forecast_coverage_hours = _CALCULATIONS.forecast_coverage_hours
grassland_temperature_increment = _CALCULATIONS.grassland_temperature_increment
growth_state = _CALCULATIONS.growth_state
hargreaves_evapotranspiration = _CALCULATIONS.hargreaves_evapotranspiration
lawn_status = _CALCULATIONS.lawn_status
mower_recommendation = _CALCULATIONS.mower_recommendation
mower_state = _CALCULATIONS.mower_state
next_forecast_rain_at = _CALCULATIONS.next_forecast_rain_at
next_lawn_action = _CALCULATIONS.next_lawn_action
penman_monteith_evapotranspiration = _CALCULATIONS.penman_monteith_evapotranspiration
precipitation_rate_amounts = _CALCULATIONS.precipitation_rate_amounts
sum_forecast_rain = _CALCULATIONS.sum_forecast_rain
sum_hourly_forecast_rain = _CALCULATIONS.sum_hourly_forecast_rain
update_soil_water = _CALCULATIONS.update_soil_water
update_soil_water_balance = _CALCULATIONS.update_soil_water_balance
watering_recommendation = _CALCULATIONS.watering_recommendation


def test_gts_monthly_weighting() -> None:
    """The standard monthly weighting is applied."""
    assert grassland_temperature_increment(date(2026, 1, 15), 10) == 5
    assert grassland_temperature_increment(date(2026, 2, 15), 10) == 7.5
    assert grassland_temperature_increment(date(2026, 3, 15), 10) == 10
    assert grassland_temperature_increment(date(2026, 3, 15), -2) == 0


def test_watering_for_loamy_family_lawn() -> None:
    """A dry sunny interval creates a 15 mm recommendation."""
    result = watering_recommendation(
        today=date(2026, 7, 20),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=30,
        forecast=[{"precipitation": 0}, {"precipitation": 1}],
        last_watering=date(2026, 7, 12),
    )
    assert result["recommended"] is True
    assert result["mm"] == 15
    assert result["liters"] == 1500


def test_forecast_rain_suppresses_watering() -> None:
    """Substantial forecast rain suppresses watering."""
    result = watering_recommendation(
        today=date(2026, 7, 20),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=25,
        forecast=[{"precipitation": 5}, {"precipitation": 5}],
        last_watering=date(2026, 7, 1),
    )
    assert result["recommended"] is False
    assert result["status"] == "wait_for_rain"


def test_watering_amount_uses_soil_water_deficit() -> None:
    """The recommendation refills the modeled reservoir to 80 percent."""
    result = watering_recommendation(
        today=date(2026, 7, 20),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=25,
        forecast=[{"precipitation": 0}],
        last_watering=date(2026, 7, 1),
        soil_moisture_percent=30,
        soil_water_mm=12,
        soil_capacity_mm=40,
    )
    assert result["recommended"] is True
    assert result["mm"] == 20
    assert result["liters"] == 2000


def test_watering_status_uses_clear_moisture_bands() -> None:
    """Modeled moisture produces sufficient, soon and immediate states."""
    common = {
        "today": date(2026, 7, 20),
        "area_m2": 100,
        "sun_exposure": "sunny",
        "soil_type": "loamy",
        "current_temperature": 24,
        "forecast": [{"precipitation": 0}],
        "last_watering": date(2026, 7, 19),
        "soil_capacity_mm": 40,
    }
    sufficient = watering_recommendation(
        **common, soil_moisture_percent=60, soil_water_mm=24
    )
    soon = watering_recommendation(**common, soil_moisture_percent=40, soil_water_mm=16)
    now = watering_recommendation(**common, soil_moisture_percent=30, soil_water_mm=12)
    assert sufficient["status"] == "not_due"
    assert soon["status"] == "water_soon"
    assert soon["recommended"] is False
    assert now["status"] == "water_now"
    assert now["recommended"] is True


def test_last_watering_supports_model_recommendation() -> None:
    """An overdue interval can advance a borderline reservoir to water soon."""
    result = watering_recommendation(
        today=date(2026, 7, 20),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=24,
        forecast=[{"precipitation": 0}],
        last_watering=date(2026, 7, 1),
        soil_moisture_percent=50,
        soil_water_mm=20,
        soil_capacity_mm=40,
    )
    assert result["status"] == "water_soon"


def test_daily_forecast_sum_uses_three_entries() -> None:
    """Only the first three daily forecast periods are added."""
    assert (
        sum_forecast_rain(
            [
                {"precipitation": 1},
                {"precipitation": 2},
                {"precipitation": 3},
                {"precipitation": 20},
            ],
            3,
        )
        == 6
    )


def test_hourly_forecast_windows_and_next_rain() -> None:
    """Hourly forecasts provide fixed rain windows and the next rain time."""
    forecast = [
        {"datetime": "2026-07-20T10:00:00+00:00", "precipitation": 0},
        {"datetime": "2026-07-20T11:00:00+00:00", "precipitation": 1.2},
        {"datetime": "2026-07-20T12:00:00+00:00", "precipitation": 2.3},
    ]
    assert sum_hourly_forecast_rain(forecast, 2) == 1.2
    assert sum_hourly_forecast_rain(forecast, 3) == 3.5
    assert next_forecast_rain_at(forecast) == "2026-07-20T11:00:00+00:00"


def test_past_forecast_entries_are_excluded() -> None:
    """Past rain must not be reported as future precipitation."""
    now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    forecast = [
        {"datetime": "2026-07-20T10:00:00+00:00", "precipitation": 5},
        {"datetime": "2026-07-20T13:00:00+00:00", "precipitation": 0},
        {"datetime": "2026-07-20T14:00:00+00:00", "precipitation": 1.5},
    ]
    assert sum_hourly_forecast_rain(forecast, 24, now) == 1.5
    assert next_forecast_rain_at(forecast, now) == "2026-07-20T14:00:00+00:00"


def test_past_forecast_has_no_future_coverage() -> None:
    """Expired timestamped entries do not count toward forecast coverage."""
    now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    forecast = [
        {"datetime": "2026-07-20T09:00:00+00:00", "precipitation": 0},
        {"datetime": "2026-07-20T10:00:00+00:00", "precipitation": 0},
    ]
    assert forecast_coverage_hours(forecast, [], 72, now) == 0


def test_forecast_coverage_reports_available_period() -> None:
    """Diagnostic coverage never claims more forecast than is available."""
    assert forecast_coverage_hours([{} for _ in range(36)], [], 72) == 36
    assert forecast_coverage_hours([], [{}, {}], 72) == 48
    assert forecast_coverage_hours([{} for _ in range(80)], [], 72) == 72


def test_hourly_forecast_improves_watering_confidence() -> None:
    """An hourly forecast is preferred for rain totals and confidence."""
    result = watering_recommendation(
        today=date(2026, 7, 20),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=25,
        forecast=[{"precipitation": 20}],
        hourly_forecast=[{"precipitation": 0} for _ in range(72)],
        last_watering=date(2026, 7, 1),
    )
    assert result["recommended"] is True
    assert result["rain_24h"] == 0
    assert result["rain_72h"] == 0
    assert result["confidence"] == "high"


def test_next_action_priorities() -> None:
    """Urgent watering takes priority over other lawn-care work."""
    assert (
        next_lawn_action(
            watering_status="water_now",
            fertilizing_recommended=True,
            mower_status="mow_regularly",
        )
        == "water_lawn"
    )
    assert (
        next_lawn_action(
            watering_status="not_due",
            fertilizing_recommended=True,
            mower_status="wait_to_mow",
        )
        == "fertilize_lawn"
    )
    assert (
        next_lawn_action(
            watering_status="water_soon",
            fertilizing_recommended=False,
            mower_status="wait_to_mow",
        )
        == "prepare_watering"
    )


def test_autumn_fertilizer_quantity() -> None:
    """Autumn recommendation returns potassium-rich NPK and product mass."""
    result = fertilizing_recommendation(
        today=date(2026, 9, 20),
        gts=900,
        area_m2=120,
        lawn_type="family",
        last_fertilizing=date(2026, 6, 1),
    )
    assert result["recommended"] is True
    assert "8-4-15" in result["npk"]
    assert result["dose"] == 30
    assert result["total_kg"] == 3.6


def test_growth_state_requests_spring_mower_start() -> None:
    """Spring growth threshold requests one mower start acknowledgement."""
    today = date(2026, 4, 10)
    assert (
        growth_state(
            today=today,
            gts=220,
            growth_temperature=9,
            soil_moisture_percent=60,
            mower_started_year=None,
        )
        == "sustained_growth_start"
    )
    assert (
        growth_state(
            today=today,
            gts=220,
            growth_temperature=9,
            soil_moisture_percent=60,
            mower_started_year=2026,
        )
        == "active_growth"
    )


def test_growth_state_detects_winter_and_drought() -> None:
    """Low temperature and low modeled water have distinct states."""
    assert (
        growth_state(
            today=date(2026, 1, 10),
            gts=10,
            growth_temperature=3,
            soil_moisture_percent=70,
            mower_started_year=None,
        )
        == "winter_dormancy"
    )
    assert (
        growth_state(
            today=date(2026, 7, 10),
            gts=700,
            growth_temperature=18,
            soil_moisture_percent=15,
            mower_started_year=2026,
        )
        == "heat_drought_stress"
    )


def test_growth_state_detects_autumn_slowdown() -> None:
    """Cool autumn weather reduces mowing before full winter dormancy."""
    assert (
        growth_state(
            today=date(2026, 10, 15),
            gts=1200,
            growth_temperature=8,
            soil_moisture_percent=65,
            mower_started_year=2026,
        )
        == "autumn_slowdown"
    )


def test_overall_status_follows_growth_in_mild_winter() -> None:
    """The overall status no longer forces dormancy only from the month."""
    assert (
        lawn_status(
            growth="first_awakening",
            watering_status="not_due",
            fertilizing_due=False,
            mower_status="keep_off",
        )
        == "early_spring"
    )


def test_overall_status_distinguishes_watering_states() -> None:
    """The care status must not call every watering state immediately due."""
    assert (
        lawn_status(
            growth="active_growth",
            watering_status="water_soon",
            fertilizing_due=False,
            mower_status="wait_to_mow",
        )
        == "water_soon"
    )
    assert (
        lawn_status(
            growth="active_growth",
            watering_status="wait_for_rain",
            fertilizing_due=False,
            mower_status="wait_to_mow",
        )
        == "wait_for_rain"
    )


def test_hourly_forecast_uses_timestamp_window() -> None:
    """Three-hour forecast entries are not mistaken for one-hour entries."""
    forecast = [
        {
            "datetime": f"2026-07-20T{hour:02d}:00:00+00:00",
            "precipitation": 1,
        }
        for hour in range(0, 24, 3)
    ]
    assert (
        sum_hourly_forecast_rain(
            forecast, 6, datetime(2026, 7, 20, tzinfo=timezone.utc)
        )
        == 2
    )
    assert forecast_coverage_hours(forecast, [], 72) == 24


def test_three_hour_forecast_coverage_uses_time_not_entry_count() -> None:
    """Eight three-hour entries provide 24 hours of future coverage."""
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    forecast = [
        {
            "datetime": (now + timedelta(hours=hour)).isoformat(),
            "precipitation": 0,
        }
        for hour in range(0, 24, 3)
    ]
    assert forecast_coverage_hours(forecast, [], 72, now) == 24


def test_growth_hysteresis_prevents_threshold_flapping() -> None:
    """An established state uses a small exit margin."""
    assert (
        growth_state(
            today=date(2026, 6, 1),
            gts=400,
            growth_temperature=7.5,
            soil_moisture_percent=60,
            mower_started_year=2026,
            previous_state="active_growth",
        )
        == "active_growth"
    )
    assert (
        growth_state(
            today=date(2026, 7, 1),
            gts=700,
            growth_temperature=20,
            soil_moisture_percent=22,
            mower_started_year=2026,
            previous_state="heat_drought_stress",
        )
        == "heat_drought_stress"
    )


def test_warm_march_is_not_forced_into_watering_pause() -> None:
    """Vegetation state controls the watering season in version 3."""
    result = watering_recommendation(
        today=date(2026, 3, 25),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=18,
        forecast=[{"precipitation": 0}],
        last_watering=date(2026, 3, 1),
        soil_moisture_percent=30,
        soil_water_mm=12,
        soil_capacity_mm=40,
        growth="active_growth",
    )
    assert result["status"] == "water_now"


def test_mower_status_is_actionable() -> None:
    """Vegetation phases are converted into clear mower actions."""
    assert (
        mower_state(growth="winter_dormancy", mower_started_year=2026, year=2026)
        == "winter_off"
    )
    assert (
        mower_state(
            growth="sustained_growth_start",
            mower_started_year=None,
            year=2026,
        )
        == "start_mower"
    )
    assert (
        mower_state(growth="active_growth", mower_started_year=2026, year=2026)
        == "mow_regularly"
    )
    assert (
        mower_state(
            growth="heat_drought_stress",
            mower_started_year=2026,
            year=2026,
        )
        == "pause_drought"
    )


def test_recent_mowing_defers_next_run() -> None:
    """A recent mowing is reflected in the primary mower state."""
    result = mower_recommendation(
        growth="active_growth",
        mower_started_year=2026,
        year=2026,
        last_mowing=date(2026, 6, 9),
        today=date(2026, 6, 10),
    )
    assert result["status"] == "wait_to_mow"
    assert result["interval"] == 4
    assert result["next_date"] == date(2026, 6, 13)


def test_soil_bucket_and_evapotranspiration() -> None:
    """Rain fills and evapotranspiration empties the bounded soil bucket."""
    et0 = hargreaves_evapotranspiration(
        day=date(2026, 7, 10),
        latitude=51.0,
        temperature_min=14,
        temperature_max=27,
    )
    assert et0 > 0
    water, actual_et = update_soil_water(
        water_mm=20,
        capacity_mm=40,
        precipitation_mm=10,
        reference_et_mm=et0,
        crop_coefficient=0.8,
    )
    assert 20 < water <= 40
    assert actual_et > 0


def test_incremental_evapotranspiration_reduces_soil_water() -> None:
    """A small refresh interval still produces a visible water loss."""
    water, actual_et = update_soil_water(
        water_mm=28,
        capacity_mm=40,
        precipitation_mm=0,
        reference_et_mm=0.08,
        crop_coefficient=0.8,
    )
    assert water < 28
    assert actual_et > 0


def test_precipitation_rate_requires_a_valid_baseline() -> None:
    """A restored rate sensor must not backfill an unavailable interval."""
    now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    assert precipitation_rate_amounts(
        rate_mm_per_hour=4,
        now=now,
        last_sample=None,
    ) == (0.0, 0.0)


def test_precipitation_rate_splits_an_interval_at_midnight() -> None:
    """Only the part after midnight contributes to the new daily total."""
    now = datetime(2026, 7, 21, 0, 15, tzinfo=timezone.utc)
    total, current_day = precipitation_rate_amounts(
        rate_mm_per_hour=4,
        now=now,
        last_sample=datetime(2026, 7, 20, 23, 45, tzinfo=timezone.utc),
    )
    assert total == 2.0
    assert current_day == 1.0


def test_penman_monteith_uses_cached_weather_inputs() -> None:
    """Humidity, wind and estimated radiation produce plausible daily ET."""
    et0 = penman_monteith_evapotranspiration(
        day=date(2026, 7, 20),
        latitude=51.0,
        elevation=100,
        temperature_min=15,
        temperature_max=28,
        humidity=55,
        wind_speed_m_s=2.5,
        cloud_coverage=25,
        pressure_hpa=1013,
        dew_point=14,
    )
    assert 2 < et0 < 10


def test_penman_monteith_reacts_to_dry_windy_weather() -> None:
    """Dry windy air evaporates more water than humid calm air."""
    common = {
        "day": date(2026, 7, 20),
        "latitude": 51.0,
        "elevation": 100,
        "temperature_min": 15,
        "temperature_max": 28,
        "cloud_coverage": 25,
    }
    dry = penman_monteith_evapotranspiration(**common, humidity=35, wind_speed_m_s=4)
    humid = penman_monteith_evapotranspiration(
        **common, humidity=85, wind_speed_m_s=0.5
    )
    assert dry > humid


def test_advanced_soil_balance_limits_clay_infiltration() -> None:
    """A short intense shower partly runs off a clayey root zone."""
    result = update_soil_water_balance(
        water_mm=30,
        soil_type="clayey",
        precipitation_mm=12,
        precipitation_intensity_mm_h=24,
        interval_hours=0.5,
        reference_et_mm=0,
        crop_coefficient=0.8,
    )
    assert result["runoff_mm"] > 0
    assert result["effective_rain_mm"] < 12
    assert result["water_mm"] <= 46


def test_advanced_soil_balance_reduces_et_during_water_stress() -> None:
    """A nearly empty root zone cannot lose the full potential ET amount."""
    result = update_soil_water_balance(
        water_mm=2,
        soil_type="loamy",
        precipitation_mm=0,
        precipitation_intensity_mm_h=0,
        interval_hours=1,
        reference_et_mm=4,
        crop_coefficient=0.8,
    )
    assert result["water_stress_factor"] < 1
    assert result["actual_et_mm"] < 3.2


def test_watering_amount_accounts_for_near_term_rain_and_et() -> None:
    """Partial forecast rain reduces rather than merely cancels watering."""
    now = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    hourly = [
        {
            "datetime": (now + timedelta(hours=hour)).isoformat(),
            "precipitation": 0.5 if hour < 10 else 0,
        }
        for hour in range(24)
    ]
    result = watering_recommendation(
        today=now.date(),
        area_m2=100,
        sun_exposure="sunny",
        soil_type="loamy",
        current_temperature=26,
        forecast=[],
        hourly_forecast=hourly,
        last_watering=date(2026, 7, 10),
        soil_moisture_percent=30,
        soil_water_mm=12,
        soil_capacity_mm=40,
        growth="active_growth",
        now=now,
        expected_et_24h_mm=3,
        rain_efficiency=0.85,
    )
    assert result["status"] == "water_now"
    assert 5 <= result["mm"] < 20
    assert result["effective_rain_24h"] > 0
