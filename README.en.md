# Lawn Care Assistant for Home Assistant

[Deutsch](README.md) | **English**

Version 3.20.0 · [Changelog](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

This integration evaluates lawn growth and maintenance needs using existing
OpenWeatherMap data in Home Assistant. It calculates the grassland temperature
sum, modeled soil moisture, and recommendations for watering, fertilizing, and
mowing. It can optionally control an existing irrigation valve; it does not
control the robotic mower.

Use **Settings → Devices & services → Lawn Care Assistant → Menu → Reconfigure** to replace the weather source. Other lawn settings remain under **Configure**. Source changes are blocked during running or paused irrigation.

See the [quality audit](docs/quality-audit.md) for checks and remaining Quality Scale requirements.
The [source code overview](docs/source-code.md) documents file responsibilities and development rules (in German).

The web dashboard shows care reasons, specific sensor checks and daily recorded water usage over 7 or 30 days. Download the full available water ledger as CSV, retaining unknown quantities and estimated date allocations. Care hints and irrigation interruptions have separate switches and minimum intervals, with shared quiet hours.

## Integrated web dashboard

Starting with **v3.17.0**, the integration serves a dedicated web interface at **`/rasenpflege-assistent`** on your Home Assistant web server. It appears as **Lawn care** in the sidebar, uses your existing HA login and discovers entity IDs automatically. Seven responsive areas cover overview with a daily plan, care planning, mowing, irrigation, trends, care log and diagnostics. Version 3.18.0 adds millimeter/liter irrigation targets, corrected manual care records and optional local HA notifications. The dashboard explains data age and evidence, remembers your lawn and view and supports direct links. No YAML import or additional container is required. [Access and setup guide](docs/web-dashboard.en.md).

## Weather stops and consumption budgets

Configure these options under **Configure → Irrigation safety**. Weather stops default to enabled: rain at 0.5 mm/h for rate sensors or 0.5 mm measured since session start for amount/cumulative sensors, wind at 8 m/s, and 120 seconds of confirmation. Short rate/wind spikes reset the timer when they subside. Currently reported rain or strong wind blocks automatic starts immediately. Without a valid rain sensor, current weather conditions provide the fallback. Missing weather is not treated as measured rainfall. Inputs use existing HA entities; there is no additional regular OWM API polling.

Daily/weekly budgets default to **0 (disabled)**. All recorded watering counts, including manual amounts and estimates; unknown or incomplete amounts block automatic starts for the affected budget period. Automatic targets are capped at the remaining budget. Reporting and valve delays can still cause overshoot. Manual starts retain the existing safety limits. The second valve remains strictly read-only.

Meter outages, stale readings, unit changes and unexpected counter resets mark a session as incompletely measured. Known quantities remain in the usage ledger; enabled daily/weekly limits block further automatic starts in the affected period. After at least one minute of confirmed watering with a measurement gap, the lawn is treated as wet even if no delivered quantity can be established. Runtime and completion time refer to confirmed valve closure rather than subsequent storage waits.

Disabling automation closes automatically controlled watering before saving the setting. A manually started session continues. Immediately before initial automatic opening, watering demand, data quality and the forecast window are checked again after any storage wait. Forecast windows span one elapsed hour across daylight-saving transitions.

Temporary automation holds also close automatic watering before storage waits. Saved state is checked after writing; storage failures block new starts. Soaking pauses count consumption and runtime until confirmed valve closure. Targets, safety limits or meter faults reached during closure finalize the session. Opening-time counter resets can be recognized for each cycle while retaining previously recorded consumption.

### Predictions, history and undo

The **care plan** combines mowing, watering and fertilizing with available times and blockers. **Next automatic irrigation start** intersects the cached forecast window with weekdays/hours, holds and retry cooldowns. Missing overlaps or prerequisites leave the timestamp unknown with an explanatory reason. This is an estimate rather than a reservation or a complete multi-day simulation.

**Remaining irrigation time** estimates active minutes from flow; `session_estimated_end` includes soak pauses. Other-valve pauses have an unknown end time. No achievable completion timestamp is given when the overall safety runtime is insufficient.

**Water consumption today**, weekly and monthly totals include completed or manually recorded watering. Active sessions are shown separately in irrigation diagnostics and included in budget checks. `recent_records` exposes the last ten records; `recent_sessions` exposes the last ten valve sessions. Cumulative readings crossing midnight are allocated in proportion to elapsed time and marked `allocation_estimated`; known total volume is preserved. Old records without measurement intervals retain their original date allocation.

Undo removes soil-model credit. Physically measured irrigation remains in the consumption ledger and continues counting against daily/weekly limits. Erroneous manual usage entries are removed. Physical measurements remain in last-session diagnostics with `undone: true`, `undone_at` and `effective_model_mm: 0`. The once-per-day automatic watering lock is retained for safety; undo does not trigger another automatic session.

`suspend_irrigation` accepts **`duration_hours`** (0.25–168), alternatively to `until`. Omit both to clear a hold. Dashboard templates: [Care plan](docs/dashboard/care-plan.en.yaml), [Consumption and history](docs/dashboard/consumption.en.yaml). The [irrigation card](docs/dashboard/irrigation.en.yaml) provides 1/3/5 mm, 100 liters and 2/24-hour holds. Other custom quantities are available in the HA action dialog.

| Diagnostic attributes | Meaning |
| --- | --- |
| `next_start_plan` | Estimated timestamp, reason and estimate flag. |
| `session_remaining_active_minutes`, `session_estimated_end`, `session_eta_reason` | Remaining time, estimated end and limitations. |
| `water_budget` | Known daily/weekly consumption, remaining budget and incomplete measurement. |
| `action_hint` | Concrete user action for the current automation blocker. |
| `allocations`, `allocation_estimated` | Per-day measured-volume shares and temporal estimate flag. |

## Irrigation targets, schedules and soaking cycles

Under **Configure → Irrigation – schedule and cycles**, choose weekdays and allowed local Home Assistant times. Equal start/end times permit the entire selected day. An overnight 22:00–02:00 window belongs to the day on which it starts. An empty weekday selection blocks automation. Existing configurations default to every day and all day.

The schedule limits automatic watering. A suitable weather window is also required at startup. A running automatic session stops at the end of the allowed time. Manual starts can occur outside the schedule, while obeying frost, mower, valve, meter and safety interlocks.

**Watering duration per cycle** defaults to 0 (disabled). A positive duration closes the owned valve after that active period. After the **soaking pause** (default: 15 minutes), all safety inputs are checked again before resuming. Pauses keep the session active and the lawn wet. Shared-meter consumption during pauses is excluded and the baseline resets before resuming. Total-runtime limits include all pauses. Restart closes a persisted paused session rather than resuming it. The second valve remains read-only.

Use **Developer tools → Actions** for these actions:

| Action | Additional fields | Behavior |
| --- | --- | --- |
| `rasenpflege_assistent.start_irrigation` | optional `target_liters` **or** `target_mm` | Manual start; volume targets require a water meter. |
| `rasenpflege_assistent.stop_irrigation` | none | Stop the owned running or paused session. |
| `rasenpflege_assistent.suspend_irrigation` | optional `until` **or** `duration_hours` | Hold automation; omit both to clear. |

All actions require `config_entry_id`. The action dialog lets you select the lawn configuration. Its ID can also be obtained with `{{ config_entry_id('sensor.YOUR_LAWN_ENTITY') }}` in **Developer tools → Template**. `until` must be a future ISO timestamp **with timezone**, such as `2026-10-02T08:00:00+02:00`.

An explicit volume target takes precedence over the usual manual minimum duration. Above-limit targets are rejected. Shutdown follows the reported meter value; sensor and valve delays can cause an overshoot. One millimeter equals one liter per square meter of lawn. The existing **Record watering** button retains its behavior without an explicit target.

A temporary hold stops an already-running automatic session, leaves the master automation switch unchanged and does not independently enable it on expiry. Manual watering remains available. Freezing air or soil readings block starts/resumes and stop a running session when that temperature information arrives.

## Leaf wetness, maintenance and consumption

Under **Configure → Input sensors**, an optional leaf wetness binary sensor uses `on` for wet and `off` for dry. A fresh dry reading can release the historical drying estimate after rain/irrigation. Active and paused irrigation still block mowing. Missing, invalid or stale readings restore the previous estimate. Maximum age is configured under **Soil and water model** (default: 360 minutes); the sensor should report regularly.

The `record_mowing`, `record_fertilizing` and `record_watering` actions accept optional `recorded_at`, a past ISO timestamp with timezone. Backdated watering requires explicit `amount_mm`. Historical water enters history and consumption without changing today's soil reservoir: past rain and evaporation are not replayed. Older events cannot replace a newer last-maintenance date. Without a timestamp, the existing immediate recording behavior applies.

Consumption sensors summarize known recorded quantities in the local calendar week (Monday to today) and current calendar month. Attributes distinguish valve measurements, user-recorded quantities, manual estimates, unmetered sessions and measurement gaps. Unknown volumes are never invented; totals with gaps are incomplete. Consumption starts with 3.7.0 and is not reconstructed from older bounded history. The usage ledger retains about one year; maintenance history retains the last 20 events. Undo removes erroneous manual usage entries. Measured irrigation consumption is retained; undo is blocked during controlled irrigation.

## Attribute language

Attribute labels and fixed values are provided in German and English. Technical keys remain stable for automations; nested explanations use the general Home Assistant language. Details and examples: [Attribute translations](docs/attributes.en.md).

## Diagnostic attributes and dashboard templates

The [complete dashboard](docs/dashboard/dashboard.en.yaml) organizes lawn care into five views using native Home Assistant cards. See the [dashboard setup guide](docs/dashboard/README.en.md) for entity mapping and import instructions. The template works with v3.17.0 and is pasted into a new dashboard's raw configuration editor.

Diagnostics read existing states without extra regular OpenWeatherMap queries. Live robot minutes update locally every 30 seconds. In-flight observations remain estimates and are discarded on restart.

| Entity / attribute | Unit | Meaning |
| --- | --- | --- |
| Irrigation status: `session_target_liters`, `session_liters`, `session_remaining_liters` | L | Target, known delivery and remainder; remaining volume is unknown without a target. |
| `session_progress_percent`, `session_delivered_mm` | %, mm | Progress and delivered water; unknown in unmetered timer mode. |
| `session_flow_l_min` | L/min | Flow while the owned valve is active, from a rate or last measured counter increment. |
| `session_active_seconds`, `session_paused_seconds`, `session_remaining_seconds` | s | Active time, pauses and remaining maximum total duration. |
| `session_cycle_number`, `session_pause_reason`, `session_resume_after` | count / code / ISO time | Current segment, pause reason and earliest resume. |
| `last_session` | object | Start/end, liters, mm, actual soil-model credit, durations, source, gap and outcome. |
| Irrigation readiness: `automatic_conditions`, `automatic_blockers`, `automatic_blockers_text` | object / lists | All start conditions and simultaneous failures, including readable explanations. |
| `automation_suspended_until` | ISO time | Temporary hold end; past timestamps no longer block. |
| Soil moisture / data quality: `input_diagnostics` | object | Entity, value, unit, age, allowed age and rejection reason for soil/leaf sensors. |
| Data quality: `forecast_diagnostics` | object | Weather entity, update time per forecast type, entry counts and missing inputs. |
| Mower status: `live_robot_session` | object | Active minutes, start and observation state; not proof of complete coverage. |
| `last_robot_session_started_at`, `last_robot_session_finished_at`, `last_robot_session_active_minutes` | ISO time, min | Last estimated robot session, excluding pauses and return travel. |
| Recorded irrigation this week / this month | L | Known recorded quantities; source and unknown sessions are attributes. |

Copyable Mushroom templates: [Overview](docs/dashboard/overview.en.yaml), [Irrigation controls](docs/dashboard/irrigation.en.yaml), [Mowing](docs/dashboard/mowing.en.yaml), [Diagnostics and consumption](docs/dashboard/diagnostics.en.yaml). Mushroom cards are required. Entity IDs are **examples** and must be replaced using **Developer tools → States**. Replace `REPLACE_WITH_ENTRY_ID` with the correct lawn's entry ID before using controls. Paste YAML into a manual dashboard card.

## Irrigation events for your automations

`rasenpflege_assistent_irrigation` provides `config_entry_id`, `phase`, `reason`, `source`, `started_at`, `liters`, `measurement_gap`, `session_id`, `target_liters` and `reason_text`. Phases are `started`, `paused`, `resumed`, `completed` and `stopped`. Completion events follow successful persistence and are not duplicated on storage retries. Events are live notifications and are not replayed after restart. The integration sends no messages itself.

```yaml
triggers:
  - trigger: event
    event_type: rasenpflege_assistent_irrigation
    event_data:
      config_entry_id: REPLACE_WITH_ENTRY_ID
      phase: stopped
actions:
  - action: persistent_notification.create
    data:
      title: Lawn irrigation stopped
      message: "Reason: {{ trigger.event.data.reason }}; known volume: {{ trigger.event.data.liters }} L"
```

## Installation

Requires Home Assistant 2026.4.0 or newer and a configured OpenWeatherMap
integration. Mode `v3.0` provides current conditions and hourly and daily
forecasts together.

1. In **HACS → Integrations → Custom repositories**, add
   `https://github.com/sisimon1904/home-assistant-rasenpflege-assistent`
   as an **Integration**.
2. Install **Lawn Care Assistant** and restart Home Assistant.
3. In **Settings → Devices & services → Add integration**, select **Lawn Care
   Assistant** and choose the OpenWeatherMap weather entity.

Alternatively, copy `custom_components/rasenpflege_assistent` to
`/config/custom_components/rasenpflege_assistent` and restart Home Assistant.
HACS updates require published GitHub releases.

## Settings and data sources

Each lawn has configurable area, use, soil type, sun exposure, root depth,
slope, compaction, irrigation efficiency, and rain correction.
Initial setup only asks for the name, OpenWeatherMap weather entity, and basic
lawn properties. **Configure** then offers separate pages for **Basic settings**,
**Input sensors**, **Mowing**, **Irrigation hardware**, **Soil and water model**, and
**Maintenance history**. **Irrigation safety** appears once a valve is selected.
Duration and other numeric values use visible entry boxes. Stop any running or
paused irrigation session before saving settings.
Outdoor temperature, observed rainfall, soil temperature, and soil moisture can use
optional separate sensors. Without a separate outdoor temperature sensor, the
integration uses OpenWeatherMap. Without a chosen rain sensor, it searches for
an active OpenWeatherMap rain sensor belonging to the weather configuration.

An optional physical soil moisture sensor supports dry and wet calibration
references. Optional **Lawn was mowed** and **Lawn was watered** binary sensors
record off-to-on transitions; manual buttons remain available without them.
Actual watering and fertilizing amounts can be recorded, and the most recent
maintenance action can be undone.

## Growth-dependent mowing

Choose **Manual mower** or **Robot mower** under **Configure → Mowing**.
Existing installations retain manual mode and their stored history by default.

| Growth | Manual mower | Robot mower |
| --- | --- | --- |
| Active | Every 4 days | Daily |
| Slow | Every 7 days | Every 3 days |
| Autumn / first awakening after season start | Every 10 days | Every 5 days |

These are recommendation estimates. Adjust all intervals with the factor:
1 = defaults, 0.5 = half the interval, 2 = twice the interval. Wetness, frost,
winter dormancy and drought stress take precedence. No robot commands are sent.

Optionally choose a mower status entity on the same page. Observation counts
only active mowing time (default: at least 10 minutes), followed by docking.
For `lawn_mower`, states normally are `mowing` and `docked`; `vacuum` entities may
use `cleaning`. Use the internal values shown in **Developer tools → States**.
Pauses and return travel do not count as mowing time. Errors, unknown states,
`idle`, short starts and restarts do not confirm a session. Observations expire
after twelve hours.

**Observation is an estimate:** Returning to charge may also create a record.
A configured **Lawn was mowed** binary input takes precedence and should report
actual job completion. 100% progress is not required. Distinct sessions on the
same day are recorded, while duplicate events are ignored.

Mower status exposes `last_mowing_at`, `next_mowing_at`, method, reason,
confidence and record source. The earliest estimated time combines the mowing
interval and wet-lawn pause. Frost, drought stress and missing temperature do
not produce a fixed release time. **Maintenance history** allows correcting or
clearing the last mowing date. Migrated and corrected date-only records use
local midnight as an estimated time; new events store the exact time.

## Optional automatic irrigation

Under **Configure**, select a valve `switch`, a water meter, and the mower's
actual dock status. Supported mower inputs include `lawn_mower`, `vacuum`,
`binary_sensor`, and custom status sensors. The mower must explicitly report
the docked state (`docked`, `on` for a binary dock sensor, or your selected
safe state). Missing or uncertain mower states block both automatic and
manual valve starts.

Supported meter units are **L**, **m³**, **gal**, **L/min**, **L/h**, **L/s**,
**m³/h**, **m³/min**, and **m³/s**. Automatic starts require a working meter.
An unmetered manual timer must be explicitly enabled and never credits an
unmeasured amount to the soil model.
The selected sensor must report **during watering**. A volume counter that
only updates after the valve closes cannot enforce the no-flow interlock;
verify reporting during a short supervised trial run.
A shared water meter is supported: all consumption while the lawn valve is
reported open is attributed to the lawn, including any simultaneous use by
other consumers. Consumption with the lawn valve closed is ignored. An optional
second `switch` or `binary_sensor` can report a competing valve. If it opens,
the lawn valve closes and the session pauses; an unavailable configured input
also closes the lawn valve. An omitted input is assumed closed. The integration
only reads this second valve; it never switches it.

With a valve configured, the existing watering button starts a supervised
session and **Stop irrigation** closes it. A configurable minimum runtime
applies to manual sessions unless a safety condition requires immediate
closure. Pauses count towards the maximum overall runtime and only resume
after renewed safety checks. The **Automatic irrigation** switch defaults to off. When enabled,
the integration does not start another session on the same local day after
water was delivered. A failed start without measured water may be retried after
30 minutes within a suitable forecast window when the inputs remain reliable.

An independent 15-second watchdog closes an owned valve for missing or
implausible flow, loss of dock confirmation, maximum runtime or volume, or
disabled automation. Persisted sessions are closed on restart rather than
resumed. Measured water enters the soil model after confirmed valve closure.
Unmetered manual sessions record a watering date, but do not invent water
volume. Following measured rain or watering, mowing is deferred until at
least the following local day and twelve hours after the wetting event;
a fresh optional leaf wetness reading can provide a more precise release.
A device-side cutoff remains advisable: sudden Home Assistant outages or radio loss prevent further commands. Orderly shutdown attempts to close the owned valve before integrations stop. Failed shutoff commands are
retried, but the physical valve must be checked if it does not respond.

No additional OpenWeatherMap API key is needed. The integration reads existing
entities and calls Home Assistant's `weather.get_forecasts` without requesting
the OpenWeatherMap API directly.

## Main entities

| Entity | Information |
| --- | --- |
| Growth status | Dormancy, awakening, growth, autumn, or drought; color as `icon_color` attribute |
| Care status | Priority action with fertilizer type, NPK, dose, and product amount as attributes |
| Mower status | Start, regular mowing, wet-grass pause, or winter off; next mow as an attribute |
| Modeled soil moisture | Estimated moisture, root-zone water, and water balance |
| Watering recommendation | Timing, mm, liters, rain forecast, and suggested window |
| Irrigation status (with valve) | Running, paused, completed, or stopped; last measured amount and stop reason |
| Irrigation diagnostics (with valve) | Start eligibility, both valve states, mower dock, meter freshness, runtime, target, and stop reason |
| Automatic irrigation decision (with valve) | Translated reason an automatic start is possible or blocked, with the next attempt time when known |
| Grassland temperature sum | Vegetation indicator with completeness details |
| Next action | One concise action recommendation |

Diagnostic entities expose data quality, confidence, sources, forecast age,
evapotranspiration method, and other model values. Some are disabled by default
and can be enabled in Home Assistant.

## History, calibration advice and amount explanations

The existing soil-moisture entity exposes `model_insights`. History retains **at most 336 hourly snapshots for 14 days**; entity attributes show the latest 24 snapshots, while downloaded diagnostics contain the full bounded history. Rain and ET terms are accumulated within each hour. Changing the soil sensor, dry/wet references, soil profile or root depth resets comparison evidence, preserving care history and water consumption.

| Diagnostic | Meaning |
| --- | --- |
| `model_insights.calibration` | Independent reports, observation span, median pre-correction disagreement, references and readable review suggestions. |
| `model_insights.watering_response` | Measured liters from the last controlled session and observed moisture change; incomplete amounts, rain and history gaps make attribution uncertain. |
| `model_insights.initialization` | Known model creation time, diagnostic recording start, missing historical temperature days and retention limits. |
| Data quality: `model_initialization`, `data_gaps` | Separate unknown observed rainfall, stale current weather, stale forecasts and unintegrated model hours. |
| Watering recommendation / next action: `watering_explanation` | Current water, 80% model target, deficit, expected ET, forecast rain, area, efficiency, gross applied mm/liters and estimated root-zone credit. |
| Irrigation diagnostics: `next_check` | Local safety rechecks normally within 15 seconds, estimated model refresh on the 30-minute interval and upcoming hold/cooldown/forecast boundaries. State events may check earlier; this does not promise a start. |

Calibration advice requires **six distinct sensor reports spanning at least 24 hours**. A median difference of at least 20 percentage points or readings remaining at reference limits produce review suggestions. Reusing one unchanged report does not create independent evidence. Review rainfall input, dry/wet references, measurement range, sensor location and soil profile first. **No parameters are changed automatically.**

Response review requires a sensor report within six hours before a fully measured controlled watering session and another between 30 minutes and 24 hours after it ends. Missing moisture increase does not prove a device fault. No measured efficiency or automatic dose correction is inferred; efficiency remains your setting.

Existing dosing policy is preserved: recommended mm and liters are **gross applied water**, and estimated root-zone credit is mm × efficiency. Forecast, ET, rounding and dose bounds influence the recommendation, so it is not simply deficit ÷ efficiency. Consumption and safety limits can further cap an automatic session target.

Older installations retain an unknown model creation time when that date was never recorded. Diagnostic recording starts at upgrade; earlier observations are not invented. A model time gap does not establish that HA was offline; its cause remains explicitly unknown. The [diagnostics card](docs/dashboard/diagnostics.en.yaml) displays advice and amount explanations. These features require no new mandatory sensors or extra regular OWM API requests.

## Care priorities, weekly comparison and cycle guidance

`care_plan.prioritized_steps` explains the order of existing recommendations: check missing temperatures or frost first, water when needed, wait for dry grass, mow within the recommended window and fertilize when due. Each step includes `action`, `after`, readable text and optional `not_before`. These are advisory steps, not automatically executed actions.

`model_insights.weekly_comparison` compares two consecutive periods of 168 actual hours, including across DST: recorded rain, estimated actual ET, mean modeled moisture and recorded liters. `recording_sufficient` requires at least 160 distinct hours without larger gaps; a total observed-rain value requires sufficient recording and known rain throughout. Incomplete recordings remain `partial_history`. Consumption uses local calendar dates, so allocation at window boundaries is estimated. `unknown_volume_records` and `estimated_volume_records` retain gaps and manual estimates. Pre-upgrade evidence is not invented.

`sensor_review` in model and data-quality attributes highlights repeated losses of valid observations or unusually flat moisture. A constant reading requires six independent reports spanning at least 24 hours and at least ten percentage points of modeled change before producing a hint. Reusing one report counts once. This is a review suggestion, not a confirmed device fault.

Irrigation diagnostics expose `cycle_plan`: active minutes, cycle count, intermediate soak pauses and total duration using existing settings. Flow comes from usable measurements in an owned active session or a fully measured session within seven days. Other users of a shared meter cannot supply a runtime estimate. Missing evidence leaves times unknown. Active sessions use the remaining target and remaining safety runtime; the current cycle phase remains estimated. If application exceeds profile-based infiltration, short cycles and soak pauses are suggested for manual review. These heuristics do not change settings or valves and require checking actual water distribution on site.

`live_robot_session` on mower-status attributes and `mowing_observation` in downloaded diagnostics show active/inactive minutes, interruptions, minimum duration, observation reason and the last persisted observation. Pauses and returns do not count as active mowing; late events are ignored. Docking after sufficient activity remains an estimate: `coverage_confirmed` is always `false`. The assistant sends no mower commands.

The [care-plan card](docs/dashboard/care-plan.en.yaml) and [diagnostics card](docs/dashboard/diagnostics.en.yaml) show these hints from existing data, without extra regular OWM API requests.

## Suitable mowing start and dew risk

Existing **mower status** and **care plan** entities expose `mowing_window`. **Data quality** contains `mowing_window_quality`; downloaded diagnostics expose `mowing_window`. No new entities are created. Existing `next_mowing_at` remains the earliest interval/wet-hold due time; `mowing_window.start` is the separate weather recommendation.

| Attribute | Meaning |
| --- | --- |
| `start`, `end` | Estimated suitable window within 48 actual hours, including local timezone; `null` when evidence is insufficient. |
| `current_dew`, `window_dew` | Current and recommended-start dew estimates, dew point in °C, temperature spread and source. |
| `reason_text`, `blockers_text` | Explanation of the recommendation or excluded times. |
| `missing_inputs`, `missing_inputs_text` | Missing temperature, precipitation, wind or dew evidence. |
| `leaf_wetness` | Existing optional binary observation: `wet`, `dry`, `unknown` or `not_configured`. |
| `estimated`, `surface_dry_confirmed` | Weather suitability remains estimated; dry grass is never claimed as confirmed. |

Under **Options → Mowing**, configure the daily allowed window, default **09:00–20:00 local time**. Equal times allow all day; an earlier end permits an overnight window. These settings guide recommendations and never command a mower.

Planning uses fresh HA observations and the existing hourly forecast cache. It respects interval due times, rain/watering wet holds, ongoing irrigation, frost, heat at 28 °C, wind above 8 m/s, predicted rain and rain probabilities of at least 50%. Each forecast slot covers at most one hour; gaps are not invented as dry evidence. Current weather supports only the next hour, never tomorrow's humidity.

A supplied dew point is preferred; otherwise temperature/humidity estimate it using the [Bolton inversion](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.dewpoint.html). Air/dew-point spreads up to 2 °C are high risk and up to 4 °C elevated risk. These are heuristics, not validated grass temperatures. After dew, fog or frost risk, require one continuous low-risk dry forecast hour before recommending a start. A fresh dry leaf observation overrides only current dew evidence, not rain, frost, future dew or ongoing watering. Invalid or future stored wet-grass timestamps cannot create a valid hold; without a fresh dry leaf observation the mowing window then remains unknown. Missing humidity and dew point remain unknown; daily forecasts do not become invented hourly values. Available fields depend on the weather provider ([HA forecast fields](https://www.home-assistant.io/actions/weather.get_forecasts/)).

**Check actual grass wetness before mowing.** Air and grass temperatures can differ, so low estimated dew risk cannot confirm a dry surface ([NWS dew development](https://www.weather.gov/source/zhu/ZHU_Training_Page/fog_stuff/Dew_Frost/Dew_Frost.htm)). No mower commands or extra regular OWM requests are added.

`prioritized_steps` adds localized availability (`now`, `later`, `blocked`, `not_needed`) and blocker explanations. Mowing uses the weather window as `not_before`; expired wet holds do not add another wait. Weekly `changes` compare rain, ET and recorded consumption, retaining unknown totals when evidence is incomplete. Cycle estimates account for remaining active segments, current soak pauses and the remaining manual standard-watering minimum. A pause with no known end leaves total duration unknown.

Conflicting forecast rows for one absolute instant become an unknown evidence slot rather than added rain or a dry hour. Conflicts affecting relevant watering forecasts lower confidence and block automatic starts; data quality reports `forecast_conflict`.

Under **Options → Mowing → Required mowing duration**, configure the time needed for a complete mowing pass (0–1440 minutes). The default **0** preserves planning without a minimum duration. For example, **120 minutes** requires a continuous supported window of at least two actual hours. Forecast gaps, unsuitable weather and the allowed schedule end split windows; daylight saving changes do not change the required real running time.

`required_minutes` reports the configured duration; `available_minutes` reports the recommended window length. `alternative` contains the next separate sufficiently long window with `start`, `end` and `available_minutes`, or `null` when no second window is available. It is a fallback window, not a second start inside the same window.

`quality` is `estimated` for a supported recommendation and `insufficient` when no sufficient window exists. `quality_text` and `quality_reasons_text` explain this in the HA language. `missing_inputs_text` describes missing information across the reviewed horizon; missing values outside the recommended window do not automatically reduce that window's quality. Dry grass is still not confirmed. Updated mowing and care-plan cards show duration and alternative windows.

### Mowing days, suggested duration and changes

Under **Options → Mowing**, select allowed weekdays and optional weekend times. Empty weekend fields inherit the general times; an empty weekday selection blocks all recommendations. Overnight windows belong to their starting day, including Friday-to-Saturday transitions. No mower commands are issued.

`duration_suggestion` reports typical elapsed mowing time from at least three comparable robot observations within 90 days. At most ten suitable observations are used: active time meets the recording minimum and at least 85% of elapsed time, at most one interruption, and matching source/observation settings. Variable, old or incomplete evidence yields no suggestion. New records include the required metadata; legacy records are not retroactively treated as complete observations. **Docking does not confirm full coverage.** Short return/pause periods are included in the suggested elapsed duration. The suggestion remains estimated and is never automatically applied as the required mowing duration.

`forecast_updated_at`, `forecast_age_minutes` and `weather_age_minutes` expose freshness; missing values remain unknown. `change` explains material recommended-start changes since the current HA startup using weather/dew evidence, data gaps, wet-lawn holds or mowing due times. Clock shifts below 15 minutes are suppressed. Restart/reload resets the baseline; attribute reads do not change history.

Soil-model diagnostics include `explanation`, a readable balance for the **last calculation**: initial + effective rain − evapotranspiration − drainage + sensor correction = final. The last watering credit is separate because it may already be included in initial water. Do not add it again. These values describe the model and do not confirm field accuracy.

## Extended model diagnostics

Download diagnostics from **Settings → Devices & services → Lawn Care Assistant → Download diagnostics**. The export includes `inputs`, `soil_model`, `storage` and `updates`. Soil moisture attributes also expose `model_diagnostics`, `model_confidence_reasons`, readable reason texts and `sensor_deviation_percentage_points`. Data quality includes storage and update diagnostics. Reading these snapshots uses existing data and does not command devices.

`soil_model.last_balance` explains the latest calculation: elapsed/integrated hours, initial water, corrected rainfall, interception, effective rain, runoff, drainage, actual evapotranspiration and final sensor correction, in millimeters. `balance_residual_mm` is the rounding residual before the separately reported sensor correction. Recorded watering changes storage when booked and is not extra rainfall in this calculation step.

Confidence is a diagnostic heuristic. Unknown observed rain, stale weather, model integration gaps, seasonal evapotranspiration estimates or a pre-correction sensor/model difference of at least 20 percentage points make it low. The threshold is not a statistical confidence interval. Without a valid soil sensor confidence is at most medium; high confidence does not prove field accuracy. Sensor corrections require a new observation and at least six hours since the previous correction, preventing repeated blending of the same unchanged reading.

`storage` reports the last successful write, last failed operation (`save` or `verify`), exception type, consecutive failures and pending writes. `updates` reports successful and failed calculations. Failure history remains visible after recovery until reload; diagnostic counters are not persisted. Error messages and filesystem paths are not exported.

The moisture percentage represents modeled plant-available root-zone capacity, not sensor volumetric water content. This single-bucket model uses profile-based soil parameters and estimated radiation/day-night distribution; it has not been validated against local field measurements. Water stress is integrated within each step to keep dry-down estimates comparable across calculation intervals.

## Soil water and limitations

The model maintains a virtual root-zone reservoir. Effective measured rain
and recorded irrigation fill it; estimated evapotranspiration depletes it.
Soil type, root depth, canopy wetting, infiltration, runoff, and water stress
affect the result. Evapotranspiration uses Penman-Monteith with estimated
radiation, or Hargreaves-Samani when inputs are unavailable. Rain probability
affects the recommendation only: forecast rain is never recorded as observed
rainfall.
During outdoor temperature outages, a conservative seasonal evaporation
estimate keeps the soil model running at low confidence. Daily totals use
Home Assistant's local time zone.

Without a measured rain source, actual rainfall remains unknown to the model.
Local showers, shade, and soil differences can cause deviations. Use
**Configure → Maintenance history → Initial estimated soil moisture** when needed. NPK and product
amounts are estimates; follow the manufacturer's dose and a soil analysis.
The diagnostic **Observed rain today** remains unknown when measurements are
missing or the day's readings were interrupted. A midyear installation marks
earlier days as missing from the grassland temperature sum until the next year
or a manual starting value is provided.

## Dashboard example

Home Assistant entities cannot set their own icon color. A Mushroom template
card can use the `icon_color` attribute:

```yaml
type: custom:mushroom-template-card
entity: sensor.rasen_wachstumsstatus
primary: "{{ state_attr(entity, 'friendly_name') }}"
secondary: "{{ state_translated(entity) }}"
icon: mdi:grass
icon_color: "{{ state_attr(entity, 'icon_color') }}"
tap_action:
  action: more-info
```

`state_translated(entity)` displays the translated state; `states(entity)`
returns the stable English machine state for automations.

See the [changelog](CHANGELOG.md) for details of previous versions.

## Removal and troubleshooting

Stop controlled irrigation first. Delete the lawn entry from **Settings → Devices & services**. Unload closes the owned valve; if closure cannot be confirmed, unloading fails and supervision stays active. Remove the integration files through HACS afterwards and restart Home Assistant. Separately configured weather and device integrations are preserved.

Download entry diagnostics and inspect irrigation readiness, automatic decision and repair issues. Automatic starts require fresh weather, a safe mower position and complete metering. For storage errors, check free space and write permissions; a successful save clears the issue. Review settings before enabling automation again.

### Traceable care guidance and completed sessions

The care plan adds `summary`: the first already prioritized action with availability, earliest time and explanation. Missing evidence preventing a mowing window appears in `mowing_window.evidence.blocking`; supporting uncertainty about robot programs appears separately under `supporting_unknown`. Gaps outside a recommended window remain visible under `excluded_horizon_inputs`.

Duration suggestions expose their observations, active/elapsed minutes, minimum/maximum and counted exclusions. Lawn area and observation sources must match. Program/area metadata is considered only when actually reported by the mower source. Changes during a run exclude it from duration comparisons. Missing metadata confirms neither an identical program nor complete coverage. Older records without area context remain in maintenance history but cannot serve as comparable duration observations.

`retrospective` compares elapsed, previously saved mowing windows with later reported weather points. At most twelve recommendations are retained for seven days; review uses up to 96 existing weather samples. It requires at least two distinct fresh report times, no more than 45 minutes apart or from the window boundaries. Reused, stale or conflicting reports cannot establish complete evidence. Results distinguish suitable sampled weather, observed blockers and insufficient evidence. **Neither continuous suitable weather nor dry grass surfaces is confirmed.**

`water_balance` in irrigation status and readiness diagnostics separates target, recorded liters, remainder against that session's target and effective model credit. Measurement gaps leave the remainder unknown; flow-based quantities carry an estimate flag. Model liters require the saved session area, which may be absent in older records. Aborted irrigation never automatically resumes to fill a remainder. Current safety conditions must be checked before a new start.

`data_gaps.impact_text` explains historical model gaps. A new soil reading can support the current state without reconstructing missing historical rainfall or evaporation. The [diagnostics card](docs/dashboard/diagnostics.en.yaml) shows these explanations and the water balance; the [care-plan card](docs/dashboard/care-plan.en.yaml) shows the compact next action.

### Care outlook and comparison diagnostics

The care plan now includes a conditional **48-hour outlook**. Diagnostics add mowing-window counts, completed-irrigation target comparisons and the current soil-moisture evidence basis. Predecessor actions remain prerequisites; gaps and estimates stay separate. No new entities or extra regular weather polling are introduced.

Details, limitations and dashboard templates: [Care outlook and comparison diagnostics](docs/care-outlook.en.md).
