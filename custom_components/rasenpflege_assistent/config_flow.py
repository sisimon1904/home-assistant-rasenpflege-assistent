"""Config flow for Lawn Care Assistant."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlowResult

try:
    from homeassistant.config_entries import OptionsFlowWithReload
except ImportError:  # Compatibility with older Home Assistant test runtimes.
    from homeassistant.config_entries import OptionsFlow as OptionsFlowWithReload
from homeassistant.const import UnitOfArea
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_UNMETERED_MANUAL,
    CONF_AREA,
    CONF_COMPACTION,
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_FLOW_START_GRACE,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_IRRIGATION_EFFICIENCY,
    CONF_IRRIGATION_FLOW,
    CONF_IRRIGATION_VALVE,
    CONF_LAST_FERTILIZING,
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_MAX_FLOW_L_MIN,
    CONF_MAX_IRRIGATION_LITERS,
    CONF_MAX_IRRIGATION_MINUTES,
    CONF_MIN_FLOW_L_MIN,
    CONF_MIN_IRRIGATION_MINUTES,
    CONF_MOWED_ENTITY,
    CONF_MOWER_LOCATION,
    CONF_MOWER_SAFE_STATE,
    CONF_NAME,
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_RAIN_CORRECTION,
    CONF_ROOT_DEPTH,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_SENSOR_DRY,
    CONF_SOIL_SENSOR_WET,
    CONF_SOIL_TEMPERATURE_ENTITY,
    CONF_SOIL_TYPE,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WATERED_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_AREA,
    DEFAULT_COMPACTION,
    DEFAULT_FLOW_START_GRACE,
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_IRRIGATION_EFFICIENCY,
    DEFAULT_LAWN_TYPE,
    DEFAULT_MAX_FLOW_L_MIN,
    DEFAULT_MAX_IRRIGATION_LITERS,
    DEFAULT_MAX_IRRIGATION_MINUTES,
    DEFAULT_MIN_FLOW_L_MIN,
    DEFAULT_MIN_IRRIGATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_PRECIPITATION_MODE,
    DEFAULT_RAIN_CORRECTION,
    DEFAULT_ROOT_DEPTH,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_SENSOR_DRY,
    DEFAULT_SOIL_SENSOR_WET,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_EXPOSURE,
    DEFAULT_WATERING_AMOUNT,
    DOMAIN,
)


def _select(translation_key: str, options: list[str]) -> selector.SelectSelector:
    """Build a translated dropdown with stable machine values."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            translation_key=translation_key,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _schema() -> vol.Schema:
    """Return the shared setup/options schema."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(CONF_TEMPERATURE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Optional(CONF_MOWED_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(CONF_WATERED_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(CONF_IRRIGATION_VALVE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Optional(CONF_IRRIGATION_FLOW): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_MOWER_LOCATION): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["lawn_mower", "vacuum", "binary_sensor", "sensor"]
                )
            ),
            vol.Optional(CONF_MOWER_SAFE_STATE, default="docked"): str,
            vol.Optional(CONF_ALLOW_UNMETERED_MANUAL, default=False): bool,
            vol.Required(
                CONF_MIN_IRRIGATION_MINUTES, default=DEFAULT_MIN_IRRIGATION_MINUTES
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            vol.Required(
                CONF_MAX_IRRIGATION_MINUTES, default=DEFAULT_MAX_IRRIGATION_MINUTES
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=240)),
            vol.Required(
                CONF_MAX_IRRIGATION_LITERS, default=DEFAULT_MAX_IRRIGATION_LITERS
            ): vol.All(vol.Coerce(float), vol.Range(min=10, max=50000)),
            vol.Required(
                CONF_FLOW_START_GRACE, default=DEFAULT_FLOW_START_GRACE
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
            vol.Required(CONF_MIN_FLOW_L_MIN, default=DEFAULT_MIN_FLOW_L_MIN): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=100)
            ),
            vol.Required(CONF_MAX_FLOW_L_MIN, default=DEFAULT_MAX_FLOW_L_MIN): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=1000)
            ),
            vol.Optional(CONF_PRECIPITATION_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class=[
                        SensorDeviceClass.PRECIPITATION,
                        SensorDeviceClass.PRECIPITATION_INTENSITY,
                    ],
                )
            ),
            vol.Required(
                CONF_PRECIPITATION_MODE,
                default=DEFAULT_PRECIPITATION_MODE,
            ): _select(
                "precipitation_mode",
                ["auto", "rate", "cumulative", "increment"],
            ),
            vol.Optional(CONF_SOIL_MOISTURE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.MOISTURE
                )
            ),
            vol.Optional(CONF_SOIL_TEMPERATURE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.TEMPERATURE
                )
            ),
            vol.Required(
                CONF_DEFAULT_WATERING_AMOUNT,
                default=DEFAULT_WATERING_AMOUNT,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=50,
                    step=0.5,
                    unit_of_measurement="mm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_AREA, default=DEFAULT_AREA): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10000,
                    step=1,
                    unit_of_measurement=UnitOfArea.SQUARE_METERS,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SUN_EXPOSURE,
                default=DEFAULT_SUN_EXPOSURE,
            ): _select("sun_exposure", ["sunny", "partial_shade", "shade"]),
            vol.Required(
                CONF_LAWN_TYPE,
                default=DEFAULT_LAWN_TYPE,
            ): _select("lawn_type", ["family", "play", "ornamental", "shade"]),
            vol.Required(
                CONF_SOIL_TYPE,
                default=DEFAULT_SOIL_TYPE,
            ): _select("soil_type", ["sandy", "loamy", "clayey"]),
            vol.Optional(CONF_LAST_WATERING): selector.DateSelector(),
            vol.Optional(CONF_LAST_FERTILIZING): selector.DateSelector(),
            vol.Required(
                CONF_INITIAL_GTS,
                default=DEFAULT_INITIAL_GTS,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=5000,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_INITIAL_SOIL_MOISTURE,
                default=DEFAULT_INITIAL_SOIL_MOISTURE,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_ROOT_DEPTH, default=DEFAULT_ROOT_DEPTH
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=30,
                    step=1,
                    unit_of_measurement="cm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_SLOPE, default=DEFAULT_SLOPE): _select(
                "slope", ["flat", "gentle", "steep"]
            ),
            vol.Required(CONF_COMPACTION, default=DEFAULT_COMPACTION): _select(
                "compaction", ["normal", "compacted"]
            ),
            vol.Required(
                CONF_IRRIGATION_EFFICIENCY,
                default=DEFAULT_IRRIGATION_EFFICIENCY,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=1.0,
                    step=0.05,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_RAIN_CORRECTION, default=DEFAULT_RAIN_CORRECTION
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=1.5,
                    step=0.05,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_SOIL_SENSOR_DRY, default=DEFAULT_SOIL_SENSOR_DRY
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SOIL_SENSOR_WET, default=DEFAULT_SOIL_SENSOR_WET
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _validate_openweathermap_entities(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Ensure weather inputs are provided by OpenWeatherMap."""
    errors: dict[str, str] = {}
    registry = er.async_get(hass)
    weather_entry = registry.async_get(user_input[CONF_WEATHER_ENTITY])
    if weather_entry is None or weather_entry.platform != "openweathermap":
        errors[CONF_WEATHER_ENTITY] = "not_openweathermap"
    else:
        weather_state = hass.states.get(user_input[CONF_WEATHER_ENTITY])
        if weather_state is None or "temperature" not in weather_state.attributes:
            errors[CONF_WEATHER_ENTITY] = "weather_data_unavailable"
    return errors


def _validate_calibration(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate optional model calibration bounds."""
    if float(user_input[CONF_SOIL_SENSOR_WET]) <= float(
        user_input[CONF_SOIL_SENSOR_DRY]
    ):
        return {CONF_SOIL_SENSOR_WET: "soil_sensor_range_invalid"}
    return {}


def _validate_irrigation(user_input: dict[str, Any]) -> dict[str, str]:
    """Check that optional valve control has a safe configuration."""
    errors: dict[str, str] = {}
    if user_input.get(CONF_IRRIGATION_VALVE):
        if not user_input.get(CONF_MOWER_LOCATION):
            errors[CONF_MOWER_LOCATION] = "mower_required"
        if not user_input.get(CONF_IRRIGATION_FLOW) and not user_input.get(
            CONF_ALLOW_UNMETERED_MANUAL
        ):
            errors[CONF_IRRIGATION_FLOW] = "flow_required"
    if user_input.get(
        CONF_MIN_IRRIGATION_MINUTES, DEFAULT_MIN_IRRIGATION_MINUTES
    ) >= user_input.get(CONF_MAX_IRRIGATION_MINUTES, DEFAULT_MAX_IRRIGATION_MINUTES):
        errors[CONF_MAX_IRRIGATION_MINUTES] = "maximum_below_minimum"
    if user_input.get(CONF_MIN_FLOW_L_MIN, DEFAULT_MIN_FLOW_L_MIN) >= user_input.get(
        CONF_MAX_FLOW_L_MIN, DEFAULT_MAX_FLOW_L_MIN
    ):
        errors[CONF_MAX_FLOW_L_MIN] = "maximum_below_minimum"
    if not user_input.get(CONF_MOWER_SAFE_STATE, "docked").strip():
        errors[CONF_MOWER_SAFE_STATE] = "safe_state_required"
    return errors


def _validate_unique_valve(
    hass: HomeAssistant, user_input: dict[str, Any], exclude_entry_id: str | None = None
) -> dict[str, str]:
    """Prevent independent lawn entries from commanding the same valve."""
    valve = user_input.get(CONF_IRRIGATION_VALVE)
    if valve:
        for entry in hass.config_entries.async_entries(DOMAIN):
            configured = (
                entry.options[CONF_IRRIGATION_VALVE]
                if CONF_IRRIGATION_VALVE in entry.options
                else entry.data.get(CONF_IRRIGATION_VALVE)
            )
            if entry.entry_id != exclude_entry_id and configured == valve:
                return {CONF_IRRIGATION_VALVE: "valve_already_used"}
    return {}


class LawnCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lawn Care Assistant."""

    VERSION = 8
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            errors = {
                **_validate_openweathermap_entities(self.hass, user_input),
                **_validate_calibration(user_input),
                **_validate_irrigation(user_input),
                **_validate_unique_valve(self.hass, user_input),
            }
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            if errors:
                return self.async_show_form(
                    step_id="user", data_schema=_schema(), errors=errors
                )
            await self.async_set_unique_id(uuid4().hex)
            return self.async_create_entry(
                title=name, data={**user_input, CONF_NAME: name}
            )

        return self.async_show_form(step_id="user", data_schema=_schema())

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Create the options flow."""
        return LawnCareOptionsFlow()


class LawnCareOptionsFlow(OptionsFlowWithReload):
    """Handle editable Lawn Care Assistant settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            errors = {
                **_validate_openweathermap_entities(self.hass, user_input),
                **_validate_calibration(user_input),
                **_validate_irrigation(user_input),
                **_validate_unique_valve(
                    self.hass, user_input, self.config_entry.entry_id
                ),
            }
            new_name = user_input[CONF_NAME].strip()
            if not new_name:
                errors[CONF_NAME] = "name_required"
            if errors:
                current = {**self.config_entry.data, **user_input}
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(_schema(), current),
                    errors=errors,
                )
            options = dict(user_input)
            options[CONF_NAME] = new_name
            options.setdefault(CONF_TEMPERATURE_ENTITY, None)
            options.setdefault(CONF_MOWED_ENTITY, None)
            options.setdefault(CONF_WATERED_ENTITY, None)
            options.setdefault(CONF_IRRIGATION_VALVE, None)
            options.setdefault(CONF_IRRIGATION_FLOW, None)
            options.setdefault(CONF_MOWER_LOCATION, None)
            options.setdefault(CONF_PRECIPITATION_ENTITY, None)
            options.setdefault(CONF_SOIL_MOISTURE_ENTITY, None)
            options.setdefault(CONF_SOIL_TEMPERATURE_ENTITY, None)
            options.setdefault(CONF_LAST_WATERING, None)
            options.setdefault(CONF_LAST_FERTILIZING, None)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=new_name,
            )
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_schema(), current),
        )
