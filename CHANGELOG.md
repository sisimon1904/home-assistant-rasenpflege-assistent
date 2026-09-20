# Changelog

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
