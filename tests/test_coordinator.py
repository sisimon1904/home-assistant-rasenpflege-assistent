"""Regression checks for local-day accounting and the water balance.

File: tests/test_coordinator.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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


async def test_manual_gts_baseline_resolves_historical_gap(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A supplied annual GTS baseline explicitly covers missing earlier days."""
    coordinator = _coordinator(hass, initial_gts=140)
    with patch.object(
        coordinator._store,
        "async_load",
        new_callable=AsyncMock,
        return_value={
            "year": 2026,
            "gts": 10,
            "sample_date": "2026-07-20",
            "configured_initial_gts": 0,
            "missing_temperature_days": 8,
            "local_day_model": True,
        },
    ):
        await coordinator._async_setup()
    assert coordinator._state is not None
    assert coordinator._state.gts == 140
    assert coordinator._state.missing_temperature_days == 0


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


async def test_mower_waits_until_next_day_and_twelve_hours_after_watering(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Watering just before local midnight must not permit mowing at midnight."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    coordinator = _coordinator(hass)
    event = datetime(2026, 9, 24, 21, 50, tzinfo=timezone.utc)
    coordinator._state = RuntimeState(
        year=2026,
        gts=500,
        sample_date="2026-09-24",
        last_watering_at=event.isoformat(),
    )
    mower = {"status": "mow_regularly", "next_date": None}
    until, reason = coordinator._pause_mower_when_wet(
        event + timedelta(minutes=10), mower
    )
    assert mower["status"] == "pause_wet"
    assert reason == "watering"
    assert until == event + timedelta(hours=12)
    assert mower["next_date"] == date(2026, 9, 25)
    mower = {"status": "mow_regularly", "next_date": None}
    assert coordinator._pause_mower_when_wet(until, mower) == (None, None)
    assert mower["status"] == "mow_regularly"


async def test_mower_wet_pause_uses_latest_measured_rain_or_watering(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """A later rain event extends the pause even after watering."""
    coordinator = _coordinator(hass)
    event = datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
    coordinator._state = RuntimeState(
        year=2026,
        gts=500,
        sample_date="2026-09-24",
        last_watering_at=event.isoformat(),
        last_wet_rain_at=(event + timedelta(hours=14)).isoformat(),
    )
    mower = {"status": "start_mower", "next_date": None}
    until, reason = coordinator._pause_mower_when_wet(
        event + timedelta(hours=15), mower
    )
    assert reason == "rain"
    assert until == event + timedelta(hours=26)
    assert mower["status"] == "pause_wet"


async def test_extra_refreshes_do_not_overweight_temperature(hass, freezer):
    """Sampling remains spaced by 30 minutes, including across reloads."""
    freezer.move_to("2026-07-20T10:00:00+00:00")
    c = _coordinator(hass)
    c._state = RuntimeState(year=2026, gts=0, sample_date="2026-07-20")
    c._roll_day_and_sample(date(2026, 7, 20), 10)
    for _ in range(100):
        c._roll_day_and_sample(date(2026, 7, 20), 30)
    assert c._state.temperature_samples == 1
    assert c._state.temperature_sum == 10
    stored = c._state.as_dict()
    c._store.async_load = AsyncMock(return_value=stored)
    await c._async_setup()
    c._roll_day_and_sample(date(2026, 7, 20), 30)
    assert c._state.temperature_samples == 1
    freezer.tick(timedelta(minutes=30))
    c._roll_day_and_sample(date(2026, 7, 20), 30)
    assert c._state.temperature_sum / c._state.temperature_samples == 20


async def test_temperature_history_expires_after_gap(hass):
    """August samples must not masquerade as October's seven-day mean."""
    c = _coordinator(hass)
    c._state = RuntimeState(
        year=2026,
        gts=1000,
        sample_date="2026-08-01",
        daily_temperature_history=[25] * 7,
    )
    c._roll_day_and_sample(date(2026, 10, 1), 7)
    assert c._state.daily_temperature_history == []


async def test_unavailable_and_nonfinite_temperature_use_fallback(hass):
    """Invalid sensor values fall back; unavailable weather is not trusted."""
    c = _coordinator(hass, temperature_entity="sensor.outside")
    hass.states.async_set("weather.openweathermap", "sunny", {"temperature": 15})
    for bad in ("nan", "inf", "-inf"):
        hass.states.async_set("sensor.outside", bad, {"unit_of_measurement": "°C"})
        assert c._read_temperature(dt_util.now())[0] == 15
    hass.states.async_set("weather.openweathermap", "unavailable", {"temperature": 15})
    assert c._read_temperature(dt_util.now())[0] is None
    hass.states.async_set(
        "weather.openweathermap", "sunny", {"temperature": float("nan")}
    )
    assert c._read_temperature(dt_util.now())[0] is None


async def test_watering_date_correction_updates_wet_timestamp(hass, freezer):
    """Correcting or clearing a date also corrects the mowing wet interlock."""
    freezer.move_to("2026-07-20T10:00:00+00:00")
    c = _coordinator(hass, last_watering="2026-07-20")
    state = RuntimeState(
        year=2026,
        gts=100,
        sample_date="2026-07-20",
        last_watering="2026-07-01",
        configured_last_watering="2026-07-01",
    )
    c._store.async_load = AsyncMock(return_value=state.as_dict())
    await c._async_setup()
    assert c._state.last_watering_at == dt_util.now().isoformat()
    saved = c._state.as_dict()
    c = _coordinator(hass, last_watering=None)
    c._store.async_load = AsyncMock(return_value=saved)
    await c._async_setup()
    assert c._state.last_watering_at is None


async def test_clearing_automatic_watering_date_uses_revision(hass):
    """A cleared date must override automatic history even if config was empty."""
    c = _coordinator(hass, last_watering=None, last_watering_revision="new")
    state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        last_watering="2026-07-20",
        last_watering_at="2026-07-20T10:00:00+00:00",
        configured_last_watering=None,
    )
    c._store.async_load = AsyncMock(return_value=state.as_dict())
    await c._async_setup()
    assert c._state.last_watering is None
    assert c._state.last_watering_at is None


async def test_physical_soil_readings_expire_at_configured_age(
    hass, enable_custom_integrations
):
    """Stale soil sensors fall back to the model and unknown temperature."""
    coordinator = _coordinator(
        hass,
        soil_moisture_entity="sensor.soil",
        soil_temperature_entity="sensor.soil_temp",
        soil_sensor_max_age_minutes=30,
    )
    hass.states.async_set("sensor.soil", "50")
    hass.states.async_set("sensor.soil_temp", "18")
    now = dt_util.now()
    assert coordinator._read_soil_moisture()[0] is not None
    assert coordinator._read_soil_temperature() == 18
    with patch(
        "custom_components.rasenpflege_assistent.coordinator.dt_util.now",
        return_value=now + timedelta(minutes=31),
    ):
        assert coordinator._read_soil_moisture()[0] is None
        assert coordinator._read_soil_temperature() is None


async def test_clearing_automatic_fertilizing_date_uses_revision(hass):
    """Clearing an automatically recorded date overrides an empty old config."""
    coordinator = _coordinator(
        hass, last_fertilizing=None, last_fertilizing_revision="new"
    )
    coordinator._state = RuntimeState(
        year=2026, gts=100, sample_date="2026-07-20", last_fertilizing="2026-07-19"
    )
    coordinator._store.async_load = AsyncMock(return_value=coordinator._state.as_dict())
    await coordinator._async_setup()
    assert coordinator._state.last_fertilizing is None
    assert coordinator._state.configured_last_fertilizing_revision == "new"


async def test_backdated_water_records_usage_without_rewatering_today(hass):
    """Historical amounts are retained without changing the current reservoir."""
    coordinator = _coordinator(hass, area=100)
    coordinator._state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        soil_water_mm=10,
        last_watering=dt_util.now().date().isoformat(),
        last_watering_at=dt_util.now().isoformat(),
    )
    coordinator._store.async_save = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    previous_date = coordinator._state.last_watering
    await coordinator.async_mark_watered(
        5, recorded_at=dt_util.now() - timedelta(days=3)
    )
    assert coordinator._state.soil_water_mm == 10
    assert coordinator._state.last_watering == previous_date
    assert coordinator._state.water_usage[0]["liters"] == 500
    assert coordinator._state.maintenance_history[-1]["details"]["applied_mm"] == 0
    await coordinator.async_undo_last_action()
    assert coordinator._state.soil_water_mm == 10
    assert not coordinator._state.water_usage


async def test_leaf_wetness_overrides_drying_estimate_but_never_live_irrigation(hass):
    """Fresh wet/dry measurements refine drying; missing readings use the estimate."""
    coordinator = _coordinator(hass, leaf_wetness_entity="binary_sensor.leaf")
    coordinator._state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        last_watering_at=dt_util.now().isoformat(),
    )
    now = dt_util.now()

    def mower():
        return {"status": "mow_regularly", "next_date": None, "next_at": None}

    hass.states.async_set("binary_sensor.leaf", "on")
    assert coordinator._pause_mower_when_wet(now, mower())[1] == "leaf_wetness"
    hass.states.async_set("binary_sensor.leaf", "off")
    assert coordinator._pause_mower_when_wet(now, mower()) == (None, None)
    coordinator._state.irrigation_session = {"paused_at": now.isoformat()}
    assert coordinator._pause_mower_when_wet(now, mower())[1] == "irrigation_paused"
    coordinator._state.irrigation_session = None
    hass.states.async_set("binary_sensor.leaf", "unavailable")
    assert coordinator._pause_mower_when_wet(now, mower())[1] == "watering"


async def test_input_diagnostics_distinguish_missing_invalid_and_stale(hass):
    """Diagnostics explain the sensor fallback instead of collapsing all failures."""
    coordinator = _coordinator(
        hass,
        soil_moisture_entity="sensor.soil",
        soil_temperature_entity="sensor.soil_temp",
    )
    assert (
        coordinator.input_diagnostics()["soil_moisture_entity"]["reason"] == "missing"
    )
    hass.states.async_set("sensor.soil", "nan")
    assert (
        coordinator.input_diagnostics()["soil_moisture_entity"]["reason"] == "invalid"
    )
    hass.states.async_set("sensor.soil", "50")
    now = dt_util.now()
    with patch(
        "custom_components.rasenpflege_assistent.coordinator.dt_util.now",
        return_value=now + timedelta(hours=7),
    ):
        assert (
            coordinator.input_diagnostics()["soil_moisture_entity"]["reason"] == "stale"
        )


async def test_37_runtime_fields_survive_reload(hass):
    """Automation hold, usage and detailed completion survive a coordinator reload."""
    coordinator = _coordinator(hass)
    state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        irrigation_suspended_until=(dt_util.now() + timedelta(hours=1)).isoformat(),
        irrigation_last_session={"liters": 10},
        water_usage=[{"date": dt_util.now().date().isoformat(), "liters": 10}],
    )
    coordinator._store.async_load = AsyncMock(return_value=state.as_dict())
    await coordinator._async_setup()
    assert (
        coordinator._state.irrigation_suspended_until
        == state.irrigation_suspended_until
    )
    assert coordinator._state.irrigation_last_session == {"liters": 10}
    assert coordinator._state.water_usage == state.water_usage


async def test_backdated_water_keeps_newer_date_without_exact_timestamp(hass):
    """Date-only legacy/zero-volume records must not be replaced by older history."""
    coordinator = _coordinator(hass, area=100)
    coordinator._state = RuntimeState(
        year=2026,
        gts=100,
        sample_date=dt_util.now().date().isoformat(),
        soil_water_mm=10,
        last_watering=dt_util.as_local(dt_util.now()).date().isoformat(),
    )
    coordinator._store.async_save = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    newer_date = coordinator._state.last_watering
    await coordinator.async_mark_watered(
        5, recorded_at=dt_util.now() - timedelta(days=2)
    )
    assert coordinator._state.last_watering == newer_date
    assert coordinator._state.last_watering_at is None
