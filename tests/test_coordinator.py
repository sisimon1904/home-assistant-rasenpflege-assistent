"""Regression checks for local-day accounting and the water balance."""

from datetime import date, datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rasenpflege_assistent.const import DOMAIN
from custom_components.rasenpflege_assistent.coordinator import LawnCoordinator
from custom_components.rasenpflege_assistent.models import RuntimeState


def _coordinator(hass: HomeAssistant, **options) -> LawnCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"weather_entity": "weather.openweathermap", "soil_type": "loamy"},
        options=options,
    )
    return LawnCoordinator(hass, entry)


async def test_missing_rain_and_temperature_do_not_fake_zero(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Unobserved rain is unknown, but temperature loss still depletes soil."""
    coordinator = _coordinator(hass)
    now = datetime(2026, 7, 20, 13, tzinfo=timezone.utc)
    coordinator._state = RuntimeState(
        year=2026,
        gts=120,
        sample_date="2026-07-20",
        soil_water_mm=24,
        last_soil_update_at=(now - timedelta(hours=1)).isoformat(),
    )
    source, amount, _, intensity = coordinator._sample_precipitation(now)
    assert source == "not_measured"
    assert amount == intensity == 0
    assert coordinator._state.daily_rain_unknown
    result = coordinator._update_soil_model(
        now=now,
        temperature=None,
        weather={"stale": True},
        precipitation_increment_mm=0,
        precipitation_intensity_mm_h=0,
    )
    assert result["method"] == "estimated_fallback"
    assert result["actual_et_mm"] > 0
    assert coordinator._state.soil_water_mm < 24


async def test_rain_correction_affects_runoff(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Corrected storm intensity must cross the soil infiltration threshold."""
    now = datetime(2026, 7, 20, 13, tzinfo=timezone.utc)
    results = []
    for correction in (1.0, 2.0):
        coordinator = _coordinator(hass, rain_correction=correction)
        coordinator._state = RuntimeState(
            year=2026,
            gts=120,
            sample_date="2026-07-20",
            soil_water_mm=10,
            last_soil_update_at=(now - timedelta(hours=1)).isoformat(),
        )
        results.append(
            coordinator._update_soil_model(
                now=now,
                temperature=20,
                weather={"stale": True},
                precipitation_increment_mm=8,
                precipitation_intensity_mm_h=8,
            )["runoff_mm"]
        )
    assert results[1] > results[0]


async def test_full_day_without_temperature_is_gts_gap(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A completed day with no temperature must lower GTS completeness."""
    coordinator = _coordinator(hass)
    coordinator._state = RuntimeState(
        year=2026, gts=100, sample_date=date(2026, 3, 3).isoformat()
    )
    coordinator._roll_day_and_sample(date(2026, 3, 4), 8)
    assert coordinator._state.gts == 100
    assert coordinator._state.missing_temperature_days == 1


async def test_local_midnight_is_day_boundary(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Berlin local date advances before the UTC date does."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    now = datetime(2026, 7, 20, 22, 15, tzinfo=timezone.utc)
    assert dt_util.as_local(now).date() == date(2026, 7, 21)
    coordinator = _coordinator(hass)
    coordinator._state = RuntimeState(
        year=2026, gts=0, sample_date="2026-07-20", temperature_samples=1
    )
    coordinator._roll_day_and_sample(dt_util.as_local(now).date(), 15)
    assert coordinator._state.sample_date == "2026-07-21"
