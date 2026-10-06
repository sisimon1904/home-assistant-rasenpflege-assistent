/**
 * File: tests/browser/test-panel.mjs
 * Chromium regression tests for the actual shipped custom element.
 * A local HTTP fixture supplies HA state/WS doubles, never real credentials or
 * devices. Assert DOM behavior, request scope and input handling on desktop and
 * mobile; Python tests independently cover server permissions and safety.
 */
import assert from "node:assert/strict";
import {test, before, after} from "node:test";
import {createServer} from "node:http";
import {readFile} from "node:fs/promises";
import {chromium} from "playwright";

let browser, server, base;
const panelPath = new URL("../../custom_components/rasenpflege_assistent/frontend/panel.js",import.meta.url);
before(async () => {
  browser = await chromium.launch({headless:true, ...(process.env.LAWN_CHROMIUM_PATH ? {executablePath:process.env.LAWN_CHROMIUM_PATH,args:["--no-sandbox","--disable-dev-shm-usage"]} : {})});
  server = createServer(async (request,response) => {
    if (request.url.startsWith("/panel.js")) { response.setHeader("Content-Type","text/javascript"); response.end(await readFile(panelPath)); }
    else { response.setHeader("Content-Type","text/html"); response.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;height:100%;}lawn-care-dashboard{height:100vh}</style></head><body><script type="module">import "/panel.js";window.panel=document.createElement("lawn-care-dashboard");document.body.append(panel);window.ready=true;</script></body></html>'); }
  });
  await new Promise(resolve => server.listen(0,"127.0.0.1",resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });

async function fixture(options={}) {
  const context = await browser.newContext({viewport:options.mobile ? {width:390,height:844} : {width:1440,height:1000}});
  const page = await context.newPage();
  const errors = []; page.on("pageerror",error => errors.push(error.message));
  page.on("dialog",dialog => dialog.accept());
  await page.goto(base+"/rasenpflege-assistent"+(options.fragment || ""));
  await page.waitForFunction(() => window.ready);
  await page.evaluate(({language,readOnly}) => {
    window.calls=[];
    const keys=["status","soil_moisture","care_plan","growth_status","gts","mower_status","watering_recommendation","irrigation_status","automatic_irrigation","irrigation_readiness","next_automatic_start","forecast_rain_24h","forecast_rain_72h","data_quality","last_calculation","soil_model_confidence","watering_confidence","water_consumption_day","water_consumption_week","water_consumption_month"];
    const entities=Object.fromEntries(keys.map(key => [key,`${key === "automatic_irrigation" ? "switch" : "sensor"}.a_${key}`]));
    const now=new Date().toISOString();
    const states=Object.fromEntries(keys.map(key => [entities[key],{entity_id:entities[key],state:"10",last_changed:now,attributes:{}}]));
    states[entities.automatic_irrigation].state="off";
    states[entities.soil_moisture].state="60";
    states[entities.soil_moisture].attributes={model_insights:{soil_evidence:{basis_text:"Model with valid soil reading"}}};
    states[entities.watering_recommendation].attributes={recommended_mm:4,recommended_liters:400};
    states[entities.irrigation_status].attributes={session_flow_l_min:5,session_target_liters:400,session_progress_percent:40};
    states[entities.data_quality].state="good";
    states[entities.data_quality].attributes={weather_age_minutes:15,forecast_age_minutes:90,input_diagnostics:{weather_entity:{reason:"accepted",age_minutes:15}}};
    states[entities.soil_model_confidence].state="high";
    states[entities.watering_confidence].state="medium";
    states[entities.care_plan].attributes={prioritized_steps:[{action_text:"Watering",availability_text:"Check weather first",not_before:now}],outlook:{scope_text:"Conditional recommendation"}};
    states[entities.last_calculation].state=now;
    states[entities.water_consumption_day].attributes={recent_records:[{recorded_at:now,liters:250,source_text:"Manuelle Erfassung"},{recorded_at:new Date(Date.now()-86400000).toISOString(),liters:400,source_text:"Bewässerungssteuerung",measurement_gap:true}]};
    window.meta={lawns:[{entry_id:"a",name:"Garden A",entities,irrigation_configured:true},{entry_id:"b",name:"Garden B",entities:{status:"sensor.b_status"},irrigation_configured:false}],can_control:!readOnly,version:"3.18.0"};
    window.extra={area_m2:100,observations:Array.from({length:12},(_,i) => ({timestamp:new Date(Date.now()-(12-i)*1800000).toISOString(),sensor_reported_at:new Date(Date.now()-(12-i)*1800000).toISOString(),modeled_percent:60-i*.2,measured_percent:i === 5 ? null : 58-i*.1,rain_mm:i === 3 ? 1.5 : 0,rain_known:i !== 8,et_mm:.05})),journal:[{action:"mowing",timestamp:now,details:{recorded_at:now,source:"manual"},can_undo:!readOnly}],notifications:readOnly ? null : {enabled:false,interval_hours:24}};
    window.hass={states,language:language || "de",config:{time_zone:"Europe/Berlin"},user:{id:"user-a"},connection:{},connected:true,callApi:async () => [[]],callWS:async request => { window.calls.push(JSON.parse(JSON.stringify(request))); if (request.type.endsWith("/dashboard")) return window.meta; if (request.type.endsWith("/dashboard_data")) return window.extra; return null; }};
    window.panel.hass=window.hass;
  },options);
  await page.waitForFunction(() => window.panel._panelData != null);
  await page.locator(".main .card").first().waitFor();
  return {page,close:async () => { assert.deepEqual(errors,[]); await context.close(); }};
}

test("all seven areas render on desktop and mobile without card overflow",async () => {
  for (const mobile of [false,true]) {
    const f=await fixture({mobile});
    for (const label of ["Übersicht","Pflegeplan","Mähen","Bewässerung","Verläufe","Pflegeprotokoll","Diagnose"]) {
      await f.page.getByRole("button",{name:label,exact:true}).click();
      await f.page.waitForFunction(label => panel.shadowRoot.querySelector('.nav[aria-current="page"]')?.textContent === label,label);
      await f.page.locator(".main .card").first().waitFor();
      assert.equal(await f.page.evaluate(() => [...panel.shadowRoot.querySelectorAll(".card")].every(card => card.getBoundingClientRect().right <= innerWidth+1)),true);
      if (process.env.LAWN_SCREENSHOTS && ["Übersicht","Verläufe","Pflegeprotokoll"].includes(label)) { await f.page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve))); await f.page.screenshot({path:`${process.env.LAWN_SCREENSHOTS}/${mobile ? "mobile" : "desktop"}-${await f.page.evaluate(() => panel._view)}.png`}); }
    }
    if (process.env.LAWN_SCREENSHOTS) await f.page.screenshot({path:`${process.env.LAWN_SCREENSHOTS}/${mobile ? "mobile" : "desktop"}.png`});
    await f.close();
  }
});

test("late history response never belongs to a lawn without a soil entity",async () => {
  const f=await fixture();
  await f.page.evaluate(async () => {
    panel._hass.callApi=() => new Promise(resolve => {window.resolveHistory=resolve;});
    window.oldHistory=panel.loadHistory();
    panel.selectLawn("b");
    resolveHistory([[{entity_id:"sensor.a_soil_moisture",state:"42"}]]);
    await oldHistory;
  });
  assert.equal(await f.page.evaluate(() => panel._history),null);
  await f.close();
});

test("same-millisecond refreshes accept only the newest history",async () => {
  const f=await fixture();
  assert.equal(await f.page.evaluate(async () => {
    const resolve=[]; panel._hass.callApi=() => new Promise(r => resolve.push(r));
    const first=panel.loadHistory(), second=panel.loadHistory();
    resolve[1]([[{state:"20"}]]); await second;
    resolve[0]([[{state:"10"}]]); await first;
    return panel._history[0].state;
  }),"20");
  await f.close();
});

test("open details survive live updates within the same view",async () => {
  const f=await fixture();
  await f.page.getByRole("button",{name:"Diagnose",exact:true}).click();
  await f.page.locator("summary").first().click();
  await f.page.evaluate(() => { const entity=panel.lawn.entities.data_quality; panel.hass={...hass,states:{...hass.states,[entity]:{...hass.states[entity],state:"limited"}}}; });
  await f.page.waitForFunction(() => panel.shadowRoot.querySelector("details").open);
  assert.equal(await f.page.locator("details").first().evaluate(node => node.open),true);
  await f.close();
});

test("unknown automation is shown honestly and cannot be toggled",async () => {
  const f=await fixture();
  await f.page.evaluate(() => { const id=panel.lawn.entities.automatic_irrigation; panel.hass={...hass,states:{...hass.states,[id]:{...hass.states[id],state:"unavailable"}}}; });
  await f.page.getByRole("button",{name:"Bewässerung",exact:true}).click();
  await f.page.getByText("Unbekannt",{exact:true}).waitFor();
  assert.equal(await f.page.getByRole("button",{name:"Automatik aktivieren",exact:true}).isDisabled(),true);
  await f.close();
});

test("liter start and invalid amount are entry scoped and validated",async () => {
  const f=await fixture();
  await f.page.getByRole("button",{name:"Bewässerung",exact:true}).click();
  await f.page.locator('[name="target_unit"]').selectOption("L");
  await f.page.locator('[name="target_liters"]').fill("250");
  await f.page.getByRole("button",{name:"Starten",exact:true}).click();
  await f.page.getByText("Aktion erfolgreich ausgeführt.").waitFor();
  assert.deepEqual(await f.page.evaluate(() => calls.filter(call => call.action === "start_irrigation").at(-1)),{type:"rasenpflege_assistent/dashboard_action",config_entry_id:"a",action:"start_irrigation",data:{target_liters:250}});
  await f.page.locator('[name="target_liters"]').fill("5001");
  await f.page.getByRole("button",{name:"Starten",exact:true}).click();
  await f.page.getByText("Bitte eine gültige Menge innerhalb des angezeigten Bereichs eingeben.").waitFor();
  assert.equal(await f.page.evaluate(() => calls.filter(call => call.action === "start_irrigation").length),1);
  await f.close();
});

test("care undo and replacement retain the displayed record timestamp",async () => {
  const f=await fixture();
  await f.page.getByRole("button",{name:"Pflegeprotokoll",exact:true}).click();
  const timestamp=await f.page.evaluate(() => extra.journal[0].timestamp);
  await f.page.getByRole("button",{name:"Zurücknehmen und neu erfassen",exact:true}).click();
  await f.page.getByText("Aktion erfolgreich ausgeführt.").waitFor();
  assert.equal(await f.page.evaluate(() => calls.find(call => call.action === "undo_last_manual").data.timestamp),timestamp);
  assert.equal(await f.page.locator('[name="care_kind"]').inputValue(),"mowing");
  assert.ok(await f.page.locator('[name="care_time"]').inputValue());
  await f.close();
});

test("care form rejects future time and records explicit historical watering",async () => {
  const f=await fixture();
  await f.page.getByRole("button",{name:"Pflegeprotokoll",exact:true}).click();
  await f.page.locator('[name="care_kind"]').selectOption("watering");
  await f.page.locator('[name="care_mm"]').fill("3");
  await f.page.locator('[name="care_time"]').fill("2099-01-01T12:00");
  await f.page.getByRole("button",{name:"Speichern",exact:true}).first().click();
  await f.page.getByText("Bitte einen vergangenen Zeitpunkt angeben.").waitFor();
  assert.equal(await f.page.evaluate(() => calls.filter(call => call.action === "record_watering").length),0);
  await f.page.locator('[name="care_time"]').fill("2026-01-01T12:00");
  await f.page.getByRole("button",{name:"Speichern",exact:true}).first().click();
  await f.page.getByText("Aktion erfolgreich ausgeführt.").waitFor();
  const request=await f.page.evaluate(() => calls.find(call => call.action === "record_watering"));
  assert.equal(request.data.amount_mm,3); assert.ok(request.data.recorded_at.endsWith("Z"));
  await f.close();
});

test("notification preferences are scoped, optional and keep their interval",async () => {
  const f=await fixture();
  await f.page.getByRole("button",{name:"Pflegeprotokoll",exact:true}).click();
  await f.page.locator('[name="notify_enabled"]').selectOption("on");
  await f.page.locator('[name="notify_interval"]').selectOption("6");
  await f.page.getByRole("button",{name:"Speichern",exact:true}).last().click();
  await f.page.getByText("Aktion erfolgreich ausgeführt.").waitFor();
  assert.deepEqual(await f.page.evaluate(() => calls.find(call => call.action === "notification_settings").data),{enabled:true,interval_hours:6});
  await f.close();
});

test("read-only users and disconnected clients cannot use controls",async () => {
  const f=await fixture({readOnly:true,language:"en"});
  await f.page.getByRole("button",{name:"Irrigation",exact:true}).click();
  assert.equal(await f.page.getByRole("button",{name:"Start",exact:true}).isDisabled(),true);
  await f.page.getByRole("button",{name:"Care log",exact:true}).click();
  assert.equal(await f.page.getByRole("button",{name:"Save",exact:true}).isDisabled(),true);
  assert.equal(await f.page.locator('[name="notify_enabled"]').count(),0);
  await f.page.evaluate(() => { panel._canControl=true; panel.hass={...hass,connected:false}; });
  await f.page.getByRole("button",{name:"Irrigation",exact:true}).click();
  assert.equal(await f.page.getByRole("button",{name:"Start",exact:true}).isDisabled(),true);
  await f.close();
});

test("validated deep links and per-user preferences select a view",async () => {
  const f=await fixture({fragment:"#view=journal&lawn=a"});
  assert.equal(await f.page.evaluate(() => panel._view),"journal");
  await f.page.getByRole("button",{name:"Verläufe",exact:true}).click();
  assert.ok(f.page.url().includes("view=trends"));
  assert.deepEqual(await f.page.evaluate(() => JSON.parse(localStorage.getItem(panel.preferenceKey()))),{view:"trends",lawn:"a"});
  await f.page.evaluate(() => { history.replaceState({},"","#view=%3Cimg%3E&lawn=missing"); panel.restoreRoute(); });
  assert.equal(await f.page.evaluate(() => panel._view),"trends");
  assert.equal(await f.page.evaluate(() => panel._entry),"a");
  await f.close();
});

test("plots separate missing readings and gaps; sensor text stays inert",async () => {
  const f=await fixture();
  const result=await f.page.evaluate(() => {
    const now=Date.now();
    const rows=[{timestamp:new Date(now-7200000).toISOString(),modeled_percent:50},{timestamp:new Date(now-600000).toISOString(),modeled_percent:60}];
    const chart=panel.plot(rows,"modeled_percent","Model","%",100);
    panel._lawns[0].name='<img src=x onerror="alert(1)">'; panel.render();
    return {lines:chart.querySelectorAll("polyline").length,points:chart.querySelectorAll("circle").length,images:panel.shadowRoot.querySelectorAll("img").length,text:panel.shadowRoot.textContent.includes("<img src=x")};
  });
  assert.deepEqual(result,{lines:0,points:2,images:0,text:true});
  await f.close();
});
