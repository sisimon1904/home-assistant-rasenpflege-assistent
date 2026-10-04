"""German and English descriptions for stable decision and safety reason codes.

File: custom_components/rasenpflege_assistent/explanations.py

Sensors, diagnostics and irrigation events expose machine-readable codes.
This lookup adds readable explanations without changing the codes used by
automations. Extra tables are merged into the language maps at import time.

Unknown languages fall back to English; unknown codes remain visible for
diagnosis. HA entity names, states and service translations are maintained
separately in strings.json and translations/*.json.
"""

# Codes are part of diagnostics/events and must not be translated in-place.
# Keep readable labels separate so automations remain independent of UI language.
EXPLANATIONS = {
    "de": {
        "response_history_gap": "Der Diagnoseverlauf enthält eine Zeitlücke; die Sensorreaktion lässt sich nicht sicher zuordnen.",
        "calibration_insufficient_history": "Für die Kalibrierungshilfe fehlen sechs unabhängige Meldungen über mindestens 24 Stunden.",
        "calibration_persistent_disagreement": "Sensor und Modell weichen im Verlauf um mindestens 20 Prozentpunkte ab.",
        "calibration_check_rain_source": "Zuerst die Niederschlagsquelle und Messlücken prüfen.",
        "calibration_check_references_and_location": "Trocken-/Nassreferenzen, Sensorposition und Bodenprofil prüfen; Abweichung allein beweist keinen Modellfehler.",
        "calibration_sensor_at_limits": "Der Sensor liegt dauerhaft an den Referenzgrenzen; Messbereich und Referenzen prüfen.",
        "response_insufficient_observations": "Frische Sensorwerte vor und 30 Minuten bis 24 Stunden nach der Bewässerung fehlen.",
        "response_incomplete_watering": "Keine vollständig gemessene, gültige Bewässerung als Vergleichsbasis vorhanden.",
        "response_rain_uncertain": "Regen oder Messlücken verhindern die Zuordnung der Sensorreaktion zur Bewässerung.",
        "response_check_delivery_and_sensor": "Keine Feuchtezunahme beobachtet: Wasserverteilung und Sensorposition prüfen. Das beweist keinen Gerätefehler.",
        "response_observed": "Nach der Bewässerung wurde eine Feuchtezunahme beobachtet; daraus wird kein Wirkungsgrad berechnet.",
        "forecast_stale": "Die Wettervorhersage ist veraltet.",
        "observed_rain_unknown": "Gemessener Niederschlag ist unbekannt",
        "weather_stale": "Wetterdaten sind veraltet",
        "model_interval_gap": "Bodenmodell enthält eine Zeitlücke",
        "evapotranspiration_fallback": "Verdunstung wird saisonal geschätzt",
        "soil_sensor_model_disagreement": "Bodensensor und Modell weichen um mindestens 20 Prozentpunkte ab",
        "soil_sensor_not_available": "Kein gültiger Bodensensor verfügbar",
        "solar_radiation_estimated": "Sonnenstrahlung wird geschätzt",
        "temperature_based_evapotranspiration": "Verdunstung beruht auf Temperaturdaten",
        "ready": "Start möglich",
        "running": "Bewässerung läuft",
        "paused": "Pausiert – zweites Ventil geöffnet",
        "stopping": "Ventil wird geschlossen",
        "completed": "Abgeschlossen",
        "stopped": "Abgebrochen",
        "mower_not_docked": "Mäher ist nicht an der Station",
        "valve_not_closed": "Rasenventil ist nicht geschlossen",
        "other_valve_open": "Zweites Ventil ist offen",
        "other_valve_unavailable": "Status des zweiten Ventils fehlt",
        "meter_unavailable": "Wasserzähler nicht verfügbar",
        "not_configured": "Kein Ventil eingerichtet",
        "meter_stale": "Durchflussmesswert zu alt",
        "storage_error": "Speicherfehler",
        "homeassistant_stopping": "Home Assistant wird beendet",
        "idle": "Bereit",
        "collecting_data": "Daten werden gesammelt",
        "winter_dormancy": "Winterruhe (Wachstumsstopp)",
        "early_spring": "Vorfrühling",
        "drought_stress": "Trockenstress",
        "water_now": "Jetzt wässern",
        "water_soon": "Bald wässern",
        "wait_for_rain": "Auf Regen warten",
        "fertilizing_recommended": "Düngung empfohlen",
        "mowing_recommended": "Mähen empfohlen",
        "good_condition": "Guter Zustand",
        "lawn_wet": "Rasen nass",
        "water_lawn": "Rasen wässern",
        "prepare_watering": "Bewässerung vorbereiten",
        "fertilize_lawn": "Rasen düngen",
        "start_mower": "Mähroboter wieder starten",
        "mow_lawn": "Rasen mähen",
        "winterize_mower": "Mähroboter für den Winter abschalten",
        "no_action": "Keine Aktion erforderlich",
        "wait_to_mow": "Bis zum nächsten Mähzeitpunkt warten",
        "wait_for_irrigation": "Bewässerung abwarten",
        "first_awakening": "Erstes Erwachen (zaghaftes Wachstum)",
        "sustained_growth_start": "Nachhaltiger Vegetationsbeginn (volles Wachstum)",
        "active_growth": "Aktives Wachstum",
        "slow_growth": "Langsames Wachstum",
        "autumn_slowdown": "Wachstum verlangsamt (Herbst)",
        "heat_drought_stress": "Hitze- oder Trockenstress (Wachstum pausiert)",
        "winter_off": "Für den Winter abschalten",
        "keep_off": "Noch ausgeschaltet lassen",
        "mow_regularly": "Regelmäßig mähen – Rasen wächst",
        "mow_less": "Seltener mähen",
        "reduce_mowing": "Mähhäufigkeit im Herbst reduzieren",
        "pause_drought": "Wegen Trockenstress pausieren",
        "pause_wet": "Wegen nassem Rasen pausieren",
        "pause_frost": "Pause wegen Frost",
        "season_pause": "Saisonpause",
        "not_due": "Bodenfeuchte ausreichend",
        "good": "Gut",
        "limited": "Eingeschränkt",
        "insufficient": "Unzureichend",
        "high": "Hoch",
        "medium": "Mittel",
        "low": "Niedrig",
        "penman_monteith_estimated_radiation": "Penman-Monteith mit geschätzter Strahlung",
        "hargreaves_samani": "Hargreaves-Samani als Rückfallverfahren",
        "estimated_fallback": "Saisonale Schätzung (Temperatur fehlt)",
        "unavailable": "Nicht verfügbar",
        "automation_disabled": "Automatische Bewässerung ist aus",
        "session_active": "Bewässerung läuft",
        "meter_required": "Wasserzähler für Automatik erforderlich",
        "waiting_for_weather": "Warte auf Wetterdaten",
        "rain_unavailable": "Gemessener Regen fehlt",
        "weather_unavailable": "Wetter oder Vorhersage fehlt",
        "low_confidence": "Wetter- oder Bodenmodelldaten zu unsicher",
        "already_watered_today": "Rasen wurde heute bereits bewässert",
        "retry_cooldown": "Wartezeit nach fehlgeschlagenem Start",
        "watering_not_due": "Bewässerung ist nicht fällig",
        "no_suitable_window": "Kein geeignetes Bewässerungsfenster",
        "waiting_for_window": "Warte auf das Bewässerungsfenster",
        "window_expired": "Bewässerungsfenster ist abgelaufen",
        "irrigation_running": "Bewässerung läuft; Mähpause bis der Rasen abgetrocknet ist.",
        "irrigation_paused": "Bewässerung ist pausiert; der Rasen gilt weiterhin als nass.",
        "last_watering_unknown": "Letzte Bewässerung ist unbekannt.",
        "last_watering_known": "Letzte Bewässerung wird berücksichtigt.",
        "forecast_precipitation_unavailable": "Regenprognose fehlt oder ist unvollständig.",
        "sufficient_rain_forecast": "Ausreichend Regen ist vorhergesagt.",
        "insufficient_rain_forecast": "Vorhergesagter Regen reicht nicht aus.",
        "heat_increases_water_demand": "Hitze erhöht den Wasserbedarf.",
        "modeled_soil_moisture_used": "Bodenfeuchte wird aus dem Modell geschätzt.",
        "target_reached": "Bewässerungsziel erreicht.",
        "stopped_manually": "Bewässerung manuell beendet.",
        "mower_left_dock": "Mäher hat die sichere Position verlassen.",
        "no_flow": "Kein ausreichender Durchfluss erkannt.",
        "excessive_flow": "Durchfluss überschreitet den Grenzwert.",
        "maximum_runtime": "Maximale Bewässerungsdauer erreicht.",
        "maximum_volume": "Maximale Wassermenge erreicht.",
        "valve_closed_externally": "Ventil wurde außerhalb der Integration geschlossen.",
        "integration_unloaded": "Integration wird beendet.",
        "robot_estimate": "Geschätzte Mähdauer; Rückkehr zur Station bestätigt keine vollständige Flächenabdeckung.",
    },
    "en": {
        "response_history_gap": "The diagnostic history has an observation gap; sensor response attribution is uncertain.",
        "calibration_insufficient_history": "Calibration advice needs six independent reports spanning at least 24 hours.",
        "calibration_persistent_disagreement": "Sensor and model have a persistent median difference of at least 20 percentage points.",
        "calibration_check_rain_source": "Check rainfall input and measurement gaps first.",
        "calibration_check_references_and_location": "Review dry/wet references, sensor location and soil profile; disagreement alone does not prove a model error.",
        "calibration_sensor_at_limits": "Sensor readings remain at reference limits; check the measurement range and references.",
        "response_insufficient_observations": "Fresh sensor observations before and 30 minutes to 24 hours after watering are missing.",
        "response_incomplete_watering": "No complete, valid measured watering session is available for comparison.",
        "response_rain_uncertain": "Rain or observation gaps prevent attributing the sensor response to watering.",
        "response_check_delivery_and_sensor": "No moisture increase observed: review water distribution and sensor location. This does not prove a device fault.",
        "response_observed": "A moisture increase was observed after watering; no efficiency is inferred.",
        "forecast_stale": "The weather forecast is stale.",
        "observed_rain_unknown": "Observed precipitation is unknown",
        "weather_stale": "Weather data is stale",
        "model_interval_gap": "Soil model has an integration gap",
        "evapotranspiration_fallback": "Evapotranspiration uses a seasonal estimate",
        "soil_sensor_model_disagreement": "Soil sensor and model differ by at least 20 percentage points",
        "soil_sensor_not_available": "No valid soil sensor is available",
        "solar_radiation_estimated": "Solar radiation is estimated",
        "temperature_based_evapotranspiration": "Evapotranspiration is based on temperature data",
        "ready": "Ready to start",
        "running": "Watering",
        "paused": "Paused – other valve open",
        "stopping": "Closing valve",
        "completed": "Completed",
        "stopped": "Stopped",
        "mower_not_docked": "Mower is not confirmed docked",
        "valve_not_closed": "Lawn valve is not closed",
        "other_valve_open": "Other valve is open",
        "other_valve_unavailable": "Other valve status unavailable",
        "meter_unavailable": "Water meter unavailable",
        "not_configured": "No valve configured",
        "meter_stale": "Flow reading too old",
        "storage_error": "Storage error",
        "homeassistant_stopping": "Home Assistant is stopping",
        "idle": "Idle",
        "collecting_data": "Collecting data",
        "winter_dormancy": "Winter dormancy (growth stopped)",
        "early_spring": "Early spring",
        "drought_stress": "Drought stress",
        "water_now": "Water now",
        "water_soon": "Water soon",
        "wait_for_rain": "Wait for rain",
        "fertilizing_recommended": "Fertilizing recommended",
        "mowing_recommended": "Mowing recommended",
        "good_condition": "Good condition",
        "lawn_wet": "Lawn wet",
        "water_lawn": "Water lawn",
        "prepare_watering": "Prepare watering soon",
        "fertilize_lawn": "Fertilize lawn",
        "start_mower": "Start mower again",
        "mow_lawn": "Mow lawn",
        "winterize_mower": "Switch mower off for winter",
        "no_action": "No action required",
        "wait_to_mow": "Wait until the next mowing time",
        "wait_for_irrigation": "Wait for irrigation",
        "first_awakening": "First awakening (tentative growth)",
        "sustained_growth_start": "Sustained vegetation start (full growth)",
        "active_growth": "Active growth",
        "slow_growth": "Slow growth",
        "autumn_slowdown": "Growth slowing (autumn)",
        "heat_drought_stress": "Heat or drought stress (growth paused)",
        "winter_off": "Switch off for winter",
        "keep_off": "Keep switched off",
        "mow_regularly": "Mow regularly – lawn is growing",
        "mow_less": "Mow less frequently",
        "reduce_mowing": "Reduce mowing for autumn",
        "pause_drought": "Pause due to drought stress",
        "pause_wet": "Pause because the lawn is wet",
        "pause_frost": "Pause because of frost",
        "season_pause": "Seasonal pause",
        "not_due": "Soil moisture sufficient",
        "good": "Good",
        "limited": "Limited",
        "insufficient": "Insufficient",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "penman_monteith_estimated_radiation": "Penman-Monteith with estimated radiation",
        "hargreaves_samani": "Hargreaves-Samani fallback",
        "estimated_fallback": "Seasonal estimate (temperature unavailable)",
        "unavailable": "Unavailable",
        "automation_disabled": "Automatic irrigation is off",
        "session_active": "Watering session in progress",
        "meter_required": "Water meter required for automatic watering",
        "waiting_for_weather": "Waiting for weather data",
        "rain_unavailable": "Observed rain is unavailable",
        "weather_unavailable": "Weather or forecast is unavailable",
        "low_confidence": "Weather or soil model confidence is too low",
        "already_watered_today": "Lawn already watered today",
        "retry_cooldown": "Waiting before retry after an unsuccessful start",
        "watering_not_due": "Watering is not due",
        "no_suitable_window": "No suitable watering window",
        "waiting_for_window": "Waiting for the watering window",
        "window_expired": "Watering window has ended",
        "irrigation_running": "Irrigation is running; wait for the lawn to dry before mowing.",
        "irrigation_paused": "Irrigation is paused; the lawn remains wet.",
        "last_watering_unknown": "Last watering is unknown.",
        "last_watering_known": "Last watering is taken into account.",
        "forecast_precipitation_unavailable": "Rain forecast is missing or incomplete.",
        "sufficient_rain_forecast": "Enough rain is forecast.",
        "insufficient_rain_forecast": "Forecast rain is insufficient.",
        "heat_increases_water_demand": "Heat increases water demand.",
        "modeled_soil_moisture_used": "Soil moisture is estimated from the model.",
        "target_reached": "Irrigation target reached.",
        "stopped_manually": "Irrigation stopped manually.",
        "mower_left_dock": "Mower left its safe position.",
        "no_flow": "Insufficient water flow detected.",
        "excessive_flow": "Water flow exceeds the limit.",
        "maximum_runtime": "Maximum irrigation duration reached.",
        "maximum_volume": "Maximum water volume reached.",
        "valve_closed_externally": "Valve was closed outside the integration.",
        "integration_unloaded": "Integration is unloading.",
        "robot_estimate": "Estimated mowing duration; docking does not confirm complete lawn coverage.",
    },
}


_EXTRA = {
    "valve_unavailable": (
        "Ventilstatus ist nicht verfügbar.",
        "Valve state is unavailable.",
    ),
    "valve_open_failed": (
        "Öffnen des Ventils fehlgeschlagen; es wird geschlossen.",
        "Opening the valve failed; closure is being enforced.",
    ),
    "valve_did_not_open": (
        "Ventil hat das Öffnen nicht bestätigt.",
        "Valve did not confirm opening.",
    ),
    "meter_reset": (
        "Wasserzähler wurde während der Bewässerung zurückgesetzt.",
        "Water meter reset during irrigation.",
    ),
    "meter_unit_changed": (
        "Einheit des Wasserzählers wurde geändert.",
        "Water meter unit changed.",
    ),
    "interrupted_by_restart": (
        "Bewässerung durch Neustart unterbrochen; Messlücke wird nicht geschätzt.",
        "Irrigation interrupted by restart; missing water measurements are not estimated.",
    ),
    "rain": ("Rasen nach Regen noch nass.", "Lawn is still wet after rain."),
    "watering": (
        "Rasen nach Bewässerung noch nass.",
        "Lawn is still wet after watering.",
    ),
    "cool_calm_dry_period": (
        "Kühles, windarmes und trockenes Zeitfenster.",
        "Cool, calm and dry time window.",
    ),
    "best_available_period": (
        "Bestes verfügbares Bewässerungszeitfenster.",
        "Best available irrigation time window.",
    ),
}
for _code, _texts in _EXTRA.items():
    EXPLANATIONS["de"][_code] = _texts[0]
    EXPLANATIONS["en"][_code] = _texts[1]


_RELEASE_EXPLANATIONS = {
    "outside_watering_season": (
        "Außerhalb der Bewässerungssaison.",
        "Outside the watering season.",
    ),
    "gts_below_200": (
        "Grünlandtemperatursumme noch unter 200.",
        "Grassland temperature sum is below 200.",
    ),
    "gts_reached_200": (
        "Grünlandtemperatursumme hat 200 erreicht.",
        "Grassland temperature sum reached 200.",
    ),
    "main_growth_and_interval_reached": (
        "Hauptwachstum und Düngeabstand erreicht.",
        "Main growth and fertilizing interval reached.",
    ),
    "avoid_nitrogen_during_heat_or_drought": (
        "Bei Hitze oder Trockenheit keinen Stickstoff düngen.",
        "Avoid nitrogen during heat or drought.",
    ),
    "potassium_supports_winter_hardiness": (
        "Kalium unterstützt die Winterhärte.",
        "Potassium supports winter hardiness.",
    ),
    "outside_fertilizing_season": (
        "Außerhalb der Düngesaison.",
        "Outside the fertilizing season.",
    ),
    "last_fertilizing_known": (
        "Letzte Düngung wird berücksichtigt.",
        "Last fertilizing is taken into account.",
    ),
    "last_fertilizing_unknown": (
        "Letzte Düngung ist unbekannt.",
        "Last fertilizing is unknown.",
    ),
    "frost": (
        "Bewässerung wegen Frost gesperrt.",
        "Irrigation blocked because of frost.",
    ),
    "leaf_wetness": (
        "Blattnässesensor meldet nassen Rasen.",
        "Leaf wetness sensor reports wet lawn.",
    ),
    "soak_pause": (
        "Versickerungspause zwischen Bewässerungsetappen.",
        "Soaking pause between irrigation cycles.",
    ),
    "automation_suspended": (
        "Automatische Bewässerung vorübergehend gesperrt.",
        "Automatic irrigation is temporarily suspended.",
    ),
    "outside_schedule": (
        "Außerhalb der erlaubten Bewässerungszeit.",
        "Outside the allowed irrigation schedule.",
    ),
    "configured": ("Kein Ventil eingerichtet.", "No valve configured."),
    "automation_enabled": ("Automatik ausgeschaltet.", "Automation disabled."),
    "no_active_session": (
        "Eine Sitzung ist bereits aktiv.",
        "A session is already active.",
    ),
    "homeassistant_running": (
        "Home Assistant wird beendet.",
        "Home Assistant is stopping.",
    ),
    "storage_available": ("Speicher nicht verfügbar.", "Storage is unavailable."),
    "mower_docked": ("Mäher nicht an Station.", "Mower is not docked."),
    "valve_closed": ("Eigenes Ventil nicht geschlossen.", "Owned valve is not closed."),
    "other_valve_closed": (
        "Zweites Ventil offen oder unbekannt.",
        "Second valve is open or unknown.",
    ),
    "meter_available": (
        "Wasserzähler fehlt oder ist ungültig.",
        "Water meter is missing or invalid.",
    ),
    "meter_fresh": (
        "Wasserzähler fehlt oder ist zu alt.",
        "Water meter is missing or stale.",
    ),
    "weather_available": (
        "Wetterdaten fehlen oder sind zu alt.",
        "Weather data is missing or stale.",
    ),
    "rain_available": ("Gemessener Regen fehlt.", "Observed rain is missing."),
    "confidence_sufficient": (
        "Datenvertrauen zu gering.",
        "Data confidence is too low.",
    ),
    "frost_free": (
        "Frost oder unbekannte Temperatur.",
        "Frost or unknown temperature.",
    ),
    "not_suspended": (
        "Automatische Bewässerung vorübergehend gesperrt.",
        "Automatic irrigation is temporarily suspended.",
    ),
    "schedule_allowed": (
        "Außerhalb der erlaubten Bewässerungszeit.",
        "Outside the allowed irrigation schedule.",
    ),
    "not_watered_today": ("Heute bereits bewässert.", "Already watered today."),
    "retry_allowed": ("Wartezeit vor erneutem Start.", "Waiting before another start."),
    "watering_due": ("Bewässerung nicht erforderlich.", "Watering is not due."),
    "forecast_window_active": (
        "Kein aktuell geeignetes Vorhersagefenster.",
        "No suitable forecast window is active.",
    ),
}
for _code, _texts in _RELEASE_EXPLANATIONS.items():
    EXPLANATIONS["de"][_code] = _texts[0]
    EXPLANATIONS["en"][_code] = _texts[1]


_NEW_EXPLANATIONS = {
    "rain_detected": ("Bewässerung wegen Regen beendet", "Watering stopped for rain"),
    "wind_too_strong": (
        "Bewässerung wegen starkem Wind beendet",
        "Watering stopped for strong wind",
    ),
    "budget_uncertain": (
        "Verbrauch unvollständig; Automatik gesperrt",
        "Consumption incomplete; automation blocked",
    ),
    "water_budget_exhausted": ("Verbrauchslimit erreicht", "Water budget exhausted"),
    "water_budget_available": (
        "Verbrauchslimit oder Messqualität prüfen",
        "Check the consumption budget or measurement quality",
    ),
    "irrigation": ("Ventilmessung", "Valve measurement"),
    "manual_record": ("Manueller Eintrag", "Manual record"),
    "manual_estimate": ("Manuelle Schätzung", "Manual estimate"),
    "schedule_ends_before_target": (
        "Erlaubtes Zeitfenster endet voraussichtlich vor Erreichen der Zielmenge",
        "Allowed schedule likely ends before the target is reached",
    ),
    "current_weather_safe": (
        "Aktuell Regen oder starken Wind abwarten",
        "Wait for current rain or strong wind to subside",
    ),
    "planned_start": (
        "Voraussichtlicher Start im erlaubten Wetterfenster",
        "Estimated start in an allowed weather window",
    ),
    "no_schedule_overlap": (
        "Zeitplan und Wetterfenster überschneiden sich nicht",
        "Schedule and forecast window do not overlap",
    ),
    "no_active_session": ("Keine laufende Bewässerung", "No active irrigation session"),
    "waiting_for_flow": (
        "Restlaufzeit erst bei messbarem Durchfluss verfügbar",
        "Remaining time requires measurable flow",
    ),
    "estimated_completion": (
        "Geschätztes Ende einschließlich Einweichpausen",
        "Estimated completion including soak pauses",
    ),
    "maximum_runtime_before_target": (
        "Zielmenge voraussichtlich nicht vor Sicherheitsende erreichbar",
        "Target likely exceeds the safety runtime",
    ),
}
for _code, _texts in _NEW_EXPLANATIONS.items():
    EXPLANATIONS["de"][_code] = _texts[0]
    EXPLANATIONS["en"][_code] = _texts[1]


# Read-only care and observation guidance introduced in 3.11.0.
_EVERYDAY_EXPLANATIONS = {
    "care_check_inputs": (
        "Aktuelle Temperaturdaten prüfen, bevor Pflege geplant wird.",
        "Check current temperature observations before planning care.",
    ),
    "care_wait_frost": ("Bei Frost Pflege aufschieben.", "Defer care during frost."),
    "care_water_before_mowing": (
        "Wasserbedarf zuerst berücksichtigen; Mähen erst im passenden Zeitfenster.",
        "Consider water demand first; mow in the appropriate time window.",
    ),
    "care_wait_dry": (
        "Nach Regen oder Bewässerung trockenen Rasen abwarten.",
        "Wait for the lawn to dry after rain or watering.",
    ),
    "care_follow_mowing_schedule": (
        "Mähintervall und verfügbares trockenes Zeitfenster berücksichtigen.",
        "Follow the mowing interval and available dry window.",
    ),
    "care_follow_fertilizing_window": (
        "Düngung im empfohlenen Zeitfenster einplanen.",
        "Plan fertilizing within its recommended window.",
    ),
    "check_inputs": ("Eingangsdaten prüfen", "Check input observations"),
    "wait_for_frost_free": (
        "Frostfreie Bedingungen abwarten",
        "Wait for frost-free conditions",
    ),
    "wait_for_irrigation": (
        "Bewässerungsende abwarten",
        "Wait for irrigation to finish",
    ),
    "prepare_watering": ("Bewässerung vorbereiten", "Prepare watering"),
    "wait_until_dry": ("Trockenen Rasen abwarten", "Wait for the lawn to dry"),
    "sensor_flat_review": (
        "Unveränderte Feuchte trotz unabhängiger Meldungen und Modelländerung: Sensorposition und Meldungen prüfen. Kein bestätigter Gerätefehler.",
        "Unchanged moisture despite independent reports and model changes: review sensor placement and reports. No confirmed device fault.",
    ),
    "sensor_repeated_outages": (
        "Wiederholte Ausfälle gültiger Feuchtemessungen im Verlauf; Datenquelle prüfen.",
        "Repeated losses of valid moisture observations in the history; review the input source.",
    ),
    "cycle_flow_unknown": (
        "Ohne verwertbare eigene Durchflussmessung sind Laufzeit und Zykluszahl unbekannt.",
        "Runtime and cycle count require usable flow measurements from owned irrigation.",
    ),
    "cycle_infiltration_review": (
        "Ausbringrate über der geschätzten Bodenaufnahme: kurze Zyklen und Sickerpausen vor Ort prüfen. Einstellungen bleiben unverändert.",
        "Application rate exceeds estimated soil infiltration: review short cycles and soak pauses on site. Settings remain unchanged.",
    ),
    "robot_old_event_ignored": (
        "Verspätetes oder doppeltes Mäherereignis verworfen.",
        "Ignored a late or duplicate mower event.",
    ),
    "robot_observation_expired": (
        "Mäherbeobachtung nach zwölf Stunden verworfen.",
        "Discarded the mower observation after twelve hours.",
    ),
    "robot_observation_discarded": (
        "Unklare Mäherzustände: laufende Beobachtung verworfen.",
        "Uncertain mower states: discarded the in-flight observation.",
    ),
    "robot_observing": (
        "Aktive Mähzeit wird beobachtet; Flächenabdeckung ist nicht bestätigt.",
        "Observing active mowing time; lawn coverage is not confirmed.",
    ),
    "robot_waiting_for_dock": (
        "Pause oder Rückfahrt; auf Station warten.",
        "Paused or returning; waiting for docking.",
    ),
}
for _code, _texts in _EVERYDAY_EXPLANATIONS.items():
    EXPLANATIONS["de"][_code] = _texts[0]
    EXPLANATIONS["en"][_code] = _texts[1]


def reason_text(code: str | None, language: str) -> str | None:
    """Return a localized explanation, preserving unknown codes for diagnosis."""
    if code is None:
        return None
    return EXPLANATIONS.get(language, EXPLANATIONS["en"]).get(code, code)
