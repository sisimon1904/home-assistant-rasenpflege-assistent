<!-- File: docs/web-dashboard.en.md — Integrated authenticated web dashboard. -->
# Web dashboard

Starting with **v3.17.0**, the integration serves its own web interface through the existing Home Assistant web server. Open **Lawn care** in the HA sidebar or append `/rasenpflege-assistent` to your existing Home Assistant address:

```text
http://YOUR-HA-ADDRESS:8123/rasenpflege-assistent
```

For HTTPS, a reverse proxy or Home Assistant Cloud, use that same base address. No additional port, Docker container, YAML import, custom cards or separate API token is required.

## Getting started

Install the updated integration, restart Home Assistant and open the panel. Sign in with your existing HA account. Actual entity IDs are discovered automatically; select the lawn at the top if multiple entries exist. Reload the page if it still shows an older interface.

The five responsive areas cover overview, care priorities and the conditional 48-hour outlook, dew-aware mowing, supervised irrigation and detailed diagnostics. The UI follows the HA frontend language in German or English. Explanatory sensor attributes continue to follow HA's configured language.

## Authentication and controls

Home Assistant owns authentication and the live state connection. Discovery respects entity read permissions. Control requires an HA administrator, enforced on the server. Other users have a read-only interface.

Starting watering, enabling automatic watering and recording care require confirmation. Stop remains immediate. Lawn selection is disabled while an action runs. Controller and persistence errors are shown instead of reporting success.

Irrigation commands use the existing supervised controller. The second valve remains read-only and the panel never starts a mower. Recording mowing or fertilizing logs completed care. Without a valve, watering can be recorded manually with an explicit quantity.

## History and limits

Live state changes use HA's existing connection. The seven-day soil-moisture graph reads Recorder history once on opening, lawn selection or explicit refresh. Recorder must retain that sensor. Unavailable samples break the line; missing history is not fabricated. No regular device or weather polling is added.

On disconnect, the last received values remain visible with a disconnected indicator; controls are disabled. Reconnection refreshes discovery. The refresh control reloads entity mappings and history without requesting weather data.

Soil moisture, dew risk and care windows remain estimates. Diagnostics show the evidence and uncertainty. [Lovelace templates](dashboard/README.en.md) remain available as another presentation. The web panel requires the standard HA frontend; intentionally headless installations retain the integration's existing entities and actions.
