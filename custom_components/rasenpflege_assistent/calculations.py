"""Pure calculation helpers for lawn-care recommendations."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
import math
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


def sum_forecast_rain(forecast: list[dict[str, Any]], days: int = 3) -> float | None:
    """Sum forecast precipitation for the next number of daily entries."""
    values: list[float] = []
    for item in forecast[:days]:
        value = item.get("precipitation")
        if value is None:
            value = item.get("native_precipitation")
        try:
            values.append(max(0.0, float(value)))
        except (TypeError, ValueError):
            continue
    return round(sum(values), 1) if values else None


def days_since(value: date | None, today: date) -> int | None:
    """Return full days since a date."""
    if value is None:
        return None
    return max(0, (today - value).days)


SOIL_CAPACITY_MM = {
    "sandy": 22.0,
    "loamy": 40.0,
    "clayey": 46.0,
}


def soil_capacity(soil_type: str) -> float:
    """Return the approximate plant-available root-zone water in mm."""
    return SOIL_CAPACITY_MM.get(soil_type, SOIL_CAPACITY_MM["loamy"])


def hargreaves_evapotranspiration(
    *, day: date, latitude: float, temperature_min: float, temperature_max: float
) -> float:
    """Estimate reference evapotranspiration using Hargreaves-Samani."""
    t_min = min(temperature_min, temperature_max)
    t_max = max(temperature_min, temperature_max)
    t_mean = (t_min + t_max) / 2
    day_of_year = day.timetuple().tm_yday
    phi = math.radians(max(-65.0, min(65.0, latitude)))
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    sunset_angle = math.acos(
        max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta)))
    )
    radiation = (
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
    radiation_water_equivalent = radiation * 0.408
    et0 = (
        0.0023
        * (t_mean + 17.8)
        * math.sqrt(max(0.0, t_max - t_min))
        * radiation_water_equivalent
    )
    return round(max(0.0, et0), 2)


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
    effective_rain = max(0.0, precipitation_mm) * max(
        0.0, min(1.0, rain_efficiency)
    )
    actual_et = max(0.0, reference_et_mm * crop_coefficient)
    updated = water_mm + effective_rain + max(0.0, irrigation_mm) - actual_et
    return round(max(0.0, min(capacity_mm, updated)), 2), round(actual_et, 2)


def growth_state(
    *,
    today: date,
    gts: float,
    growth_temperature: float | None,
    soil_moisture_percent: float,
    mower_started_year: int | None,
) -> str:
    """Classify the vegetation phase of the lawn."""
    if growth_temperature is None:
        return "collecting_data"
    if soil_moisture_percent < 20 and growth_temperature >= 5:
        return "heat_drought_stress"
    if growth_temperature < 5 or (
        today.month in (11, 12, 1, 2) and growth_temperature < 7
    ):
        return "winter_dormancy"
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
    if growth_temperature >= 8:
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


def watering_recommendation(
    *,
    today: date,
    area_m2: float,
    sun_exposure: str,
    soil_type: str,
    current_temperature: float | None,
    forecast: list[dict[str, Any]],
    last_watering: date | None,
    soil_moisture_percent: float | None = None,
) -> dict[str, Any]:
    """Calculate a conservative weather-based watering recommendation."""
    rain = sum_forecast_rain(forecast, 3)
    elapsed = days_since(last_watering, today)
    month = today.month

    if month not in (4, 5, 6, 7, 8, 9, 10):
        return {
            "recommended": False,
            "status": "Saisonpause",
            "mm": 0.0,
            "liters": 0.0,
            "reasons": ["Außerhalb der üblichen Bewässerungssaison"],
            "rain": rain,
            "confidence": "medium" if rain is not None else "low",
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

    due_by_time = elapsed is None or elapsed >= interval
    if soil_moisture_percent is not None:
        due_by_time = soil_moisture_percent < 35.0
    enough_rain = rain is not None and rain >= 8.0
    recommended = due_by_time and not enough_rain

    reasons: list[str] = []
    if elapsed is None:
        reasons.append("Letzte Bewässerung ist nicht bekannt")
    else:
        reasons.append(f"Letzte Bewässerung vor {elapsed} Tagen")
    if rain is None:
        reasons.append("Vorhersage enthält keine Niederschlagsmenge")
    elif enough_rain:
        reasons.append(
            f"In den nächsten 3 Tagen werden etwa {rain:.1f} mm Regen erwartet"
        )
    else:
        reasons.append(
            f"Nur etwa {rain:.1f} mm Regen in den nächsten 3 Tagen erwartet"
        )
    if hot:
        reasons.append("Aktuelle Temperatur erhöht den Wasserbedarf")
    if soil_moisture_percent is not None:
        reasons.append(
            f"Modellierte Bodenfeuchte: {soil_moisture_percent:.0f} %"
        )

    if recommended:
        status = "Jetzt wässern"
        mm = target_mm
    elif enough_rain:
        status = "Auf Regen warten"
        mm = 0.0
    else:
        remaining = max(1, interval - (elapsed or 0))
        status = f"Voraussichtlich in {remaining} Tagen"
        mm = 0.0

    return {
        "recommended": recommended,
        "status": status,
        "mm": mm,
        "liters": round(mm * area_m2),
        "reasons": reasons,
        "rain": rain,
        "confidence": "medium" if rain is not None and elapsed is not None else "low",
    }


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
        f"{start_day:02d}.{start_month:02d}.{year}–"
        f"{end_day:02d}.{end_month:02d}.{year}"
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

    due = False
    status = "Derzeit nicht düngen"
    npk = "–"
    next_window = "–"

    if month in (3, 4):
        npk = "Rasendünger, NPK etwa 20-5-8"
        next_window = _window(today, 3, 15, 4, 30)
        if gts < 200:
            status = "Auf Vegetationsbeginn warten"
            reasons.append(f"Grünlandtemperatursumme erst {gts:.1f}; Richtwert: 200")
        elif elapsed is None or elapsed >= 42:
            due = True
            status = "Frühjahrsdüngung empfohlen"
            reasons.append("Grünlandtemperatursumme hat den Richtwert 200 erreicht")
        else:
            status = "Frühjahrsdüngung bereits protokolliert"
    elif month in (5, 6):
        npk = "Langzeit-Rasendünger, NPK etwa 20-5-8"
        next_window = _window(today, 5, 15, 6, 30)
        if elapsed is None or elapsed >= 56:
            due = True
            status = "Sommerdüngung empfohlen"
            reasons.append(
                "Hauptwachstumsphase und ausreichender Abstand zur letzten Düngung"
            )
        else:
            status = "Noch keine erneute Düngung"
    elif month in (7, 8):
        npk = "Kaliumbetonter Rasendünger, NPK etwa 15-5-15"
        next_window = _window(today, 8, 15, 9, 30)
        status = "Nur bei sichtbarem Bedarf düngen"
        reasons.append("Bei Hitze oder Trockenstress keine stickstoffreiche Düngung")
    elif month in (9, 10):
        npk = "Herbstrasendünger, NPK etwa 8-4-15"
        next_window = _window(today, 9, 1, 10, 15)
        if elapsed is None or elapsed >= 42:
            due = True
            status = "Herbstdüngung empfohlen"
            reasons.append("Kaliumbetonte Herbstdüngung unterstützt die Winterhärte")
        else:
            status = "Herbstdüngung bereits protokolliert"
    else:
        npk = "–"
        next_window = _window(today, 3, 15, 4, 30)
        reasons.append("Außerhalb der üblichen Düngeperiode")

    if elapsed is not None:
        reasons.append(f"Letzte Düngung vor {elapsed} Tagen")
    else:
        reasons.append("Letzte Düngung ist nicht bekannt")

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
    today: date,
    gts: float,
    watering_due: bool,
    fertilizing_due: bool,
) -> str:
    """Return a concise overall lawn status."""
    if today.month in (11, 12, 1, 2):
        return "Winterruhe"
    if gts < 200 and today.month <= 4:
        return "Vorfrühling"
    if watering_due:
        return "Bewässerung empfohlen"
    if fertilizing_due:
        return "Düngung empfohlen"
    return "Guter Zustand"
