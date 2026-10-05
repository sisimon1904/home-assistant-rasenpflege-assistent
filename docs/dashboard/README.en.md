<!-- File: docs/dashboard/README.en.md — Standalone dashboard installation instructions. -->
# Lawn Care Assistant dashboard

Use [dashboard.en.yaml](dashboard.en.yaml) with **v3.17.0 or newer**. It contains a complete dashboard with native Home Assistant cards; Mushroom and card-mod are not required. The five views cover overview, care priorities and the 48-hour outlook, mowing and dew, irrigation and consumption, and model/data diagnostics.

## Setup

1. Create a new empty dashboard under **Settings → Dashboards**.
2. Find your lawn's actual entity IDs under **Developer tools → States**. Replace every example ID in the YAML, including IDs inside templates. Both language variants share the German example IDs listed in the [entity mapping table](README.de.md#entitätszuordnung).
3. Under **Developer tools → Template**, evaluate `{{ config_entry_id('sensor.YOUR_LAWN_ENTITY') }}` and replace every `REPLACE_WITH_ENTRY_ID` with that lawn's configuration entry ID.
4. Open the new dashboard, choose **Edit dashboard → three-dot menu → Raw configuration editor**, paste the entire file and save. This file is a dashboard, not a manual card. Enable any disabled diagnostic entities on the integration device page if necessary.
5. Review all five views and resolve any missing entity IDs before using controls.

## Behavior

The irrigation control section and optional irrigation diagnostics are hidden when their status entity does not exist. Recommendations and consumption remain visible. Start, stop and suspension buttons use the integration's supervised actions. Enabling automatic irrigation can activate automatic watering. The dashboard never controls the second valve directly.

Native cards show HA-translated states; explanatory attributes use your configured Home Assistant language. Select English there for English explanations. Missing details appear as “—”. Unavailable entities retain their status indication and do not imply permission to start irrigation.

Recorder must retain soil-moisture history for the seven-day graph. Soil moisture is modeled; the gauge intentionally has no universal dry/wet thresholds. Weather windows and the care outlook remain estimates. No new sensors or regular weather API requests are introduced. Importing this file into your HA instance is a manual step.

The other YAML files remain individual Mushroom cards for existing dashboards.
