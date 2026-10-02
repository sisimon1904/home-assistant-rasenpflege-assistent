# Rasenpflege-Assistent für Home Assistant

**Deutsch** | [English](README.en.md)

Version 3.8.2 · [Änderungsverlauf](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

Diese Integration bewertet Wachstum und Pflegebedarf deines Rasens aus den
vorhandenen OpenWeatherMap-Daten in Home Assistant. Sie berechnet die
Grünlandtemperatursumme, modellierte Bodenfeuchte sowie Empfehlungen zum
Bewässern, Düngen und Mähen. Optional kann sie ein vorhandenes Bewässerungsventil
steuern; sie schaltet den Mähroboter nicht.

## Neu in 3.8.2

- Tatsächlich gemessener Wasserverbrauch bleibt nach Rückgängigmachen im Protokoll und zählt weiterhin gegen Tages-/Wochenlimits.
- Pflegeaktionen und Sitzungsabschluss werden bei gleichzeitigen Aktionen oder Speicherfehlern konsistent verarbeitet.
- Das Ventil wird vor dem Speichern geschlossen; langsame Speicherung verzögert keinen Sicherheitsstopp.
- Automatische Wiederaufnahme bleibt bei bereits gemeldetem Regen oder starkem Wind gesperrt.
- Die 24-Stunden-Regenprognose berücksichtigt Zeitumstellungen korrekt.
- Unbrauchbare Wettertemperaturen werden bei der Einrichtung abgelehnt; Quellenwechsel sind während einer laufenden Bewässerung gesperrt.

## Neu in 3.8.1

Diese Wartungsversion behebt die Umrechnung von Wettervorhersagen, das Entladen der Bewässerungsüberwachung, Speicherfehler am Automatikschalter und abgebrochene Ventilbefehle. Ungültige Niederschlagswerte werden als unbekannt behandelt. Aktionsfehler und Icons verwenden Home Assistants Übersetzungssystem.

Die Wetterquelle lässt sich über **Einstellungen → Geräte & Dienste → Rasenpflege-Assistent → Menü → Neu konfigurieren** wechseln. Weitere Raseneinstellungen bleiben unter **Konfigurieren** verfügbar.

Prüfumfang, Ausnahmen und noch offene Quality-Scale-Anforderungen stehen im [Qualitätsaudit](docs/quality-audit.md). Es wird keine Fehlerfreiheit und keine offizielle Quality-Scale-Einstufung zugesagt.

## Neu in 3.8.0

- Direkter Frostschutz durch aktuelle Luft-/Bodensensorwerte und Zustandsereignisse.
- Automatische Bewässerung stoppt bei anhaltendem Regen oder starkem Wind; manuelle Starts bleiben möglich.
- Optionales Tages-/Wochenlimit für die Automatik, Tagesverbrauch und Sitzungsverlauf.
- Pflegeplan, nächste Startprognose und geschätzte Restlaufzeit einschließlich Einweichpausen.
- Verbrauchsaufteilung über Mitternacht; rückgängig gemachte Sitzungen werden in der Diagnose kenntlich gemacht.
- Dashboard-Vorlagen für Pflegeplan und Verlauf, auswählbare Mengenvorgaben und Automatikpausen.

### Wetterstopps und Verbrauchslimits

Unter **Konfigurieren → Bewässerung – Sicherheit** stehen die neuen Einstellungen. Der Wetterstopp ist standardmäßig aktiv: Regen ab 0,5 mm/h bei Ratensensoren beziehungsweise 0,5 mm seit Sitzungsbeginn bei Mengen-/Zählersensoren, Wind ab 8 m/s, Bestätigungsdauer 120 Sekunden. Kurzzeitige Rate-/Windausschläge setzen die Bestätigungszeit zurück, sobald sie abklingen. Bereits gemeldeter Regen oder starker Wind sperrt einen automatischen Start sofort. Ohne gültigen Regensensor verwendet die Integration den aktuellen Wetterzustand. Fehlende Wetterinformationen werden nicht als gemessener Regen interpretiert. Alle Eingaben stammen aus vorhandenen HA-Entitäten; es gibt keine zusätzlichen regelmäßigen OWM-API-Abfragen.

Tages-/Wochenlimits sind mit **0 deaktiviert**. Sie zählen sämtliche erfassten Bewässerungsmengen einschließlich manueller Einträge und Schätzungen; unbekannte oder unvollständige Mengen blockieren automatische Starts im betroffenen Budgetzeitraum. Das automatische Mengenziel wird auf das verbleibende Budget begrenzt. Mess- und Schaltverzögerungen können dennoch Überschreitungen verursachen. Manuelle Starts bleiben durch die bisherigen Sicherheitsgrenzen geschützt. Das zweite Ventil bleibt ausschließlich eine Statusquelle und wird nie geschaltet.

### Prognosen, Verlauf und Rückgängigmachen

Der **Pflegeplan** fasst Mähen, Bewässern und Düngen mit Zeitangaben und Hindernissen zusammen. Der **nächste automatische Bewässerungsstart** schneidet das vorhandene Vorhersagefenster mit Zeitplan, Automatiksperre und Wiederholungswartezeit. Fehlt eine Überschneidung oder eine Voraussetzung, bleibt der Zeitpunkt unbekannt und die Diagnose erklärt den Grund. Die Prognose ist keine Terminreservierung und keine vollständige mehrtägige Simulation.

Die **verbleibende Bewässerungsdauer** schätzt aktive Minuten aus dem Durchfluss; `session_estimated_end` berücksichtigt Einweichpausen. Bei einer Pause wegen des zweiten Ventils ist das Ende unbekannt. Wenn die maximale Gesamtdauer nicht ausreicht, wird kein erreichbares Abschlussdatum versprochen.

**Wasserverbrauch heute** sowie Wochen-/Monatssummen enthalten abgeschlossene oder manuell erfasste Sitzungen. Eine laufende Sitzung wird separat im Bewässerungsstatus und bei den Budgetprüfungen berücksichtigt. `recent_records` zeigt die letzten zehn erfassten Bewässerungen; `recent_sessions` zeigt die letzten zehn Ventilsitzungen. Zählerzuwächse über Mitternacht werden zeitanteilig aufgeteilt und mit `allocation_estimated` gekennzeichnet. Bekannte Gesamtmengen bleiben erhalten. Alte Einträge ohne Messabschnitte behalten ihre bisherige Tageszuordnung.

Rückgängigmachen entfernt die Modellgutschrift. Tatsächlich gemessener Verbrauch einer gesteuerten Bewässerung bleibt im Verbrauchsprotokoll und zählt weiterhin gegen Tages-/Wochenlimits. Fehlerhafte manuelle Verbrauchseinträge werden entfernt. Die physisch gemessene Sitzung bleibt zur Diagnose sichtbar, mit `undone: true`, `undone_at` und `effective_model_mm: 0`. Die einmalige automatische Tagesbewässerung bleibt aus Sicherheitsgründen gesperrt; Rückgängigmachen löst keine neue automatische Bewässerung aus.

Die Aktion `suspend_irrigation` akzeptiert jetzt auch **`duration_hours`** (0,25 bis 168), alternativ zu `until`. Ohne beide Felder wird die Pause aufgehoben. Neue Vorlagen: [Pflegeplan](docs/dashboard/care-plan.de.yaml), [Verbrauch und Verlauf](docs/dashboard/consumption.de.yaml). Die [Bewässerungskarte](docs/dashboard/irrigation.de.yaml) bietet 1/3/5 mm, 100 Liter sowie Pausen für 2/24 Stunden. Weitere individuelle Mengen können im HA-Aktionsdialog gewählt werden.

| Neue Diagnoseattribute | Bedeutung |
| --- | --- |
| `next_start_plan` | Voraussichtlicher Zeitpunkt, Grund und Schätzungskennzeichen. |
| `session_remaining_active_minutes`, `session_estimated_end`, `session_eta_reason` | Restlaufzeit, geschätztes Ende und Einschränkung. |
| `water_budget` | Bekannter Tages-/Wochenverbrauch, Restbudget und unvollständige Messung. |
| `action_hint` | Konkreter Handlungshinweis zum aktuellen Automatik-Hindernis. |
| `allocations`, `allocation_estimated` | Tagesanteile der gemessenen Menge und Schätzungskennzeichen der Zuordnung. |

## Bewässerung: Menge, Zeitplan und Etappen

Unter **Konfigurieren → Bewässerung – Zeitplan und Etappen** legst du erlaubte Wochentage und Uhrzeiten fest. Die Zeiten beziehen sich auf die lokale Home-Assistant-Zeitzone. Gleiche Start- und Endzeit erlaubt den ganzen ausgewählten Tag. Ein Fenster von 22:00 bis 02:00 gehört zum Wochentag seines Beginns. Eine leere Tagesauswahl sperrt die Automatik. Bestehende Konfigurationen behalten zunächst alle Tage und den ganzen Tag.

Der Zeitplan gilt für automatische Bewässerung. Zum Start muss zusätzlich das Wetterfenster geeignet sein. Am Ende der erlaubten Zeit wird eine laufende automatische Sitzung beendet. Manuelle Starts bleiben außerhalb des Zeitplans möglich, beachten aber Frost, Mäherstandort, Ventile, Zähler und alle Sicherheitsgrenzen.

**Bewässerungsdauer je Etappe** ist standardmäßig 0: keine Etappen. Ein größerer Wert schließt das eigene Ventil nach der angegebenen aktiven Dauer. Nach der **Versickerungspause** (Standard: 15 Minuten) wird nur bei sicheren Eingängen fortgesetzt. Während der Pause bleibt die Sitzung aktiv, der Rasen nass und die Wasserbuchung offen. Verbrauch am gemeinsamen Zähler wird während der Pause ausgeschlossen. Vor Wiederaufnahme wird dessen Basis neu gesetzt. Nach einem Neustart wird auch eine pausierte Sitzung beendet. Das zweite Ventil bleibt ausschließlich ein Leseeingang.

Unter **Entwicklerwerkzeuge → Aktionen** stehen folgende Aktionen zur Verfügung:

| Aktion | Zusätzliche Felder | Verhalten |
| --- | --- | --- |
| `rasenpflege_assistent.start_irrigation` | `target_liters` **oder** `target_mm`, optional | Startet manuell; ein Mengenziel erfordert einen Wasserzähler. |
| `rasenpflege_assistent.stop_irrigation` | keine | Beendet die eigene laufende oder pausierte Sitzung. |
| `rasenpflege_assistent.suspend_irrigation` | `until` **oder** `duration_hours`, optional | Sperrt nur die Automatik; ohne beide Felder wird die Sperre aufgehoben. |

Alle Aktionen benötigen `config_entry_id`; im Aktionsdialog lässt sich die Rasen-Konfiguration auswählen. Die Kennung ist außerdem über `{{ config_entry_id('sensor.DEINE_RASEN_ENTITAET') }}` unter **Entwicklerwerkzeuge → Template** ermittelbar. `until` ist ein zukünftiger ISO-Zeitstempel **mit Zeitzone**, beispielsweise `2026-10-02T08:00:00+02:00`.

Ein explizites Mengenziel hat Vorrang vor der sonst geltenden manuellen Mindestdauer. Ziele oberhalb der Sicherheitsgrenze werden abgelehnt. Die Abschaltung erfolgt nach dem gemeldeten Zählerwert; Mess- und Schaltverzögerungen können zu einer Überschreitung führen. 1 mm entspricht 1 Liter je Quadratmeter Rasenfläche. Ohne explizites Ziel bleibt die bisherige Schaltfläche **Bewässerung erfassen** erhalten.

Eine temporäre Sperre beendet eine bereits laufende automatische Sitzung. Sie verändert den Automatikschalter nicht und aktiviert ihn nach Ablauf nicht eigenständig. Manuelle Starts bleiben möglich. Bei Frost werden Start und Wiederaufnahme gesperrt und eine laufende Sitzung beendet, sobald die Temperaturinformation vorliegt.

## Blattnässe, Verlauf und Verbrauch

Unter **Konfigurieren → Eingangssensoren** ist ein optionaler Blattnässe-Binärsensor wählbar: `on` bedeutet nass, `off` trocken. Ein frischer Trockenwert kann die historische Abtrocknungsschätzung nach Regen/Bewässerung aufheben. Laufende oder pausierte Bewässerung sperrt das Mähen weiterhin. Fehlende, ungültige oder alte Blattnässewerte verwenden wieder die bisherige Schätzung. Das maximale Alter wird unter **Boden- und Wassermodell** eingestellt (Standard: 360 Minuten); der Sensor sollte seine Werte regelmäßig melden.

Die Aktionen `record_mowing`, `record_fertilizing` und `record_watering` akzeptieren optional `recorded_at` als vergangenen ISO-Zeitstempel mit Zeitzone. Nachgetragene Bewässerungen benötigen eine ausdrückliche `amount_mm`. Sie erscheinen im Verlauf und Verbrauch, verändern aber den heutigen Bodenspeicher nicht: Eine nachträgliche vollständige Wasserbilanz mit damaligem Regen und Verdunstung wird nicht simuliert. Ein älteres Pflegeereignis verdrängt kein bereits neueres Datum. Ohne Zeitstempel gilt die bisherige Buchung für jetzt.

Die Verbrauchssensoren summieren bekannte erfasste Mengen für die lokale Kalenderwoche (Montag bis heute) beziehungsweise den laufenden Kalendermonat. Attribute trennen Ventilmessungen, manuell gemeldete Mengen, manuelle Schätzungen, ungemessene Sitzungen und Sitzungen mit Messlücken. Unbekannte Mengen werden nicht erfunden; Summen mit Messlücken sind unvollständig. Neue Verbrauchswerte beginnen mit 3.7.0, frühere Sitzungen werden nicht rückwirkend aus der begrenzten Historie geschätzt. Das Verbrauchsjournal wird für etwa ein Jahr gehalten, der Pflegeverlauf weiterhin für die letzten 20 Einträge. Rückgängigmachen entfernt den zugehörigen Verbrauchseintrag; während kontrollierter Bewässerung ist es gesperrt.

## Neue Diagnoseattribute und Dashboard-Vorlagen

Die Diagnose liest vorhandene Zustände; sie löst keine zusätzlichen regelmäßigen OpenWeatherMap-Abfragen aus. Eine laufende Robotersitzung aktualisiert ihre Minuten lokal alle 30 Sekunden. Sie bleibt eine Schätzung und wird nach Neustart verworfen.

| Entität / Attribut | Einheit | Bedeutung |
| --- | --- | --- |
| Bewässerungsstatus: `session_target_liters`, `session_liters`, `session_remaining_liters` | L | Ziel, bekannte Lieferung und Restmenge; ohne Mengenziel ist die Restmenge unbekannt. |
| `session_progress_percent`, `session_delivered_mm` | %, mm | Fortschritt und ausgebrachte Wassermenge; im ungemessenen Timerbetrieb unbekannt. |
| `session_flow_l_min` | L/min | Durchfluss während der aktiven Ventilöffnung; aus Rate oder zuletzt gemessenem Zählerzuwachs. |
| `session_active_seconds`, `session_paused_seconds`, `session_remaining_seconds` | s | Aktive Zeit, Pausen und verbleibende maximale Gesamtdauer. |
| `session_cycle_number`, `session_pause_reason`, `session_resume_after` | Anzahl / Code / ISO-Zeit | Aktueller Abschnitt, Pausengrund und früheste Wiederaufnahme. |
| `last_session` | Objekt | Beginn, Ende, Liter, mm, tatsächlich wirksamer Modellbeitrag, Dauer, Quelle, Messlücke und Abschlussgrund. |
| Bewässerungsdiagnose: `automatic_conditions`, `automatic_blockers`, `automatic_blockers_text` | Objekt / Listen | Alle Startbedingungen und gleichzeitig blockierende Gründe, zusätzlich lesbar. |
| `automation_suspended_until` | ISO-Zeit | Ende einer temporären Automatiksperre; nach Ablauf blockiert sie nicht mehr. |
| Bodenfeuchte / Datenqualität: `input_diagnostics` | Objekt | Entität, Wert, Einheit, Alter, Höchstalter und Verwerfungsgrund für Boden- und Blattnässesensoren. |
| Datenqualität: `forecast_diagnostics` | Objekt | Wetterentität, Aktualisierung je Prognosetyp, Anzahl Einträge und fehlende Eingangswerte. |
| Mähroboterstatus: `live_robot_session` | Objekt | Aktive Minuten, Beginn und Beobachtungsstatus; kein Nachweis vollständiger Flächenabdeckung. |
| `last_robot_session_started_at`, `last_robot_session_finished_at`, `last_robot_session_active_minutes` | ISO-Zeit, min | Letzte geschätzte Robotersitzung ohne Pausen und Rückfahrt. |
| Erfasste Bewässerung diese Woche / diesen Monat | L | Bekannte erfasste Mengen; Herkunft und unbekannte Sitzungen stehen in den Attributen. |

Kopierbare Mushroom-Vorlagen: [Rasenübersicht](docs/dashboard/overview.de.yaml), [Bewässerung mit Bedienung](docs/dashboard/irrigation.de.yaml), [Mähen](docs/dashboard/mowing.de.yaml) und [Diagnose mit Verbrauch](docs/dashboard/diagnostics.de.yaml). Sie benötigen die Mushroom-Karten. Entitätsnamen sind **Beispiele** und müssen anhand **Entwicklerwerkzeuge → Zustände** ersetzt werden. Vor Bedienaktionen muss außerdem `REPLACE_WITH_ENTRY_ID` durch die Kennung der richtigen Rasenfläche ersetzt werden. YAML in eine manuelle Dashboard-Karte kopieren.

## Bewässerungsereignisse für eigene Automationen

Das Ereignis `rasenpflege_assistent_irrigation` liefert `config_entry_id`, `phase`, `reason`, `source`, `started_at`, `liters`, `measurement_gap`, `session_id`, `target_liters` und `reason_text`. Phasen sind `started`, `paused`, `resumed`, `completed` oder `stopped`. Abschlussereignisse werden erst nach erfolgreicher Speicherung gesendet und bei einem Speicher-Wiederholungsversuch nicht doppelt erzeugt. Ereignisse sind aktuelle Meldungen und werden nach Neustart nicht wiederholt. Die Integration versendet selbst keine Nachrichten.

```yaml
triggers:
  - trigger: event
    event_type: rasenpflege_assistent_irrigation
    event_data:
      config_entry_id: REPLACE_WITH_ENTRY_ID
      phase: stopped
actions:
  - action: persistent_notification.create
    data:
      title: Rasenbewässerung beendet
      message: "Grund: {{ trigger.event.data.reason }}; bekannte Menge: {{ trigger.event.data.liters }} L"
```

## Installation

Benötigt werden Home Assistant 2026.4.0 oder neuer und eine eingerichtete
OpenWeatherMap-Integration. Der Modus `v3.0` bietet aktuelle Wetterdaten sowie
stündliche und tägliche Vorhersagen.

1. In **HACS → Integrationen → Benutzerdefinierte Repositories** die Adresse
   `https://github.com/sisimon1904/home-assistant-rasenpflege-assistent`
   mit der Kategorie **Integration** eintragen.
2. **Rasenpflege-Assistent** installieren und Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** den
   **Rasenpflege-Assistenten** wählen und die OpenWeatherMap-Wetterentität
   angeben.

Alternativ den Ordner `custom_components/rasenpflege_assistent` nach
`/config/custom_components/rasenpflege_assistent` kopieren und Home Assistant
neu starten. Updates per HACS erfordern veröffentlichte GitHub-Releases.

## Einrichtung und Datenquellen

Pro Rasen lassen sich Fläche, Nutzung, Bodenart, Sonnenlage, Wurzeltiefe,
Gefälle, Verdichtung, Bewässerungseffizienz und Regenkorrektur einstellen.
Bei der Ersteinrichtung genügen Name, OpenWeatherMap-Wetterentität und die
grundlegenden Rasendaten. **Konfigurieren** öffnet danach die getrennten Seiten
**Grundeinstellungen**, **Eingangssensoren**, **Mähen**, **Bewässerung**, **Boden- und
Wassermodell** und **Pflegeverlauf**. Mit Ventil erscheinen zusätzlich
**Bewässerung – Sicherheit** und **Bewässerung – Zeitplan und Etappen**. Die Dauer und andere Zahlen werden in Feldern
mit sichtbaren Werten eingegeben. Während eine Bewässerung läuft oder pausiert,
muss sie vor einer Konfigurationsänderung gestoppt werden.
Optional sind Außentemperatur, Niederschlag, Bodentemperatur und Bodenfeuchte
als separate Sensoren wählbar. Fehlt ein Außentemperatursensor, verwendet die
Integration OpenWeatherMap. Ohne ausdrücklich ausgewählten Regensensor sucht
sie einen aktiven OpenWeatherMap-Regensensor derselben Wetterkonfiguration.

Ein physischer Bodenfeuchtesensor lässt sich mit Trocken- und Nassreferenzen
kalibrieren. Optionale Binärsensoren für **Rasen wurde gemäht** und **Rasen wurde
bewässert** protokollieren eine Aus→Ein-Flanke. Bei eingerichtetem Ventil wird
der Eingang „Rasen wurde bewässert“ ausgeblendet; ohne Ventil stehen die manuellen
Schaltflächen zur Verfügung. Bewässerung und Düngung lassen sich mit
tatsächlichen Mengen protokollieren und das letzte Ereignis rückgängig machen.

## Wachstumsabhängig mähen

Unter **Konfigurieren → Mähen** wählst du **Handmäher** oder **Mähroboter**.
Bestehende Installationen behalten zunächst den Handmäher-Modus und ihre Daten.

| Wachstum | Handmäher | Mähroboter |
| --- | --- | --- |
| Volles Wachstum | alle 4 Tage | täglich |
| Langsames Wachstum | alle 7 Tage | alle 3 Tage |
| Herbst / erstes Erwachen nach Saisonstart | alle 10 Tage | alle 5 Tage |

Das sind Schätzungen für die Empfehlung. Der Faktor passt alle Abstände an:
1 = Vorgaben, 0,5 = halber Abstand, 2 = doppelter Abstand. Nässe, Frost,
Winterruhe und Trockenstress haben Vorrang. Der Roboter wird nicht gesteuert.

Optional wählst du auf derselben Seite eine Mäherstatus-Entität. Die Erkennung
zählt ausschließlich aktive Mähzeit (Vorgabe: mindestens 10 Minuten) und erfasst
anschließend die Rückkehr zur Station. Für `lawn_mower` sind üblicherweise
`mowing` und `docked` einzutragen; bei `vacuum` kann der aktive Zustand `cleaning`
heißen. Verwende die internen Zustände aus **Entwicklerwerkzeuge → Zustände**.
Pausen und Rückfahrt zählen nicht als Mähzeit. Fehler, unbekannte Zustände,
`idle`, kurze Starts und Neustarts bestätigen keinen Einsatz; eine begonnene
Beobachtung wird nach zwölf Stunden verworfen.

**Die Erkennung ist eine Schätzung:** Auch die Rückkehr zum Laden kann einen
Eintrag auslösen. Ein eingerichteter Binäreingang **Rasen wurde gemäht** hat
Vorrang und sollte einen tatsächlich abgeschlossenen Auftrag melden.
100 % Fortschritt sind keine Voraussetzung. Verschiedene Einsätze am selben
Tag werden gespeichert, doppelte Meldungen desselben Ereignisses nicht.

Im Mähroboterstatus stehen `last_mowing_at`, `next_mowing_at`, Mähmethode,
Grund, Vertrauen und die Quelle des letzten Eintrags. Der früheste geschätzte
Termin berücksichtigt sowohl den Zeitabstand als auch die Nässepause.
Bei Frost, Trockenstress oder fehlender Temperatur gibt es keinen festen
Freigabetermin. Unter **Pflegeverlauf** kannst du das letzte Mähdatum korrigieren
oder leeren. Übernommene und korrigierte reine Datumswerte verwenden den lokalen
Tagesbeginn als geschätzte Uhrzeit; neue Ereignisse speichern die genaue Uhrzeit.

## Optionale automatische Bewässerung

Unter **Konfigurieren** können ein `switch` für das Ventil, ein Wassersensor
und eine Entität für den tatsächlichen Mähroboterstandort ausgewählt werden.
Unterstützt werden `lawn_mower`, `vacuum`, `binary_sensor` und frei wählbare
Statussensoren. Der Roboter muss eindeutig an der Station gemeldet sein
(`docked`, beim Binärsensor `on` oder der konfigurierte sichere Zustand).
Fehlt dieser Nachweis, öffnet das Ventil weder automatisch noch manuell.

Ein Wassersensor darf eine Menge in **L**, **m³** oder **gal** oder einen
Durchfluss in **L/min**, **L/h**, **L/s**, **m³/h**, **m³/min** oder **m³/s**
melden. Ohne Messung sind automatische Starts nicht möglich. Ein manueller
Zeitbetrieb ohne Sensor muss ausdrücklich erlaubt werden und verbucht keine
unbekannte Wassermenge im Bodenmodell.
Der ausgewählte Sensor muss **während der Bewässerung** neue Werte liefern;
ein erst nach dem Schließen aktualisierter Mengenzähler kann den fehlenden
Durchfluss während des Betriebs nicht absichern. Prüfe dies beim Einrichten
mit einem kurzen beaufsichtigten Probelauf.
Ein gemeinsamer Zähler ist erlaubt. Die Integration ordnet dessen Zunahme
während der Öffnung des Rasenventils der Bewässerung zu. Verbrauch anderer
Abnehmer im gleichen Zeitraum wird dabei mitgezählt. Bei geschlossenem
Rasenventil wird der Zähler ignoriert. Optional kann der Zustand eines zweiten
Ventils (`switch` oder `binary_sensor`) ausgewählt werden: Ist es offen,
pausiert die Rasenbewässerung; ist sein Zustand unbekannt, schließt das
Rasenventil. Ohne Auswahl gilt das zweite Ventil als geschlossen. Die
Integration schaltet das zweite Ventil nicht selbst.

Mit Ventil startet die bisherige Schaltfläche **Bewässerung erfassen** eine
Sitzung; **Bewässerung stoppen** beendet sie. Die konfigurierbare Mindestdauer
gilt für manuelle Starts, soweit keine Sicherheitsabschaltung nötig ist.
Pausen zählen zur maximalen Gesamtdauer und enden erst nach erneuter Prüfung
der Sicherheitsbedingungen. Die separate Entität **Automatische Bewässerung**
ist anfangs ausgeschaltet.
Sie startet nach einer erfolgreichen Bewässerung nicht erneut am selben lokalen
Tag. Nach einem Start ohne gemessenes Wasser kann sie nach 30 Minuten im passenden
Vorhersagefenster, sofern Wetter, Regenmessung und Wassersensor ausreichend
zuverlässig sind, erneut versuchen.

Ein unabhängiger 15-Sekunden-Wächter schließt das Ventil bei fehlendem,
unplausiblem oder ausbleibendem Durchfluss, Überschreitung von Zeit oder Menge,
Verlust des Stationsstatus oder deaktivierter Automatik. Nach Neustart wird
eine noch gespeicherte Sitzung geschlossen statt fortgesetzt. Die tatsächlich
gemessene Wassermenge wird erst nach bestätigtem Schließen dem Bodenmodell
gutgeschrieben. Der manuelle Zeitbetrieb ohne Messgerät protokolliert den
Bewässerungstag, ohne dem Bodenmodell eine ungemessene Menge gutzuschreiben.
Nach ausreichend gemessenem Regen oder einer Bewässerung empfiehlt der
Mähroboterstatus frühestens am nächsten lokalen Tag und nach zwölf Stunden
wieder das Mähen, sofern kein frischer Blattnässesensor eine genauere Freigabe liefert.
Ein geräteseitiger Abschalttimer ist zusätzlich sinnvoll,
weil Home Assistant bei einem plötzlichen Ausfall oder Funkverlust keine Schaltbefehle mehr senden kann. Beim regulären Herunterfahren versucht die Integration das eigene Ventil vorher zu schließen. Bei einem fehlgeschlagenen Schließversuch versucht die Integration
es erneut; prüfe in diesem Fall das Ventil vor Ort.

Die Integration benötigt keinen weiteren OpenWeatherMap-API-Schlüssel. Sie
liest vorhandene Entitäten und ruft Vorhersagen über Home Assistants
`weather.get_forecasts` ab, ohne OpenWeatherMap direkt anzufragen.

## Wichtige Entitäten

| Entität | Inhalt |
| --- | --- |
| Wachstumsstatus | Winterruhe, Erwachen, Wachstum, Herbst oder Trockenstress; Symbolfarbe als Attribut `icon_color` |
| Pflegestatus | Wichtigster Pflegebedarf mit Düngeempfehlung, NPK, Dosis und Produktmenge als Attributen |
| Mähroboterstatus | Start, regelmäßiges Mähen, Pause bei nassem Rasen oder Winterabschaltung; frühester Mähzeitpunkt als Attribut |
| Modellierte Bodenfeuchte | Geschätzte Feuchte, Wasservorrat und Wasserbilanz |
| Bewässerungsempfehlung | Zeitpunkt, mm, Liter, Regenprognose und empfohlenes Zeitfenster |
| Bewässerungsstatus (mit Ventil) | Laufend, wegen zweitem Ventil oder Versickerung pausiert, abgeschlossen oder gestoppt; letzte gemessene Menge und Stoppgrund |
| Bewässerung – Diagnose (mit Ventil) | Startfreigabe, beide Ventilzustände, Mäherstandort, Zählerwert und Alter, Laufzeit, Zielmenge und Abschaltgrund |
| Automatische Bewässerung – Entscheidung (mit Ventil) | Übersetzter Grund, weshalb ein automatischer Start möglich oder blockiert ist; gegebenenfalls Zeitpunkt des nächsten Versuchs |
| Grünlandtemperatursumme | Vegetationsindikator mit Angaben zur Vollständigkeit |
| Nächste Aktion | Kompakte Handlungsempfehlung |

Diagnose-Entitäten zeigen Datenqualität, Modellvertrauen, Quellen,
Vorhersagealter, Verdunstungsverfahren und weitere Modellwerte. Einige sind
standardmäßig deaktiviert und können in Home Assistant aktiviert werden.

## Bodenwasser und Grenzen

Das Modell führt einen virtuellen Wasserspeicher: wirksamer gemessener Regen
und protokollierte Bewässerung füllen ihn; geschätzte Verdunstung leert ihn.
Dabei berücksichtigt es Bodenart, Wurzeltiefe, Blattbenetzung, Versickerung,
Abfluss und Wasserstress. Die Verdunstung stammt aus Penman-Monteith mit
geschätzter Strahlung oder bei fehlenden Eingangswerten aus Hargreaves-Samani.
Die Regenwahrscheinlichkeit beeinflusst nur die Empfehlung; vorhergesagter
Regen wird niemals als tatsächlich gefallener Regen verbucht.
Fehlt die Außentemperatur vorübergehend, verwendet das Modell eine vorsichtige
saisonale Verdunstungsschätzung und kennzeichnet die Modellgüte als niedrig.
Tageswerte beziehen sich auf die lokale Zeitzone von Home Assistant.

Ohne Messwert für gefallenen Regen bleibt dessen Anteil in der Bodenbilanz
unbekannt. Lokale Schauer, Bodenunterschiede und Schatten können vom Modell
abweichen. Bei Bedarf den Ausgangswert unter **Konfigurieren → Pflegeverlauf → Geschätzte Bodenfeuchte beim Start** korrigieren. NPK und Produktmenge sind
Richtwerte; Herstellerdosierung und Bodenanalyse haben Vorrang.
Der Diagnosewert **Beobachteter Regen heute** bleibt unbekannt, wenn kein
Messwert vorliegt oder die Messreihe für den Tag unterbrochen war. Nach einer
Neuinstallation während des Jahres zeigt die Grünlandtemperatursumme fehlende
frühere Tage an, bis die Jahresgrenze erreicht ist oder ein Ausgangswert
manuell gesetzt wird.

## Anzeige auf dem Dashboard

Home-Assistant-Sensoren setzen ihre Symbolfarbe nicht selbst. Eine
Mushroom-Template-Karte kann das Attribut `icon_color` verwenden:

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

`state_translated(entity)` zeigt den übersetzten Zustand; `states(entity)`
liefert den englischen Rohzustand für Automationen.

Für Einzelheiten früherer Versionen siehe den [Änderungsverlauf](CHANGELOG.md).



## Entfernen und Fehlerdiagnose

Die gesteuerte Bewässerung zunächst stoppen. Unter **Einstellungen → Geräte & Dienste** den Raseneintrag im Menü löschen. Ein laufendes eigenes Ventil wird beim Entladen geschlossen; kann HA die Schließung nicht bestätigen, wird das Entladen verweigert und die Überwachung bleibt aktiv. HACS kann anschließend die Integrationsdateien entfernen; danach Home Assistant neu starten. Die separat eingerichteten Wetter- und Geräteintegrationen bleiben erhalten.

Bei Problemen die Diagnose des Raseneintrags herunterladen und die Sensoren **Bewässerungsbereitschaft**, **Automatikentscheidung** sowie die Reparaturmeldungen prüfen. Automatikstart benötigt verfügbare, frische Wetterdaten, eine sichere Mäherposition und vollständige Mengenmessung. Nach einer Speicherfehlermeldung zuerst freien Speicherplatz und Schreibrechte prüfen; die Meldung wird nach erfolgreichem Speichern aufgehoben. Vor dem erneuten Aktivieren die Einstellungen kontrollieren.
