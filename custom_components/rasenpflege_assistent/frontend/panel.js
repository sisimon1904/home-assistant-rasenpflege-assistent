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
const missing = (v) => v == null || v === "unknown" || v === "unavailable";
const finite = (v) => !missing(v) && v !== "" && Number.isFinite(Number(v));

export class LawnCareDashboard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._lawns = []; this._view = "overview"; this._entry = "";
    this._draft = {}; this._history = null; this._historyError = false;
    this._busy = false; this._loading = false; this._message = null;
  }

  // HA supplies an updated hass object for live state changes. No polling loop.
  set hass(value) {
    const previous = this._hass;
    this._hass = value;
    const entities = Object.values(this.lawn?.entities || {});
    if (!this._loaded && !this._loading && this.isConnected) this.loadLawns();
    if (!previous || previous.connection !== value.connection || previous.connected !== value.connected || previous.language !== value.language || entities.some(id => previous.states[id] !== value.states[id])) this.scheduleRender();
    if ((previous?.connection !== value.connection || previous?.connected === false && value.connected !== false) && this._loaded) this.loadLawns();
  }
  get hass() { return this._hass; }
  connectedCallback() { if (this._hass && !this._loaded) this.loadLawns(); this.scheduleRender(); }
  disconnectedCallback() { cancelAnimationFrame(this._frame); this._frame = null; }
  get lawn() { return this._lawns.find(l => l.entry_id === this._entry); }
  get lang() { return (this._hass?.language || this._hass?.locale?.language || "de").toLowerCase().startsWith("de") ? "de" : "en"; }
  t(key) { return WORDS[this.lang][key] || key; }
  state(key) { return this._hass?.states?.[this.lawn?.entities?.[key]]; }
  attrs(key) { return this.state(key)?.attributes || {}; }
  text(key) {
    const state = this.state(key);
    if (!state || missing(state.state)) return this.t("unknown");
    if (this._hass.formatEntityState) return this._hass.formatEntityState(state);
    return state.state;
  }
  num(value, unit="") { return finite(value) ? `${new Intl.NumberFormat(this.lang, {maximumFractionDigits:1}).format(Number(value))}${unit ? " " + unit : ""}` : "—"; }
  date(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return new Intl.DateTimeFormat(this.lang, {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",timeZone:this._hass?.config?.time_zone || undefined}).format(date);
  }
  scheduleRender() {
    if (!this.isConnected || this._frame) return;
    this._frame = requestAnimationFrame(() => { this._frame = null; this.render(); });
  }

  async loadLawns() {
    if (!this._hass || this._loading) return;
    this._loading = true; this.scheduleRender();
    try {
      const result = await this._hass.callWS({type:"rasenpflege_assistent/dashboard"});
      this._lawns = result.lawns || []; this._canControl = result.can_control; this._version = result.version;
      this._entry = this._lawns.some(l => l.entry_id === this._entry) ? this._entry : this._lawns[0]?.entry_id || "";
      this._loaded = true; this._message = null; this._history = null; this._historyToken = null;
      this.loadHistory();
    } catch (error) { this._loaded = true; this._message = {type:"error",text:this.t("refreshError") + " " + (error.message || "")}; }
    finally { this._loading = false; this.scheduleRender(); }
  }

  // Recorder history is fetched on lawn selection/explicit refresh only. Use
  // full states to retain unknown/unavailable gaps instead of fabricating data.
  async loadHistory() {
    const entity = this.lawn?.entities?.soil_moisture;
    if (!entity) return;
    const token = `${this._entry}:${Date.now()}`; this._historyToken = token; this._historyError = false;
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
  field(name, label, value, min, max, cls="") {
    const input = el("input",cls); input.type = "number"; input.name = name;
    input.min = String(min); input.max = String(max); input.step = "0.1";
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
    } catch (error) { this._message = {type:"error",text:`${this.t("failed")}: ${error.message || error.code || "—"}`}; }
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
    const health = this.card(this.t("quality"),"mdi:database-check",this.tag(this.text("data_quality"), this.state("data_quality")?.state === "good" ? "" : "orange"),this.row(this.t("updated"),this.date(this.state("last_calculation")?.state)),el("div","hint",this.t("modelNote")));
    return [hero,moisture,growth,rain,use,history,health];
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
    return [priorities,dose,outlook];
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
    const progress = this.card(this.t("session"),"mdi:sprinkler-variant",el("div","value compact",this.text("irrigation_status")),this.meter(session.session_progress_percent),this.row(this.t("progress"),this.num(session.session_progress_percent,"%")),this.row(this.t("delivered"),this.num(session.session_liters,"L")),this.row(this.t("target"),this.num(session.session_target_liters,"L")),this.row(this.t("remaining"),this.num(session.session_remaining_liters,"L")),this.row(this.t("finish"),this.date(session.session_estimated_end)),this.notes([session.reason_text,session.action_hint]),el("div","actions",this.button(this.t("stop"),"stop_irrigation",{},"danger"))); progress.classList.add("span2");
    const control = this.card(this.t("automatic"),"mdi:shield-check",this.tag(this.state("automatic_irrigation")?.state === "on" ? this.t("on") : this.t("off")),this.notes(this.attrs("irrigation_readiness").automatic_blockers_text),el("div","form",this.field("target_mm",`${this.t("amount")} · mm (0.1–50)`,recommendation.recommended_mm,.1,50),this.button(this.t("start"),"start_irrigation",() => { const amount = this.amount("target_mm",.1,50); return amount == null ? null : {target_mm:amount}; },"primary","confirmStart")),el("div","actions",this.button(this.state("automatic_irrigation")?.state === "on" ? this.t("disable") : this.t("enable"),this.state("automatic_irrigation")?.state === "on" ? "disable_automatic" : "enable_automatic",{},"",this.state("automatic_irrigation")?.state === "on" ? "" : "confirmEnable")),el("div","actions",this.button(this.t("pause2"),"suspend_irrigation",{duration_hours:2}),this.button(this.t("pause24"),"suspend_irrigation",{duration_hours:24}),this.button(this.t("resume"),"suspend_irrigation")),this.row(this.t("next"),this.date(this.state("next_automatic_start")?.state)));
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
    const cards = [inputs,evidence,balance,mowing];
    if (this.lawn.irrigation_configured) cards.push(this.card(this.t("comparison"),"mdi:sprinkler",this.notes([...irrigation.automatic_blockers_text || [],irrigation.quantity_comparison?.reason_text,irrigation.water_balance?.reason_text,irrigation.water_balance?.delivery_quality_text,irrigation.quantity_comparison?.scope_text]),this.detail(irrigation)));
    return cards;
  }

  render() {
    const scroll = this.shadowRoot.querySelector(".main")?.scrollTop || 0;
    const focused = this.shadowRoot.activeElement?.name;
    const style = el("style","",STYLE), app = el("div","app");
    const menu = el("button","menu",icon("mdi:menu")); menu.type = "button"; menu.setAttribute("aria-label","Home Assistant menu");
    menu.addEventListener("click", () => this.dispatchEvent(new CustomEvent("hass-toggle-menu",{bubbles:true,composed:true})));
    const brand = el("div","brand",menu,el("div","brand-icon",icon("mdi:grass")),el("div","",el("h1","",this.t("brand")),el("div","small",this.t("sub"))));
    const select = el("select"); select.name = "lawn"; select.setAttribute("aria-label",this.t("garden")); select.disabled = this._busy || this._loading;
    for (const lawn of this._lawns) { const option = el("option","",lawn.name); option.value = lawn.entry_id; select.append(option); }
    select.value = this._entry;
    select.addEventListener("change", () => { this._entry = select.value; this._draft = {}; this._history = null; this._message = null; this.loadHistory(); this.scheduleRender(); });
    const connected = this._hass?.connected !== false;
    app.append(el("header","top",brand,el("div","top-actions",el("div","connection",el("span",`dot ${connected ? "" : "off"}`),this.t(connected ? "live" : "offline")),select)));
    const rail = el("nav","rail",el("div","rail-label",this.t("garden"))); rail.setAttribute("aria-label",this.t("brand"));
    for (const [view,label,symbol] of [["overview","overview","mdi:view-dashboard-outline"],["plan","plan","mdi:calendar-check-outline"],["mowing","mowing","mdi:robot-mower-outline"],["water","water","mdi:sprinkler-variant"],["diagnostics","diagnostics","mdi:chart-box-outline"]]) {
      const button = el("button",`nav ${view === this._view ? "active" : ""}`,icon(symbol),this.t(label)); button.type = "button";
      button.setAttribute("aria-current",view === this._view ? "page" : "false");
      button.addEventListener("click", () => { this._view = view; this._message = null; this.scheduleRender(); }); rail.append(button);
    }
    const refresh = el("button","nav",icon("mdi:refresh"),this.t("refresh")); refresh.type = "button"; refresh.disabled = this._loading || this._busy; refresh.addEventListener("click",() => this.loadLawns()); rail.append(refresh);
    rail.append(el("div","rail-foot",el("div","","Home Assistant"),el("div","",`${this.t("version")} ${this._version || "3.17.0"}`)));
    const main = el("main","main");
    if (this._message) { const notice = el("div",`notice ${this._message.type}`,this._message.text); notice.setAttribute("role",this._message.type === "error" ? "alert" : "status"); main.append(notice); }
    if (!connected) main.append(el("div","notice",this.t("offline")));
    if (this._loading && !this.lawn) main.append(el("div","empty",this.t("loading")));
    else if (!this.lawn) main.append(el("div","empty",el("h2","",this.t("noLawns")),el("p","",this.t("noLawnsText"))));
    else {
      main.append(el("div","page-head",el("div","",el("div","eyebrow",this.lawn.name),el("h2","",this._view === "overview" ? this.t("today") : this.t(this._view)),el("div","subtitle",this._view === "overview" ? this.t("overviewSub") : this.t("modelNote"))),this.tag(new Intl.DateTimeFormat(this.lang,{day:"2-digit",month:"long",timeZone:this._hass?.config?.time_zone || undefined}).format(new Date()))));
      if (!this._canControl) main.append(el("div","notice",this.t("readOnly")));
      const cards = this._view === "overview" ? this.overview() : this._view === "plan" ? this.plan() : this._view === "mowing" ? this.mowing() : this._view === "water" ? this.watering() : this.diagnostics();
      main.append(el("div","grid",cards));
    }
    app.append(el("div","layout",rail,main));
    this.shadowRoot.replaceChildren(style,app);
    main.scrollTop = scroll;
    if (focused) this.shadowRoot.querySelector(`[name="${focused}"]`)?.focus({preventScroll:true});
  }
}
if (!customElements.get("lawn-care-dashboard")) customElements.define("lawn-care-dashboard",LawnCareDashboard);
