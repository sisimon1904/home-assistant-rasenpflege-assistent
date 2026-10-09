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
## Extensions in 3.19.0

- **Explain care:** Overview and care plan expose existing reasons for mowing, watering and fertilizing. The time comparison reuses the conditional 48-hour outlook, preserving prerequisites and unknown times. It never reserves or starts actions.
- **Check inputs:** Unavailable, invalid and stale configured inputs show practical checks. Unconfigured optional sensors are not treated as failures.
- **Compare consumption:** Trends show local calendar weeks starting Monday and calendar months. Complete measured valve quantities, flow estimates and uncertain quantities are separated, with manual records/estimates shown separately. Unknown volume is not measured zero. l/m² divides recorded volume by the current area; after area changes it is a comparison value. Active sessions are excluded.
- **Export care:** Filter mowing, watering or fertilizing and download the visible, at most 20 records as CSV, including with read-only permissions. Timestamps retain their timezone. Cells are quoted and user-entered spreadsheet formulas neutralized. This export is not a complete annual archive.
- **Notifications:** Set optional HH:MM quiet hours in the Home Assistant timezone in the care log; leave both fields empty to disable. Overnight intervals are supported; equal endpoints are rejected. No new hints are published during quiet hours, existing hints remain visible and safety shutdowns remain active. Current recommendations and aborts no older than 24 hours are evaluated on the next successful update after quiet hours.
- **Changes only:** Optionally suppress recurring unchanged care hints. Changes in recommended care categories and mowing availability returning after an unavailable period can trigger a new hint. Category cooldowns still apply; moving forecast times alone do not trigger messages. The same irrigation abort is not repeated after restart.

Care history and saved model observations refresh in coalesced batches when lawn entities change. Reopening the same panel reloads its current data. No additional weather requests are made. Recorder history is still fetched on selection, reopening or explicit refresh.

## Extensions in 3.20.0

- **Full water CSV:** In Trends, download all available completed water-ledger entries, usually up to one year, separately from the short care-log export. Current sessions are excluded. Missing liters remain empty; JSON columns retain calendar allocations and uncertainty dates. Date, source and quality fields are exported without private session, meter or valve IDs. Readers with full lawn entity permissions can export; no administrator permission is required. Cells are quoted and spreadsheet formulas neutralized.
- **Daily water chart:** Choose 7 or 30 local calendar days. Stacked bars separate measured valve water, flow estimates, manual records, manual estimates and uncertain valve quantities. Expand the data table for dates, volumes and quality counts. A question mark indicates an unknown quantity or measurement gap; a partial known amount does not imply a complete total. No record means no recorded water, not measured zero consumption. Existing calendar allocations may themselves be estimated. Active sessions are excluded.
- **Specific diagnostics:** Configured inputs show age and available freshness limit, the care decisions they affect, and practical checks for that input. Recommendations remain conditional on their existing evidence.
- **Separate hints:** The global notification switch remains off by default. Care hints and abnormal irrigation interruption hints each have their own switch and 1, 6 or 24-hour minimum interval. Older saved preferences inherit their former interval for both categories. Quiet hours and changes-only remain shared settings. Care state changes are tracked during quiet hours and cooldowns: the currently applicable returning recommendation can be sent on a subsequent successful update, including after restart; a withdrawn recommendation is discarded. Safety shutdowns do not depend on hint settings.
- **Small quantities:** Unit-aware decimal precision avoids showing small nonzero liters, kilograms, millimeters or liters per square meter as zero. Very small nonzero values use scientific notation.

The charts and CSV reuse the saved ledger and the existing authenticated connection; they do not add regular weather or device polling. Second-valve data remains read-only.
