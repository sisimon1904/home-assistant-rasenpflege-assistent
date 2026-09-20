"""Constants for the Rasenpflege-Assistent integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "rasenpflege_assistent"
INTEGRATION_VERSION = "1.3.1"
PLATFORMS = ["sensor", "binary_sensor", "button"]

CONF_NAME = "name"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_MOWED_ENTITY = "mowed_entity"
CONF_WATERED_ENTITY = "watered_entity"
CONF_AREA = "area"
CONF_SUN_EXPOSURE = "sun_exposure"
CONF_LAWN_TYPE = "lawn_type"
CONF_SOIL_TYPE = "soil_type"
CONF_LAST_WATERING = "last_watering"
CONF_LAST_FERTILIZING = "last_fertilizing"
CONF_INITIAL_GTS = "initial_gts"
CONF_INITIAL_SOIL_MOISTURE = "initial_soil_moisture"

DEFAULT_NAME = "Rasen"
DEFAULT_AREA = 100.0
DEFAULT_SUN_EXPOSURE = "sunny"
DEFAULT_LAWN_TYPE = "family"
DEFAULT_SOIL_TYPE = "loamy"
DEFAULT_INITIAL_GTS = 0.0
DEFAULT_INITIAL_SOIL_MOISTURE = 70.0

UPDATE_INTERVAL = timedelta(minutes=30)
STORE_VERSION = 1
STORE_KEY_PREFIX = f"{DOMAIN}."

SUN_EXPOSURES = ["sunny", "partial_shade", "shade"]
LAWN_TYPES = ["family", "play", "ornamental", "shade"]
SOIL_TYPES = ["sandy", "loamy", "clayey"]

ATTR_REASONS = "reasons"
ATTR_CONFIDENCE = "confidence"
ATTR_RECOMMENDED_MM = "recommended_mm"
ATTR_RECOMMENDED_LITERS = "recommended_liters"
ATTR_FORECAST_RAIN_MM = "forecast_rain_mm"
ATTR_DAYS_SINCE_WATERING = "days_since_watering"
ATTR_NPK = "npk"
ATTR_DOSE_G_M2 = "dose_g_m2"
ATTR_TOTAL_KG = "total_kg"
ATTR_DAYS_SINCE_FERTILIZING = "days_since_fertilizing"
ATTR_NEXT_WINDOW = "next_window"
ATTR_MODEL_CONFIDENCE = "model_confidence"
ATTR_SOIL_WATER_MM = "soil_water_mm"
ATTR_SOIL_CAPACITY_MM = "soil_capacity_mm"
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
