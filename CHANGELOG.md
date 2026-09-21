# Changelog

## 3.0.1

### Fixed

- Exclude past hourly forecast entries from future rain totals and next-rain
  timestamps.
- Detect stale hourly or daily forecast data independently and use the weather
  entity update time instead of only the local fetch time.
- Reset precipitation sampling safely after unavailable states, source changes,
  and interpretation-mode changes.
- Avoid assigning an entire precipitation interval crossing midnight to the new
  day.
- Preserve the configured precipitation mode while its sensor is unavailable.
- Allow configured last-watering and last-fertilizing dates to be cleared.
- Keep the config-entry title and unique name in sync when a lawn is renamed.
- Preserve manual maintenance buttons and their entity-registry customizations.
- Correct the grassland-temperature-sum unit and remove misleading measurement
  statistics from accumulating daily diagnostic values.

## 3.0.0

### Breaking changes

- Remove the legacy watering and fertilizing binary sensors. Their information
  remains available on the primary recommendation and care-status sensors.
- Replace the ambiguous overall `watering_recommended` care state with explicit
  `water_soon`, `water_now`, and `wait_for_rain` states.

### Added

- Automatic discovery of an active OpenWeatherMap precipitation entity from the
  selected weather configuration without direct API requests.
- Configurable precipitation interpretation for rate, cumulative, and increment
  sensors.
- Optional soil-temperature input.
- Stale-forecast detection, diagnostics, and a Home Assistant repair issue.
- Reversible maintenance history and actions for watering, fertilizing, mowing,
  and undoing the latest event.
- A disabled-by-default undo button and automated calculation test workflow.

### Changed

- Catch up as much as 24 hours of modeled evapotranspiration after downtime.
- Calculate hourly forecast windows from timestamps and use daily data beyond
  OpenWeatherMap's 48-hour hourly range.
- Let calculated vegetation state determine the watering season.
- Add hysteresis to growth and drought-state thresholds.
- Downgrade data quality and recommendation confidence when measured rain is
  unavailable or a forecast is stale.
- Migrate config entries to version 6 and remove obsolete registry entities.

## 2.1.1

### Fixed

- Update modeled soil moisture incrementally instead of only at midnight.
- Apply measured precipitation immediately and never book forecast rain as
  observed precipitation.
- Prevent forecast windows from claiming more hourly coverage than available.
- Preserve measured rain when temperature data is temporarily unavailable.
- Derive the overall care status from the calculated vegetation phase.

### Changed

- Translate the existing `not_due` state as a clear sufficient-soil-moisture
  message and add a distinct `water_soon` state.
- Use the last watering interval as a supporting soil-moisture criterion.
- Add forecast coverage, soil-update time, and model-gap diagnostics.
- Display modeled soil moisture with one decimal place.
- Mark duplicate watering and fertilizing binary sensors as legacy and disable
  them by default for new installations.

## 2.1.0

### Added

- Hourly forecast evaluation for 24, 48, and 72 hours plus the next expected
  rain timestamp.
- Optional physical soil-moisture sensor with gradual model calibration.
- A translated `Next action` enum sensor.
- Diagnostic entities for data quality, confidence, forecast age, rain,
  sources, soil water, and evapotranspiration.
- Home Assistant repair issues for unavailable weather and configured inputs.

### Changed

- Watering confidence is raised when an hourly forecast is available.
- Config entries migrate automatically to version 5.

## 2.0.1

### Changed

- Keep German as the default GitHub and HACS README and add a complete English
  `README.en.md` with language links in both files.
- Use the English static integration name `Lawn Care Assistant`; Home Assistant
  still displays the localized German title from `translations/de.json`.
- Correct the documented config-entry migration version from 3 to 4.
- Update the Mushroom example to use `state_translated(entity)`.
- Remove an outdated fixed 15 mm reference from the source documentation.

## 2.0.0

### Breaking change

- Recommendation and care sensor states now use stable English machine keys.
  Home Assistant translates them for German and English frontends. Automations
  comparing the former German raw states must be updated.

### Added

- Optional precipitation depth or intensity sensor.
- Separate observed-rain and three-day forecast attributes.
- Configurable default watering amount.
- Forecast timestamp, precipitation source and dynamic model confidence.
- Mowing interval and next recommended mowing date.
- English and German state translations.

### Changed

- Watering amounts are calculated from the modeled soil-water deficit.
- The OpenWeatherMap forecast is cached for one hour and is only read through
  Home Assistant's `weather.get_forecasts` action.
- All Python source values and status keys are English.
