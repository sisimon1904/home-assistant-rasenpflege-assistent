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
from homeassistant.util import dt as dt_util

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
    CONF_LAST_MOWING,
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
    CONF_MOWING_ACTIVE_STATE,
    CONF_MOWING_DONE_STATE,
    CONF_MOWING_ENTITY,
    CONF_MOWING_INTERVAL_FACTOR,
    CONF_MOWING_MIN_MINUTES,
    CONF_MOWING_MODE,
    CONF_NAME,
    CONF_OTHER_VALVE,
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
    DEFAULT_MOWING_MIN_MINUTES,
    DEFAULT_MOWING_MODE,
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

GENERAL_FIELDS = (
    CONF_NAME,
    CONF_WEATHER_ENTITY,
    CONF_AREA,
    CONF_SUN_EXPOSURE,
    CONF_LAWN_TYPE,
    CONF_SOIL_TYPE,
)
SENSOR_FIELDS = (
    CONF_TEMPERATURE_ENTITY,
    CONF_MOWED_ENTITY,
    CONF_WATERED_ENTITY,
    CONF_PRECIPITATION_ENTITY,
    CONF_PRECIPITATION_MODE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_TEMPERATURE_ENTITY,
)
IRRIGATION_FIELDS = (
    CONF_IRRIGATION_VALVE,
    CONF_OTHER_VALVE,
    CONF_IRRIGATION_FLOW,
    CONF_MOWER_LOCATION,
    CONF_MOWER_SAFE_STATE,
    CONF_ALLOW_UNMETERED_MANUAL,
)
SAFETY_FIELDS = (
    CONF_MIN_IRRIGATION_MINUTES,
    CONF_MAX_IRRIGATION_MINUTES,
    CONF_MAX_IRRIGATION_LITERS,
    CONF_FLOW_START_GRACE,
    CONF_MIN_FLOW_L_MIN,
    CONF_MAX_FLOW_L_MIN,
)
MODEL_FIELDS = (
    CONF_DEFAULT_WATERING_AMOUNT,
    CONF_ROOT_DEPTH,
    CONF_SLOPE,
    CONF_COMPACTION,
    CONF_IRRIGATION_EFFICIENCY,
    CONF_RAIN_CORRECTION,
    CONF_SOIL_SENSOR_DRY,
    CONF_SOIL_SENSOR_WET,
)
MAINTENANCE_FIELDS = (
    CONF_LAST_MOWING,
    CONF_LAST_WATERING,
    CONF_LAST_FERTILIZING,
    CONF_INITIAL_GTS,
    CONF_INITIAL_SOIL_MOISTURE,
)
MOWING_FIELDS = (
    CONF_MOWING_MODE,
    CONF_MOWING_INTERVAL_FACTOR,
    CONF_MOWING_ENTITY,
    CONF_MOWING_ACTIVE_STATE,
    CONF_MOWING_DONE_STATE,
    CONF_MOWING_MIN_MINUTES,
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


def _schema(
    *, show_watered: bool = True, fields: tuple[str, ...] | None = None
) -> vol.Schema:
    """Return the fields needed by a setup or options page."""
    schema = vol.Schema(
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
            **(
                {
                    vol.Optional(CONF_WATERED_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    )
                }
                if show_watered
                else {}
            ),
            vol.Optional(CONF_IRRIGATION_VALVE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Optional(CONF_OTHER_VALVE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "binary_sensor"])
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
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_MAX_IRRIGATION_MINUTES, default=DEFAULT_MAX_IRRIGATION_MINUTES
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, max=240, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_MAX_IRRIGATION_LITERS, default=DEFAULT_MAX_IRRIGATION_LITERS
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10, max=50000, step="any", mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_FLOW_START_GRACE, default=DEFAULT_FLOW_START_GRACE
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30, max=600, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_MIN_FLOW_L_MIN, default=DEFAULT_MIN_FLOW_L_MIN
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step="any", mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_MAX_FLOW_L_MIN, default=DEFAULT_MAX_FLOW_L_MIN
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=1000, step="any", mode=selector.NumberSelectorMode.BOX
                )
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
            vol.Optional(CONF_LAST_MOWING): selector.DateSelector(),
            vol.Required(CONF_MOWING_MODE, default=DEFAULT_MOWING_MODE): _select(
                "mowing_mode", ["manual", "robot"]
            ),
            vol.Required(
                CONF_MOWING_INTERVAL_FACTOR, default=1.0
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=2.0, step=0.1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_MOWING_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["lawn_mower", "vacuum", "sensor"])
            ),
            vol.Required(CONF_MOWING_ACTIVE_STATE, default="mowing"): str,
            vol.Required(CONF_MOWING_DONE_STATE, default="docked"): str,
            vol.Required(
                CONF_MOWING_MIN_MINUTES, default=DEFAULT_MOWING_MIN_MINUTES
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=180,
                    step=1,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
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
                    mode=selector.NumberSelectorMode.BOX,
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
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RAIN_CORRECTION, default=DEFAULT_RAIN_CORRECTION
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=1.5,
                    step=0.05,
                    mode=selector.NumberSelectorMode.BOX,
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
    if fields is None:
        return schema
    return vol.Schema(
        {
            marker: value
            for marker, value in schema.schema.items()
            if marker.schema in fields
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
    if float(user_input.get(CONF_SOIL_SENSOR_WET, DEFAULT_SOIL_SENSOR_WET)) <= float(
        user_input.get(CONF_SOIL_SENSOR_DRY, DEFAULT_SOIL_SENSOR_DRY)
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
    if user_input.get(CONF_OTHER_VALVE) and user_input.get(
        CONF_OTHER_VALVE
    ) == user_input.get(CONF_IRRIGATION_VALVE):
        errors[CONF_OTHER_VALVE] = "other_valve_same"
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

    VERSION = 9
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            errors = {
                **_validate_openweathermap_entities(self.hass, user_input),
            }
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            if errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.add_suggested_values_to_schema(
                        _schema(fields=GENERAL_FIELDS), user_input
                    ),
                    errors=errors,
                )
            await self.async_set_unique_id(uuid4().hex)
            return self.async_create_entry(
                title=name,
                data={
                    **{
                        key: user_input[key]
                        for key in GENERAL_FIELDS
                        if key in user_input
                    },
                    CONF_NAME: name,
                },
            )

        weather_entities = [
            entity.entity_id
            for entity in er.async_get(self.hass).entities.values()
            if entity.domain == "weather"
            and entity.platform == "openweathermap"
            and self.hass.states.get(entity.entity_id) is not None
        ]
        suggested = (
            {CONF_WEATHER_ENTITY: weather_entities[0]}
            if len(weather_entities) == 1
            else {}
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _schema(fields=GENERAL_FIELDS), suggested
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Create the options flow."""
        return LawnCareOptionsFlow()


class LawnCareOptionsFlow(OptionsFlowWithReload):
    """Handle editable Lawn Care Assistant settings."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Offer short, independent settings pages."""
        choices = ["general", "sensors", "mowing", "irrigation", "model", "maintenance"]
        if self._current_settings().get(CONF_IRRIGATION_VALVE):
            choices.insert(4, "safety")
        return self.async_show_menu(step_id="init", menu_options=choices)

    def _current_settings(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def _section(
        self,
        step_id: str,
        fields: tuple[str, ...],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        current = self._current_settings()
        if step_id == "maintenance":
            state = getattr(
                getattr(self.config_entry, "runtime_data", None), "_state", None
            )
            if state is not None:
                current[CONF_LAST_MOWING] = state.last_mowing
                current[CONF_LAST_WATERING] = state.last_watering
        show_watered = not bool(current.get(CONF_IRRIGATION_VALVE))
        if step_id == "irrigation" and user_input is not None:
            show_watered = not bool(user_input.get(CONF_IRRIGATION_VALVE))
        schema = _schema(fields=fields, show_watered=show_watered)
        if user_input is None:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self.add_suggested_values_to_schema(schema, current),
            )

        updates = dict(user_input)
        for marker in schema.schema:
            if isinstance(marker, vol.Optional) and marker.schema not in updates:
                updates[marker.schema] = None
        merged = {**current, **updates}
        if merged.get(CONF_IRRIGATION_VALVE):
            updates[CONF_WATERED_ENTITY] = None
            merged[CONF_WATERED_ENTITY] = None
        errors: dict[str, str] = {}
        if step_id == "general":
            errors.update(_validate_openweathermap_entities(self.hass, merged))
            if not merged[CONF_NAME].strip():
                errors[CONF_NAME] = "name_required"
        elif step_id == "model":
            errors.update(_validate_calibration(merged))
        elif step_id == "mowing":
            active = merged[CONF_MOWING_ACTIVE_STATE].strip()
            done = merged[CONF_MOWING_DONE_STATE].strip()
            if not active or active.casefold() in {
                "unknown",
                "unavailable",
                "error",
                "idle",
                "paused",
                "returning",
                "docked",
            }:
                errors[CONF_MOWING_ACTIVE_STATE] = "mowing_states_invalid"
            if (
                not done
                or done.casefold()
                in {"unknown", "unavailable", "error", "idle", "paused", "returning"}
                or active.casefold() == done.casefold()
            ):
                errors[CONF_MOWING_DONE_STATE] = "mowing_states_invalid"
            updates[CONF_MOWING_ACTIVE_STATE] = active
            updates[CONF_MOWING_DONE_STATE] = done
        elif step_id in {"irrigation", "safety"}:
            errors.update(_validate_irrigation(merged))
            if step_id == "irrigation":
                errors.update(
                    _validate_unique_valve(
                        self.hass, merged, self.config_entry.entry_id
                    )
                )
        errors = {
            key if key == "base" or key in fields else "base": value
            for key, value in errors.items()
        }
        irrigation = getattr(
            getattr(self.config_entry, "runtime_data", None), "irrigation", None
        )
        if irrigation is not None and irrigation.active:
            errors["base"] = "irrigation_active"
        if errors:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self.add_suggested_values_to_schema(schema, merged),
                errors=errors,
            )

        if step_id == "general":
            updates[CONF_NAME] = merged[CONF_NAME].strip()
            self.hass.config_entries.async_update_entry(
                self.config_entry, title=updates[CONF_NAME]
            )
        if step_id == "maintenance":
            if (
                state is not None
                and updates.get(CONF_LAST_WATERING) == state.last_watering
            ):
                updates.pop(CONF_LAST_WATERING, None)
            else:
                updates["last_watering_revision"] = dt_util.now().isoformat()
            if state is not None and updates.get(CONF_LAST_MOWING) == state.last_mowing:
                # Saving fertilizer or model history must not replace an exact
                # mowing timestamp with midnight for an unchanged date.
                updates.pop(CONF_LAST_MOWING, None)
            else:
                updates["last_mowing_revision"] = dt_util.now().isoformat()
        return self.async_create_entry(data={**self.config_entry.options, **updates})

    async def async_step_mowing(self, user_input=None) -> ConfigFlowResult:
        return await self._section("mowing", MOWING_FIELDS, user_input)

    async def async_step_general(self, user_input=None) -> ConfigFlowResult:
        return await self._section("general", GENERAL_FIELDS, user_input)

    async def async_step_sensors(self, user_input=None) -> ConfigFlowResult:
        fields = SENSOR_FIELDS
        if self._current_settings().get(CONF_IRRIGATION_VALVE):
            fields = tuple(key for key in fields if key != CONF_WATERED_ENTITY)
        return await self._section("sensors", fields, user_input)

    async def async_step_irrigation(self, user_input=None) -> ConfigFlowResult:
        return await self._section("irrigation", IRRIGATION_FIELDS, user_input)

    async def async_step_safety(self, user_input=None) -> ConfigFlowResult:
        return await self._section("safety", SAFETY_FIELDS, user_input)

    async def async_step_model(self, user_input=None) -> ConfigFlowResult:
        return await self._section("model", MODEL_FIELDS, user_input)

    async def async_step_maintenance(self, user_input=None) -> ConfigFlowResult:
        return await self._section("maintenance", MAINTENANCE_FIELDS, user_input)
