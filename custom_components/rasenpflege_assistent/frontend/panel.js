/**
 * File: custom_components/rasenpflege_assistent/frontend/panel.js
 * Local, authenticated Lawn Care Assistant web dashboard.
 * Home Assistant injects hass and owns authentication/state subscriptions.
 * Text from sensors is inserted as textContent, never executable HTML.
 * Only the admin-authorized WebSocket gateway performs scoped mutations.
 * No framework, CDN, credential storage, device polling or weather calls.
 */

const STYLE = `
:host{display:block;height:100%;color:#233c32;font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--green:#23684b;--muted:#697b71;--line:#e1e8df;--surface:#fff;--bg:#f5f7f1;--shadow:0 3px 18px #254b3010}
*{box-sizing:border-box}button,input,select{font:inherit}button,select{cursor:pointer}button:disabled{cursor:default;opacity:.55}button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #78bda0;outline-offset:3px}
.app{height:100%;display:flex;flex-direction:column;background:var(--bg);overflow:hidden}.top{display:flex;align-items:center;justify-content:space-between;padding:18px 30px;background:var(--surface);border-bottom:1px solid var(--line);gap:15px}.brand{display:flex;align-items:center;gap:12px}.brand-icon{display:grid;place-items:center;width:42px;height:42px;background:#e4efdf;border-radius:13px;color:var(--green)}h1{font-size:19px;line-height:1.3;letter-spacing:-.5px;margin:0}.small{font-size:12px;color:var(--muted)}.top-actions{display:flex;align-items:center;gap:12px}.connection{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}.dot{width:7px;height:7px;border-radius:50%;background:#438b59}.dot.off{background:#c37a40}select{max-width:250px;background:var(--bg);color:inherit;border:1px solid var(--line);border-radius:9px;padding:8px 12px}.layout{display:flex;flex:1;min-height:0}.rail{width:208px;flex-shrink:0;border-right:1px solid var(--line);padding:24px 14px;background:#eef2e9;display:flex;flex-direction:column;gap:8px}.rail-label{padding:2px 14px 12px;font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--muted)}.nav{display:flex;align-items:center;gap:12px;width:100%;padding:12px;border:0;border-radius:10px;background:transparent;text-align:left;color:var(--muted);font-size:14px}.nav:hover{background:#e3e9dc}.nav.active{background:var(--surface);color:var(--green);box-shadow:var(--shadow);font-weight:650}.rail-foot{margin-top:auto;padding:14px;font-size:11px;color:var(--muted)}ha-icon{--mdc-icon-size:22px}.main{flex:1;min-width:0;overflow:auto;padding:30px 38px 50px}.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:15px;margin-bottom:24px}.eyebrow{text-transform:uppercase;font-size:10px;letter-spacing:2px;color:var(--muted);margin-bottom:6px}h2{font-size:30px;line-height:1.2;letter-spacing:-1px;margin:0 0 6px;font-weight:650}.subtitle{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:var(--shadow);min-width:0}.span2{grid-column:span 2}.span3{grid-column:1/-1}.card-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:15px;gap:10px}.card-title{font-size:13px;font-weight:650;color:var(--muted)}.card-top ha-icon{color:var(--green)}.value{font-size:28px;letter-spacing:-.8px;font-weight:650;line-height:1.3;margin:5px 0 10px;overflow-wrap:anywhere}.value.compact{font-size:21px}.hint{color:var(--muted);font-size:12px}.hero{background:#e3edde;border-color:#d5e1cd}.hero .value{font-size:25px}.tag{display:inline-block;padding:4px 10px;border-radius:20px;background:#eef4e9;color:var(--green);font-size:11px}.tag.orange{background:#fff0dc;color:#95622c}.tag.red{background:#fbe9e3;color:#a0442c}.tag.blue{background:#e9f1f8;color:#416b8c}.tag.grey{background:#f0f1ee;color:#737d72}.meter{height:9px;border-radius:20px;background:#e9eee4;overflow:hidden;margin:15px 0}.meter-fill{height:100%;background:#5d9270;border-radius:inherit}.row{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}.row:last-child{border-bottom:0}.row-label{color:var(--muted)}.row-value{text-align:right;overflow-wrap:anywhere;max-width:65%}.steps{display:flex;flex-direction:column;gap:18px}.step{display:flex;gap:14px}.step-num{display:grid;place-items:center;width:30px;height:30px;flex-shrink:0;background:#ecf2e7;border-radius:50%;font-size:12px;color:var(--green);font-weight:650}.step-title{font-weight:650;font-size:14px}.step-text{font-size:12px;color:var(--muted);margin-top:3px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}button.action{border:1px solid var(--line);background:var(--surface);border-radius:9px;padding:9px 14px;color:var(--green);font-size:12px;font-weight:600}button.primary{background:var(--green);border-color:var(--green);color:white}button.danger{border-color:#d8b1a3;color:#a0442c}.form{display:flex;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-top:16px}.field{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}input{width:120px;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px}input.wide{width:165px}.notice{padding:13px 18px;border:1px solid #e2d3b2;background:#fff8e8;border-radius:10px;font-size:13px;margin-bottom:20px}.notice.error{border-color:#d9aca0;background:#fff0eb;color:#9b4934}.notice.success{border-color:#cfdecb;background:#edf4e8;color:var(--green)}.empty{max-width:620px;margin:55px auto}.empty h2{font-size:25px}.empty p{color:var(--muted)}.notes{display:flex;flex-direction:column;gap:8px;font-size:12px;color:var(--muted)}details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px;font-size:12px}summary{cursor:pointer;color:var(--green);font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:1.6;background:var(--bg);padding:14px;border-radius:10px;max-height:420px;overflow:auto}.spark{width:100%;height:105px;display:block;margin-top:12px}.chart-labels{display:flex;justify-content:space-between;color:var(--muted);font-size:10px}.menu{border:0;background:none;color:var(--green);padding:4px}.readonly{margin-top:10px;font-size:11px;color:var(--muted)}
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.span3{grid-column:1/-1}.rail{width:176px}.main{padding:26px}.top{padding:15px 22px}}
@media(max-width:760px){.top{padding:12px 16px}.connection{display:none}.top-actions{gap:5px}select{max-width:150px;font-size:12px}.small{font-size:10px}.layout{flex-direction:column}.rail{width:100%;padding:9px 10px;border-right:0;border-bottom:1px solid var(--line);flex-direction:row;overflow:auto;gap:4px}.rail-label,.rail-foot{display:none}.nav{width:auto;flex-shrink:0;padding:8px 10px;gap:6px;font-size:11px}.nav ha-icon{--mdc-icon-size:17px}.main{padding:22px 16px 36px}.grid{grid-template-columns:1fr;gap:14px}.span2,.span3{grid-column:auto}.card{padding:20px}h2{font-size:26px}.page-head{align-items:flex-start}.page-head .tag{display:none}.value{font-size:26px}}
@media(prefers-color-scheme:dark){:host{color:#dce8df;--surface:#23342b;--bg:#19271f;--line:#37473a;--muted:#a4b5a5;--green:#98cda9;--shadow:none}.rail{background:#1f2e25}.rail .nav:hover{background:#2b3b30}.hero{background:#314832;border-color:#415943}.brand-icon,.step-num{background:#354833}.tag{background:#344834}.tag.grey{background:#344034;color:#afbbac}.tag.orange{background:#5b4528;color:#f1c784}.tag.red{background:#5c352d;color:#f0b29e}.tag.blue{background:#2d4252;color:#b1d1ed}.meter{background:#3b4c3d}.notice{background:#433b27;border-color:#665b3d}.notice.error{background:#432c27;border-color:#6c4439;color:#edb49e}.notice.success{background:#2d432e;border-color:#425c42}.action.primary{background:#86b594;color:#18271d;border-color:#86b594}}
`;

// Keep static UI wording independent from HA's server-language explanations.
const WORDS = {
  de: {brand:"Rasenpflege",sub:"Dein Garten. Gut versorgt.",overview:"Übersicht",plan:"Pflegeplan",mowing:"Mähen",water:"Bewässerung",diagnostics:"Diagnose",garden:"DEIN GARTEN",today:"Heute im Blick",overviewSub:"Die nächste richtige Pflege – aus deinen vorhandenen Daten.",live:"Live verbunden",offline:"Verbindung unterbrochen",next:"Nächste Pflege",growth:"Wachstum",soil:"Bodenfeuchte",modeled:"Modellierter Wert",quality:"Datenqualität",forecast:"Regenprognose",rain24:"Nächste 24 Stunden",rain72:"Nächste 72 Stunden",recorded:"Erfasste Bewässerung",week:"Diese Woche",month:"Dieser Monat",todayWater:"Heute",mower:"Mähempfehlung",reason:"Begründung",window:"Zeitfenster",alternative:"Ausweichtermin",duration:"Benötigte Dauer",available:"Verfügbare Dauer",dew:"Tauprüfung",last:"Zuletzt gemäht",nextMow:"Nächster Mähtermin",interval:"Mähintervall",minutes:"min",days:"Tage",fertilizer:"Düngung",dose:"Dosierung",total:"Gesamtmenge",npk:"NPK",priority:"Pflegereihenfolge",outlook:"Ausblick · 48 Stunden",earliest:"Frühestens",candidate:"Wetterfenster zur Prüfung",dependency:"Voraussetzung",watering:"Bewässerungsempfehlung",session:"Bewässerungssitzung",delivered:"Geliefert",target:"Ziel",remaining:"Verbleibend",finish:"Geschätztes Ende",automatic:"Automatische Bewässerung",enable:"Automatik aktivieren",disable:"Automatik deaktivieren",start:"Starten",stop:"Stoppen",pause2:"2 h sperren",pause24:"24 h sperren",resume:"Sperre aufheben",recordMow:"Mähen erfassen",recordFert:"Düngung erfassen",recordWater:"Bewässerung erfassen",notConfigured:"Kein Bewässerungsventil eingerichtet. Empfehlungen und manuelle Erfassung bleiben verfügbar.",readOnly:"Nur Ansicht. Bedienaktionen benötigen einen HA-Administrator.",loading:"Rasenflächen werden geladen …",noLawns:"Keine Rasenfläche verfügbar",noLawnsText:"Prüfe, ob die Integration geladen ist und dein Benutzer die Rasenentitäten lesen darf.",retry:"Erneut laden",refresh:"Rasenflächen aktualisieren",done:"Aktion erfolgreich ausgeführt.",busy:"Aktion wird ausgeführt …",confirmStart:"Die Bewässerung jetzt für diese Rasenfläche starten?",confirmEnable:"Automatische Bewässerung für diese Rasenfläche aktivieren?",confirmRecord:"Diese Pflege als erledigt erfassen?",failed:"Aktion fehlgeschlagen",details:"Alle Attribute",inputs:"Datenquellen",balance:"Bodenwasserbilanz",evidence:"Messgrundlage",calibration:"Modellkalibrierung",gaps:"Historische Datenlücken",irrigationQuality:"Bewässerungsfreigabe",comparison:"Bewässerung · Sollvergleich",review:"Mähfenster · Rückblick",weekly:"Wochenvergleich",source:"Quelle",age:"Alter",modelNote:"Bodenfeuchte, Tau und Wetterfenster sind Schätzungen. Diagnose zeigt ihre Messgrundlage.",history:"Bodenfeuchte · 7 Tage",historyEmpty:"Noch keine aufgezeichneten Werte für diesen Zeitraum.",historyError:"Verlauf konnte nicht geladen werden.",amount:"Menge",validAmount:"Bitte eine gültige Menge innerhalb des angezeigten Bereichs eingeben.",wetUntil:"Nässepause bis",version:"Version",unknown:"Nicht verfügbar",on:"Aktiv",off:"Deaktiviert",updated:"Letzte Berechnung",noSteps:"Aktuell keine weiteren Schritte verfügbar.",flow:"Durchfluss",progress:"Fortschritt",missingEntity:"Entität fehlt oder ist deaktiviert",recordNote:"Erfassung trägt abgeschlossene Pflege ein; sie startet keinen Mäher.",historyNote:"Recorder-Aufzeichnungen; Lücken werden nicht verbunden.",status:"Status",refreshError:"Rasenflächen konnten nicht geladen werden."},
  en: {brand:"Lawn care",sub:"Your garden. Well cared for.",overview:"Overview",plan:"Care plan",mowing:"Mowing",water:"Irrigation",diagnostics:"Diagnostics",garden:"YOUR GARDEN",today:"Today at a glance",overviewSub:"The next right step – from your existing data.",live:"Live connected",offline:"Connection interrupted",next:"Next care action",growth:"Growth",soil:"Soil moisture",modeled:"Modeled value",quality:"Data quality",forecast:"Rain forecast",rain24:"Next 24 hours",rain72:"Next 72 hours",recorded:"Recorded irrigation",week:"This week",month:"This month",todayWater:"Today",mower:"Mowing recommendation",reason:"Reason",window:"Window",alternative:"Alternative window",duration:"Required duration",available:"Available duration",dew:"Dew check",last:"Last mowing",nextMow:"Next mowing",interval:"Mowing interval",minutes:"min",days:"days",fertilizer:"Fertilizing",dose:"Dose",total:"Total amount",npk:"NPK",priority:"Care priorities",outlook:"Outlook · 48 hours",earliest:"Not before",candidate:"Weather window to review",dependency:"Prerequisite",watering:"Watering recommendation",session:"Irrigation session",delivered:"Delivered",target:"Target",remaining:"Remaining",finish:"Estimated finish",automatic:"Automatic irrigation",enable:"Enable automatic irrigation",disable:"Disable automatic irrigation",start:"Start",stop:"Stop",pause2:"Hold for 2 h",pause24:"Hold for 24 h",resume:"Clear hold",recordMow:"Record mowing",recordFert:"Record fertilizing",recordWater:"Record watering",notConfigured:"No irrigation valve configured. Recommendations and manual records remain available.",readOnly:"View only. Controls require a Home Assistant administrator.",loading:"Loading lawns …",noLawns:"No lawn available",noLawnsText:"Check whether the integration is loaded and your user may read the lawn entities.",retry:"Try again",refresh:"Refresh lawns",done:"Action completed successfully.",busy:"Action in progress …",confirmStart:"Start watering this lawn now?",confirmEnable:"Enable automatic irrigation for this lawn?",confirmRecord:"Record this care task as completed?",failed:"Action failed",details:"All attributes",inputs:"Data sources",balance:"Soil water balance",evidence:"Measurement evidence",calibration:"Model calibration",gaps:"Historical data gaps",irrigationQuality:"Irrigation readiness",comparison:"Irrigation · target comparison",review:"Mowing window · review",weekly:"Weekly comparison",source:"Source",age:"Age",modelNote:"Soil moisture, dew and weather windows are estimates. Diagnostics explain the evidence.",history:"Soil moisture · 7 days",historyEmpty:"No recorded values for this period yet.",historyError:"Could not load history.",amount:"Amount",validAmount:"Enter a valid amount within the displayed range.",wetUntil:"Wet-grass hold until",version:"Version",unknown:"Unavailable",on:"Enabled",off:"Disabled",updated:"Last calculation",noSteps:"No additional steps available right now.",flow:"Flow",progress:"Progress",missingEntity:"Entity missing or disabled",recordNote:"Recording logs completed care; it does not start a mower.",historyNote:"Recorder samples; gaps are not connected.",status:"Status",refreshError:"Could not load lawns."}
};

// This helper handles all sensor-supplied text. Only STYLE is trusted HTML.
function el(tag, cls, ...children) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  for (const child of children.flat()) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
function icon(name) { const node = el("ha-icon"); node.setAttribute("icon", name); return node; }
// View IDs and preference keys are static allowlists. Never persist credentials.
const VIEWS = ["overview", "plan", "mowing", "water", "trends", "journal", "diagnostics"];
Object.assign(WORDS.de, {good:"Gut",limited:"Eingeschränkt",insufficient:"Unzureichend",trends:"Verläufe",journal:"Pflegeprotokoll",dayPlan:"Tagesplan",rain:"Erfasster Regen",measured:"Sensorwert",waterEvents:"Bewässerung · erfasste Mengen",trendNote:"Modell und Messung sind getrennt. Regen zeigt erfasste Intervalle, keine vollständigen Tagessummen. Fehlende Daten bedeuten nicht null.",journalNote:"Bis zu 20 Pflegeeinträge. Nur der letzte manuelle Eintrag kann zurückgenommen und anschließend korrigiert neu erfasst werden. Physische Bewässerung und automatische Mähbeobachtungen bleiben geschützt.",undo:"Zurücknehmen und neu erfassen",confirmUndo:"Den letzten manuellen Pflegeeintrag zurücknehmen? Danach kannst du ihn korrigiert neu erfassen.",recordCare:"Pflege erfassen",careTime:"Zeitpunkt · lokale Zeit dieses Geräts (leer = jetzt)",validTime:"Bitte einen vergangenen Zeitpunkt angeben.",notifications:"Benachrichtigungen",notifyNote:"Optionale Hinweise in der Home-Assistant-Glocke bei empfohlener Pflege und Bewässerungsabbrüchen. Keine Push-Nachrichten an ein Telefon.",notifyInterval:"Mindestabstand je Hinweisart",save:"Speichern",hours:"Stunden",journalError:"Pflegeprotokoll ist nicht verfügbar. Vollständige Leserechte für die Rasenfläche erforderlich; danach erneut aktualisieren.",noJournal:"Noch keine Pflegeeinträge.",unit:"Einheit",confidence:"Verlässlichkeit",high:"Hoch",medium:"Mittel",low:"Gering",weatherAge:"Alter Wetter",forecastAge:"Alter Prognose",soilSource:"Bodenmodell · Messgrundlage",noSamples:"Noch keine gespeicherten Modellbeobachtungen.",partial:"Unvollständige oder unsichere Messung",historical:"Historisch erfasst",manual:"Manuell",robot_estimate:"Automatische Mähbeobachtung",completion_input:"Fertigmeldung",fertilizing:"Düngung",watering:"Bewässerung",mowing:"Mähen",autoUnknown:"Unbekannt",product:"Produkt · NPK (optional)",kg:"Düngermenge · kg (optional)",actualFlow:"Durchfluss · Messung/Schätzung"});
Object.assign(WORDS.en, {good:"Good",limited:"Limited",insufficient:"Insufficient",trends:"Trends",journal:"Care log",dayPlan:"Daily plan",rain:"Recorded rain",measured:"Sensor reading",waterEvents:"Irrigation · recorded quantities",trendNote:"Model and measurements are separate. Rain shows recorded intervals, not complete daily totals. Missing data does not mean zero.",journalNote:"Up to 20 care records. Only the latest manual record can be undone and then entered again with corrections. Physical irrigation and automatic mower observations stay protected.",undo:"Undo and enter again",confirmUndo:"Undo the latest manual care record? You can then enter it again with corrections.",recordCare:"Record care",careTime:"Time · this device’s local time (empty = now)",validTime:"Enter a time in the past.",notifications:"Notifications",notifyNote:"Optional hints in Home Assistant’s notification drawer for recommended care and interrupted irrigation. No phone push notifications.",notifyInterval:"Minimum interval per notification category",save:"Save",hours:"hours",journalError:"Care history unavailable. Full lawn read access is required; refresh afterwards.",noJournal:"No care records yet.",unit:"Unit",confidence:"Confidence",high:"High",medium:"Medium",low:"Low",weatherAge:"Weather age",forecastAge:"Forecast age",soilSource:"Soil model · measurement evidence",noSamples:"No saved model observations yet.",partial:"Incomplete or uncertain measurement",historical:"Historical record",manual:"Manual",robot_estimate:"Automatic mower observation",completion_input:"Completion input",fertilizing:"Fertilizing",watering:"Watering",mowing:"Mowing",autoUnknown:"Unknown",product:"Product · NPK (optional)",kg:"Fertilizer amount · kg (optional)",actualFlow:"Flow · measured/estimated"});
Object.assign(WORDS.de, {stale:"Veraltet",missing:"Fehlt",unavailable:"Nicht verfügbar",invalid:"Ungültig",invalid_or_stale:"Ungültig oder veraltet"});
Object.assign(WORDS.en, {stale:"Stale",missing:"Missing",unavailable:"Unavailable",invalid:"Invalid",invalid_or_stale:"Invalid or stale"});
Object.assign(WORDS.de, {measuredWater:"Gemessene Ventilmenge",flowEstimatedWater:"Geschätzte Ventilmenge",uncertainWater:"Ventilmenge · Messgrundlage unklar"});
Object.assign(WORDS.en, {measuredWater:"Measured valve volume",flowEstimatedWater:"Estimated valve volume",uncertainWater:"Valve volume · uncertain evidence"});
const missing = (v) => v == null || v === "unknown" || v === "unavailable";
const finite = (v) => !missing(v) && v !== "" && Number.isFinite(Number(v));

// Export only the currently visible, permission-filtered journal. Quote every
// CSV cell and neutralize spreadsheet formulas in user-entered product text.
export function careCsv(records) {
  const rows = [["action","recorded_at","logged_at","amount_mm","amount_kg","product_npk","source","historical"]];
  for (const row of records) {
    const d = row.details || {};
    rows.push([row.action,d.recorded_at || row.timestamp,row.timestamp,d.amount_mm,d.amount_kg,d.product_npk,d.source,d.historical]);
  }
  return csvRows(rows);
}

function csvRows(rows) {
  const cell = value => {
    let text = value == null ? "" : String(value);
    if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"','""') + '"';
  };
  return "\uFEFF" + rows.map(row => row.map(cell).join(",")).join("\r\n") + "\r\n";
}

export function waterCsv(records) {
  // All available ledger rows, not merely the ten recent sensor attributes.
  // Preserve nulls as empty cells and keep calendar allocations explicit.
  const keys = ["date","recorded_at","liters","source","volume_estimated","measurement_gap","allocation_estimated","allocations","uncertainty_dates"];
  return csvRows([keys,...records.map(row => keys.map(key => ["allocations","uncertainty_dates"].includes(key) ? JSON.stringify(row[key] || []) : row[key]))]);
}

Object.assign(WORDS.de, {why:"Warum jetzt – warum noch nicht?",possible:"Nächster sinnvoller Zeitpunkt",conditional:"Zeitpunkte sind bedingt durch Wetter und Voraussetzungen. Ohne ausreichende Daten bleibt der Zeitpunkt offen.",filter:"Einträge filtern",all:"Alle",export:"CSV herunterladen",consumption:"Wasserverbrauch · Kalenderzeiträume",perArea:"Liter je m² · heutige Fläche",physical:"Erfasste Ventilsitzungen",manualWater:"Manuell erfasste Menge",estimatedWater:"Manuelle Schätzung",volumeNote:"Ventilsitzungen können Messlücken enthalten. l/m² nutzt die heutige Fläche und ist bei Flächenänderungen ein Vergleichswert. Aktive Sitzungen sind nicht enthalten.",gaps:"Messlücken / unbekannte Mengen",quietStart:"Ruhezeit ab (HA-Zeit)",quietEnd:"Ruhezeit bis (HA-Zeit)",changesOnly:"Nur geänderte Pflegeempfehlungen",yes:"Ja",no:"Nein",quietNote:"Beide Zeiten leer lassen, um Ruhezeiten auszuschalten. Während der Ruhezeit werden keine neuen Hinweise veröffentlicht. Sicherheitsabschaltungen bleiben aktiv.",sensorProblem:"Daten prüfen",staleHint:"Sensor aktualisieren und dessen Verbindung sowie eingestellte maximale Datenalter prüfen.",missingHint:"Entität, Verfügbarkeit und Einheit in Home Assistant prüfen.",impact:"Diese Daten können Empfehlungen einschränken. Wetter und Regen beeinflussen Pflege und Wasserbilanz; Bodenwerte unterstützen das Modell; Tau und Blattnässe beeinflussen Mähfenster.",noProblem:"Keine Probleme an den aufgeführten Eingängen erkannt.",unknownVolume:"Unbekannte Menge bleibt offen."});
Object.assign(WORDS.en, {why:"Why now – why wait?",possible:"Next useful care time",conditional:"Times depend on weather and prerequisites. Without sufficient evidence the time remains unknown.",filter:"Filter records",all:"All",export:"Download CSV",consumption:"Water use · calendar periods",perArea:"Liters per m² · current area",physical:"Recorded valve sessions",manualWater:"Manually recorded amount",estimatedWater:"Manual estimate",volumeNote:"Valve sessions can contain measurement gaps. l/m² uses the current area and is a comparison value after area changes. Active sessions are excluded.",gaps:"Measurement gaps / unknown quantities",quietStart:"Quiet hours from (HA time)",quietEnd:"Quiet hours until (HA time)",changesOnly:"Changed care recommendations only",yes:"Yes",no:"No",quietNote:"Leave both times empty to disable quiet hours. No new hints are published during quiet hours. Safety shutdowns remain active.",sensorProblem:"Check data",staleHint:"Update the sensor and check its connection and configured maximum data age.",missingHint:"Check the entity, availability and unit in Home Assistant.",impact:"These inputs may limit recommendations. Weather and rain affect care and the water balance; soil readings support the model; dew and leaf wetness affect mowing windows.",noProblem:"No problems detected for the listed inputs.",unknownVolume:"Unknown quantities remain unknown."});
Object.assign(WORDS.de, {dailyWater:"Bewässerung nach Tagen",period:"Zeitraum",exportWater:"Gesamtes Wasserprotokoll als CSV",ledgerNote:"Exportiert alle vorhandenen abgeschlossenen Verbrauchseinträge, üblicherweise bis zu einem Jahr. Fehlende Mengen bleiben leer; Datumsaufteilungen und Unsicherheiten bleiben erhalten. Laufende Sitzungen sind nicht enthalten.",dailyNote:"Erfasste Mengen je lokalem Kalendertag. Kein Eintrag bedeutet keine erfasste Menge, nicht gemessenen Nullverbrauch. ? kennzeichnet unbekannte Mengen oder Messlücken. Datumsaufteilungen können geschätzt sein.",careHints:"Pflegehinweise",abortHints:"Bewässerungsabbrüche",careCooldown:"Mindestabstand · Pflege",abortCooldown:"Mindestabstand · Abbrüche",unclassified:"Unklare Messgrundlage",measuredLegend:"Gemessen",estimatedLegend:"Ventil-Schätzung",manualLegend:"Manuell erfasst",manualEstimateLegend:"Manuelle Schätzung",uncertainLegend:"Unklar",affected:"Betroffene Empfehlungen",sensorClock:"Alter / zulässiges Alter"});
Object.assign(WORDS.en, {dailyWater:"Irrigation by day",period:"Period",exportWater:"Export complete water ledger as CSV",ledgerNote:"Exports all available completed consumption records, usually up to one year. Unknown amounts stay empty; date allocations and uncertainty are preserved. Active sessions are excluded.",dailyNote:"Recorded quantities per local calendar date. No record means no recorded amount, not measured zero consumption. ? marks unknown amounts or measurement gaps. Date allocations may be estimated.",careHints:"Care hints",abortHints:"Irrigation interruptions",careCooldown:"Minimum interval · care",abortCooldown:"Minimum interval · interruptions",unclassified:"Uncertain evidence",measuredLegend:"Measured",estimatedLegend:"Valve estimate",manualLegend:"Manual record",manualEstimateLegend:"Manual estimate",uncertainLegend:"Uncertain",affected:"Affected recommendations",sensorClock:"Age / maximum age"});

export class LawnCareDashboard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._lawns = []; this._view = "overview"; this._entry = "";
    this._draft = {}; this._history = null; this._historyError = false;
    this._panelData = null; this._detailsContext = ""; this._preferencesLoaded = false;
    this._dataRefreshTimer = null;
    this._routeChanged = () => { this.restoreRoute(); this.scheduleRender(); };
    this._busy = false; this._loading = false; this._message = null;
  }

  // HA supplies an updated hass object for live state changes. No polling loop.
  set hass(value) {
    const previous = this._hass;
    this._hass = value;
    if (!this._preferencesLoaded && value.user?.id) { this._preferencesLoaded = true; this.restoreRoute(); }
    const entities = Object.values(this.lawn?.entities || {});
    if (!this._loaded && !this._loading && this.isConnected) this.loadLawns();
    if (!previous || previous.connection !== value.connection || previous.connected !== value.connected || previous.language !== value.language || entities.some(id => previous.states[id] !== value.states[id])) this.scheduleRender();
    if ((previous?.connection !== value.connection || previous?.connected !== value.connected) && this._loaded) {
      this._lawnToken = null; this._loading = false;
      this._dataToken = null; this._historyToken = null;
      if (value.connected !== false && this.isConnected) this.loadLawns();
    }
    else if (previous && this._loaded && entities.some(id => previous.states[id] !== value.states[id])) this.queuePanelData();
  }
  get hass() { return this._hass; }
  connectedCallback() { window.addEventListener("hashchange",this._routeChanged); window.addEventListener("popstate",this._routeChanged); if (this._hass) this.loadLawns(); this.scheduleRender(); }
  disconnectedCallback() { window.removeEventListener("hashchange",this._routeChanged); window.removeEventListener("popstate",this._routeChanged); this._historyToken = null; this._dataToken = null; this._lawnToken = null; this._loading = false; clearTimeout(this._dataRefreshTimer); this._dataRefreshTimer = null; cancelAnimationFrame(this._frame); this._frame = null; }
  queuePanelData() {
    // Coalesce HA update bursts without periodic polling. One follow-up is
    // enough to pick up care records/model observations written externally.
    if (!this.isConnected || this._dataRefreshTimer || this._hass?.connected === false) return;
    this._dataRefreshTimer = setTimeout(() => { this._dataRefreshTimer = null; if (this.isConnected) this.loadPanelData(true); }, 350);
  }
  get lawn() { return this._lawns.find(l => l.entry_id === this._entry); }
  get lang() { return (this._hass?.language || this._hass?.locale?.language || "de").toLowerCase().startsWith("de") ? "de" : "en"; }
  t(key) { return WORDS[this.lang][key] || key; }
  state(key) { return this._hass?.states?.[this.lawn?.entities?.[key]]; }
  attrs(key) { return this.state(key)?.attributes || {}; }
  text(key) {
    const state = this.state(key);
    if (!state || missing(state.state)) return this.t("unknown");
    if (this._hass.formatEntityState) return this._hass.formatEntityState(state);
    return WORDS[this.lang][state.state] || state.state;
  }
  num(value, unit="") {
    if (!finite(value)) return "—";
    const amount = Number(value), digits = unit === "L/m²" ? 3 : ["kg","L","mm"].includes(unit) ? 2 : 1;
    // Do not display a real nonzero amount as zero. Scientific notation only
    // covers values smaller than the usual unit precision, without padding
    // larger estimates with meaningless trailing zeros.
    const tiny = amount !== 0 && Math.abs(amount) < 10 ** -digits;
    return `${new Intl.NumberFormat(this.lang,{maximumFractionDigits:digits,...(tiny ? {notation:"scientific"} : {})}).format(amount)}${unit ? " " + unit : ""}`;
  }
  date(value) {
    if (!value) return "—";
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const date = new Date(dateOnly ? `${value}T12:00:00Z` : value);
    if (!Number.isFinite(date.getTime())) return "—";
    if (dateOnly) return new Intl.DateTimeFormat(this.lang,{day:"2-digit",month:"2-digit",year:"numeric",timeZone:"UTC"}).format(date);
    return new Intl.DateTimeFormat(this.lang, {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",timeZone:this._hass?.config?.time_zone || undefined}).format(date);
  }
  scheduleRender() {
    if (!this.isConnected || this._frame) return;
    this._frame = requestAnimationFrame(() => { this._frame = null; this.render(); });
  }

  // Remember only view and lawn identity, scoped to the signed-in HA user.
  // URL fragments are validated and never become selectors, markup or actions.
  preferenceKey() { return `rasenpflege_assistent:view:${this._hass?.user?.id || "anonymous"}`; }
  restoreRoute() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(this.preferenceKey()) || "{}"); } catch (_) { /* Storage may be blocked by the browser. */ }
    const route = new URLSearchParams(window.location.hash.slice(1));
    const view = route.get("view") || saved?.view;
    const entry = route.get("lawn") || saved?.lawn;
    if (VIEWS.includes(view)) this._view = view;
    if (typeof entry === "string" && entry.length <= 128 && !this._busy) {
      if (!this._loaded) this._entry = entry;
      else if (this._lawns.some(lawn => lawn.entry_id === entry) && entry !== this._entry) this.selectLawn(entry);
    }
  }
  saveRoute() {
    const value = {view:this._view,lawn:this._entry};
    try { localStorage.setItem(this.preferenceKey(),JSON.stringify(value)); } catch (_) { /* Optional preference only. */ }
    const route = new URLSearchParams(value);
    window.history.replaceState(window.history.state,"",`${window.location.pathname}${window.location.search}#${route}`);
  }
  selectLawn(entry) {
    this._entry = entry; this._draft = {}; this._message = null;
    this.saveRoute(); this.loadHistory(); this.loadPanelData(); this.scheduleRender();
  }
  async loadPanelData(preserve=false) {
    const token = {}; this._dataToken = token; if (!preserve) this._panelData = null; this._dataError = false;
    if (!this.lawn) return;
    try {
      const result = await this._hass.callWS({type:"rasenpflege_assistent/dashboard_data",config_entry_id:this._entry});
      if (token !== this._dataToken) return;
      this._panelData = result;
    } catch (_) { if (token === this._dataToken) { this._dataError = true; this._panelData = null; } }
    this.scheduleRender();
  }
  qualityCard() {
    const quality = this.attrs("data_quality"), soil = this.attrs("soil_moisture");
    return this.card(this.t("quality"),"mdi:database-check",this.tag(this.text("data_quality"),this.state("data_quality")?.state === "good" ? "" : "orange"),this.row(this.t("updated"),this.date(this.state("last_calculation")?.state)),this.row(this.t("weatherAge"),this.num(quality.weather_age_minutes,"min")),this.row(this.t("forecastAge"),this.num(quality.forecast_age_minutes,"min")),this.row(this.t("confidence"),this.text("soil_model_confidence")),this.row(this.t("watering"),this.text("watering_confidence")),this.notes(soil.model_insights?.soil_evidence?.basis_text),el("div","hint",this.t("modelNote")));
  }
  inputAdvice(key) {
    // Describe the particular input's effect without changing controller
    // policy or assuming that a missing optional sensor blocks all care.
    const rules = this.lang === "de" ? {
      soil_moisture_entity:["Bodenmodell und Bewässerung","Feuchtesensor und dessen Einheit prüfen; ohne gültigen Wert bleibt die Berechnung modellbasiert."],
      soil_temperature_entity:["Wachstums- und Pflegebewertung","Bodentemperaturquelle und Einheit prüfen; die Integration verwendet ihre vorhandenen Ersatzwerte."],
      leaf_wetness_entity:["Tauprüfung und Mähfenster","Blattnässesensor muss gültige Ein-/Aus-Zustände liefern; trockenes Gras wird ohne Messung nicht bestätigt."],
      weather_entity:["Pflegefenster, Regen und Wasserbilanz","Wetterintegration und Prognosebereitstellung prüfen; bestehende HA-Daten werden genutzt."],
      temperature_entity:["Frostprüfung, Wachstum und Pflege","Außentemperaturquelle und Einheit prüfen; verfügbare Ersatzwerte stammen aus den vorhandenen Wetterdaten."],
      precipitation_entity:["Regenbilanz und Nassrasenschutz","Regenquelle, Mengeneinheit und Aktualisierung prüfen; fehlender Regenwert bedeutet nicht keinen Regen."],
      irrigation_flow:["Dosierung und Bewässerungssicherheit","Durchflussquelle, Rate/Zählerart und Einheit prüfen. Fehlerhafte Messwerte können Start oder Fortsetzung verhindern."],
      irrigation_valve:["Bewässerungssteuerung","Ventilzustand und Erreichbarkeit prüfen. Ein unbekannter Zustand bestätigt kein geschlossenes Ventil."],
      other_valve:["Gemeinsame Durchflussmessung","Zustand des zweiten Ventils prüfen. Es wird ausschließlich gelesen und niemals von dieser Integration gesteuert."],
      mower_location:["Mähbeobachtung und Bewässerungsfreigabe","Mäherstatusquelle und Statuszuordnung prüfen. Fehlende Beobachtung bestätigt keinen abgeschlossenen Mähvorgang."],
    } : {
      soil_moisture_entity:["Soil model and watering","Check the moisture sensor and unit; without a valid reading calculations remain model-based."],
      soil_temperature_entity:["Growth and care assessment","Check the soil temperature source and unit; existing fallback values remain in use."],
      leaf_wetness_entity:["Dew assessment and mowing windows","The leaf-wetness sensor must report valid on/off states; missing readings do not confirm dry grass."],
      weather_entity:["Care windows, rainfall and water balance","Check weather integration and forecast availability; existing HA data is reused."],
      temperature_entity:["Frost assessment, growth and care","Check the outdoor temperature source and unit; available fallbacks use existing weather data."],
      precipitation_entity:["Rain balance and wet-lawn protection","Check rain source, quantity unit and freshness; missing rainfall does not mean no rain."],
      irrigation_flow:["Dosing and irrigation safety","Check flow source, rate/counter type and unit. Invalid measurements can prevent starting or continuing irrigation."],
      irrigation_valve:["Irrigation control","Check valve state and availability. An unknown state does not confirm a closed valve."],
      other_valve:["Shared flow measurement","Check the second valve state. It is read only and is never controlled by this integration."],
      mower_location:["Mower observations and irrigation permission","Check mower status source and mappings. Missing observations do not confirm completed mowing."],
    };
    return rules[key] || [this.t("impact"),this.t("missingHint")];
  }
  inputProblems() {
    const inputs = this.attrs("data_quality").input_diagnostics || {};
    const problems = Object.entries(inputs).filter(([,value]) => value && !["accepted","not_configured"].includes(value.reason));
    const names = {soil_moisture_entity:this.t("soil"),soil_temperature_entity:this.lang === "de" ? "Bodentemperatur" : "Soil temperature",leaf_wetness_entity:this.lang === "de" ? "Blattnässe" : "Leaf wetness",weather_entity:this.t("forecast"),temperature_entity:this.lang === "de" ? "Außentemperatur" : "Outdoor temperature",precipitation_entity:this.t("rain"),irrigation_flow:this.t("actualFlow"),irrigation_valve:this.lang === "de" ? "Ventil" : "Valve",other_valve:this.lang === "de" ? "Zweites Ventil" : "Second valve"};
    return this.card(this.t("sensorProblem"),"mdi:alert-circle-outline",
      ...problems.map(([key,value]) => el("div","notes",this.row(names[key] || key,this.t(value.reason)),this.row(this.t("sensorClock"),`${this.num(value.age_minutes,"min")} / ${this.num(value.maximum_age_minutes,"min")}`),this.row(this.t("affected"),this.inputAdvice(key)[0]),el("div","",this.t(value.reason === "stale" ? "staleHint" : "missingHint")),this.notes(this.inputAdvice(key)[1]))),
      this.notes(problems.length ? this.t("impact") : this.t("noProblem")));
  }
  whyCard() {
    const care = this.attrs("care_plan"), mowing = this.attrs("mower_status"), watering = this.attrs("watering_recommendation");
    return this.card(this.t("why"),"mdi:help-circle-outline",
      this.row(this.t("mowing"),care.mowing?.status_text || this.text("mower_status")),
      this.notes([care.mowing?.reason_text,mowing.mowing_window?.reason_text,mowing.mowing_window?.current_dew_risk_text]),
      this.row(this.t("watering"),care.watering?.status_text || this.text("watering_recommendation")),
      this.notes([watering.reason_text,care.watering?.blocker_text,...(watering.reasons_text || [])]),
      this.row(this.t("fertilizing"),care.fertilizing?.status_text || "—"),
      this.notes(care.fertilizing?.reasons_text));
  }
  possibleCard() {
    const care = this.attrs("care_plan"), steps = care.outlook?.steps || [];
    return this.card(this.t("possible"),"mdi:calendar-clock",
      ...["mow_lawn","water_lawn","fertilize_lawn"].map(action => {
        const step = steps.find(row => row.action === action || action === "water_lawn" && row.action === "prepare_watering");
        return el("div","",this.row(step?.action_text || this.t({mow_lawn:"mowing",water_lawn:"watering",fertilize_lawn:"fertilizing"}[action]),this.date(step?.candidate_at || step?.not_before)),this.notes([step?.outlook_reason_text,step?.dependency_text]));
      }),this.notes([this.t("conditional"),care.outlook?.scope_text]));
  }
  consumptionCard() {
    const totals = this._panelData?.consumption || this.attrs("water_consumption_day"), area = this._panelData?.area_m2;
    return this.card(this.t("consumption"),"mdi:water-check",
      ...[["week","week"],["month","month"]].map(([prefix,label]) => el("div","",
        this.row(this.t(label),this.num(totals[prefix+"_liters"],"L")),
        this.row(this.t("perArea"),finite(area) && Number(area) > 0 && finite(totals[prefix+"_liters"]) ? this.num(Number(totals[prefix+"_liters"])/Number(area),"L/m²") : "—"),
        this.row(this.t("physical"),this.num(totals[prefix+"_irrigation_liters"],"L")),
        this.row(this.t("measuredWater"),this.num(totals[prefix+"_measured_liters"],"L")),
        this.row(this.t("flowEstimatedWater"),this.num(totals[prefix+"_estimated_liters"],"L")),
        this.row(this.t("uncertainWater"),this.num(totals[prefix+"_uncertain_liters"],"L")),
        this.row(this.t("manualWater"),this.num(totals[prefix+"_manual_record_liters"],"L")),
        this.row(this.t("estimatedWater"),this.num(totals[prefix+"_manual_estimate_liters"],"L")),
        this.row(this.t("gaps"),`${this.num(totals[prefix+"_measurement_gap_sessions"])} / ${this.num(totals[prefix+"_unmetered_sessions"])}`))),
      this.notes([this.t("volumeNote"),this.t("unknownVolume")]));
  }
  dailyWaterCard() {
    const days = Number(this._draft.water_days || 7), rows = (this._panelData?.daily_consumption || []).slice(-days);
    const selector = this.choose("water_days",this.t("period"),[["7","7 "+this.t("days")],["30","30 "+this.t("days")]],"7"); selector.querySelector("select").disabled = false;
    const records = this._panelData?.water_records || [];
    const download = el("button","action",this.t("exportWater")); download.type = "button"; download.disabled = !records.length || this._dataError;
    download.addEventListener("click",() => this.downloadCsv(waterCsv(records),"lawn-water-ledger.csv"));
    const card = this.card(this.t("dailyWater"),"mdi:chart-bar",el("div","form",selector,download),this.dailyWaterPlot(rows),this.notes([this.t("dailyNote"),this.t("ledgerNote")]));
    const table = el("details","",el("summary","",this.t("details")));
    for (const row of rows) table.append(this.row(this.date(row.date),`${this.num(row.liters,"L")}${row.unknown_sessions || row.gap_sessions ? " · ?" : ""}${row.allocation_estimated_sessions ? " · "+this.t("partial") : ""}`));
    card.append(table); card.classList.add("span3"); return card;
  }
  dailyWaterPlot(rows) {
    if (!rows.length) return this.notes(this._dataError ? this.t("journalError") : this.t("loading"));
    const kinds = [["measured","#23684b","measuredLegend"],["estimated","#7196b3","estimatedLegend"],["manual_record","#ada34f","manualLegend"],["manual_estimate","#c08055","manualEstimateLegend"],["uncertain","#8a7d90","uncertainLegend"]];
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns,"svg");
    svg.setAttribute("viewBox","0 0 600 130"); svg.setAttribute("class","spark"); svg.setAttribute("role","img"); svg.setAttribute("aria-label",this.t("dailyWater"));
    const peak = Math.max(1,...rows.map(row => finite(row.liters) ? Number(row.liters) : 0)), width = 600/rows.length;
    rows.forEach((row,index) => {
      let used = 0;
      for (const [kind,color] of kinds) {
        const value = finite(row[kind]) ? Math.max(0,Number(row[kind])) : 0;
        if (!value) continue;
        const rect = document.createElementNS(ns,"rect"); const height = value/peak*95;
        rect.setAttribute("x",index*width+width*.15); rect.setAttribute("width",width*.7); rect.setAttribute("y",110-used-height); rect.setAttribute("height",height); rect.setAttribute("fill",color);
        const title = document.createElementNS(ns,"title"); title.textContent = `${this.date(row.date)} · ${this.num(value,"L")}`; rect.append(title); svg.append(rect); used += height;
      }
      if (row.unknown_sessions || row.gap_sessions) {
        const mark = document.createElementNS(ns,"text"); mark.textContent = "?"; mark.setAttribute("x",(index+.5)*width); mark.setAttribute("y",Math.max(12,105-used)); mark.setAttribute("text-anchor","middle"); mark.setAttribute("fill","currentColor"); svg.append(mark);
      }
    });
    const legend = el("div","form",kinds.map(([,color,label]) => { const item = el("span","hint",this.t(label)); item.style.borderLeft = "8px solid "+color; item.style.paddingLeft = "5px"; return item; }));
    return el("div","",this.row("L",`0–${this.num(peak,"L")}`),svg,el("div","chart-labels",el("span","",this.date(rows[0].date)),el("span","",this.date(rows.at(-1).date))),legend);
  }
  exportJournal(rows) {
    this.downloadCsv(careCsv(rows),"lawn-care-log.csv");
  }
  downloadCsv(content,filename) {
    const blob = new Blob([content],{type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  choose(name, label, options, defaultValue) {
    const select = el("select"); select.name = name;
    for (const [value,text] of options) { const option = el("option","",text); option.value = value; select.append(option); }
    select.value = this._draft[name] ?? String(defaultValue);
    select.disabled = this._busy || !this._canControl;
    select.addEventListener("change",() => { this._draft[name] = select.value; this.scheduleRender(); });
    return el("label","field",label,select);
  }
  targetForm(recommendation) {
    const liters = this._draft.target_unit === "L", name = liters ? "target_liters" : "target_mm";
    const area = this._panelData?.area_m2;
    const max = liters ? Math.min(50000,finite(area) ? Number(area)*50 : 50000) : 50;
    return el("div","form",this.choose("target_unit",this.t("unit"),[["mm","mm"],["L","L"]],"mm"),this.field(name,`${this.t("amount")} · ${liters ? "L" : "mm"} (0.1–${max})`,liters ? recommendation.recommended_liters : recommendation.recommended_mm,.1,max),this.button(this.t("start"),"start_irrigation",() => { const amount = this.amount(name,.1,max); return amount == null ? null : {[name]:amount}; },"primary","confirmStart"));
  }

  // Draw saved observations rather than requesting additional weather data.
  // Each source has its own scale/unit. Explicit missing values, source changes
  // and gaps longer than an hour break the line; no missing zero is fabricated.
  plot(rows, key, label, unit, maximum=null, bars=false) {
    const now = Date.now(), start = now-7*86400000, ns = "http://www.w3.org/2000/svg";
    const points = rows.map(row => ({time:new Date(key === "measured_percent" && finite(row[key]) ? row.sensor_reported_at || row.timestamp : row.timestamp).getTime(),value:key === "rain_mm" && !row.rain_known ? null : row[key],break:row.context_changed})).filter(row => Number.isFinite(row.time) && row.time >= start && row.time <= now);
    const valid = points.filter(row => finite(row.value));
    if (!valid.length) return el("div","hint",this.t("noSamples"));
    const peak = maximum ?? Math.max(1,...valid.map(row => Number(row.value)));
    const svg = document.createElementNS(ns,"svg"); svg.setAttribute("viewBox","0 0 600 110"); svg.setAttribute("class","spark"); svg.setAttribute("role","img"); svg.setAttribute("aria-label",`${label} (${unit})`);
    let segment = [], last = null;
    const draw = () => {
      if (!segment.length) return;
      const shape = document.createElementNS(ns,segment.length > 1 ? "polyline" : "circle");
      if (segment.length > 1) { shape.setAttribute("points",segment.join(" ")); shape.setAttribute("fill","none"); shape.setAttribute("stroke","#669b76"); shape.setAttribute("stroke-width","2.5"); }
      else { const [x,y] = segment[0].split(","); shape.setAttribute("cx",x); shape.setAttribute("cy",y); shape.setAttribute("r","3"); shape.setAttribute("fill","#669b76"); }
      svg.append(shape); segment = [];
    };
    for (const point of points) {
      if (point.break || last != null && point.time-last > 3600000) draw();
      last = point.time;
      if (!finite(point.value)) { draw(); continue; }
      const x = (point.time-start)/(now-start)*600, y = 100-Math.max(0,Math.min(peak,Number(point.value)))/peak*90;
      if (bars) {
        const rect = document.createElementNS(ns,"rect"); rect.setAttribute("x",Math.max(0,x-2)); rect.setAttribute("y",y); rect.setAttribute("width","4"); rect.setAttribute("height",100-y); rect.setAttribute("fill","#669b76");
        const title = document.createElementNS(ns,"title"); title.textContent = `${this.date(new Date(point.time).toISOString())}: ${this.num(point.value,unit)}`; rect.append(title); svg.append(rect);
      } else segment.push(`${x},${y}`);
    }
    draw();
    return el("div","",this.row(label,`0–${this.num(peak,unit)}`),svg,el("div","chart-labels",el("span","",this.date(new Date(start).toISOString())),el("span","",this.date(new Date(now).toISOString()))));
  }
  trends() {
    const rows = this._panelData?.observations || [];
    const soil = this.card(this.t("soil"),"mdi:chart-timeline-variant",this.plot(rows,"modeled_percent",this.t("modeled"),"%",100),this.plot(rows,"measured_percent",this.t("measured"),"%",100),this.notes(this.t("trendNote"))); soil.classList.add("span2");
    const rain = this.card(this.t("rain"),"mdi:weather-rainy",this.plot(rows,"rain_mm",this.t("rain"),"mm",null,true),this.notes(this.t("trendNote")));
    const records = this.attrs("water_consumption_day").recent_records || [];
    const irrigation = this.card(this.t("waterEvents"),"mdi:sprinkler",this.plot(records.map(row => ({timestamp:row.recorded_at || row.date,liters:row.undone ? null : row.liters})),"liters",this.t("recorded"),"L",null,true),...records.slice(0,10).map(row => this.row(this.date(row.recorded_at || row.date),`${this.num(row.liters,"L")} · ${row.source_text || "—"}${row.measurement_gap || row.allocation_estimated ? ` · ${this.t("partial")}` : ""}`)));
    const cards = [this.dailyWaterCard(),soil,rain,irrigation,this.consumptionCard(),this.qualityCard()];
    if (this._dataError) cards.unshift(this.card(this.t("journal"),"mdi:alert",this.notes(this.t("journalError"))));
    return cards;
  }
  quietField(name,label,value) {
    const input = el("input"); input.type = "time"; input.name = name; input.value = this._draft[name] ?? value ?? ""; input.disabled = this._busy || !this._canControl;
    input.addEventListener("input",() => { this._draft[name] = input.value; });
    return el("label","field",label,input);
  }
  optionalText(name, label, type="text") {
    const input = el("input","wide"); input.name = name; input.type = type; if (type === "datetime-local") input.step = "1"; input.value = this._draft[name] || ""; input.disabled = this._busy || !this._canControl;
    if (type === "text") input.maxLength = 80;
    input.addEventListener("input",() => { this._draft[name] = input.value; });
    return el("label","field",label,input);
  }
  recordPayload() {
    const data = {}, at = this._draft.care_time;
    if (at) {
      const parsed = new Date(at);
      if (!Number.isFinite(parsed.getTime()) || parsed.getTime() > Date.now()) { this._message = {type:"error",text:this.t("validTime")}; this.scheduleRender(); return null; }
      data.recorded_at = parsed.toISOString();
    }
    const kind = this._draft.care_kind || "mowing";
    if (kind === "watering") { const amount = this.amount("care_mm",.1,50); if (amount == null) return null; data.amount_mm = amount; }
    if (kind === "fertilizing") {
      if (this._draft.care_npk) data.product_npk = this._draft.care_npk;
      if (this._draft.care_kg) { const amount = this.amount("care_kg",0,100); if (amount == null) return null; data.amount_kg = amount; }
    }
    return data;
  }
  async undoRecord(record) {
    if (!await this.act("undo_last_manual",{timestamp:record.timestamp},"confirmUndo")) return;
    const details = record.details || {}, at = new Date(details.recorded_at);
    // datetime-local uses this device's timezone; preserve the original instant
    // when pre-filling a replacement instead of treating it as HA local time.
    const local = Number.isFinite(at.getTime()) ? new Date(at.getTime()-at.getTimezoneOffset()*60000).toISOString().slice(0,19) : "";
    this._draft = {...this._draft,care_kind:record.action,care_time:local,care_mm:details.amount_mm == null ? "" : String(details.amount_mm),care_kg:details.amount_kg == null ? "" : String(details.amount_kg),care_npk:details.product_npk || ""};
    this.scheduleRender();
  }
  journal() {
    const filter = this._draft.journal_filter || "all";
    const rows = (this._panelData?.journal || []).filter(row => filter === "all" || row.action === filter);
    const log = this.card(this.t("journal"),"mdi:history",this.notes(this.t("journalNote")));
    log.classList.add("span2");
    // Filters and export remain available to read-only users; they never send
    // a write action, and operate only on server-authorized visible records.
    const selector = this.choose("journal_filter",this.t("filter"),[["all",this.t("all")],["mowing",this.t("mowing")],["watering",this.t("watering")],["fertilizing",this.t("fertilizing")]],"all");
    selector.querySelector("select").disabled = false;
    const download = el("button","action",this.t("export")); download.type = "button"; download.disabled = !rows.length || this._dataError;
    download.addEventListener("click",() => this.exportJournal(rows));
    log.append(el("div","form",selector,download));
    if (this._dataError) log.append(this.notes(this.t("journalError")));
    else if (!this._panelData) log.append(this.notes(this.t("loading")));
    else if (!rows.length) log.append(this.notes(this.t("noJournal")));
    for (const record of rows) {
      const details = record.details || {};
      log.append(this.row(this.t(record.action),this.date(details.recorded_at || record.timestamp)),this.notes([details.source ? this.t(details.source) : this.t("manual"),details.historical ? this.t("historical") : "",details.amount_mm != null ? this.num(details.amount_mm,"mm") : "",details.amount_kg != null ? this.num(details.amount_kg,"kg") : "",details.product_npk]));
      if (record.can_undo) { const button = el("button","action",this.t("undo")); button.disabled = this._busy || !this._canControl || this._hass?.connected === false; button.addEventListener("click",() => this.undoRecord(record)); log.append(el("div","actions",button)); }
    }
    const kind = this._draft.care_kind || "mowing";
    const form = this.card(this.t("recordCare"),"mdi:clipboard-check",this.choose("care_kind",this.t("recordCare"),[["mowing",this.t("mowing")],["watering",this.t("watering")],["fertilizing",this.t("fertilizing")]],"mowing"),this.optionalText("care_time",this.t("careTime"),"datetime-local"));
    if (kind === "watering") form.append(this.field("care_mm",`${this.t("amount")} · mm (0.1–50)`,this.attrs("watering_recommendation").recommended_mm,.1,50));
    if (kind === "fertilizing") form.append(this.optionalText("care_npk",this.t("product")),this.field("care_kg",this.t("kg"),null,0,100,"","0.01"));
    form.append(el("div","actions",this.button(this.t("save"),`record_${kind}`,() => this.recordPayload(),"primary","confirmRecord")));
    const cards = [log,form];
    const preferences = this._panelData?.notifications;
    if (this._canControl && preferences) {
      cards.push(this.notificationCard(preferences));
    }
    return cards;
  }

  notificationCard(preferences) {
    const boolDefault = (key,fallback=true) => preferences[key] == null ? fallback : preferences[key];
    const choices = [["off",this.t("off")],["on",this.t("on")]];
    const hours = [1,6,24].map(value => [String(value),value+" "+this.t("hours")]);
    const card = this.card(this.t("notifications"),"mdi:bell-outline",this.notes(this.t("notifyNote")));
    card.append(el("div","form",
      this.choose("notify_enabled",this.t("status"),choices,preferences.enabled ? "on" : "off"),
      this.choose("notify_care",this.t("careHints"),choices,boolDefault("care_enabled") ? "on" : "off"),
      this.choose("notify_interval",this.t("careCooldown"),hours,preferences.care_interval_hours ?? preferences.interval_hours),
      this.choose("notify_irrigation",this.t("abortHints"),choices,boolDefault("irrigation_enabled") ? "on" : "off"),
      this.choose("notify_irrigation_interval",this.t("abortCooldown"),hours,preferences.irrigation_interval_hours ?? preferences.interval_hours),
      this.choose("notify_changes",this.t("changesOnly"),[["off",this.t("no")],["on",this.t("yes")]],preferences.changes_only ? "on" : "off"),
      this.quietField("notify_start",this.t("quietStart"),preferences.quiet_start),
      this.quietField("notify_end",this.t("quietEnd"),preferences.quiet_end),
      this.notes(this.t("quietNote")),
      this.button(this.t("save"),"notification_settings",() => ({
        enabled:(this._draft.notify_enabled ?? (preferences.enabled ? "on" : "off")) === "on",
        interval_hours:Number(this._draft.notify_interval ?? preferences.care_interval_hours ?? preferences.interval_hours),
        care_enabled:(this._draft.notify_care ?? (boolDefault("care_enabled") ? "on" : "off")) === "on",
        irrigation_enabled:(this._draft.notify_irrigation ?? (boolDefault("irrigation_enabled") ? "on" : "off")) === "on",
        care_interval_hours:Number(this._draft.notify_interval ?? preferences.care_interval_hours ?? preferences.interval_hours),
        irrigation_interval_hours:Number(this._draft.notify_irrigation_interval ?? preferences.irrigation_interval_hours ?? preferences.interval_hours),
        changes_only:(this._draft.notify_changes ?? (preferences.changes_only ? "on" : "off")) === "on",
        quiet_start:this._draft.notify_start ?? preferences.quiet_start ?? "",
        quiet_end:this._draft.notify_end ?? preferences.quiet_end ?? "",
      }))));
    return card;
  }

  async loadLawns() {
    if (!this._hass || this._loading) return;
    const token = {}; this._lawnToken = token;
    this._loading = true; this.scheduleRender();
    try {
      const result = await this._hass.callWS({type:"rasenpflege_assistent/dashboard"});
      if (token !== this._lawnToken) return;
      this._lawns = result.lawns || []; this._canControl = result.can_control; this._version = result.version;
      const previousEntry = this._entry;
      this._entry = this._lawns.some(l => l.entry_id === this._entry) ? this._entry : this._lawns[0]?.entry_id || "";
      this._loaded = true; this._message = null; this._history = null; this._historyToken = null;
      if (previousEntry !== this._entry) this._draft = {};
      this.saveRoute(); this.loadHistory(); this.loadPanelData();
    } catch (error) { if (token === this._lawnToken) { this._loaded = true; this._message = {type:"error",text:this.t("refreshError") + " " + (error.message || "")}; } }
    finally { if (token === this._lawnToken) { this._loading = false; this.scheduleRender(); } }
  }

  // Recorder history is fetched on lawn selection/explicit refresh only. Use
  // full states to retain unknown/unavailable gaps instead of fabricating data.
  async loadHistory() {
    // Invalidate BEFORE the no-entity return. Object identity also distinguishes
    // two requests created in the same millisecond for the same lawn.
    const token = {}; this._historyToken = token; this._historyError = false;
    this._history = null;
    const entity = this.lawn?.entities?.soil_moisture;
    if (!entity) { this.scheduleRender(); return; }
    const end = new Date(), start = new Date(end.getTime() - 7 * 86400000);
    try {
      const data = await this._hass.callApi("GET", `history/period/${start.toISOString()}?filter_entity_id=${encodeURIComponent(entity)}&end_time=${end.toISOString()}&significant_changes_only=0`);
      if (this._historyToken !== token) return;
      this._history = data[0] || [];
    } catch (_) { if (this._historyToken === token) { this._history = []; this._historyError = true; } }
    this.scheduleRender();
  }

  card(title, symbol, ...content) { return el("section","card",el("div","card-top",el("div","card-title",title),icon(symbol)),content); }
  row(label, value) { return el("div","row",el("div","row-label",label),el("div","row-value",missing(value) ? "—" : value)); }
  notes(values) { return el("div","notes",(Array.isArray(values) ? values : [values]).filter(Boolean).map(value => el("div","",value))); }
  tag(text, tone="") { return el("span",`tag ${tone}`,text); }
  detail(attrs) {
    const node = el("details","",el("summary","",this.t("details")),el("pre","",JSON.stringify(attrs,null,2)));
    return node;
  }
  button(label, action, data={}, cls="", confirmation="") {
    const button = el("button",`action ${cls}`,label);
    button.type = "button"; button.disabled = this._busy || !this._canControl || this._hass?.connected === false;
    button.addEventListener("click", () => this.act(action, typeof data === "function" ? data() : data, confirmation));
    return button;
  }
  field(name, label, value, min, max, cls="", step="0.1") {
    const input = el("input",cls); input.type = "number"; input.name = name;
    input.min = String(min); input.max = String(max); input.step = step;
    input.value = this._draft[name] ?? (finite(value) && Number(value) >= min ? String(value) : "");
    input.disabled = this._busy || !this._canControl;
    input.addEventListener("input", () => { this._draft[name] = input.value; });
    return el("label","field",label,input);
  }
  amount(name, min, max) {
    const input = this.shadowRoot.querySelector(`input[name="${name}"]`);
    if (!input || !input.checkValidity() || input.value === "" || !finite(input.value) || Number(input.value) < min || Number(input.value) > max) {
      this._message = {type:"error",text:this.t("validAmount")}; this.scheduleRender(); return null;
    }
    return Number(input.value);
  }
  async act(action, data, confirmation) {
    if (data === null || !this._canControl || this._busy || !this.lawn) return;
    if (confirmation && !window.confirm(`${this.lawn.name}\n\n${this.t(confirmation)}`)) return;
    // Freeze the selected lawn for the whole request; switching controls is
    // disabled until the server acknowledges the action or reports an error.
    const entry = this._entry;
    this._busy = true; this._message = {type:"",text:this.t("busy")}; this.scheduleRender();
    try {
      await this._hass.callWS({type:"rasenpflege_assistent/dashboard_action",config_entry_id:entry,action,data});
      this._message = {type:"success",text:this.t("done")};
      this.loadPanelData();
      return true;
    } catch (error) { this._message = {type:"error",text:`${this.t("failed")}: ${error.message || error.code || "—"}`};
      return false; }
    finally { this._busy = false; this.scheduleRender(); }
  }

  overview() {
    const soil = this.attrs("soil_moisture"), plan = this.attrs("care_plan"), summary = plan.summary || {};
    const hero = this.card(this.t("next"),"mdi:grass",this.tag(this.text("status"), this.attrs("status").icon_color === "red" ? "red" : ""),el("div","value",summary.action_text || this.text("next_action")),this.notes([summary.availability_text,summary.blocker_text || summary.reason_text]),this.row(this.t("earliest"),this.date(summary.not_before)));
    hero.classList.add("span2","hero");
    const moisture = this.card(this.t("soil"),"mdi:water-percent",el("div","value",this.num(this.state("soil_moisture")?.state,"%")),this.meter(this.state("soil_moisture")?.state),el("div","hint",this.t("modeled")),this.notes((soil.model_insights?.soil_evidence || {}).basis_text));
    const growth = this.card(this.t("growth"),"mdi:sprout",el("div","value compact",this.text("growth_status")),this.row("GTS",this.text("gts")),this.row(this.t("mower"),this.text("mower_status")));
    const rain = this.card(this.t("forecast"),"mdi:weather-partly-rainy",this.row(this.t("rain24"),this.text("forecast_rain_24h")),this.row(this.t("rain72"),this.text("forecast_rain_72h")),this.row(this.t("quality"),this.text("data_quality")));
    const use = this.card(this.t("recorded"),"mdi:water-check",el("div","value",this.text("water_consumption_day")),this.row(this.t("week"),this.text("water_consumption_week")),this.row(this.t("month"),this.text("water_consumption_month")));
    const history = this.card(this.t("history"),"mdi:chart-timeline-variant",this.chart(),el("div","hint",this.t("historyNote"))); history.classList.add("span2");
    const health = this.qualityCard();
    const daily = this.card(this.t("dayPlan"),"mdi:calendar-today",this.steps(plan.prioritized_steps),this.notes(plan.outlook?.scope_text)); daily.classList.add("span3");
    return [hero,moisture,growth,rain,use,history,health,daily,this.whyCard(),this.possibleCard(),this.inputProblems()];
  }
  meter(value) {
    const bar = el("div","meter"), fill = el("div","meter-fill");
    fill.style.width = finite(value) ? `${Math.max(0,Math.min(100,Number(value)))}%` : "0%";
    bar.append(fill); return bar;
  }
  chart() {
    if (!this._history?.length) return el("div","hint",this._historyError ? this.t("historyError") : this.t("historyEmpty"));
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns,"svg");
    svg.setAttribute("viewBox","0 0 600 110"); svg.setAttribute("class","spark"); svg.setAttribute("role","img"); svg.setAttribute("aria-label",this.t("history"));
    const samples = this._history.map(row => ({v:finite(row.state) ? Number(row.state) : null,t:new Date(row.last_changed || row.last_updated).getTime()})).filter(p => Number.isFinite(p.t));
    const start = Date.now()-7*86400000, span = 7*86400000;
    let segment = [];
    const draw = () => {
      if (!segment.length) return;
      const shape = document.createElementNS(ns,segment.length > 1 ? "polyline" : "circle");
      if (segment.length > 1) { shape.setAttribute("points",segment.join(" ")); shape.setAttribute("fill","none"); shape.setAttribute("stroke","#669b76"); shape.setAttribute("stroke-width","2.5"); }
      else { const [x,y] = segment[0].split(","); shape.setAttribute("cx",x); shape.setAttribute("cy",y); shape.setAttribute("r","3"); shape.setAttribute("fill","#669b76"); }
      svg.append(shape); segment = [];
    };
    for (const p of samples) { if (p.v == null) { draw(); continue; } segment.push(`${Math.max(0,Math.min(600,(p.t-start)/span*600))},${100-Math.max(0,Math.min(100,p.v))*.9}`); }
    draw();
    return el("div","",svg,el("div","chart-labels",el("span","",this.date(new Date(start).toISOString())),el("span","",this.date(new Date().toISOString()))));
  }
  steps(items, outlook=false) {
    if (!items?.length) return el("div","hint",this.t("noSteps"));
    return el("div","steps",items.map((step,i) => el("div","step",el("div","step-num",i+1),el("div","",el("div","step-title",step.action_text || "—"),el("div","step-text",step.availability_text || step.outlook_reason_text || ""),el("div","step-text",step.blocker_text || step.reason_text || step.window_reason_text || ""),this.row(this.t("earliest"),this.date(step.not_before)),...(outlook ? [this.row(this.t("candidate"),this.date(step.candidate_at)),this.row(this.t("dependency"),step.dependency_text)] : [])))));
  }
  plan() {
    const attrs = this.attrs("care_plan"), fertilizer = attrs.fertilizing || {}, status = this.attrs("status");
    const priorities = this.card(this.t("priority"),"mdi:format-list-numbered",this.steps(attrs.prioritized_steps)); priorities.classList.add("span2");
    const dose = this.card(this.t("fertilizer"),"mdi:flower",el("div","value compact",fertilizer.status_text || "—"),this.row(this.t("window"),fertilizer.window),this.row(this.t("npk"),status.npk),this.row(this.t("dose"),this.num(status.dose_g_m2,"g/m²")),this.row(this.t("total"),this.num(fertilizer.recommended_kg,"kg")),this.notes(fertilizer.reasons_text),el("div","actions",this.button(this.t("recordFert"),"record_fertilizing",{},"","confirmRecord")));
    const outlook = this.card(this.t("outlook"),"mdi:calendar-clock",this.steps(attrs.outlook?.steps,true),this.notes(attrs.outlook?.scope_text)); outlook.classList.add("span3");
    return [priorities,dose,outlook,this.whyCard(),this.possibleCard()];
  }
  mowing() {
    const attrs = this.attrs("mower_status"), p = attrs.mowing_window || {}, alt = p.alternative || {}, suggestion = p.duration_suggestion || {};
    const main = this.card(this.t("mower"),"mdi:robot-mower",el("div","value compact",this.text("mower_status")),this.notes(attrs.recommendation_reason_text),this.row(this.t("last"),this.date(attrs.last_mowing_at || attrs.last_mowing)),this.row(this.t("nextMow"),this.date(attrs.next_mowing_at)),this.row(this.t("interval"),this.num(attrs.mowing_interval_days,this.t("days"))),this.row(this.t("wetUntil"),this.date(attrs.wet_until)),el("div","actions",this.button(this.t("recordMow"),"record_mowing",{},"","confirmRecord")),el("div","readonly",this.t("recordNote"))); 
    const window = this.card(this.t("window"),"mdi:weather-fog",el("div","value compact",this.date(p.start)),this.row(this.t("finish"),this.date(p.end)),this.notes([p.current_dew_risk_text,p.reason_text,p.quality_text,...(p.quality_reasons_text || [])]),this.row(this.t("duration"),this.num(p.required_minutes,this.t("minutes"))),this.row(this.t("available"),this.num(p.available_minutes,this.t("minutes"))),this.row(this.t("alternative"),this.date(alt.start)),this.notes(p.missing_inputs_text)); window.classList.add("span2");
    const detail = this.card(this.t("diagnostics"),"mdi:chart-box",this.notes([suggestion.reason_text,p.change?.reason_text,...(p.evidence?.blocking_text || []),...(p.evidence?.supporting_unknown_text || [])]),this.detail(attrs)); detail.classList.add("span3");
    return [main,window,detail];
  }
  watering() {
    const recommendation = this.attrs("watering_recommendation"), session = this.attrs("irrigation_status"), configured = this.lawn.irrigation_configured;
    const rec = this.card(this.t("watering"),"mdi:water",el("div","value compact",this.text("watering_recommendation")),this.row(this.t("amount"),this.num(recommendation.recommended_mm,"mm")),this.row(this.t("total"),this.num(recommendation.recommended_liters,"L")),this.notes(recommendation.reason_text),this.detail(recommendation));
    const records = this.card(this.t("recorded"),"mdi:history",this.row(this.t("todayWater"),this.text("water_consumption_day")),this.row(this.t("week"),this.text("water_consumption_week")),this.row(this.t("month"),this.text("water_consumption_month")),this.notes((this.attrs("water_consumption_day").recent_records || []).slice(0,6).map(r => `${this.date(r.recorded_at || r.date)} · ${this.num(r.liters,"L")} · ${r.source_text || "—"}${r.measurement_gap ? " · ⚠" : ""}`)));
    if (!configured) {
      const manual = this.card(this.t("recordWater"),"mdi:water-check",this.notes(this.t("notConfigured")),el("div","form",this.field("record_mm",`${this.t("amount")} · mm (0.1–50)`,recommendation.recommended_mm,.1,50),this.button(this.t("recordWater"),"record_watering",() => { const amount = this.amount("record_mm",.1,50); return amount == null ? null : {amount_mm:amount}; },"","confirmRecord")));
      return [rec,manual,records];
    }
    const progress = this.card(this.t("session"),"mdi:sprinkler-variant",el("div","value compact",this.text("irrigation_status")),this.meter(session.session_progress_percent),this.row(this.t("progress"),this.num(session.session_progress_percent,"%")),this.row(this.t("delivered"),this.num(session.session_liters,"L")),this.row(this.t("target"),this.num(session.session_target_liters,"L")),this.row(this.t("remaining"),this.num(session.session_remaining_liters,"L")),this.row(this.t("finish"),this.date(session.session_estimated_end)),this.row(this.t("actualFlow"),this.num(session.session_flow_l_min,"L/min")),this.notes([session.reason_text,session.action_hint]),el("div","actions",this.button(this.t("stop"),"stop_irrigation",{},"danger"))); progress.classList.add("span2");
    const auto = this.state("automatic_irrigation")?.state;
    const toggle = this.button(auto === "on" ? this.t("disable") : this.t("enable"),auto === "on" ? "disable_automatic" : "enable_automatic",{},"",auto === "on" ? "" : "confirmEnable");
    if (!["on","off"].includes(auto)) toggle.disabled = true;
    const control = this.card(this.t("automatic"),"mdi:shield-check",this.tag(auto === "on" ? this.t("on") : auto === "off" ? this.t("off") : this.t("autoUnknown")),this.notes(this.attrs("irrigation_readiness").automatic_blockers_text),this.targetForm(recommendation),el("div","actions",toggle),el("div","actions",this.button(this.t("pause2"),"suspend_irrigation",{duration_hours:2}),this.button(this.t("pause24"),"suspend_irrigation",{duration_hours:24}),this.button(this.t("resume"),"suspend_irrigation")),this.row(this.t("next"),this.date(this.state("next_automatic_start")?.state)));
    return [rec,progress,control,records];
  }
  diagnostics() {
    const soil = this.attrs("soil_moisture"), quality = this.attrs("data_quality"), irrigation = this.attrs("irrigation_readiness"), window = quality.mowing_window_quality || {}, model = soil.model_insights || {};
    const inputNames = {soil_moisture_entity:this.t("soil"),soil_temperature_entity:this.lang === "de" ? "Bodentemperatur" : "Soil temperature",leaf_wetness_entity:this.lang === "de" ? "Blattnässe" : "Leaf wetness",weather_entity:this.lang === "de" ? "Wetter" : "Weather",temperature_entity:this.lang === "de" ? "Außentemperatur" : "Outdoor temperature",precipitation_entity:this.lang === "de" ? "Regen" : "Rain",irrigation_flow:this.t("flow"),irrigation_valve:this.lang === "de" ? "Ventil" : "Valve",other_valve:this.lang === "de" ? "Zweites Ventil" : "Second valve",mower_location:this.lang === "de" ? "Mäherposition" : "Mower position"};
    const inputReasons = this.lang === "de" ? {accepted:"Gültig",not_configured:"Nicht eingerichtet",missing:"Fehlt",unavailable:"Nicht verfügbar",stale:"Veraltet",invalid:"Ungültig",invalid_or_stale:"Ungültig oder veraltet"} : {accepted:"Valid",not_configured:"Not configured",missing:"Missing",unavailable:"Unavailable",stale:"Stale",invalid:"Invalid",invalid_or_stale:"Invalid or stale"};
    const inputs = this.card(this.t("inputs"),"mdi:database-check",this.tag(this.text("data_quality")),...Object.entries(quality.input_diagnostics || {}).map(([key,value]) => this.row(inputNames[key] || key,`${inputReasons[value.reason] || "—"} · ${this.num(value.age_minutes,"min")}`)),this.detail(quality)); inputs.classList.add("span2");
    const evidence = this.card(this.t("evidence"),"mdi:water-check",this.notes(model.soil_evidence?.basis_text),this.row(this.t("soil"),this.num(model.soil_evidence?.current_sensor_percent,"%")),this.row(this.t("updated"),this.date(model.soil_evidence?.last_correction_at)),this.notes(model.calibration?.reasons_text),this.notes(model.watering_response?.reasons_text),this.detail(soil));
    const balance = this.card(this.t("balance"),"mdi:water-percent",this.notes(soil.model_diagnostics?.explanation?.scope_text),...(soil.model_diagnostics?.explanation?.terms || []).map(term => this.row(term.text,this.num(term.amount_mm,"mm"))),this.notes([quality.data_gaps?.impact_text,...(model.weekly_comparison?.reasons_text || [])]),this.detail(soil.model_diagnostics || {}));
    const mowing = this.card(this.t("review"),"mdi:weather-partly-rainy",this.notes([window.current_dew_risk_text,window.reason_text,...(window.quality_reasons_text || [])]),...(window.retrospective?.summary?.counts_text || []).map(row => this.row(row.text,this.num(row.count))),this.notes(window.retrospective?.summary?.scope_text),this.detail(window));
    const cards = [inputs,evidence,balance,mowing,this.inputProblems()];
    if (this.lawn.irrigation_configured) cards.push(this.card(this.t("comparison"),"mdi:sprinkler",this.notes([...irrigation.automatic_blockers_text || [],irrigation.quantity_comparison?.reason_text,irrigation.water_balance?.reason_text,irrigation.water_balance?.delivery_quality_text,irrigation.quantity_comparison?.scope_text]),this.detail(irrigation)));
    return cards;
  }

  render() {
    const scroll = this.shadowRoot.querySelector(".main")?.scrollTop || 0;
    const railScroll = this.shadowRoot.querySelector(".rail")?.scrollLeft || 0;
    const focused = this.shadowRoot.activeElement?.name;
    const context = `${this._entry}:${this._view}`;
    const detailsOpen = context === this._detailsContext ? [...this.shadowRoot.querySelectorAll("details")].map(node => node.open) : [];
    this._detailsContext = context;
    const style = el("style","",STYLE), app = el("div","app");
    const menu = el("button","menu",icon("mdi:menu")); menu.type = "button"; menu.setAttribute("aria-label","Home Assistant menu");
    menu.addEventListener("click", () => this.dispatchEvent(new CustomEvent("hass-toggle-menu",{bubbles:true,composed:true})));
    const brand = el("div","brand",menu,el("div","brand-icon",icon("mdi:grass")),el("div","",el("h1","",this.t("brand")),el("div","small",this.t("sub"))));
    const select = el("select"); select.name = "lawn"; select.setAttribute("aria-label",this.t("garden")); select.disabled = this._busy || this._loading;
    for (const lawn of this._lawns) { const option = el("option","",lawn.name); option.value = lawn.entry_id; select.append(option); }
    select.value = this._entry;
    select.addEventListener("change", () => { this.selectLawn(select.value); });
    const connected = this._hass?.connected !== false;
    app.append(el("header","top",brand,el("div","top-actions",el("div","connection",el("span",`dot ${connected ? "" : "off"}`),this.t(connected ? "live" : "offline")),select)));
    const rail = el("nav","rail",el("div","rail-label",this.t("garden"))); rail.setAttribute("aria-label",this.t("brand"));
    for (const [view,label,symbol] of [["overview","overview","mdi:view-dashboard-outline"],["plan","plan","mdi:calendar-check-outline"],["mowing","mowing","mdi:robot-mower-outline"],["water","water","mdi:sprinkler-variant"],["trends","trends","mdi:chart-timeline-variant"],["journal","journal","mdi:history"],["diagnostics","diagnostics","mdi:chart-box-outline"]]) {
      const button = el("button",`nav ${view === this._view ? "active" : ""}`,icon(symbol),this.t(label)); button.type = "button";
      button.setAttribute("aria-current",view === this._view ? "page" : "false");
      button.addEventListener("click", () => { this._view = view; if (!this._busy) this._message = null; this.saveRoute(); this.scheduleRender(); }); rail.append(button);
    }
    const refresh = el("button","nav",icon("mdi:refresh"),this.t("refresh")); refresh.type = "button"; refresh.disabled = this._loading || this._busy; refresh.addEventListener("click",() => this.loadLawns()); rail.append(refresh);
    rail.append(el("div","rail-foot",el("div","","Home Assistant"),el("div","",`${this.t("version")} ${this._version || "3.20.0"}`)));
    const main = el("main","main");
    if (this._message) { const notice = el("div",`notice ${this._message.type}`,this._message.text); notice.setAttribute("role",this._message.type === "error" ? "alert" : "status"); main.append(notice); }
    if (!connected) main.append(el("div","notice",this.t("offline")));
    if (this._loading && !this.lawn) main.append(el("div","empty",this.t("loading")));
    else if (!this.lawn) main.append(el("div","empty",el("h2","",this.t("noLawns")),el("p","",this.t("noLawnsText"))));
    else {
      main.append(el("div","page-head",el("div","",el("div","eyebrow",this.lawn.name),el("h2","",this._view === "overview" ? this.t("today") : this.t(this._view)),el("div","subtitle",this._view === "overview" ? this.t("overviewSub") : this.t("modelNote"))),this.tag(new Intl.DateTimeFormat(this.lang,{day:"2-digit",month:"long",timeZone:this._hass?.config?.time_zone || undefined}).format(new Date()))));
      if (!this._canControl) main.append(el("div","notice",this.t("readOnly")));
      const cards = this._view === "overview" ? this.overview() : this._view === "plan" ? this.plan() : this._view === "mowing" ? this.mowing() : this._view === "water" ? this.watering() : this._view === "trends" ? this.trends() : this._view === "journal" ? this.journal() : this.diagnostics();
      main.append(el("div","grid",cards));
    }
    app.append(el("div","layout",rail,main));
    this.shadowRoot.replaceChildren(style,app);
    [...this.shadowRoot.querySelectorAll("details")].forEach((node,i) => { node.open = detailsOpen[i] === true; });
    main.scrollTop = scroll; rail.scrollLeft = railScroll;
    if (focused) this.shadowRoot.querySelector(`[name="${focused}"]`)?.focus({preventScroll:true});
  }
}
if (!customElements.get("lawn-care-dashboard")) customElements.define("lawn-care-dashboard",LawnCareDashboard);
