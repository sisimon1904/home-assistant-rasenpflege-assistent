"""Config flow for Rasenpflege-Assistent."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import UnitOfArea
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    CONF_AREA,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
    CONF_LAST_FERTILIZING,
    CONF_LAST_WATERING,
    CONF_LAWN_TYPE,
    CONF_NAME,
    CONF_RAIN_ENTITY,
    CONF_SOIL_TYPE,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_AREA,
    DEFAULT_INITIAL_GTS,
    DEFAULT_INITIAL_SOIL_MOISTURE,
    DEFAULT_LAWN_TYPE,
    DEFAULT_NAME,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_EXPOSURE,
    DOMAIN,
)


def _select(options: list[tuple[str, str]]) -> selector.SelectSelector:
    """Build a dropdown with stable values and German labels."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": value, "label": label} for value, label in options],
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
            vol.Optional(CONF_RAIN_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="precipitation_intensity"
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
            ): _select(
                [
                    ("sunny", "Sonnig"),
                    ("partial_shade", "Halbschatten"),
                    ("shade", "Schatten"),
                ]
            ),
            vol.Required(
                CONF_LAWN_TYPE,
                default=DEFAULT_LAWN_TYPE,
            ): _select(
                [
                    ("family", "Familienrasen"),
                    ("play", "Stark beanspruchter Spielrasen"),
                    ("ornamental", "Zierrasen"),
                    ("shade", "Schattenrasen"),
                ]
            ),
            vol.Required(
                CONF_SOIL_TYPE,
                default=DEFAULT_SOIL_TYPE,
            ): _select(
                [
                    ("sandy", "Sandig"),
                    ("loamy", "Lehmig und ausgewogen"),
                    ("clayey", "Tonig"),
                ]
            ),
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
    rain_entity = user_input.get(CONF_RAIN_ENTITY)
    if rain_entity:
        rain_entry = registry.async_get(rain_entity)
        if rain_entry is None or rain_entry.platform != "openweathermap":
            errors[CONF_RAIN_ENTITY] = "not_openweathermap"
    return errors


class LawnCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rasenpflege-Assistent."""

    VERSION = 2
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            errors = _validate_openweathermap_entities(self.hass, user_input)
            if errors:
                return self.async_show_form(
                    step_id="user", data_schema=_schema(), errors=errors
                )
            await self.async_set_unique_id(user_input[CONF_NAME].strip().lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME].strip(), data=user_input
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
    """Handle editable Rasenpflege-Assistent settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            errors = _validate_openweathermap_entities(self.hass, user_input)
            if errors:
                current = {**self.config_entry.data, **user_input}
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(
                        _schema(), current
                    ),
                    errors=errors,
                )
            options = dict(user_input)
            options.setdefault(CONF_TEMPERATURE_ENTITY, None)
            options.setdefault(CONF_RAIN_ENTITY, None)
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_schema(), current),
        )
