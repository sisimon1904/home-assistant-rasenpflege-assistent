"""Data models for the Rasenpflege-Assistent integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class LawnData:
    """Calculated lawn data exposed by the coordinator."""

    gts: float = 0.0
    lawn_status: str = "unavailable"
    watering_recommended: bool = False
    watering_status: str = "Keine Empfehlung"
    watering_mm: float = 0.0
    watering_liters: float = 0.0
    watering_reasons: list[str] = field(default_factory=list)
    forecast_rain_mm: float | None = None
    watering_confidence: str = "low"
    fertilizing_recommended: bool = False
    fertilizing_status: str = "Keine Empfehlung"
    fertilizer_npk: str = "–"
    fertilizer_dose_g_m2: float = 0.0
    fertilizer_total_kg: float = 0.0
    fertilizing_reasons: list[str] = field(default_factory=list)
    next_fertilizing_window: str = "–"
    last_watering: date | None = None
    last_fertilizing: date | None = None
    days_since_watering: int | None = None
    days_since_fertilizing: int | None = None
    current_temperature: float | None = None
    temperature_source: str = "unavailable"
    growth_status: str = "collecting_data"
    mower_status: str = "collecting_data"
    mower_start_recommended: bool = False
    mower_can_be_switched_off: bool = False
    growth_temperature_7d: float | None = None
    soil_moisture_percent: float = 70.0
    soil_water_mm: float = 0.0
    soil_capacity_mm: float = 0.0
    daily_evapotranspiration_mm: float = 0.0
    soil_model_confidence: str = "low"


@dataclass(slots=True)
class RuntimeState:
    """Persistent sampling and maintenance state."""

    year: int
    gts: float
    sample_date: str
    temperature_sum: float = 0.0
    temperature_samples: int = 0
    last_watering: str | None = None
    last_fertilizing: str | None = None
    configured_initial_gts: float = 0.0
    configured_last_watering: str | None = None
    configured_last_fertilizing: str | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    daily_rain_mm: float = 0.0
    forecast_today_rain_mm: float | None = None
    soil_water_mm: float | None = None
    last_evapotranspiration_mm: float = 0.0
    daily_temperature_history: list[float] = field(default_factory=list)
    mower_started_year: int | None = None
    last_sample_at: str | None = None
    configured_initial_soil_moisture: float = 70.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "year": self.year,
            "gts": self.gts,
            "sample_date": self.sample_date,
            "temperature_sum": self.temperature_sum,
            "temperature_samples": self.temperature_samples,
            "last_watering": self.last_watering,
            "last_fertilizing": self.last_fertilizing,
            "configured_initial_gts": self.configured_initial_gts,
            "configured_last_watering": self.configured_last_watering,
            "configured_last_fertilizing": self.configured_last_fertilizing,
            "temperature_min": self.temperature_min,
            "temperature_max": self.temperature_max,
            "daily_rain_mm": self.daily_rain_mm,
            "forecast_today_rain_mm": self.forecast_today_rain_mm,
            "soil_water_mm": self.soil_water_mm,
            "last_evapotranspiration_mm": self.last_evapotranspiration_mm,
            "daily_temperature_history": self.daily_temperature_history,
            "mower_started_year": self.mower_started_year,
            "last_sample_at": self.last_sample_at,
            "configured_initial_soil_moisture": self.configured_initial_soil_moisture,
        }
