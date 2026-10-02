"""Typed contracts for soil calculations and runtime diagnostic snapshots.

File: custom_components/rasenpflege_assistent/diagnostic_types.py

These structures keep units and optional observations explicit. Diagnostics
describe the last calculation/write and perform no I/O when read. Confidence
is a rule-based assessment, not a statistical probability of model accuracy.
"""

from typing import Literal, TypedDict


class SoilBalance(TypedDict):
    """Water depths in millimeters; stress is a dimensionless factor."""

    water_mm: float
    actual_et_mm: float
    effective_rain_mm: float
    interception_mm: float
    runoff_mm: float
    drainage_mm: float
    water_stress_factor: float


class SoilUpdate(SoilBalance):
    """Balance plus the method and daily ET estimates used by recommendations."""

    reference_et_daily_mm: float
    expected_et_24h_mm: float
    method: str
    capacity_mm: float


class ModelConfidence(TypedDict):
    """Explain a confidence level and any pre-correction sensor disagreement."""

    level: Literal["low", "medium", "high"]
    reasons: list[str]
    sensor_deviation_percentage_points: float | None
    disagreement_threshold_percentage_points: float


class SoilTrace(TypedDict):
    """Last update ledger; rounding can leave a small conservation residual."""

    calculated_at: str
    elapsed_hours: float
    integrated_hours: float
    initial_water_mm: float
    precipitation_mm: float
    interception_mm: float
    effective_rain_mm: float
    runoff_mm: float
    drainage_mm: float
    actual_et_mm: float
    water_before_sensor_mm: float
    sensor_correction_mm: float
    final_water_mm: float
    balance_residual_mm: float
    method: str


class StorageStatus(TypedDict):
    """Process-local write health; error text and filesystem paths are omitted."""

    last_success_at: str | None
    last_failure_at: str | None
    last_failure_operation: str | None
    last_error_type: str | None
    consecutive_failures: int
    successful_writes: int
    pending: bool
