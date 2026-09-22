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
    CONF_AREA,
    CONF_COMPACTION,
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_IRRIGATION_EFFICIENCY,
    CONF_LAST_FERTILIZING,
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_MOWED_ENTITY,
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
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_IRRIGATION_EFFICIENCY,
    DEFAULT_LAWN_TYPE,
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


class LawnCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lawn Care Assistant."""

    VERSION = 7
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            errors = {
                **_validate_openweathermap_entities(self.hass, user_input),
                **_validate_calibration(user_input),
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
