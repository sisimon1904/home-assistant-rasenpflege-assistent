"""Data models for the Lawn Care Assistant integration."""

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
    watering_status: str = "not_due"
    watering_mm: float = 0.0
    watering_liters: float = 0.0
    watering_reasons: list[str] = field(default_factory=list)
    forecast_rain_mm: float | None = None
    forecast_rain_24h_mm: float | None = None
    forecast_rain_48h_mm: float | None = None
    forecast_rain_72h_mm: float | None = None
    next_rain_at: str | None = None
    forecast_updated_at: str | None = None
    observed_rain_today_mm: float = 0.0
    precipitation_source: str = "forecast_estimate"
    watering_confidence: str = "low"
    fertilizing_recommended: bool = False
    fertilizing_status: str = "not_due"
    fertilizer_npk: str = "–"
    fertilizer_dose_g_m2: float = 0.0
    fertilizer_total_kg: float = 0.0
    fertilizing_reasons: list[str] = field(default_factory=list)
    next_fertilizing_window: str = "–"
    last_watering: date | None = None
    last_fertilizing: date | None = None
    last_mowing: date | None = None
    days_since_watering: int | None = None
    days_since_fertilizing: int | None = None
    days_since_mowing: int | None = None
    current_temperature: float | None = None
    temperature_source: str = "unavailable"
    growth_status: str = "collecting_data"
    mower_status: str = "collecting_data"
    mower_start_recommended: bool = False
    mower_can_be_switched_off: bool = False
    mowing_interval_days: int | None = None
    next_mowing_date: date | None = None
    growth_temperature_7d: float | None = None
    soil_moisture_percent: float = 70.0
    measured_soil_moisture_percent: float | None = None
    soil_moisture_source: str = "model"
    soil_water_mm: float = 0.0
    soil_capacity_mm: float = 0.0
    daily_evapotranspiration_mm: float = 0.0
    soil_model_confidence: str = "low"
    next_action: str = "collecting_data"
    data_quality: str = "insufficient"
    data_warnings: list[str] = field(default_factory=list)
    forecast_age_minutes: int | None = None
    temperature_history_days: int = 0
    last_calculation_at: str | None = None


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
    last_mowing: str | None = None
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
    precipitation_last_value: float | None = None
    precipitation_last_sample_at: str | None = None
    soil_sensor_last_calibrated_at: str | None = None

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
            "last_mowing": self.last_mowing,
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
            "precipitation_last_value": self.precipitation_last_value,
            "precipitation_last_sample_at": self.precipitation_last_sample_at,
            "soil_sensor_last_calibrated_at": self.soil_sensor_last_calibrated_at,
        }
