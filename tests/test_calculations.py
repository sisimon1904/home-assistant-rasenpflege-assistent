"""Tests for the pure lawn-care calculations."""

from datetime import date

from custom_components.rasenpflege_assistent.calculations import (
    fertilizing_recommendation,
    grassland_temperature_increment,
    growth_state,
    hargreaves_evapotranspiration,
    mower_state,
    update_soil_water,
    watering_recommendation,
)


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
    assert result["status"] == "Auf Regen warten"


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
