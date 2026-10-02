"""Calculated output and JSON-compatible persistent state for each lawn entry.

File: custom_components/rasenpflege_assistent/models.py

LawnData is the coordinator output consumed by entities and recommendations.
RuntimeState retains sampling baselines, maintenance history, water usage and
irrigation ownership across restarts. These structures contain no device logic.

Optional values distinguish unknown information from measured zero. Mutable
collections use default factories so entries cannot share history accidentally.
The explicit serialization mapping is paired with coordinator setup loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class LawnData:
    """Calculated lawn data exposed by the coordinator."""

    # Recommendation output: stable status/reason codes are translated by HA.
    # They must remain machine-readable for user automations and dashboards.
    gts: float = 0.0
    lawn_status: str = "collecting_data"
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
    observed_rain_today_mm: float | None = None
    precipitation_source: str = "not_measured"
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
    mowing_interval_days: float | None = None
    next_mowing_date: date | None = None
    last_mowing_at: str | None = None
    next_mowing_at: str | None = None
    mowing_mode: str = "manual"
    mowing_reason: str = "collecting_data"
    mowing_confidence: str = "low"
    last_robot_session_started_at: str | None = None
    last_robot_session_finished_at: str | None = None
    last_robot_session_active_seconds: float | None = None
    mowing_record_source: str | None = None
    growth_temperature_7d: float | None = None
    # Separate modeled root-zone storage from direct sensor observations. A
    # percentage is relative to model capacity, while water depths use mm.
    soil_moisture_percent: float = 70.0
    measured_soil_moisture_percent: float | None = None
    soil_moisture_source: str = "model"
    soil_water_mm: float = 0.0
    soil_capacity_mm: float = 0.0
    daily_evapotranspiration_mm: float = 0.0
    reference_evapotranspiration_mm: float = 0.0
    evapotranspiration_method: str = "hargreaves_samani"
    effective_rain_today_mm: float = 0.0
    runoff_today_mm: float = 0.0
    drainage_today_mm: float = 0.0
    interception_today_mm: float = 0.0
    water_stress_factor: float = 1.0
    weather_age_minutes: int | None = None
    humidity: float | None = None
    wind_speed_m_s: float | None = None
    cloud_coverage: float | None = None
    pressure_hpa: float | None = None
    dew_point: float | None = None
    hours_until_rain: float | None = None
    expected_et_24h_mm: float = 0.0
    forecast_72h_estimated: bool = False
    probability_adjusted_rain_24h_mm: float | None = None
    watering_window_start: str | None = None
    watering_window_end: str | None = None
    watering_window_reason: str | None = None
    watering_window_temperature: float | None = None
    watering_window_wind_speed_m_s: float | None = None
    soil_model_confidence: str = "low"
    next_action: str = "collecting_data"
    data_quality: str = "insufficient"
    data_warnings: list[str] = field(default_factory=list)
    forecast_age_minutes: int | None = None
    forecast_coverage_hours: int = 0
    forecast_stale: bool = False
    temperature_history_days: int = 0
    last_calculation_at: str | None = None
    last_soil_update_at: str | None = None
    soil_model_gap_hours: float = 0.0
    precipitation_mode: str = "auto"
    soil_temperature: float | None = None
    last_maintenance_event: dict[str, Any] | None = None
    gts_complete: bool = True
    missing_temperature_days: int = 0
    # Live controller overlays avoid waiting for a weather refresh to expose
    # valve progress and mowing restrictions caused by current irrigation.
    irrigation_status: str = "not_configured"
    irrigation_enabled: bool = False
    irrigation_liters: float | None = None
    irrigation_reason: str | None = None
    mower_wet_until: str | None = None
    mower_wet_reason: str | None = None


@dataclass(slots=True)
class RuntimeState:
    """Persistent sampling and maintenance state."""

    # Local-day sampling baselines and annual GTS survive reloads/restarts.
    year: int
    gts: float
    sample_date: str
    temperature_sum: float = 0.0
    temperature_samples: int = 0
    temperature_sample_at: str | None = None
    last_watering: str | None = None
    last_fertilizing: str | None = None
    last_mowing: str | None = None
    last_mowing_at: str | None = None
    last_mowing_source: str | None = None
    last_mowing_event_id: str | None = None
    configured_last_mowing: str | None = None
    configured_last_mowing_revision: str | None = None
    configured_initial_gts: float = 0.0
    configured_last_watering: str | None = None
    configured_last_watering_revision: str | None = None
    last_robot_session_started_at: str | None = None
    last_robot_session_finished_at: str | None = None
    last_robot_session_active_seconds: float | None = None
    configured_last_fertilizing_revision: str | None = None
    configured_last_fertilizing: str | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    daily_rain_mm: float = 0.0
    daily_rain_unknown: bool = True
    local_day_model: bool = True
    soil_water_mm: float | None = None
    current_day_evapotranspiration_mm: float = 0.0
    daily_temperature_history: list[float] = field(default_factory=list)
    mower_started_year: int | None = None
    configured_initial_soil_moisture: float = 70.0
    precipitation_last_value: float | None = None
    precipitation_last_sample_at: str | None = None
    precipitation_last_source: str | None = None
    precipitation_last_mode: str | None = None
    soil_sensor_last_calibrated_at: str | None = None
    last_soil_update_at: str | None = None
    last_soil_model_gap_at: str | None = None
    last_soil_model_gap_hours: float = 0.0
    last_growth_state: str | None = None
    # Each entry owns independent collections. History stores reversible model
    # credits; the usage ledger below also retains physical water evidence.
    maintenance_history: list[dict[str, Any]] = field(default_factory=list)
    weather_samples: list[dict[str, Any]] = field(default_factory=list)
    daily_effective_rain_mm: float = 0.0
    daily_runoff_mm: float = 0.0
    daily_drainage_mm: float = 0.0
    daily_interception_mm: float = 0.0
    water_model_version: int = 3
    canopy_storage_mm: float = 0.0
    last_rain_at: str | None = None
    last_wet_rain_at: str | None = None
    last_watering_at: str | None = None
    configured_soil_type: str | None = None
    configured_root_depth_cm: float = 10.0
    missing_temperature_days: int = 0
    # Ownership is represented by a retained session, including paused/closing
    # sessions. On restart the controller closes it instead of blindly resuming.
    irrigation_enabled: bool = False
    irrigation_session: dict[str, Any] | None = None
    irrigation_last_auto_date: str | None = None
    irrigation_last_status: str = "idle"
    irrigation_last_reason: str | None = None
    irrigation_last_liters: float | None = None
    irrigation_valve_id: str | None = None
    irrigation_recent_valve_id: str | None = None
    irrigation_recent_until: str | None = None
    irrigation_retry_after: str | None = None
    irrigation_last_active_seconds: float | None = None
    irrigation_last_paused_seconds: float | None = None
    irrigation_last_measurement_gap: bool = False

    irrigation_suspended_until: str | None = None
    irrigation_last_session: dict[str, Any] | None = None
    water_usage: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation.

        This explicit mapping is the persistence contract used by coordinator
        loading. It returns nested collections by reference; storage/transaction
        callers take deep snapshots before awaits to isolate a durable write.
        """
        return {
            "irrigation_suspended_until": self.irrigation_suspended_until,
            "irrigation_last_session": self.irrigation_last_session,
            "water_usage": self.water_usage,
            "year": self.year,
            "gts": self.gts,
            "sample_date": self.sample_date,
            "temperature_sum": self.temperature_sum,
            "temperature_samples": self.temperature_samples,
            "temperature_sample_at": self.temperature_sample_at,
            "last_watering": self.last_watering,
            "last_fertilizing": self.last_fertilizing,
            "last_mowing": self.last_mowing,
            "last_mowing_at": self.last_mowing_at,
            "last_mowing_source": self.last_mowing_source,
            "last_mowing_event_id": self.last_mowing_event_id,
            "configured_last_mowing": self.configured_last_mowing,
            "configured_last_mowing_revision": self.configured_last_mowing_revision,
            "configured_initial_gts": self.configured_initial_gts,
            "configured_last_watering": self.configured_last_watering,
            "configured_last_watering_revision": self.configured_last_watering_revision,
            "last_robot_session_started_at": self.last_robot_session_started_at,
            "last_robot_session_finished_at": self.last_robot_session_finished_at,
            "last_robot_session_active_seconds": self.last_robot_session_active_seconds,
            "configured_last_fertilizing_revision": self.configured_last_fertilizing_revision,
            "configured_last_fertilizing": self.configured_last_fertilizing,
            "temperature_min": self.temperature_min,
            "temperature_max": self.temperature_max,
            "daily_rain_mm": self.daily_rain_mm,
            "daily_rain_unknown": self.daily_rain_unknown,
            "local_day_model": self.local_day_model,
            "soil_water_mm": self.soil_water_mm,
            "current_day_evapotranspiration_mm": (
                self.current_day_evapotranspiration_mm
            ),
            "daily_temperature_history": self.daily_temperature_history,
            "mower_started_year": self.mower_started_year,
            "configured_initial_soil_moisture": self.configured_initial_soil_moisture,
            "precipitation_last_value": self.precipitation_last_value,
            "precipitation_last_sample_at": self.precipitation_last_sample_at,
            "precipitation_last_source": self.precipitation_last_source,
            "precipitation_last_mode": self.precipitation_last_mode,
            "soil_sensor_last_calibrated_at": self.soil_sensor_last_calibrated_at,
            "last_soil_update_at": self.last_soil_update_at,
            "last_soil_model_gap_at": self.last_soil_model_gap_at,
            "last_soil_model_gap_hours": self.last_soil_model_gap_hours,
            "last_growth_state": self.last_growth_state,
            "maintenance_history": self.maintenance_history[-20:],
            "weather_samples": self.weather_samples[-96:],
            "daily_effective_rain_mm": self.daily_effective_rain_mm,
            "daily_runoff_mm": self.daily_runoff_mm,
            "daily_drainage_mm": self.daily_drainage_mm,
            "daily_interception_mm": self.daily_interception_mm,
            "water_model_version": self.water_model_version,
            "canopy_storage_mm": self.canopy_storage_mm,
            "last_rain_at": self.last_rain_at,
            "last_wet_rain_at": self.last_wet_rain_at,
            "last_watering_at": self.last_watering_at,
            "configured_soil_type": self.configured_soil_type,
            "configured_root_depth_cm": self.configured_root_depth_cm,
            "missing_temperature_days": self.missing_temperature_days,
            "irrigation_enabled": self.irrigation_enabled,
            "irrigation_session": self.irrigation_session,
            "irrigation_last_auto_date": self.irrigation_last_auto_date,
            "irrigation_last_status": self.irrigation_last_status,
            "irrigation_last_reason": self.irrigation_last_reason,
            "irrigation_last_liters": self.irrigation_last_liters,
            "irrigation_valve_id": self.irrigation_valve_id,
            "irrigation_recent_valve_id": self.irrigation_recent_valve_id,
            "irrigation_recent_until": self.irrigation_recent_until,
            "irrigation_retry_after": self.irrigation_retry_after,
            "irrigation_last_active_seconds": self.irrigation_last_active_seconds,
            "irrigation_last_paused_seconds": self.irrigation_last_paused_seconds,
            "irrigation_last_measurement_gap": self.irrigation_last_measurement_gap,
        }
