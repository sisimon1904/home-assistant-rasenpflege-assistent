"""Constants for the Lawn Care Assistant integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "rasenpflege_assistent"
INTEGRATION_VERSION = "3.1.0"
PLATFORMS = ["sensor", "button"]

CONF_NAME = "name"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_MOWED_ENTITY = "mowed_entity"
CONF_WATERED_ENTITY = "watered_entity"
CONF_PRECIPITATION_ENTITY = "precipitation_entity"
CONF_SOIL_MOISTURE_ENTITY = "soil_moisture_entity"
CONF_SOIL_TEMPERATURE_ENTITY = "soil_temperature_entity"
CONF_PRECIPITATION_MODE = "precipitation_mode"
CONF_DEFAULT_WATERING_AMOUNT = "default_watering_amount"
CONF_AREA = "area"
CONF_SUN_EXPOSURE = "sun_exposure"
CONF_LAWN_TYPE = "lawn_type"
CONF_SOIL_TYPE = "soil_type"
CONF_LAST_WATERING = "last_watering"
CONF_LAST_FERTILIZING = "last_fertilizing"
CONF_INITIAL_GTS = "initial_gts"
CONF_INITIAL_SOIL_MOISTURE = "initial_soil_moisture"

DEFAULT_NAME = "Lawn"
DEFAULT_AREA = 100.0
DEFAULT_SUN_EXPOSURE = "sunny"
DEFAULT_LAWN_TYPE = "family"
DEFAULT_SOIL_TYPE = "loamy"
DEFAULT_INITIAL_GTS = 0.0
DEFAULT_INITIAL_SOIL_MOISTURE = 70.0
DEFAULT_WATERING_AMOUNT = 15.0
DEFAULT_PRECIPITATION_MODE = "auto"

UPDATE_INTERVAL = timedelta(minutes=30)
FORECAST_CACHE_INTERVAL = timedelta(hours=1)
FORECAST_STALE_AFTER = timedelta(hours=3)
SOIL_SENSOR_CALIBRATION_INTERVAL = timedelta(hours=6)
SOIL_SENSOR_BLEND_FACTOR = 0.25
MAX_SOIL_MODEL_INTERVAL = timedelta(hours=6)
CURRENT_WEATHER_STALE_AFTER = timedelta(hours=3)
PRECIPITATION_RATE_STALE_AFTER = timedelta(hours=2)
STORE_VERSION = 1
STORE_KEY_PREFIX = f"{DOMAIN}."

SUN_EXPOSURES = ["sunny", "partial_shade", "shade"]
LAWN_TYPES = ["family", "play", "ornamental", "shade"]
SOIL_TYPES = ["sandy", "loamy", "clayey"]
PRECIPITATION_MODES = ["auto", "rate", "cumulative", "increment"]

ATTR_REASONS = "reasons"
ATTR_CONFIDENCE = "confidence"
ATTR_RECOMMENDED_MM = "recommended_mm"
ATTR_RECOMMENDED_LITERS = "recommended_liters"
ATTR_WATERING_RECOMMENDED = "watering_recommended"
ATTR_FORECAST_RAIN_MM = "forecast_rain_mm"
ATTR_FORECAST_RAIN_24H_MM = "forecast_rain_24h_mm"
ATTR_FORECAST_RAIN_48H_MM = "forecast_rain_48h_mm"
ATTR_FORECAST_RAIN_72H_MM = "forecast_rain_72h_mm"
ATTR_NEXT_RAIN_AT = "next_rain_at"
ATTR_FORECAST_PERIOD_DAYS = "forecast_period_days"
ATTR_FORECAST_UPDATED_AT = "forecast_updated_at"
ATTR_PRECIPITATION_SOURCE = "precipitation_source"
ATTR_OBSERVED_RAIN_MM = "observed_rain_today_mm"
ATTR_DAYS_SINCE_WATERING = "days_since_watering"
ATTR_NPK = "npk"
ATTR_DOSE_G_M2 = "dose_g_m2"
ATTR_TOTAL_KG = "total_kg"
ATTR_DAYS_SINCE_FERTILIZING = "days_since_fertilizing"
ATTR_NEXT_WINDOW = "next_window"
ATTR_MODEL_CONFIDENCE = "model_confidence"
ATTR_SOIL_WATER_MM = "soil_water_mm"
ATTR_SOIL_CAPACITY_MM = "soil_capacity_mm"
ATTR_MEASURED_SOIL_MOISTURE = "measured_soil_moisture"
ATTR_SOIL_MOISTURE_SOURCE = "soil_moisture_source"
ATTR_DAILY_EVAPOTRANSPIRATION_MM = "daily_evapotranspiration_mm"
ATTR_GROWTH_TEMPERATURE = "growth_temperature_7d"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_TEMPERATURE_SOURCE = "temperature_source"
ATTR_ICON_COLOR = "icon_color"
ATTR_FERTILIZING_RECOMMENDED = "fertilizing_recommended"
ATTR_FERTILIZER_STATUS = "fertilizer_status"
ATTR_MOWER_START_RECOMMENDED = "mower_start_recommended"
ATTR_MOWER_CAN_BE_SWITCHED_OFF = "mower_can_be_switched_off"
ATTR_LAST_MOWING = "last_mowing"
ATTR_DAYS_SINCE_MOWING = "days_since_mowing"
ATTR_MOWING_INTERVAL_DAYS = "mowing_interval_days"
ATTR_NEXT_MOWING_DATE = "next_mowing_date"
ATTR_DATA_WARNINGS = "data_warnings"
ATTR_FORECAST_AGE_MINUTES = "forecast_age_minutes"
ATTR_TEMPERATURE_HISTORY_DAYS = "temperature_history_days"
ATTR_FORECAST_COVERAGE_HOURS = "forecast_coverage_hours"
ATTR_LAST_SOIL_UPDATE = "last_soil_update"
ATTR_SOIL_MODEL_GAP_HOURS = "soil_model_gap_hours"
ATTR_SOIL_MOISTURE_PERCENT = "soil_moisture_percent"
ATTR_FORECAST_STALE = "forecast_stale"
ATTR_PRECIPITATION_MODE = "precipitation_mode"
ATTR_SOIL_TEMPERATURE = "soil_temperature"
ATTR_REFERENCE_EVAPOTRANSPIRATION_MM = "reference_evapotranspiration_mm"
ATTR_EVAPOTRANSPIRATION_METHOD = "evapotranspiration_method"
ATTR_EFFECTIVE_RAIN_MM = "effective_rain_today_mm"
ATTR_RUNOFF_MM = "runoff_today_mm"
ATTR_DRAINAGE_MM = "drainage_today_mm"
ATTR_INTERCEPTION_MM = "interception_today_mm"
ATTR_WATER_STRESS_FACTOR = "water_stress_factor"
ATTR_WEATHER_AGE_MINUTES = "weather_age_minutes"
ATTR_HUMIDITY = "humidity"
ATTR_WIND_SPEED = "wind_speed_m_s"
ATTR_CLOUD_COVERAGE = "cloud_coverage"
ATTR_PRESSURE = "pressure_hpa"
ATTR_DEW_POINT = "dew_point"
ATTR_HOURS_UNTIL_RAIN = "hours_until_rain"
ATTR_EXPECTED_ET_24H = "expected_et_24h_mm"
ATTR_FORECAST_72H_ESTIMATED = "forecast_72h_estimated"
ATTR_LAST_MAINTENANCE_EVENT = "last_maintenance_event"
