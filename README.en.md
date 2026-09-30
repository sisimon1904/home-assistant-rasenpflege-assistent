# Lawn Care Assistant for Home Assistant

[Deutsch](README.md) | **English**

Version 3.5.0 · [Changelog](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

This integration evaluates lawn growth and maintenance needs using existing
OpenWeatherMap data in Home Assistant. It calculates the grassland temperature
sum, modeled soil moisture, and recommendations for watering, fertilizing, and
mowing. It can optionally control an existing irrigation valve; it does not
control the robotic mower.

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
leaf wetness is estimated rather than measured.
A device-side cutoff remains advisable: Home Assistant cannot send a shutoff
command when it or the radio link is down. Failed shutoff commands are
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
**Configure → Recalibrate modeled soil moisture** when needed. NPK and product
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
