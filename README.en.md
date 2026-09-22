# Lawn Care Assistant for Home Assistant

[Deutsch](README.md) | **English**

Version 3.1.0

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

This custom integration evaluates a lawn using data provided by Home
Assistant's **OpenWeatherMap** integration. It calculates lawn growth, the
grassland temperature sum, modeled soil moisture, and watering and fertilizing
recommendations. It does not directly control irrigation or a robotic mower.

## Requirements

- Home Assistant 2026.4.0 or newer
- a configured OpenWeatherMap integration
- recommended: OpenWeatherMap mode `v3.0`, because it provides current weather
  plus hourly and daily forecasts together

No additional OpenWeatherMap API key is required. The integration only reads
entities already available in Home Assistant and requests forecasts through
`weather.get_forecasts`.

## Features

- UI-based setup and options
- selection and validation of an OpenWeatherMap weather entity
- freely selectable outdoor temperature sensor with automatic OpenWeatherMap
  fallback
- automatic use of an active OpenWeatherMap rain sensor or an optional selected
  precipitation sensor
- selectable precipitation interpretation as rate, cumulative total, or increment
- optional physical soil-moisture sensor for gentle model calibration
- optional soil-temperature sensor for vegetation decisions
- OpenWeatherMap forecasts for watering decisions, kept separate from observed
  rainfall
- timestamp-based rain windows; OpenWeatherMap v3.0 supplies 48 hourly hours and
  daily data is used to extend the 72-hour view
- optional binary sensors for “lawn was mowed” and “lawn was watered”
- grassland temperature sum weighted by January 0.5, February 0.75, and 1.0
  from March onward
- growth status:
  - collecting data
  - winter dormancy (growth stopped)
  - first awakening (tentative growth)
  - sustained vegetation start (full growth)
  - active growth
  - slow growth
  - growth slowing in autumn
  - heat or drought stress
- dedicated mower status with clear actions, seasonal guidance, and the most
  recent mowing date as attributes
- modeled soil moisture in percent
- enhanced Penman-Monteith evapotranspiration with an automatic
  Hargreaves-Samani fallback
- a soil-water balance with interception, infiltration, runoff, drainage, and
  water-stress-limited evapotranspiration
- watering recommendation with target amount in millimeters and liters
- seasonal NPK recommendation and product quantity
- downloadable diagnostics through Home Assistant
- diagnostic entities for data quality, confidence, and data sources
- a “Next action” sensor with one concise recommendation
- Home Assistant repair issues for missing weather or configured input data
- stale-forecast detection after three hours
- maintenance actions with actual watering/fertilizer amounts and reversible history
- automatic migration of configurations from version 1.0.0
- HACS-compatible repository structure and release workflow

## Modeled soil moisture

The model uses a virtual water reservoir for the rooted soil layer:

```text
new water level = previous water level
                  + effective rain
                  + recorded irrigation
                  - estimated lawn evapotranspiration
```

Reservoir capacity and infiltration depend on soil type. When fresh
temperature, humidity, wind, and cloud data are available, reference
evapotranspiration is calculated with FAO-56 Penman-Monteith. Solar radiation
is estimated from location, date, and cloud coverage. The integration falls
back automatically to Hargreaves-Samani when required inputs are unavailable.
A lawn and sun-exposure coefficient adapts reference ET to the lawn.

Observed rain is not treated as completely available soil water. Depending on
soil type and rain intensity, the model accounts for interception,
infiltration, surface runoff, and drainage. Water stress limits actual
evapotranspiration when the root zone is nearly empty.

The model first uses an explicitly selected precipitation sensor. Otherwise it
automatically searches for an active OpenWeatherMap rain sensor belonging to
the selected weather configuration. Without an available measurement source,
no assumed rain is added to the
soil reservoir. Home Assistant's cached OpenWeatherMap forecast is used only
for the watering recommendation. Model confidence is reported as `high`,
`medium`, or `low` depending on the available data source. When the optional
“lawn was watered” binary sensor changes from off to on, the calculated amount
or the configured default amount is added to the virtual reservoir.

`forecast_rain_mm` is the sum of the first three daily forecast periods. The
integration does not call OpenWeatherMap directly: `weather.get_forecasts`
reads the official Home Assistant integration's cache. Lawn Care Assistant
also caches the forecast for one hour. A forecast is marked stale after three
hours without a successful update and data quality becomes insufficient.

Modeled soil moisture is not a replacement for a physical sensor. Shade,
slope, soil compaction, roof overhangs, and localized showers can cause
deviations. Use **Configure → Recalibrate modeled soil moisture** to correct
the virtual reservoir.

## Growth and robotic-mower logic

Growth status combines:

- grassland temperature sum
- mean temperature of the previous seven complete days
- season
- modeled soil moisture
- confirmation that the mowing season has started

A grassland temperature sum of 200 is used as a spring guideline. When the
seven-day average also reaches approximately 8 °C and the lawn is not under
drought stress, mower status reports **Start mower again**. Then press
**Record mowing** or briefly switch on the optional “lawn was mowed” binary
sensor. This records the mowing date and confirms the season start. The prompt
remains acknowledged for the rest of the calendar year and resets on January 1.

In autumn, falling seven-day temperatures first produce **Reduce mowing for
autumn**. Once growth stops, the status changes to **Switch off for winter**.
Drought stress pauses mowing recommendations regardless of season.

## Outdoor temperature source

Any Home Assistant temperature sensor can be selected under **Configure**.
While it provides a valid value, it takes priority. Without a selection, or
when that entity is `unavailable` or `unknown`, the integration automatically
uses the current temperature from the selected OpenWeatherMap weather entity.
The entity actually used is exposed as the `temperature_source` attribute on
growth and mower status.

## Installation

### Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and select **Custom repositories**.
3. Enter
   `https://github.com/sisimon1904/home-assistant-rasenpflege-assistent`
   and select **Integration** as the category.
4. Download Lawn Care Assistant and restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and search for
   **Lawn Care Assistant**.

### Manual installation

1. Copy the complete `custom_components/rasenpflege_assistent` directory to
   `/config/custom_components/rasenpflege_assistent`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **Lawn Care Assistant**.
5. Select the OpenWeatherMap weather entity, optional event sensors, and lawn
   parameters.

## Updating from version 1.0.0

1. Replace the existing
   `/config/custom_components/rasenpflege_assistent` directory.
2. Restart Home Assistant.
3. Home Assistant automatically migrates the config entry to version 6 during
   the next startup.
4. Open **Settings → Devices & services → Lawn Care Assistant → Configure** and
   verify the initial soil moisture. A local outdoor temperature sensor can
   also be selected there.

## Changes in version 1.3.0

- The former “Fertilizing recommendation” and “Status” entities were combined
  into **Care status**. NPK type, dose, total amount, time window, and reasons
  remain available as attributes.
- “Mower start recommended” and “Mower can be switched off” are now attributes
  of **Mower status**. The deprecated duplicate entities are removed during
  setup.
- Growth, care, and mower status expose an `icon_color` attribute for dashboard
  cards that support dynamic colors. Standard Home Assistant entities cannot
  enforce their own icon color.
- Optional binary sensors automatically record mowing and irrigation on an
  off-to-on transition. Without a configured sensor, the corresponding manual
  button remains available.

## Fix in version 1.3.1

- Fixes a setup failure caused by accidentally passing `last_mowing` to the
  fertilizing recommendation calculation.

## Automatic updates with HACS

Stable versions are published as GitHub releases such as `v2.0.0`. HACS shows
new releases as updates for HACS-installed copies. An integration copied
manually into `custom_components` cannot update itself from the internet.

## Main entities

- Care status
- Growth status
- Mower status
- Modeled soil moisture
- Grassland temperature sum
- Watering recommendation
- Next action
- Data quality and model confidence
- Recommended water amount
- Recommended fertilizer amount
- Record mowing, when no automatic binary sensor is configured
- Record watering, when no automatic binary sensor is configured
- Record fertilizing
- Undo last maintenance action (disabled by default)

## Changes in version 2.0.0

- Python source values and internal status keys are English. Home Assistant
  translations provide German and English display values.
- Measured and forecast precipitation are handled separately.
- An optional sensor accepts precipitation in `mm` or `mm/h`; forecasts remain
  available separately for watering decisions.
- Watering amounts are calculated from the modeled soil-water deficit.
- The default amount for recorded irrigation is configurable.
- Mower status accounts for the most recent mowing and reports an interval and
  next mowing date.
- Weather source, forecast timestamp, and model confidence are exposed as
  attributes.
- Existing config entries migrate automatically to version 4. Automations that
  compared former German raw state values must be updated for the stable
  English machine values.

### Dynamic icon colors with Mushroom

The `icon_color` attribute can be used like this:

```yaml
type: custom:mushroom-template-card
entity: sensor.lawn_growth_status
primary: "{{ state_attr(entity, 'friendly_name') }}"
secondary: "{{ state_translated(entity) }}"
icon: mdi:grass
icon_color: "{{ state_attr(entity, 'icon_color') }}"
tap_action:
  action: more-info
```

For translatable enum sensors, `states(entity)` returns the stable English raw
state. `state_translated(entity)` returns the state translated for the current
Home Assistant user.

## Changes in version 2.0.1

- German remains the default README shown by GitHub and HACS.
- This complete English README is available through the language selector.
- Static metadata uses the English name `Lawn Care Assistant`; Home Assistant
  continues to display **Rasenpflege-Assistent** through its German
  translations.
- Outdated references to the config version and fixed irrigation amount were
  corrected.
- The Mushroom example now uses the translated state.

## Changes in version 2.1.0

- Hourly OpenWeatherMap forecasts are evaluated for the next 24, 48, and
  72 hours without calling OpenWeatherMap directly.
- An optional physical soil-moisture sensor moves the modeled reservoir 25%
  toward the measured value at most once every six hours.
- The new **Next action** sensor summarizes the most important upcoming task.
- Diagnostic entities report data quality, model confidence, forecast age,
  rain, input sources, soil water, and evapotranspiration.
- Home Assistant creates repair issues when temperature, forecasts, or
  configured input entities are unavailable.
- Existing config entries migrate automatically to config-entry version 5.

## Changes in version 2.1.1

- Modeled soil moisture is updated on every refresh; evapotranspiration and
  measured rain no longer wait for the day boundary.
- Forecast rain is never added to the soil model as observed precipitation.
- Watering states now distinguish sufficient moisture, water soon, water now,
  wait for rain, and seasonal pause.
- The last watering date again supports the modeled moisture decision.
- Soil moisture is displayed with one decimal place.
- Diagnostics expose forecast coverage, the last soil update, and time gaps.
- Care and growth status now use a consistent vegetation phase.
- Legacy watering and fertilizing binary sensors are disabled by default for
  new installations; their boolean values remain available as attributes.

## Changes in version 3.1.0

- Penman-Monteith uses existing OpenWeatherMap humidity, wind, pressure, dew
  point, and cloud data without an additional direct API request.
- Hargreaves-Samani remains available as an automatic fallback.
- The soil model accounts for infiltration, interception, runoff, drainage,
  and water stress.
- Provider timestamps prevent stale precipitation rates from being counted
  repeatedly.
- Effective forecast rain reduces the recommended irrigation amount.
- Diagnostics expose the ET method, weather age, and water-balance components.
- Automatic maintenance inputs are protected against duplicate triggers.
- Undoing a watering event no longer discards later natural water-balance
  changes.

## Changes in version 3.0.1

- Exclude past forecast entries from future rain totals and next-rain times.
- Evaluate hourly and daily forecast freshness independently.
- Establish a safe new precipitation baseline after outages and source or mode
  changes.
- Attribute precipitation intervals crossing midnight to the correct day.
- Allow optional maintenance dates to be cleared and lawn entries to be
  renamed consistently.
- Preserve manual maintenance buttons when input binary sensors are configured.
- Correct diagnostics, units, and statistics metadata.

## Changes in version 3.0.0

- Catch up as much as 24 hours of modeled evapotranspiration after downtime.
- Automatically use an active OpenWeatherMap rain sensor when no explicit
  precipitation sensor is configured.
- Interpret precipitation automatically or explicitly as a rate, cumulative
  total, or amount per update.
- Calculate forecast windows from timestamps and detect stale data after three
  hours.
- Distinguish water soon, water now, wait for rain, drought, fertilizing, and
  mowing in the primary care status.
- Stabilize growth and drought states with threshold hysteresis.
- Use an optional soil-temperature sensor for vegetation decisions.
- Add Home Assistant actions for recording and undoing maintenance events.
- Remove legacy duplicate binary sensors and migrate config entries to version 6.

## Limitations

The soil model is a transparent estimate, not a measurement. Fertilizer amount
refers to approximate product mass, not pure nutrient mass. Always follow the
manufacturer's dosage, soil analysis results, and local regulations. Do not
fertilize frozen, dried-out, or waterlogged lawn.
