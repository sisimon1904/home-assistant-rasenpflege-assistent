"""Pure calculation helpers for lawn-care recommendations."""

from __future__ import annotations

import math
from calendar import monthrange
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Any


def grassland_temperature_increment(day: date, mean_temperature: float) -> float:
    """Return the weighted GTS contribution for one day."""
    if mean_temperature <= 0:
        return 0.0
    if day.month == 1:
        factor = 0.5
    elif day.month == 2:
        factor = 0.75
    else:
        factor = 1.0
    return mean_temperature * factor


def sum_forecast_rain(
    forecast: list[dict[str, Any]],
    days: int = 3,
    *,
    probability_adjusted: bool = False,
) -> float | None:
    """Sum forecast precipitation for the next number of daily entries."""
    values: list[float] = []
    for item in forecast[:days]:
        value = item.get("precipitation")
        if value is None:
            value = item.get("native_precipitation")
        try:
            amount = max(0.0, float(value))
            if probability_adjusted:
                try:
                    probability = float(item.get("precipitation_probability", 100))
                except (TypeError, ValueError):
                    probability = 100.0
                amount *= max(0.0, min(100.0, probability)) / 100
            values.append(amount)
        except (TypeError, ValueError):
            continue
    return round(sum(values), 1) if values else None


def sum_hourly_forecast_rain(
    forecast: list[dict[str, Any]],
    hours: int,
    now: datetime | None = None,
    *,
    probability_adjusted: bool = False,
) -> float | None:
    """Sum precipitation inside a real timestamp window."""
    dated: list[tuple[datetime, dict[str, Any]]] = []
    for item in forecast:
        raw = item.get("datetime")
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        dated.append((value, item))
    if not dated:
        return sum_forecast_rain(
            forecast, hours, probability_adjusted=probability_adjusted
        )
    dated.sort(key=lambda value: value[0])
    start = now or dated[0][0]
    if start.tzinfo is None and dated[0][0].tzinfo is not None:
        start = start.replace(tzinfo=dated[0][0].tzinfo)
    elif start.tzinfo is not None and dated[0][0].tzinfo is None:
        dated = [
            (timestamp.replace(tzinfo=start.tzinfo), item) for timestamp, item in dated
        ]
    end = start + timedelta(hours=hours)
    return sum_forecast_rain(
        [item for timestamp, item in dated if start <= timestamp < end],
        len(dated),
        probability_adjusted=probability_adjusted,
    )


def forecast_coverage_hours(
    hourly_forecast: list[dict[str, Any]],
    daily_forecast: list[dict[str, Any]],
    maximum_hours: int = 72,
    now: datetime | None = None,
) -> int:
    """Return the approximate future period covered by available forecasts."""
    timestamps: list[datetime] = []
    for item in hourly_forecast:
        try:
            timestamps.append(
                datetime.fromisoformat(str(item["datetime"]).replace("Z", "+00:00"))
            )
        except (KeyError, TypeError, ValueError):
            continue
    had_timestamps = bool(timestamps)
    timestamps.sort()
    if timestamps and now is not None:
        reference = now
        if reference.tzinfo is None and timestamps[0].tzinfo is not None:
            reference = reference.replace(tzinfo=timestamps[0].tzinfo)
        elif reference.tzinfo is not None and timestamps[0].tzinfo is None:
            timestamps = [
                timestamp.replace(tzinfo=reference.tzinfo) for timestamp in timestamps
            ]
        timestamps = [timestamp for timestamp in timestamps if timestamp >= reference]
    if len(timestamps) >= 2:
        intervals = sorted(
            max(0.0, (current - previous).total_seconds() / 3600)
            for previous, current in pairwise(timestamps)
            if current > previous
        )
        step = intervals[len(intervals) // 2] if intervals else 1.0
        step = max(1.0, min(24.0, step))
        hourly_coverage = min(
            maximum_hours,
            round((timestamps[-1] - timestamps[0]).total_seconds() / 3600 + step),
        )
    elif timestamps:
        hourly_coverage = min(maximum_hours, 1)
    elif had_timestamps:
        hourly_coverage = 0
    else:
        hourly_coverage = min(maximum_hours, len(hourly_forecast))
    daily_coverage = min(maximum_hours, len(daily_forecast) * 24)
    return max(hourly_coverage, daily_coverage)


def next_forecast_rain_at(
    forecast: list[dict[str, Any]], now: datetime | None = None
) -> str | None:
    """Return the timestamp of the next meaningful hourly precipitation."""
    dated: list[tuple[datetime, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for item in forecast:
        raw = item.get("datetime")
        if not raw:
            undated.append(item)
            continue
        try:
            dated.append(
                (datetime.fromisoformat(str(raw).replace("Z", "+00:00")), item)
            )
        except ValueError:
            continue
    dated.sort(key=lambda value: value[0])
    if now is not None and dated:
        reference = now
        if reference.tzinfo is None and dated[0][0].tzinfo is not None:
            reference = reference.replace(tzinfo=dated[0][0].tzinfo)
        elif reference.tzinfo is not None and dated[0][0].tzinfo is None:
            dated = [
                (timestamp.replace(tzinfo=reference.tzinfo), item)
                for timestamp, item in dated
            ]
        dated = [
            (timestamp, item) for timestamp, item in dated if timestamp >= reference
        ]
    for _timestamp, item in dated:
        value = item.get("precipitation", item.get("native_precipitation"))
        try:
            if float(value) >= 0.1:
                timestamp = item.get("datetime")
                return str(timestamp) if timestamp else None
        except (TypeError, ValueError):
            continue
    for item in undated:
        value = item.get("precipitation", item.get("native_precipitation"))
        try:
            if float(value) >= 0.1:
                return None
        except (TypeError, ValueError):
            continue
    return None


def days_since(value: date | None, today: date) -> int | None:
    """Return full days since a date."""
    if value is None:
        return None
    return max(0, (today - value).days)


SOIL_PROFILES = {
    "sandy": {
        "capacity_mm": 22.0,
        "wilting_point_fraction": 0.12,
        "readily_available_fraction": 0.45,
        "infiltration_mm_per_hour": 18.0,
        "interception_mm": 0.25,
    },
    "loamy": {
        "capacity_mm": 40.0,
        "wilting_point_fraction": 0.18,
        "readily_available_fraction": 0.50,
        "infiltration_mm_per_hour": 12.0,
        "interception_mm": 0.35,
    },
    "clayey": {
        "capacity_mm": 46.0,
        "wilting_point_fraction": 0.25,
        "readily_available_fraction": 0.55,
        "infiltration_mm_per_hour": 7.0,
        "interception_mm": 0.45,
    },
}


def soil_capacity(soil_type: str, root_depth_cm: float = 10.0) -> float:
    """Return the approximate plant-available root-zone water in mm."""
    base = float(SOIL_PROFILES.get(soil_type, SOIL_PROFILES["loamy"])["capacity_mm"])
    return round(base * max(0.5, min(3.0, root_depth_cm / 10.0)), 2)


def soil_profile(soil_type: str) -> dict[str, float]:
    """Return hydrological properties for a lawn root zone."""
    return dict(SOIL_PROFILES.get(soil_type, SOIL_PROFILES["loamy"]))


def extraterrestrial_radiation(day: date, latitude: float) -> float:
    """Return daily extraterrestrial radiation in MJ m-2 day-1."""
    day_of_year = day.timetuple().tm_yday
    phi = math.radians(max(-65.0, min(65.0, latitude)))
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    sunset_angle = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return (
        24
        * 60
        / math.pi
        * 0.0820
        * dr
        * (
            sunset_angle * math.sin(phi) * math.sin(delta)
            + math.cos(phi) * math.cos(delta) * math.sin(sunset_angle)
        )
    )


def hargreaves_evapotranspiration(
    *, day: date, latitude: float, temperature_min: float, temperature_max: float
) -> float:
    """Estimate reference evapotranspiration using Hargreaves-Samani."""
    t_min = min(temperature_min, temperature_max)
    t_max = max(temperature_min, temperature_max)
    t_mean = (t_min + t_max) / 2
    radiation = extraterrestrial_radiation(day, latitude)
    radiation_water_equivalent = radiation * 0.408
    et0 = (
        0.0023
        * (t_mean + 17.8)
        * math.sqrt(max(0.0, t_max - t_min))
        * radiation_water_equivalent
    )
    return round(max(0.0, et0), 2)


def _saturation_vapor_pressure(temperature: float) -> float:
    """Return saturation vapor pressure in kPa."""
    return 0.6108 * math.exp(17.27 * temperature / (temperature + 237.3))


def penman_monteith_evapotranspiration(
    *,
    day: date,
    latitude: float,
    elevation: float,
    temperature_min: float,
    temperature_max: float,
    humidity: float,
    wind_speed_m_s: float,
    cloud_coverage: float,
    pressure_hpa: float | None = None,
    dew_point: float | None = None,
    wind_measurement_height_m: float = 10.0,
) -> float:
    """Estimate daily reference ET with FAO-56 Penman-Monteith inputs."""
    t_min = min(temperature_min, temperature_max)
    t_max = max(temperature_min, temperature_max)
    t_mean = (t_min + t_max) / 2
    relative_humidity = max(1.0, min(100.0, humidity))
    wind = max(0.0, min(25.0, wind_speed_m_s))
    height = max(0.2, wind_measurement_height_m)
    if abs(height - 2.0) > 0.01:
        wind *= 4.87 / math.log(67.8 * height - 5.42)
    clouds = max(0.0, min(100.0, cloud_coverage))

    es = (_saturation_vapor_pressure(t_min) + _saturation_vapor_pressure(t_max)) / 2
    ea = (
        _saturation_vapor_pressure(dew_point)
        if dew_point is not None
        else _saturation_vapor_pressure(t_mean) * relative_humidity / 100
    )
    vapor_pressure_deficit = max(0.0, es - ea)
    delta = 4098 * _saturation_vapor_pressure(t_mean) / (t_mean + 237.3) ** 2
    pressure_kpa = (
        max(80.0, min(110.0, pressure_hpa / 10))
        if pressure_hpa is not None
        else 101.3 * ((293 - 0.0065 * max(-100.0, elevation)) / 293) ** 5.26
    )
    gamma = 0.000665 * pressure_kpa

    ra = extraterrestrial_radiation(day, latitude)
    sunshine_fraction = 1 - clouds / 100
    solar_radiation = ra * (0.25 + 0.5 * sunshine_fraction)
    clear_sky_radiation = max(0.1, (0.75 + 0.00002 * elevation) * ra)
    net_shortwave = (1 - 0.23) * solar_radiation
    cloud_factor = max(
        0.05,
        min(1.0, 1.35 * solar_radiation / clear_sky_radiation - 0.35),
    )
    net_longwave = (
        4.903e-9
        * (((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4) / 2)
        * max(0.05, 0.34 - 0.14 * math.sqrt(max(0.0, ea)))
        * cloud_factor
    )
    net_radiation = max(0.0, net_shortwave - net_longwave)
    numerator = (
        0.408 * delta * net_radiation
        + gamma * (900 / (t_mean + 273)) * wind * vapor_pressure_deficit
    )
    denominator = delta + gamma * (1 + 0.34 * wind)
    return round(max(0.0, numerator / denominator), 2) if denominator else 0.0


def interval_evapotranspiration(
    *, daily_et_mm: float, end: datetime, interval_hours: float, latitude: float
) -> float:
    """Distribute daily ET with most loss occurring during daylight."""
    if interval_hours <= 0 or daily_et_mm <= 0:
        return 0.0
    day_of_year = end.date().timetuple().tm_yday
    phi = math.radians(max(-65.0, min(65.0, latitude)))
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    angle = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    daylight_hours = max(1.0, min(23.0, 24 * angle / math.pi))
    sunrise = 12 - daylight_hours / 2
    sunset = 12 + daylight_hours / 2
    midpoint = end - timedelta(hours=interval_hours / 2)
    local_hour = midpoint.hour + midpoint.minute / 60
    is_daylight = sunrise <= local_hour < sunset
    daily_share = 0.85 if is_daylight else 0.15
    period_hours = daylight_hours if is_daylight else 24 - daylight_hours
    return round(daily_et_mm * daily_share * interval_hours / period_hours, 4)


def recommended_watering_window(
    forecast: list[dict[str, Any]],
    now: datetime,
    *,
    wind_speed_unit: str = "m/s",
) -> dict[str, Any]:
    """Choose a cool, calm and dry forecast hour for watering."""
    candidates: list[tuple[float, datetime, dict[str, Any], float | None]] = []
    for item in forecast:
        raw_timestamp = item.get("datetime")
        if not raw_timestamp:
            continue
        try:
            timestamp = datetime.fromisoformat(
                str(raw_timestamp).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        reference = now
        if timestamp.tzinfo is not None and reference.tzinfo is not None:
            timestamp = timestamp.astimezone(reference.tzinfo)
        elif timestamp.tzinfo is not None:
            reference = reference.replace(tzinfo=timestamp.tzinfo)
        elif reference.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=reference.tzinfo)
        if not reference <= timestamp <= reference + timedelta(hours=48):
            continue
        try:
            precipitation = max(0.0, float(item.get("precipitation", 0)))
        except (TypeError, ValueError):
            precipitation = 0.0
        try:
            probability = max(
                0.0, min(100.0, float(item.get("precipitation_probability", 0)))
            )
        except (TypeError, ValueError):
            probability = 0.0
        if precipitation >= 0.2 or probability >= 50:
            continue
        try:
            temperature = float(item["temperature"])
        except (KeyError, TypeError, ValueError):
            temperature = None
        try:
            wind = max(0.0, float(item.get("wind_speed", 0)))
        except (TypeError, ValueError):
            wind = 0.0
        normalized_unit = wind_speed_unit.lower()
        if "km/h" in normalized_unit or "kmh" in normalized_unit:
            wind /= 3.6
        elif "mph" in normalized_unit:
            wind *= 0.44704
        elif "kn" in normalized_unit:
            wind *= 0.514444
        if wind > 6:
            continue
        hour_penalty = abs(timestamp.hour + timestamp.minute / 60 - 6)
        if not 4 <= timestamp.hour < 10:
            hour_penalty += 5
        temperature_penalty = max(0.0, (temperature or 18.0) - 24) * 0.8
        score = hour_penalty + wind * 1.5 + temperature_penalty + probability / 25
        candidates.append((score, timestamp, item, wind))
    if not candidates:
        return {
            "start": None,
            "end": None,
            "reason": "no_suitable_window",
            "temperature": None,
            "wind_speed_m_s": None,
        }
    _, start, item, wind = min(candidates, key=lambda candidate: candidate[0])
    try:
        temperature = round(float(item["temperature"]), 1)
    except (KeyError, TypeError, ValueError):
        temperature = None
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "reason": "cool_calm_dry_period"
        if 4 <= start.hour < 10
        else "best_available_period",
        "temperature": temperature,
        "wind_speed_m_s": round(wind, 1) if wind is not None else None,
    }


def update_soil_water_balance(
    *,
    water_mm: float,
    soil_type: str,
    precipitation_mm: float,
    precipitation_intensity_mm_h: float,
    interval_hours: float,
    irrigation_mm: float = 0.0,
    reference_et_mm: float,
    crop_coefficient: float,
    root_depth_cm: float = 10.0,
    slope: str = "flat",
    compaction: str = "normal",
    interception_available_mm: float | None = None,
) -> dict[str, float]:
    """Update a bounded lawn root-zone balance with infiltration and ET stress."""
    profile = soil_profile(soil_type)
    capacity = soil_capacity(soil_type, root_depth_cm)
    rain = max(0.0, precipitation_mm)
    hours = max(0.0, interval_hours)
    interception_limit = (
        profile["interception_mm"]
        if interception_available_mm is None
        else max(0.0, interception_available_mm)
    )
    interception = min(rain, interception_limit)
    throughfall = max(0.0, rain - interception)
    infiltration_rate = profile["infiltration_mm_per_hour"]
    infiltration_rate *= 0.65 if compaction == "compacted" else 1.0
    infiltration_rate *= {"flat": 1.0, "gentle": 0.85, "steep": 0.6}.get(slope, 1.0)
    infiltration_limit = infiltration_rate * max(hours, 1 / 60)
    if precipitation_intensity_mm_h <= infiltration_rate:
        infiltration_limit = throughfall
    infiltrated = min(throughfall, infiltration_limit)
    runoff = max(0.0, throughfall - infiltrated)

    available_before_et = max(0.0, water_mm) + infiltrated + max(0.0, irrigation_mm)
    drainage = max(0.0, available_before_et - capacity)
    available_before_et = min(capacity, available_before_et)
    readily_available = capacity * profile["readily_available_fraction"]
    stress_factor = min(1.0, available_before_et / max(0.1, readily_available))
    potential_et = max(0.0, reference_et_mm * crop_coefficient)
    actual_et = min(available_before_et, potential_et * stress_factor)
    updated = max(0.0, available_before_et - actual_et)
    return {
        "water_mm": round(updated, 3),
        "actual_et_mm": round(actual_et, 3),
        "effective_rain_mm": round(infiltrated, 3),
        "interception_mm": round(interception, 3),
        "runoff_mm": round(runoff, 3),
        "drainage_mm": round(drainage, 3),
        "water_stress_factor": round(stress_factor, 3),
    }


def update_soil_water(
    *,
    water_mm: float,
    capacity_mm: float,
    precipitation_mm: float,
    irrigation_mm: float = 0.0,
    reference_et_mm: float,
    crop_coefficient: float,
    rain_efficiency: float = 0.8,
) -> tuple[float, float]:
    """Update a simple root-zone bucket and return water plus actual ET."""
    effective_rain = max(0.0, precipitation_mm) * max(0.0, min(1.0, rain_efficiency))
    actual_et = max(0.0, reference_et_mm * crop_coefficient)
    updated = water_mm + effective_rain + max(0.0, irrigation_mm) - actual_et
    return round(max(0.0, min(capacity_mm, updated)), 2), round(actual_et, 2)


def precipitation_rate_amounts(
    *,
    rate_mm_per_hour: float,
    now: datetime,
    last_sample: datetime | None,
    maximum_hours: float = 2.0,
) -> tuple[float, float]:
    """Return total and current-day rain represented by a rate sample."""
    if last_sample is None:
        return 0.0, 0.0
    elapsed_hours = min(
        maximum_hours,
        max(0.0, (now - last_sample).total_seconds() / 3600),
    )
    amount = max(0.0, rate_mm_per_hour) * elapsed_hours
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_day_hours = min(
        elapsed_hours,
        max(0.0, (now - midnight).total_seconds() / 3600),
    )
    return amount, max(0.0, rate_mm_per_hour) * current_day_hours


def growth_state(
    *,
    today: date,
    gts: float,
    growth_temperature: float | None,
    soil_moisture_percent: float,
    mower_started_year: int | None,
    previous_state: str | None = None,
) -> str:
    """Classify the vegetation phase of the lawn."""
    if growth_temperature is None:
        return "collecting_data"
    winter_limit = 6 if previous_state == "winter_dormancy" else 5
    if growth_temperature < winter_limit or (
        today.month in (11, 12, 1, 2) and growth_temperature < 7
    ):
        return "winter_dormancy"
    drought_limit = 25 if previous_state == "heat_drought_stress" else 20
    if (
        today.month in range(3, 11)
        and soil_moisture_percent < drought_limit
        and growth_temperature >= 8
    ):
        return "heat_drought_stress"
    if today.month in (9, 10, 11) and growth_temperature < 10:
        return "autumn_slowdown"
    if today.month <= 5 and gts < 200:
        if growth_temperature >= 5 or gts >= 80:
            return "first_awakening"
        return "winter_dormancy"
    if (
        today.month in (2, 3, 4, 5)
        and gts >= 200
        and growth_temperature >= 8
        and mower_started_year != today.year
    ):
        return "sustained_growth_start"
    active_limit = 7 if previous_state == "active_growth" else 8
    if growth_temperature >= active_limit:
        return "active_growth"
    return "slow_growth"


def mower_state(*, growth: str, mower_started_year: int | None, year: int) -> str:
    """Return an actionable mower recommendation for the current phase."""
    if growth == "collecting_data":
        return "collecting_data"
    if growth == "winter_dormancy":
        return "winter_off"
    if growth == "heat_drought_stress":
        return "pause_drought"
    if growth == "autumn_slowdown":
        return "reduce_mowing"
    if growth == "first_awakening":
        return "keep_off" if mower_started_year != year else "mow_less"
    if growth == "sustained_growth_start":
        return "start_mower"
    if growth == "active_growth":
        return "mow_regularly"
    return "mow_less"


def mower_recommendation(
    *,
    growth: str,
    mower_started_year: int | None,
    year: int,
    last_mowing: date | None,
    today: date,
) -> dict[str, Any]:
    """Return mower state, interval and next recommended mowing date."""
    base_state = mower_state(
        growth=growth, mower_started_year=mower_started_year, year=year
    )
    interval = {
        "active_growth": 4,
        "slow_growth": 7,
        "autumn_slowdown": 10,
        "first_awakening": 10,
    }.get(growth)
    next_date = None
    if interval is not None and last_mowing is not None:
        next_date = last_mowing.fromordinal(last_mowing.toordinal() + interval)
        if today < next_date and base_state in {
            "mow_regularly",
            "mow_less",
            "reduce_mowing",
        }:
            base_state = "wait_to_mow"
    return {"status": base_state, "interval": interval, "next_date": next_date}


def watering_recommendation(
    *,
    today: date,
    area_m2: float,
    sun_exposure: str,
    soil_type: str,
    current_temperature: float | None,
    forecast: list[dict[str, Any]],
    last_watering: date | None,
    hourly_forecast: list[dict[str, Any]] | None = None,
    soil_moisture_percent: float | None = None,
    soil_water_mm: float | None = None,
    soil_capacity_mm: float | None = None,
    growth: str | None = None,
    now: datetime | None = None,
    expected_et_24h_mm: float = 0.0,
    rain_efficiency: float = 0.8,
) -> dict[str, Any]:
    """Calculate a conservative weather-based watering recommendation."""
    hourly_forecast = hourly_forecast or []
    coverage_hours = forecast_coverage_hours(hourly_forecast, forecast, now=now)
    hourly_coverage_hours = forecast_coverage_hours(hourly_forecast, [], now=now)
    daily_rain = sum_forecast_rain(forecast, 3)
    rain_24h = (
        sum_hourly_forecast_rain(hourly_forecast, 24, now)
        if hourly_coverage_hours >= 24
        else None
    )
    rain_48h = (
        sum_hourly_forecast_rain(hourly_forecast, 48, now)
        if hourly_coverage_hours >= 48
        else None
    )
    rain_72h = (
        sum_hourly_forecast_rain(hourly_forecast, 72, now)
        if hourly_coverage_hours >= 72
        else None
    )
    if rain_24h is None and forecast:
        rain_24h = sum_forecast_rain(forecast, 1)
    if rain_48h is None and len(forecast) >= 2:
        rain_48h = sum_forecast_rain(forecast, 2)
    if rain_72h is None and len(forecast) >= 3:
        rain_72h = daily_rain
    if rain_72h is not None:
        rain = rain_72h
    elif rain_48h is not None:
        rain = rain_48h
    else:
        rain = rain_24h
    probability_adjusted_rain_24h = (
        sum_hourly_forecast_rain(hourly_forecast, 24, now, probability_adjusted=True)
        if hourly_coverage_hours >= 24
        else None
    )
    if probability_adjusted_rain_24h is None and forecast:
        probability_adjusted_rain_24h = sum_forecast_rain(
            forecast, 1, probability_adjusted=True
        )
    probability_adjusted_rain = (
        sum_hourly_forecast_rain(
            hourly_forecast,
            72 if hourly_coverage_hours >= 72 else 48,
            now,
            probability_adjusted=True,
        )
        if hourly_coverage_hours >= 48
        else None
    )
    if probability_adjusted_rain is None and forecast:
        probability_adjusted_rain = sum_forecast_rain(
            forecast, min(3, len(forecast)), probability_adjusted=True
        )
    elapsed = days_since(last_watering, today)
    month = today.month

    if growth == "winter_dormancy" or (
        growth is None and month not in (4, 5, 6, 7, 8, 9, 10)
    ):
        return {
            "recommended": False,
            "status": "season_pause",
            "mm": 0.0,
            "liters": 0.0,
            "reasons": ["outside_watering_season"],
            "rain": rain,
            "rain_24h": rain_24h,
            "rain_48h": rain_48h,
            "rain_72h": rain_72h,
            "next_rain_at": next_forecast_rain_at(hourly_forecast, now),
            "hours_until_rain": None,
            "effective_rain_24h": 0.0,
            "probability_adjusted_rain_24h": probability_adjusted_rain_24h,
            "expected_et_24h": round(max(0.0, expected_et_24h_mm), 1),
            "forecast_72h_estimated": (
                hourly_coverage_hours < 72 and rain_72h is not None
            ),
            "forecast_coverage_hours": coverage_hours,
            "confidence": (
                "high"
                if hourly_coverage_hours >= 24
                else "medium"
                if rain is not None
                else "low"
            ),
        }

    interval = 7
    target_mm = 15.0
    if soil_type == "sandy":
        interval = 4
        target_mm = 10.0
    elif soil_type == "clayey":
        interval = 9
        target_mm = 15.0

    if sun_exposure == "sunny":
        interval -= 1
    elif sun_exposure == "shade":
        interval += 2
        target_mm = max(10.0, target_mm - 3.0)

    hot = current_temperature is not None and current_temperature >= 28.0
    if hot:
        interval = max(3, interval - 2)

    deficit = target_mm
    if soil_water_mm is not None and soil_capacity_mm:
        target_water = soil_capacity_mm * 0.8
        deficit = max(0.0, target_water - soil_water_mm)
        target_mm = min(20.0, max(5.0, round(deficit))) if deficit > 0 else 0.0
    next_rain = next_forecast_rain_at(hourly_forecast, now)
    hours_until_rain: float | None = None
    if next_rain and now is not None:
        try:
            rain_at = datetime.fromisoformat(next_rain.replace("Z", "+00:00"))
            reference = now
            if reference.tzinfo is None and rain_at.tzinfo is not None:
                reference = reference.replace(tzinfo=rain_at.tzinfo)
            elif reference.tzinfo is not None and rain_at.tzinfo is None:
                rain_at = rain_at.replace(tzinfo=reference.tzinfo)
            hours_until_rain = max(0.0, (rain_at - reference).total_seconds() / 3600)
        except ValueError:
            pass
    effective_rain_24h = (
        max(0.0, probability_adjusted_rain_24h) * max(0.0, min(1.0, rain_efficiency))
        if probability_adjusted_rain_24h is not None
        else 0.0
    )
    near_term_need = max(0.0, deficit + max(0.0, expected_et_24h_mm))
    enough_rain_24h = rain_24h is not None and effective_rain_24h >= min(
        8.0, max(3.0, near_term_need)
    )
    enough_later_rain = (
        (soil_moisture_percent is None or soil_moisture_percent >= 35.0)
        and probability_adjusted_rain is not None
        and probability_adjusted_rain * max(0.0, min(1.0, rain_efficiency)) >= 8.0
    )
    enough_rain = enough_rain_24h or enough_later_rain

    due_by_time = elapsed is None or elapsed >= interval
    if soil_moisture_percent is None:
        water_now = due_by_time
        water_soon = False
    else:
        critical = soil_moisture_percent < 25.0
        rain_very_soon = hours_until_rain is not None and hours_until_rain <= 12
        water_now = soil_moisture_percent < 35.0 and not (
            critical and rain_very_soon and enough_rain_24h
        )
        water_soon = (
            soil_moisture_percent < 45.0
            or (due_by_time and soil_moisture_percent < 55.0)
        ) and not water_now

    recommended = water_now and not enough_rain

    reasons: list[str] = []
    if elapsed is None:
        reasons.append("last_watering_unknown")
    else:
        reasons.append("last_watering_known")
    if rain is None:
        reasons.append("forecast_precipitation_unavailable")
    elif enough_rain:
        reasons.append("sufficient_rain_forecast")
    else:
        reasons.append("insufficient_rain_forecast")
    if hot:
        reasons.append("heat_increases_water_demand")
    if soil_moisture_percent is not None:
        reasons.append("modeled_soil_moisture_used")

    adjusted_deficit = max(0.0, near_term_need - effective_rain_24h)
    adjusted_amount = (
        min(20.0, max(5.0, round(adjusted_deficit))) if adjusted_deficit > 0 else 0.0
    )
    if enough_rain and (water_now or water_soon):
        status = "wait_for_rain"
        mm = 0.0
    elif recommended:
        status = "water_now"
        mm = adjusted_amount or target_mm
    elif water_soon:
        status = "water_soon"
        mm = adjusted_amount or target_mm
    else:
        status = "not_due"
        mm = 0.0

    return {
        "recommended": recommended,
        "status": status,
        "mm": mm,
        "liters": round(mm * area_m2),
        "reasons": reasons,
        "rain": rain,
        "rain_24h": rain_24h,
        "rain_48h": rain_48h,
        "rain_72h": rain_72h,
        "next_rain_at": next_rain,
        "hours_until_rain": (
            round(hours_until_rain, 1) if hours_until_rain is not None else None
        ),
        "effective_rain_24h": round(effective_rain_24h, 1),
        "probability_adjusted_rain_24h": probability_adjusted_rain_24h,
        "expected_et_24h": round(max(0.0, expected_et_24h_mm), 1),
        "forecast_72h_estimated": (hourly_coverage_hours < 72 and rain_72h is not None),
        "forecast_coverage_hours": coverage_hours,
        "confidence": (
            "high"
            if hourly_coverage_hours >= 24 and elapsed is not None
            else "medium"
            if rain is not None and elapsed is not None
            else "low"
        ),
    }


def next_lawn_action(
    *,
    watering_status: str,
    fertilizing_recommended: bool,
    mower_status: str,
) -> str:
    """Return the single most useful next lawn-care action."""
    if watering_status == "water_now":
        return "water_lawn"
    if watering_status == "water_soon":
        return "prepare_watering"
    if watering_status == "wait_for_rain":
        return "wait_for_rain"
    if mower_status == "start_mower":
        return "start_mower"
    if mower_status == "winter_off":
        return "winterize_mower"
    if fertilizing_recommended:
        return "fertilize_lawn"
    if mower_status in {"mow_regularly", "mow_less", "reduce_mowing"}:
        return "mow_lawn"
    if mower_status == "collecting_data":
        return "collecting_data"
    return "no_action"


def _window(
    today: date,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
) -> str:
    """Return a human-readable fertilizing window."""
    year = today.year
    end = date(year, end_month, min(end_day, monthrange(year, end_month)[1]))
    if today > end:
        year += 1
    return (
        f"{start_day:02d}.{start_month:02d}.{year}–{end_day:02d}.{end_month:02d}.{year}"
    )


def fertilizing_recommendation(
    *,
    today: date,
    gts: float,
    area_m2: float,
    lawn_type: str,
    last_fertilizing: date | None,
) -> dict[str, Any]:
    """Return seasonal NPK type and product quantity recommendation."""
    elapsed = days_since(last_fertilizing, today)
    month = today.month
    reasons: list[str] = []

    dose = 30.0
    if lawn_type == "play":
        dose = 35.0
    elif lawn_type == "ornamental":
        dose = 25.0
    elif lawn_type == "shade":
        dose = 22.0

    due = False
    status = "not_due"
    npk = "–"
    next_window = "–"

    if month in (3, 4):
        npk = "20-5-8"
        next_window = _window(today, 3, 15, 4, 30)
        if gts < 200:
            status = "wait_for_growth"
            reasons.append("gts_below_200")
        elif elapsed is None or elapsed >= 42:
            due = True
            status = "spring_fertilizing_recommended"
            reasons.append("gts_reached_200")
        else:
            status = "spring_fertilizing_recorded"
    elif month in (5, 6):
        npk = "20-5-8"
        next_window = _window(today, 5, 15, 6, 30)
        if elapsed is None or elapsed >= 56:
            due = True
            status = "summer_fertilizing_recommended"
            reasons.append("main_growth_and_interval_reached")
        else:
            status = "fertilizing_not_due_yet"
    elif month in (7, 8):
        npk = "15-5-15"
        next_window = _window(today, 8, 15, 9, 30)
        status = "fertilize_only_if_needed"
        reasons.append("avoid_nitrogen_during_heat_or_drought")
    elif month in (9, 10):
        npk = "8-4-15"
        next_window = _window(today, 9, 1, 10, 15)
        if elapsed is None or elapsed >= 42:
            due = True
            status = "autumn_fertilizing_recommended"
            reasons.append("potassium_supports_winter_hardiness")
        else:
            status = "autumn_fertilizing_recorded"
    else:
        npk = "–"
        next_window = _window(today, 3, 15, 4, 30)
        reasons.append("outside_fertilizing_season")

    if elapsed is not None:
        reasons.append("last_fertilizing_known")
    else:
        reasons.append("last_fertilizing_unknown")

    product_kg = round(dose * area_m2 / 1000, 2) if due else 0.0
    return {
        "recommended": due,
        "status": status,
        "npk": npk,
        "dose": dose if due else 0.0,
        "total_kg": product_kg,
        "reasons": reasons,
        "next_window": next_window,
    }


def lawn_status(
    *,
    growth: str,
    watering_status: str,
    fertilizing_due: bool,
    mower_status: str,
) -> str:
    """Return a concise overall lawn status."""
    if growth == "collecting_data":
        return "collecting_data"
    if growth == "heat_drought_stress":
        return "drought_stress"
    if watering_status == "water_now":
        return "water_now"
    if watering_status == "water_soon":
        return "water_soon"
    if watering_status == "wait_for_rain":
        return "wait_for_rain"
    if fertilizing_due:
        return "fertilizing_recommended"
    if mower_status in {"start_mower", "mow_regularly", "mow_less", "reduce_mowing"}:
        return "mowing_recommended"
    if growth == "winter_dormancy":
        return "winter_dormancy"
    if growth in {"first_awakening", "sustained_growth_start"}:
        return "early_spring"
    return "good_condition"
