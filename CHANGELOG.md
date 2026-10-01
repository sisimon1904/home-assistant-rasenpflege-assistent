# Changelog

## 3.5.1

### Fixed

- Persist completed irrigation sessions and their water credit together.
- Exclude shared-meter consumption during restart gaps and preserve wet-lawn protection.
- Integrate flow rates at their report timestamps instead of applying new rates retroactively.
- Account for final volume reports received before an external valve closure.
- Renew the valve-opening grace period when resuming a paused session.
- Keep temperature sampling independent of extra coordinator refreshes.
- Discard outdated temperature history after missing days.
- Reject non-finite temperatures and cached temperatures on unavailable weather entities.
- Synchronize corrected or cleared watering dates with the wet-grass timestamp.
- Require contiguous near-term hourly forecasts before reporting high confidence.
- Preserve existing model values when migrating older configuration entries.
- Add regression coverage for irrigation, temperature, forecasts and configuration migration.

## 3.5.0

### Added

- Dedicated mowing settings with manual/robot modes, growth-dependent robot
  intervals of 1/3/5 days and an optional interval adjustment factor.
- Read-only robot-session observation using active work time followed by docking;
  estimates are labeled and a configured completion binary input takes precedence.
- Exact mowing timestamps, earliest estimated mowing time, recommendation reason,
  confidence and record source on the existing mower status entity.
- Correction and clearing of the last mowing date in maintenance history.
- Explicit protection against commanding the optional second valve.

### Changed

- Combine elapsed mowing intervals with the next-local-day and twelve-hour wet pause.
- Apply autumn growth hysteresis and suppress mowing recommendations when current
  temperature is unavailable or frost is detected.
- Keep legacy dates and manual mode on upgrade; date-only times remain estimates.

### Fixed

- Record distinct mowing sessions within twelve hours and deduplicate by event identity.
- Preserve exact mowing times when saving unrelated maintenance settings.
- Check safety inputs immediately after a valve-opening service call returns.
- Stop irrigation safely if the meter changes its unit during a session.

### Validation

- Regression coverage for robot pauses, short starts, errors, idle, restart,
  date migration, history corrections and second-valve read-only behavior.
- No additional OpenWeatherMap polling loop or mower control is introduced.

## 3.4.1

### Fixed

- Include the required English translation file for the custom integration so
  Home Assistant can show translated settings labels and descriptions.
- Add explanatory descriptions for every setting on the new options pages in
  English and German.
- Verify both languages through Home Assistant's translation loader.

## 3.4.0

### Added

- Short initial setup and separate options pages for basic settings, sensors,
  irrigation hardware, safety limits, soil modeling, and maintenance history.
- Translated diagnostic sensor explaining the current automatic irrigation
  decision and the next available start when known.
- Persisted irrigation active and paused durations and a shared-meter
  measurement-gap flag for diagnostics.

### Changed

- Stop irrigation before saving a settings page so a reload cannot interrupt
  an owned watering session.
- Defer mowing in the next-action sensor while the lawn is estimated wet.
- Permit another automatic attempt after a 30-minute cooldown when a failed
  attempt delivered no measured water.

### Fixed

- Ignore stale positive flow-rate readings left by another water consumer.
- Avoid attributing ambiguous shared-meter updates when a competing valve opens.
- Record sufficiently long time-only watering even if another valve paused it.
- Extend the delayed valve closure guard after a failed open or restart.

## 3.3.2

### Fixed

- Show editable numeric boxes with visible values for manual minimum and
  maximum irrigation time in the setup and options forms.
- Apply the same input style to maximum volume, flow startup grace period,
  and minimum and maximum flow while preserving existing configured values.

## 3.3.1

### Added

- Optional read-only competing-valve input with safe pause and guarded resume.
- Live irrigation diagnostics with start blockers, meter freshness, runtime,
  valve states, and the last shutdown reason.
- Mowing pause after observed rain or recorded watering until the following
  local day and at least twelve hours after the wetting event.
- An actionable Home Assistant repair issue if the controlled valve fails to
  report closed after shutdown.

### Changed

- Replace numeric configuration sliders with precise value boxes.
- Hide the optional watered binary input whenever a controlled valve is used.
- Attribute shared-meter changes only while the lawn valve is open; do not
  treat unrelated consumption while closed as a fault or lawn irrigation.
- Count competing-valve pauses toward the maximum session duration, and mark
  unmetered manual watering as wet without inventing a measured volume.

### Fixed

- Enforce the mower safety interlock even before the valve reports opened.
- Evaluate delayed cumulative meter updates over their real change interval.
- Permit quiet meters to start, then demand live flow within the safety grace
  period; refresh live irrigation entities without extra weather API polling.
- Bound valve service-call waits so a stalled device cannot hold the safety
  watchdog indefinitely; retry failed closure and expose a repair issue.
- Keep delayed shared-meter updates after valve closure out of the soil model.
- Preserve the original valve and meter across options reloads, and watch for
  a late valve-open report after a restart or valve reconfiguration.

## 3.3.0

### Added

- Optional hardware-independent valve, water meter, and mower dock inputs.
- An opt-in automatic irrigation switch and manual valve start/stop buttons.
- Minimum manual runtime, target volume, maximum time and volume, startup flow
  grace period, and configurable minimum and maximum flow thresholds.
- A separate safety watchdog with immediate mower and meter state monitoring,
  fail-closed restart handling, and valve closure retries.
- Irrigation status with last measured volume and stop reason; meter supports
  volume totals and instantaneous flow rates in common Home Assistant units.

### Changed

- The existing watering button starts a supervised session if a valve is
  selected; without a valve it retains its previous recording behavior.
- Record actual measured water only after the valve is confirmed closed;
  ignore the optional watered binary sensor during controlled sessions.
- Migrate existing entries to version 8 with automatic control disabled.

### Fixed

- Expose the seasonal temperature-outage evapotranspiration method as a valid
  translated sensor state.

## 3.2.1

### Fixed

- Report observed rain today as unknown when measurements are absent or the
  day's rain readings are incomplete, instead of showing a misleading zero.
- Continue estimated evapotranspiration during outdoor temperature outages;
  indicate reduced water-model confidence.
- Apply the configured rain correction to rainfall intensity as well as its
  volume for consistent infiltration and runoff calculations.
- Use Home Assistant's local day for rain, evaporation, grassland temperature
  sums, and maintenance timestamps, including midnight and DST transitions.
- Mark days with no temperature samples and earlier days before a midyear
  installation as gaps in the grassland temperature sum.

## 3.2.0

### Added

- Configurable root depth, slope, compaction, irrigation efficiency, and rain
  correction for the soil-water model.
- Dry/wet reference calibration for an optional physical soil-moisture sensor.
- Probability-aware forecast rain, explainable watering windows, and additional
  grassland-temperature completeness diagnostics.
- Canopy interception storage and daylight-weighted evapotranspiration.
- Config-flow, migration, and Home Assistant compatibility tests.
- Shorter German and English installation guides with detailed history in this
  changelog.

### Changed

- Migrate existing configuration entries to model version 3 while preserving
  fractional soil-water state.
- Scale soil capacity and infiltration according to root depth, slope, and
  compaction.
- Prefer fresh measured weather values and avoid phantom rain after outages.

### Fixed

- Correct watering decisions when forecast rain has only a low probability.
- Prevent stale precipitation baselines from creating false rain increments.
- Keep the integration compatible with Home Assistant runtimes that still
  expose `OptionsFlow` instead of `OptionsFlowWithReload`.
- Calculate the suggested irrigation window and daylight evaporation using
  local time.

## 3.1.0

### Added

- Estimate reference evapotranspiration with FAO-56 Penman-Monteith using
  cached OpenWeatherMap humidity, wind, pressure, dew point, and cloud data.
- Fall back automatically to Hargreaves-Samani when current weather inputs are
  incomplete or stale.
- Model soil-specific interception, infiltration, runoff, drainage, and
  water-stress-limited evapotranspiration.
- Persist recent weather samples and expose the evapotranspiration method and
  water-balance components in diagnostics.
- Create a repair issue when current OpenWeatherMap observations are stale.

### Changed

- Integrate precipitation rates only when the provider reports a fresh sample
  and use the average of consecutive rates.
- Reduce watering amounts by effective near-term rain while accounting for
  expected evapotranspiration.
- Mark 72-hour rain totals when daily forecasts were needed to extend the
  exact hourly window.
- Limit uncertain post-outage soil-model catch-up to six hours.
- Debounce automatic mowing and watering input events.
- Derive model confidence from weather freshness, precipitation availability,
  model gaps, and the evapotranspiration method.

### Fixed

- Undo a recorded watering without discarding rain and evapotranspiration that
  occurred after the maintenance event.
- Use a median forecast interval instead of assuming the first two entries
  represent the complete forecast cadence.

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

