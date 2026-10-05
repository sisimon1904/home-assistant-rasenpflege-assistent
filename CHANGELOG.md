# Changelog

## 3.15.0

### Added
- Expose comparable mowing-duration observations, elapsed range and localized exclusion counts. Match lawn area, observation sources and explicitly reported program/area metadata; exclude runs whose metadata changes without claiming full coverage.
- Review elapsed saved mowing windows against distinct later weather reports. Keep advice bounded to twelve records/seven days, require conservative point-sample coverage and report missing/conflicting evidence without confirming continuous weather or dry grass.
- Explain completed irrigation targets, recorded delivery, uncertain remainders and effective soil-model credit using the saved session area. Mark flow-based estimates and require a new safety check rather than automatically resuming aborted watering.
- Add a compact care-plan summary and distinguish blocking mowing evidence from supporting uncertainty. Explain why fresh soil readings do not reconstruct historical model gaps.
- Extend German/English dashboards and documentation on existing entities, without additional regular weather polling or mower commands.

### Fixed
- Load optional malformed weather-history containers safely and discard invalid rows without preventing setup.
- Handle missing or malformed last-irrigation finish reasons in status and readiness sensor attributes.
- Preserve recorded irrigation/model evidence after area settings change; prevent backdated program records from replacing the latest observed comparison program.

### Validation
- Reproduce four failing weather-history/finish-reason regressions against 3.14.0 before correction.
- Add 46 cases for bounded/reloaded advice, repeated/conflicting weather clocks, unknown water quantities, immutable finished-session area, source/program comparisons, attribute-only program changes, failed/cancelled persistence, supporting evidence and populated German/English dashboard rendering.
- All 800 tests pass with 89.30% combined line/branch coverage. Ruff and Mypy pass; Mypy checks all 23 program modules.
- Existing irrigation restart, soak-pause, sensor failure and safety regressions pass. The second valve remains read-only; existing dosing and safety policy is retained.
- Weather review remains based on point samples, robot observations do not confirm coverage, and the soil model still requires field validation.

## 3.14.0

### Added
- Select allowed mowing weekdays and optional weekend start/end times. Empty weekday selection blocks recommendations; overnight windows belong to their starting day.
- Suggest typical elapsed mowing duration from at least three recent comparable robot observations, including short return/pause periods. Exclude incomplete, stale, source-changed, conflicting or highly variable observations; never apply suggestions automatically or claim full coverage.
- Expose forecast/current-weather age and process-local explanations for material recommended-start changes. Attribute reads remain side-effect free; restart/reload establishes a new comparison baseline.
- Explain the last soil calculation with signed rain, evapotranspiration, drainage and sensor-correction terms; show previous watering credit separately to avoid double counting.
- Update German/English settings, dashboards and documentation using existing entities and weather caches.

### Fixed
- Restore structurally valid maintenance history safely when persisted optional records are malformed; preserve older valid entries without detailed metadata.
- Reject saved mowing timestamps without timezone information before comparing them with new recorded events.

### Validation
- Reproduce four failing restore/clock cases against the previous coordinator before correction.
- Add 42 tests covering observation eligibility, persisted/undone duration samples, source changes, weekday/weekend schedules, overnight/DST boundaries, invalid configuration, data freshness, advice changes, history recovery and rendered German/English dashboards.
- All 754 tests pass with 89.09% combined line/branch coverage. Ruff and Mypy pass; Mypy checks all 22 program modules.
- Existing irrigation restart, soak-pause, sensor failure and safety regressions pass. No additional regular weather polling or mower commands; the second valve remains read-only.
- Mowing duration and grass dryness remain estimates; the soil model still requires field validation.

## 3.13.0

### Added
- Configure the required mowing duration (0–1440 minutes, default 0) and recommend only continuous weather windows long enough for a complete pass.
- Expose the next separate suitable window as an alternative, including available minutes; keep all guidance on existing entities without device commands or additional regular weather polling.
- Explain estimated versus insufficient mowing-window quality with localized reasons. Missing evidence outside the recommended window is reported separately.
- Update German/English mowing and care-plan dashboards, settings descriptions and documentation.

### Fixed
- Preserve conflicting forecast evidence when fresh current observations share the same instant. Conflicting duplicate hours remain unknown regardless of input order.
- Clear alternatives, available duration and quality when saved wet-event history makes mowing advice uncertain.

### Validation
- Reproduce three conflict regression cases against the previous planner before correcting them.
- Add 27 tests for required durations, alternative windows, forecast gaps, current-only evidence, schedule ends, DST, invalid configuration, read-only diagnostics and rendered German/English dashboards.
- All 712 tests pass with 88.94% combined line/branch coverage. Ruff and Mypy pass; Mypy checks all 21 program modules.
- Existing restart, sensor failure and irrigation safety regressions pass. The second valve remains read-only.
- Mowing suitability and grass dryness remain estimates requiring field checks.

## 3.12.0

### Added
- Recommend the next suitable mowing window using existing hourly forecasts, conservative dew-risk estimates, drying holds, mowing intervals and configurable allowed local times. Expose advice through existing entities; do not command the mower.
- Explain current/later/blocked care availability, remaining irrigation cycle/soak duration and observed weekly changes.
- Extend German/English dashboards, documentation and diagnostic attributes without additional regular weather polling.

### Fixed
- Reject naive forecast timestamps and Boolean weather values. Deduplicate equivalent forecast instants; conflicting entries remain explicitly unknown and cannot authorize automatic irrigation.
- Ignore expired wet-lawn care holds and handle malformed or future saved wet-event timestamps without crashing or claiming a dry lawn.
- Account for current irrigation segments, manual minimum durations and unknown pause end times in read-only cycle guidance.

### Validation
- Reproduce eight failing regression cases before correction; add 79 cases covering input errors, dew estimates, weather gaps, local/DST schedules, configuration, diagnostics, cycle phases and actual HA dashboard rendering.
- All 685 tests pass with 88.82% combined line/branch coverage. Mypy checks all 21 program modules, with stronger checks for ten core modules.
- Ruff, compilation, JSON/YAML, file headers, documentation links and whitespace checks pass. The second valve remains read-only.
- Mowing weather windows remain estimates; grass-surface dryness and soil-model accuracy require field validation.

## 3.11.0

### Added
- Explain ordered care priorities and prerequisites in existing care-plan attributes.
- Compare two rolling 168-hour periods using a bounded 14-day/336-snapshot history. Keep partial observations, uncertain consumption and manual estimates visible.
- Add conservative hints for independently reported flat moisture and repeated losses of valid sensor observations.
- Explain configured irrigation cycles, soak pauses and total duration using owned measured flow or a recent complete session. Suggest manual review when application exceeds profile-based infiltration.
- Expose live/last robot observation interruptions and inactive time, without claiming confirmed coverage or commanding the mower.
- Extend German/English explanations, README and dashboard templates.

### Fixed
- Reject future flow timestamps consistently in start/running checks, input diagnostics and completion estimates.
- Reject future current-weather, temperature, rain and forecast-cache timestamps instead of treating them as fresh or clamping rain reports to now.
- Preserve the original pre-correction comparison when a soil-sensor report is reused after model blending.
- Normalize history buckets to UTC so equivalent hours with different offsets cannot duplicate evidence.
- Ignore replayed/out-of-order mower transitions rather than inflating active mowing time.

### Validation
- Reproduce seven failing regression cases before correction; add 52 tests for chronology, care priorities, weekly totals/DST/gaps, sensor evidence, owned flow, robot persistence/rollback and read-only diagnostics.
- All 606 tests pass with 88.83% combined line/branch coverage. Mypy checks all 20 program modules, with stronger checks for nine core modules.
- Ruff, compilation, JSON/YAML, HA dashboard-template rendering, file headers, documentation links and whitespace checks pass.
- Preserve existing settings, maintenance and consumption. The second valve remains read-only and no extra regular OWM polling is introduced.

## 3.10.0

### Added
- Persist seven days of hourly model/sensor comparisons, bounded to 168 snapshots. Show recent evidence in existing sensor attributes and full history in downloaded diagnostics.
- Add conservative calibration advice using independent sensor reports, observation span, median disagreement and reference-limit checks. Parameter changes remain manual.
- Compare complete measured watering sessions with subsequent sensor observations, explicitly marking rain, incomplete metering and history gaps as uncertainty.
- Explain gross watering doses, model target/deficit, area, configured efficiency and estimated root-zone water credit without changing the existing dosing policy.
- Expose model initialization, missing historical data, distinct data gaps and estimated local/model recheck timing.
- Extend German/English diagnostic dashboard templates and documentation.

### Fixed
- Share flow normalization/freshness rules between diagnostics, start conditions and running checks; stale rates no longer appear accepted in input diagnostics.
- Safely close and finalize restored sessions with missing, null, invalid, naive or future timing fields; retain recovery and measurement-gap evidence.

### Validation
- Add 63 regression cases covering bounded history, conservative advice, live flow age, restart recovery, upgrade preservation, sensor attributes and drought/rewetting references.
- All 554 tests pass with 87.53% combined line/branch coverage. Mypy checks all 19 program modules without findings, with stronger checks for seven core modules.
- Existing care history, user settings and recorded consumption are preserved across upgrades.

## 3.9.0

### Diagnostics and model quality
- Export raw and normalized input observations, source age/rejection reasons, model assumptions, pre-correction sensor disagreement and a complete last-step soil balance.
- Explain model confidence conservatively: a fresh soil sensor no longer hides missing rain, stale weather, integration gaps or seasonal ET fallback. Expose readable German/English reasons.
- Preserve non-finite raw weather attributes as text so diagnostic exports remain valid JSON.
- Record storage save/verification outcomes and calculation failures without exposing error messages or filesystem paths; retain failure history after recovery until reload.
- Integrate the existing water-stress function within each step, fixing dry-down differences between short and long update intervals.
- Require a new sensor observation before the six-hour soil calibration can blend another reading.
- Close restored irrigation sessions even when their persisted timing fields are malformed; keep incomplete measurement visible.

### Validation and documentation
- Resolve the existing type-checking errors, introduce typed balance/confidence/storage contracts and run Mypy in GitHub CI. Apply stricter checks to five core modules; dynamic boundary payloads remain explicitly documented.
- Add 83 regression cases for multi-day conservation, interval sensitivity, calibration, diagnostic exports, storage/update failures and configuration error paths.
- All 491 tests pass with 86.98% combined line/branch coverage. Update German/English README, source-code guide and quality audit.

## 3.8.7

### Fixed

- Keep maintenance writes shielded through repeated cancellation so watering, fertilizing, mowing and undo transactions retain the model lock until persistence has resolved.
- Preserve committed maintenance changes after cancellation; roll back failed writes before releasing the lock or allowing a following action.
- Process expected storage errors without unhandled exceptions from a cancelled shielded task.

### Changed

- Add 19 regression cases covering repeated cancellation, failed writes, rollback/retry and concurrent maintenance actions; all 408 tests pass with 85.91% combined line/branch coverage.
- Add explanatory file headers to all 37 Python files and 16 YAML files, and expand documentation for 101 central functions.
- Document safety rules, units, calculation assumptions, persistence and file responsibilities in the source and a new source code overview; describe JSON files separately to preserve valid schemas.
- Confirm unchanged executable Python structure and parsed YAML configuration during commenting, and verify cancellation consistency with actual Home Assistant file storage.
- Update integration version identifiers, both READMEs and the quality audit.

## 3.8.6

### Fixed

- Apply temporary automation holds and close automatic watering before storage waits; retain safety holds after failed writes and preserve manual sessions.
- Preserve measured volume and active runtime until confirmed valve closure when entering soaking pauses.
- Finalize closed sessions when targets, runtime/volume limits, water budgets or meter faults are reached during pause closure; prevent reopening completed paused sessions.
- Find allowed schedule windows re-entered during the autumn clock rollback, including overnight windows.
- Accept opening-time counter resets for each watering cycle while retaining previous-cycle consumption; keep genuine later resets as safety faults.
- Prevent negative daily allocations when rounding small consumption amounts across midnight.
- Resolve cancelled and repeatedly cancelled irrigation completion transactions, publishing successful results once and retaining failed credits for retry.
- Verify saved state through Home Assistant's public storage API so write failures that HA only logs cannot permit an unsecured valve start or automation activation.

### Changed

- Add 47 regression cases; all 389 tests pass with 85.90% combined line/branch coverage.
- Update German and English documentation, the quality audit and all integration version identifiers.
- Verify the actual file-write failure path in addition to HA lifecycle and storage regression tests.

## 3.8.5

### Fixed

- Close automatically controlled irrigation before waiting for storage when automation is disabled, including blocked controller operations and failed writes.
- Run active safety checks before persisting expired late-opening supervision.
- Recheck watering demand, forecast freshness, rain availability, confidence and the forecast window immediately before initial automatic valve opening.
- Calculate forecast windows in elapsed hours across spring and autumn daylight-saving changes.
- Reject implausible soil temperatures after unit conversion and expose invalid readings in input diagnostics.
- Preserve the physical watering date, automatic daily lock and wet-lawn timestamp when completion bookkeeping crosses midnight.

### Changed

- Add 18 regression cases; all 342 tests pass with 85.25% combined line/branch coverage.
- Update German/English documentation, version identifiers and the quality audit.

## 3.8.4

### Fixed

- Make repeated stop requests safe during asynchronous irrigation completion.
- Enforce meter faults, flow limits, volume targets and water budgets while controller storage is blocked.
- Preserve known consumption at safety closure, during closing commands and before excessive-flow reports.
- Mark meter outages, stale readings, unit changes and counter resets as incomplete measurements; retain the wet-lawn interlock after confirmed watering with gaps.
- Freeze physical completion timestamps so storage waits do not inflate runtime or shift usage records.
- Recheck live weather before automatic valve opening/resume and expose lost weather immediately in diagnostics.
- Normalize current wind and pressure with Home Assistant converters and reject invalid meteorological inputs.
- Resolve schedule starts in the spring daylight-saving gap to the first existing allowed instant.
- Remove the Home Assistant stop listener cleanly without duplicate-unsubscribe errors.
- Synchronize manifest, device and diagnostic version identifiers.

### Changed

- Add 31 regression cases; all 324 tests pass with 84.98% combined line/branch coverage.
- Update German/English documentation and the quality audit.

## 3.8.3

### Fixed

- Recheck live safety inputs immediately before opening or resuming irrigation after a storage await.
- Close unsafe owned valves even while a controller storage operation holds the lock.
- Run watchdog safety checks before retrying failed storage writes.
- Refresh shared-meter baselines at valve opening so unrelated consumption during storage waits is excluded.
- Prevent delayed starts beyond the maximum runtime and reject rain arriving during an automatic resume.

### Changed

- Remove version-specific update blocks from both READMEs and keep release history in this changelog.
- Correct consumption and undo documentation and document the weather-source reconfiguration lock.
- Add 19 safety regression cases; all 293 tests pass with 84.28% combined line/branch coverage.

## 3.8.2

### Fixed

- Preserve measured irrigation usage and daily/weekly safety budgets when undoing model water credits.
- Serialize maintenance, model updates and irrigation completion to prevent concurrent persistence races.
- Roll back failed maintenance saves, translate storage errors and retain successful commits during cancellation.
- Close the owned valve before persistence so slow storage cannot delay safety stops.
- Block automatic weather-pause resume while rain or strong wind is already reported.
- Sum hourly forecast rain over 24 elapsed hours across daylight-saving changes.
- Reject missing, malformed, non-finite and implausible weather temperatures during configuration.
- Block weather-source reconfiguration during active irrigation.

### Changed

- Document physical-consumption retention after undo in German and English.
- Add 16 regression cases; all 274 tests pass with 84% combined line/branch coverage.
- Update the quality audit without claiming complete Home Assistant Quality Scale compliance.

## 3.8.1

### Fixed

- Normalize HA forecast temperature, precipitation and wind units, without converting wind twice.
- Reject malformed, non-finite and physically implausible forecast and rain readings.
- Retain valve safety supervision when platform unloading fails; clean up setup failures and shutdown timers.
- Close owned valves when opening/resume commands are cancelled.
- Report automation-toggle storage failures and roll back failed enable requests.
- Reject actions on never-loaded entries, future config-entry migrations and malformed imported schedules.
- Prevent direct maintenance water recording during an owned irrigation session.

### Changed

- Add weather-source reconfiguration while preserving lawn settings and history.
- Translate action exceptions and move entity icons to HA icon translations.
- Declare switch update concurrency and type platform config-entry runtime data.
- Expand real HA lifecycle, platform, diagnostics, unit and storage regression tests.
- Use Python 3.14 and pinned HA 2026.9.4 test dependencies in CI, with coverage reporting.
- Document audit evidence and remaining Quality Scale coverage/typing requirements.

## 3.8.0

### Added

- Debounced rain/wind stops for automatic irrigation using existing HA entities.
- Optional daily/weekly automation budgets, capped targets and incomplete-metering guards.
- Combined care-plan, daily consumption, next automatic start and remaining-time sensors.
- Completion estimates including soaking pauses and clear reasons for unavailable predictions.
- Ten-record consumption/session histories and actionable irrigation diagnostics.
- Duration-based automation holds, volume presets and German/English care-plan/history dashboards.
- Stable irrigation session IDs, target volumes and localized reasons in events.

### Fixed

- Read live air/soil temperatures and react directly to temperature state changes.
- Allocate measured intervals across local days, weeks and months, including DST; mark temporal estimates.
- Mark undone irrigation diagnostics and remove their effective model credit while retaining physical measurements and the daily safety lock.
- Mark bounded-rate integration gaps as incomplete measurement.
- Combine all prerequisites in next-start predictions instead of hiding blockers behind schedule/hold conditions.

## 3.7.0

### Added

- Manual irrigation targets in liters or millimeters, with metering and safety-limit validation.
- Optional watering cycles with supervised soaking pauses and shared-meter baseline resets.
- Local weekday/time schedules, including overnight windows, and persisted temporary automation holds.
- Optional leaf wetness input with freshness checks and safe fallback to estimated drying delays.
- Weekly and monthly consumption sensors with separate recorded, estimated, unmetered and incomplete-session details.
- Backdated mowing, fertilizing and watering actions; historical water does not alter today's soil balance.
- Entry-scoped irrigation start, pause, resume and completion events for user automations.
- Simultaneous irrigation condition diagnostics, detailed last-session accounting, sensor rejection reasons and forecast-source diagnostics.
- Live estimated robot session minutes updated locally without weather polling.
- German and English Mushroom dashboard templates, service descriptions and attribute tables.

### Fixed

- Block irrigation starts/resumes and stop active watering on freezing air or soil readings.
- Reject unknown, negative or non-finite wind and invalid/freezing temperatures in watering windows.
- Normalize naive and timezone-aware forecast timestamps before comparison and sorting.
- Restore all robot session details when undoing a mowing event.
- Complete watering/fertilizer explanations and add wet-lawn/frost status colors.
- Keep shared-meter flow out of paused-session diagnostics and consumption accounting.
- Persist usage and final water credit together; retries do not duplicate ledger entries or completion events.
- Keep older maintenance records from replacing newer dates and remove linked usage on undo.
- Correct README menu paths and distinguish orderly shutdown from sudden outages.

## 3.6.0

### Added

- Apply the wet-lawn mowing interlock immediately during running and paused irrigation, without additional weather polling.
- Show the last estimated robot mowing session's start, end and active minutes; exclude pauses and return travel.
- Expose irrigation target, delivered and remaining liters, progress percentage and delivered millimeters.
- Add readable German and English decision explanations alongside stable machine-readable reason codes.
- Add a configurable maximum age for physical soil moisture and temperature readings (default: six hours).

### Fixed

- Close the owned irrigation valve on orderly Home Assistant shutdown and block reopening during shutdown.
- Require successful session persistence before opening or resuming irrigation.
- Continue valve closure despite storage errors and retry failed water credits without duplicate accounting.
- Keep post-close shared-meter consumption out of completed and pending irrigation credits.
- Reject stale flow-rate readings at startup while allowing unchanged cumulative-meter baselines.
- Treat missing, negative and non-finite forecast precipitation as unknown instead of dry weather.
- Keep an eligible watering hour available while it is underway; reject expired or invalid forecast hours.
- Apply corrected or cleared fertilizing dates even when the prior configuration was empty.
- Remove obsolete optional irrigation entities and valve repair notifications when a valve is removed.

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


