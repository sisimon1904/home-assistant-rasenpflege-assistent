# Changelog

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
