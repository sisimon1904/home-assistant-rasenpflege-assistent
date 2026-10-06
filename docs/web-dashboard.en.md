<!-- File: docs/web-dashboard.en.md — Integrated authenticated web dashboard. -->
# Web dashboard

Starting with **v3.17.0**, the integration serves its own web interface through the existing Home Assistant web server. Open **Lawn care** in the HA sidebar or append `/rasenpflege-assistent` to your existing Home Assistant address:

```text
http://YOUR-HA-ADDRESS:8123/rasenpflege-assistent
```

For HTTPS, a reverse proxy or Home Assistant Cloud, use that same base address. No additional port, Docker container, YAML import, custom cards or separate API token is required.

## Getting started

Install the updated integration, restart Home Assistant and open the panel. Sign in with your existing HA account. Actual entity IDs are discovered automatically; select the lawn at the top if multiple entries exist. Reload the page if it still shows an older interface.

The seven responsive areas cover overview, care priorities and the conditional 48-hour outlook, dew-aware mowing, supervised irrigation, trends, care log and detailed diagnostics. The UI follows the HA frontend language in German or English. Explanatory sensor attributes continue to follow HA's configured language.

## Authentication and controls

Home Assistant owns authentication and the live state connection. Discovery respects entity read permissions. Control requires an HA administrator, enforced on the server. Other users have a read-only interface.

Starting watering, enabling automatic watering and recording care require confirmation. Stop remains immediate. Lawn selection is disabled while an action runs. Controller and persistence errors are shown instead of reporting success.

Irrigation commands use the existing supervised controller. The second valve remains read-only and the panel never starts a mower. Recording mowing or fertilizing logs completed care. Without a valve, watering can be recorded manually with an explicit quantity.

## History and limits

Live state changes use HA's existing connection. The seven-day soil-moisture graph reads Recorder history once on opening, lawn selection or explicit refresh. Recorder must retain that sensor. Unavailable samples break the line; missing history is not fabricated. No regular device or weather polling is added.

On disconnect, the last received values remain visible with a disconnected indicator; controls are disabled. Reconnection refreshes discovery. The refresh control reloads entity mappings and history without requesting weather data.

Soil moisture, dew risk and care windows remain estimates. Diagnostics show the evidence and uncertainty. [Lovelace templates](dashboard/README.en.md) remain available as another presentation. The web panel requires the standard HA frontend; intentionally headless installations retain the integration's existing entities and actions.

## Extensions in v3.18.0

| Extension | Controls and data basis |
| --- | --- |
| Daily plan | Overview shows existing care priorities with earliest times, prerequisites and blockers. Future suggestions do not reserve actions. |
| Data quality | Calculation time, weather/forecast age and available confidence ratings. A live connection does not imply fresh weather data. |
| Trends | Seven days from the existing local model history, with separate model/sensor charts, recorded rain intervals and recent recorded irrigation quantities. |
| Care log | Up to 20 care entries, with manual mowing/watering/fertilizing records, timestamps, actual NPK product and quantity. |
| Liter targets | Enter irrigation targets in millimeters or liters, using existing server-side quantity and safety validation. |
| Notifications | Off by default; administrators can enable local HA hints with a 1, 6 or 24-hour minimum interval per category. |
| Remembered views | Lawn and view are stored per user in this browser; the current URL links directly to the selected view. |

**Trends:** Sensor readings use their saved measurement timestamp. Rain bars represent known recorded intervals, not complete daily totals. Irrigation bars show up to ten available usage entries within seven days in liters. Record labels distinguish sources, estimates and measurement gaps; unknown quantities never mean zero. Model/sensor lines break at missing values, source changes and gaps longer than an hour. Charts are snapshots: opening, changing lawns or refreshing reloads them. Full read access to the lawn's enabled entities is required for care history; partial permissions still allow other authorized dashboard data.

**Timestamps:** An empty time means now. An entered time uses the controlling device's local timezone, is sent with a timezone and must be in the past. Historical watering needs an explicit amount and never refills today's soil model retrospectively. Date-only records are displayed without a fabricated time.

**Undo and enter again:** Only the latest manual care record is eligible. The server rechecks its identity within the model transaction; a changed journal causes rejection. Automatic mower observations, mower completion inputs and physical irrigation cannot be removed through this shortcut. Undo is unavailable during controlled irrigation. A successful undo prefills the replacement form; saving records the corrected event. Undo and replacement are two separate actions.

**Liter targets:** When lawn area is available, the liter form additionally caps the target at 50 mm or 50,000 liters, whichever is smaller. Session details show available flow. Missing automatic permission is displayed as Unknown and its toggle is disabled.

**Notifications:** Hints appear in Home Assistant's notification drawer for recommended care and abnormal irrigation interruptions. Ordinary manual stops are excluded. Hints describe recommendations rather than asserting overdue care. Preferences and cooldowns survive restart; notifications do not replace safety shutdown. No phone push or external message recipient is configured. Enable them in the care log.

**Direct links:** Example: `/rasenpflege-assistent#view=water&lawn=YOUR_ENTRY_ID`. Allowed views: `overview`, `plan`, `mowing`, `water`, `trends`, `journal`, `diagnostics`. No credentials are stored. Expanded diagnostic details survive live updates of the same view.
