# Lawn Care Assistant for Home Assistant

[Deutsch](README.md) | **English**

Version 3.2.0 · [Changelog](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

This integration evaluates lawn growth and maintenance needs using existing
OpenWeatherMap data in Home Assistant. It calculates the grassland temperature
sum, modeled soil moisture, and recommendations for watering, fertilizing, and
mowing. It does not control irrigation or a robotic mower.

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
slope, compaction, irrigation efficiency, and rain correction. Outdoor
temperature, observed rainfall, soil temperature, and soil moisture can use
optional separate sensors. Without a separate outdoor temperature sensor, the
integration uses OpenWeatherMap. Without a chosen rain sensor, it searches for
an active OpenWeatherMap rain sensor belonging to the weather configuration.

An optional physical soil moisture sensor supports dry and wet calibration
references. Optional **Lawn was mowed** and **Lawn was watered** binary sensors
record off-to-on transitions; manual buttons remain available without them.
Actual watering and fertilizing amounts can be recorded, and the most recent
maintenance action can be undone.

No additional OpenWeatherMap API key is needed. The integration reads existing
entities and calls Home Assistant's `weather.get_forecasts` without requesting
the OpenWeatherMap API directly.

## Main entities

| Entity | Information |
| --- | --- |
| Growth status | Dormancy, awakening, growth, autumn, or drought; color as `icon_color` attribute |
| Care status | Priority action with fertilizer type, NPK, dose, and product amount as attributes |
| Mower status | Start, regular mowing, pause, or winter off; next mow as an attribute |
| Modeled soil moisture | Estimated moisture, root-zone water, and water balance |
| Watering recommendation | Timing, mm, liters, rain forecast, and suggested window |
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

Without a measured rain source, actual rainfall remains unknown to the model.
Local showers, shade, and soil differences can cause deviations. Use
**Configure → Recalibrate modeled soil moisture** when needed. NPK and product
amounts are estimates; follow the manufacturer's dose and a soil analysis.

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
