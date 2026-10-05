# Rasenpflege-Assistent für Home Assistant

**Deutsch** | [English](README.en.md)

Version 3.15.0 · [Änderungsverlauf](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

Diese Integration bewertet Wachstum und Pflegebedarf deines Rasens aus den
vorhandenen OpenWeatherMap-Daten in Home Assistant. Sie berechnet die
Grünlandtemperatursumme, modellierte Bodenfeuchte sowie Empfehlungen zum
Bewässern, Düngen und Mähen. Optional kann sie ein vorhandenes Bewässerungsventil
steuern; sie schaltet den Mähroboter nicht.

Die Wetterquelle lässt sich über **Einstellungen → Geräte & Dienste → Rasenpflege-Assistent → Menü → Neu konfigurieren** wechseln. Weitere Raseneinstellungen bleiben unter **Konfigurieren** verfügbar. Während einer laufenden oder pausierten Bewässerung ist ein Quellenwechsel gesperrt.

Prüfumfang und offene Quality-Scale-Anforderungen stehen im [Qualitätsaudit](docs/quality-audit.md).
Die [Quellcode-Übersicht](docs/source-code.md) erläutert Dateizuständigkeiten und Regeln für die Weiterentwicklung.

## Wetterstopps und Verbrauchslimits

Unter **Konfigurieren → Bewässerung – Sicherheit** stehen diese Einstellungen. Der Wetterstopp ist standardmäßig aktiv: Regen ab 0,5 mm/h bei Ratensensoren beziehungsweise 0,5 mm seit Sitzungsbeginn bei Mengen-/Zählersensoren, Wind ab 8 m/s, Bestätigungsdauer 120 Sekunden. Kurzzeitige Rate-/Windausschläge setzen die Bestätigungszeit zurück, sobald sie abklingen. Bereits gemeldeter Regen oder starker Wind sperrt einen automatischen Start sofort. Ohne gültigen Regensensor verwendet die Integration den aktuellen Wetterzustand. Fehlende Wetterinformationen werden nicht als gemessener Regen interpretiert. Alle Eingaben stammen aus vorhandenen HA-Entitäten; es gibt keine zusätzlichen regelmäßigen OWM-API-Abfragen.

Tages-/Wochenlimits sind mit **0 deaktiviert**. Sie zählen sämtliche erfassten Bewässerungsmengen einschließlich manueller Einträge und Schätzungen; unbekannte oder unvollständige Mengen blockieren automatische Starts im betroffenen Budgetzeitraum. Das automatische Mengenziel wird auf das verbleibende Budget begrenzt. Mess- und Schaltverzögerungen können dennoch Überschreitungen verursachen. Manuelle Starts bleiben durch die bisherigen Sicherheitsgrenzen geschützt. Das zweite Ventil bleibt ausschließlich eine Statusquelle und wird nie geschaltet.

Zählerausfälle, veraltete Messwerte, Einheitenwechsel und unerwartete Zählerrücksetzungen kennzeichnen die Sitzung als unvollständig gemessen. Bereits bekannte Mengen bleiben im Verbrauch erhalten; aktive Tages-/Wochenlimits sperren weitere automatische Starts im betroffenen Zeitraum. Nach mindestens einer Minute bestätigter Bewässerung mit Messlücke gilt der Rasen vorsorglich als nass, auch wenn keine Menge nachweisbar ist. Laufzeit und Abschlusszeit beziehen sich auf die bestätigte Ventilschließung, nicht auf anschließende Speicherwartezeiten.

Das Abschalten der Automatik schließt eine automatisch gesteuerte Bewässerung vor dem Speichern der Einstellung. Eine manuell gestartete Sitzung läuft dabei weiter. Vor dem ersten automatischen Öffnen werden Pflegebedarf, Datenqualität und Prognosefenster nach möglichen Speicherwartezeiten erneut geprüft. Prognosefenster umfassen auch bei Zeitumstellungen eine tatsächlich verstrichene Stunde.

Zeitweise Automatiksperren schließen automatisch gesteuerte Bewässerung ebenfalls vor Speicherwartezeiten. Die Integration prüft nach dem Speichern, ob der gespeicherte Zustand übereinstimmt; Speicherfehler blockieren neue Starts. Bei Einweichpausen zählen Verbrauch und Laufzeit bis zur bestätigten Ventilschließung. Dabei erreichte Ziele, Sicherheitslimits oder Messfehler beenden die Sitzung. Ein Zählerreset unmittelbar nach dem Öffnen kann je Etappe erkannt werden; bereits erfasster Verbrauch bleibt erhalten.

### Prognosen, Verlauf und Rückgängigmachen

Der **Pflegeplan** fasst Mähen, Bewässern und Düngen mit Zeitangaben und Hindernissen zusammen. Der **nächste automatische Bewässerungsstart** schneidet das vorhandene Vorhersagefenster mit Zeitplan, Automatiksperre und Wiederholungswartezeit. Fehlt eine Überschneidung oder eine Voraussetzung, bleibt der Zeitpunkt unbekannt und die Diagnose erklärt den Grund. Die Prognose ist keine Terminreservierung und keine vollständige mehrtägige Simulation.

Die **verbleibende Bewässerungsdauer** schätzt aktive Minuten aus dem Durchfluss; `session_estimated_end` berücksichtigt Einweichpausen. Bei einer Pause wegen des zweiten Ventils ist das Ende unbekannt. Wenn die maximale Gesamtdauer nicht ausreicht, wird kein erreichbares Abschlussdatum versprochen.

**Wasserverbrauch heute** sowie Wochen-/Monatssummen enthalten abgeschlossene oder manuell erfasste Sitzungen. Eine laufende Sitzung wird separat im Bewässerungsstatus und bei den Budgetprüfungen berücksichtigt. `recent_records` zeigt die letzten zehn erfassten Bewässerungen; `recent_sessions` zeigt die letzten zehn Ventilsitzungen. Zählerzuwächse über Mitternacht werden zeitanteilig aufgeteilt und mit `allocation_estimated` gekennzeichnet. Bekannte Gesamtmengen bleiben erhalten. Alte Einträge ohne Messabschnitte behalten ihre bisherige Tageszuordnung.

Rückgängigmachen entfernt die Modellgutschrift. Tatsächlich gemessener Verbrauch einer gesteuerten Bewässerung bleibt im Verbrauchsprotokoll und zählt weiterhin gegen Tages-/Wochenlimits. Fehlerhafte manuelle Verbrauchseinträge werden entfernt. Die physisch gemessene Sitzung bleibt zur Diagnose sichtbar, mit `undone: true`, `undone_at` und `effective_model_mm: 0`. Die einmalige automatische Tagesbewässerung bleibt aus Sicherheitsgründen gesperrt; Rückgängigmachen löst keine neue automatische Bewässerung aus.

Die Aktion `suspend_irrigation` akzeptiert **`duration_hours`** (0,25 bis 168), alternativ zu `until`. Ohne beide Felder wird die Pause aufgehoben. Dashboard-Vorlagen: [Pflegeplan](docs/dashboard/care-plan.de.yaml), [Verbrauch und Verlauf](docs/dashboard/consumption.de.yaml). Die [Bewässerungskarte](docs/dashboard/irrigation.de.yaml) bietet 1/3/5 mm, 100 Liter sowie Pausen für 2/24 Stunden. Weitere individuelle Mengen können im HA-Aktionsdialog gewählt werden.

| Diagnoseattribute | Bedeutung |
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

Die Verbrauchssensoren summieren bekannte erfasste Mengen für die lokale Kalenderwoche (Montag bis heute) beziehungsweise den laufenden Kalendermonat. Attribute trennen Ventilmessungen, manuell gemeldete Mengen, manuelle Schätzungen, ungemessene Sitzungen und Sitzungen mit Messlücken. Unbekannte Mengen werden nicht erfunden; Summen mit Messlücken sind unvollständig. Neue Verbrauchswerte beginnen mit 3.7.0, frühere Sitzungen werden nicht rückwirkend aus der begrenzten Historie geschätzt. Das Verbrauchsjournal wird für etwa ein Jahr gehalten, der Pflegeverlauf weiterhin für die letzten 20 Einträge. Rückgängigmachen entfernt fehlerhafte manuelle Verbrauchseinträge. Tatsächlich gemessener Verbrauch einer gesteuerten Bewässerung bleibt erhalten; während kontrollierter Bewässerung ist Rückgängigmachen gesperrt.

## Diagnoseattribute und Dashboard-Vorlagen

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
| Bodenfeuchte / Datenqualität: `input_diagnostics` | Objekt | Quelle, Rohwert, normalisierter Wert, Einheit, Meldezeit, Alter und Verwerfungsgrund für Wetter-, Regen-, Boden-, Durchfluss- und Sicherheitsquellen. |
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

## Verlauf, Kalibrierungshilfe und Mengen-Erklärung

Die bestehende Bodenfeuchteentität enthält `model_insights`. Der Verlauf speichert höchstens **336 stündliche Momentaufnahmen für 14 Tage**; Sensorattribute enthalten die letzten 24 Aufnahmen, der Diagnoseexport den gesamten begrenzten Verlauf. Innerhalb einer Stunde werden Regen und Verdunstung zusammengefasst. Wechsel von Bodensensor, Trocken-/Nassreferenzen, Bodenprofil oder Wurzeltiefe starten die Vergleichsdaten neu. Pflegehistorie und Verbrauch bleiben erhalten.

| Diagnose | Bedeutung |
| --- | --- |
| `model_insights.calibration` | Unabhängige Sensorberichte, Beobachtungsdauer, mediane Abweichung vor der Sensorkorrektur, Referenzen und lesbare Prüfhilfen. |
| `model_insights.watering_response` | Gemessene Liter der letzten gesteuerten Sitzung und beobachtete Feuchteänderung; unvollständige Mengen, Regen und Verlaufszeitlücken verhindern eine sichere Zuordnung. |
| `model_insights.initialization` | Bekannter Modellbeginn, Beginn der Diagnoseaufzeichnung, fehlende historische Temperaturtage und Aufbewahrungsgrenzen. |
| Datenqualität: `model_initialization`, `data_gaps` | Getrennte Hinweise auf unbekannten gemessenen Regen, veraltetes Wetter, veraltete Prognose und nicht integrierte Modellstunden. |
| Bewässerungsempfehlung / nächste Aktion: `watering_explanation` | Wasservorrat, 80-%-Modellziel, Fehlmenge, erwartete Verdunstung, Regenprognose, Fläche, Wirkungsgrad, auszubringende mm/Liter und geschätzter wirksamer Bodenbeitrag. |
| Bewässerungsdiagnose: `next_check` | Lokale Sicherheitsprüfung normalerweise spätestens nach 15 Sekunden, geschätzte Modellaktualisierung im 30-Minuten-Rhythmus und bevorstehende Sperr-/Prognosegrenzen. Zustandsereignisse können früher prüfen; dies ist keine Startzusage. |

Die Kalibrierungshilfe benötigt **mindestens sechs unterschiedliche Sensorberichte über mindestens 24 Stunden**. Eine mediane Abweichung ab 20 Prozentpunkten oder dauerhaft an den Referenzgrenzen liegende Werte führen zu Prüfhilfen. Derselbe wiederholt verwendete Bericht zählt einmal. Das ist eine Heuristik; überprüfe zunächst Niederschlagsquelle, Trocken-/Nassreferenzen, Messbereich, Sensorposition und Bodenprofil. Es werden **keine Parameter automatisch geändert**.

Für die Reaktionsprüfung werden Sensorberichte höchstens sechs Stunden vor dem Beginn und zwischen 30 Minuten und 24 Stunden nach dem Ende einer vollständig gemessenen gesteuerten Bewässerung benötigt. Ein fehlender Feuchteanstieg beweist keinen Gerätefehler. Das Programm leitet weder einen gemessenen Wirkungsgrad noch eine automatische Dosiskorrektur daraus ab. Der Wirkungsgrad bleibt deine Einstellung.

Die vorhandene Dosierungsregel bleibt erhalten: empfohlene mm und Liter sind **auszubringendes Wasser**; geschätzter wirksamer Bodenbeitrag ist mm × Wirkungsgrad. Die Empfehlung berücksichtigt Prognose, Verdunstung, Rundung und Mengengrenzen und ist deshalb nicht einfach Fehlmenge ÷ Wirkungsgrad. Verbrauchs-/Sicherheitsgrenzen können die automatische Sitzungszielmenge zusätzlich begrenzen.

Bei einem Update aus älteren Versionen bleibt der tatsächliche Modellbeginn unbekannt, wenn er nie gespeichert wurde. Die Diagnoseaufzeichnung beginnt beim Update; frühere Beobachtungen werden nicht erfunden. Eine Modellzeitlücke beweist allein keinen HA-Ausfall, deshalb bleibt die Ursache ausdrücklich unbekannt. Die [Diagnosekarte](docs/dashboard/diagnostics.de.yaml) zeigt die neuen Prüfhilfen und die Mengen-Erklärung. Neue Pflichtsensoren oder zusätzliche regelmäßige OWM-Abfragen sind dafür nicht erforderlich.

## Pflegeprioritäten, Wochenvergleich und Zyklushinweise

`care_plan.prioritized_steps` erläutert die Reihenfolge bestehender Empfehlungen: fehlende Temperaturdaten oder Frost zuerst prüfen, gegebenenfalls bewässern, trockenen Rasen abwarten, im empfohlenen Fenster mähen und bei Bedarf düngen. Jeder Schritt enthält `action`, `after`, lesbare Texte und gegebenenfalls `not_before`. Das sind Planungshinweise, keine automatisch ausgeführten Aktionen.

`model_insights.weekly_comparison` vergleicht zwei aufeinanderfolgende Zeiträume von jeweils 168 echten Stunden, auch über Zeitumstellungen: aufgezeichneten Regen, geschätzte tatsächliche Verdunstung, mittlere Modellfeuchte und eingetragene Liter. `recording_sufficient` verlangt mindestens 160 unterschiedliche Stunden ohne größere Lücken; ein Regen-Gesamtwert erscheint nur bei ausreichender Aufzeichnung und durchgehend bekannter Regenquelle. Teilaufzeichnungen bleiben als `partial_history` erkennbar. Verbrauch wird anhand lokaler Kalendertage zugeordnet; diese Randzuordnung ist geschätzt. `unknown_volume_records` und `estimated_volume_records` halten Messlücken und manuelle Schätzungen sichtbar. Historische Daten vor dem Update werden nicht ergänzt.

`sensor_review` in Modell- und Datenqualitätsattributen weist auf wiederholte Ausfälle oder auffällig gleichbleibende Feuchte hin. Ein konstanter Wert wird erst nach sechs unabhängigen Meldungen über mindestens 24 Stunden und mindestens zehn Prozentpunkten Modelländerung auffällig. Derselbe wiederverwendete Bericht zählt einmal. Das ist ein Prüfhinweis, kein bestätigter Sensordefekt.

Die Bewässerungsdiagnose enthält `cycle_plan`: aktive Minuten, Zykluszahl, dazwischenliegende Sickerpausen und Gesamtdauer aus den vorhandenen Einstellungen. Grundlage ist verwertbarer Durchfluss einer eigenen laufenden Sitzung oder eine vollständig gemessene Sitzung der letzten sieben Tage. Fremder Verbrauch am gemeinsamen Zähler liefert keine Laufzeitschätzung. Ohne Grundlage bleiben die Zeiten unbekannt. Bei laufenden Sitzungen gelten Restzielmenge und verbleibende Sicherheitslaufzeit; die aktuelle Zyklusphase bleibt geschätzt. Liegt die Ausbringrate über der Bodenprofil-Aufnahme, werden kurze Zyklen und Sickerpausen zur manuellen Prüfung vorgeschlagen. Diese Faustwerte ändern weder Einstellungen noch Ventile und ersetzen keine Prüfung der Wasserverteilung vor Ort.

`live_robot_session` an der Mähstatusentität und `mowing_observation` im Diagnoseexport zeigen aktive/inaktive Minuten, Unterbrechungen, Mindestdauer, Beobachtungsgrund und letzte gespeicherte Beobachtung. Pausen und Rückfahrten zählen nicht als aktive Mähzeit; verspätete Ereignisse werden verworfen. Eine Stationserkennung nach ausreichender Aktivität bleibt eine Schätzung: `coverage_confirmed` ist immer `false`. Der Assistent sendet keine Mäherbefehle.

Die [Pflegeplankarte](docs/dashboard/care-plan.de.yaml) und [Diagnosekarte](docs/dashboard/diagnostics.de.yaml) zeigen diese Hinweise aus vorhandenen Daten. Es erfolgen keine zusätzlichen regelmäßigen OWM-Abfragen.

## Geeigneter Mähbeginn und Taurisiko

Die vorhandenen Entitäten **Mähstatus** und **Pflegeplan** zeigen `mowing_window`. **Datenqualität** enthält `mowing_window_quality`; der Diagnoseexport enthält dieselben Informationen unter `mowing_window`. Es werden keine neuen Entitäten angelegt. Der bisherige `next_mowing_at` bleibt die früheste Fälligkeit aus Mähintervall und Nassrasenpause; `mowing_window.start` ist davon getrennt der nächste ausreichend belegte Wettertermin.

| Attribut | Bedeutung |
| --- | --- |
| `start`, `end` | Geschätztes geeignetes Mähfenster innerhalb der nächsten 48 echten Stunden, mit lokaler Zeitzone; ohne ausreichende Daten `null`. |
| `current_dew`, `window_dew` | Aktuelles bzw. zum empfohlenen Beginn geschätztes Taurisiko, Taupunkt in °C, Abstand zur Lufttemperatur und Quelle. |
| `reason_text`, `blockers_text` | Erklärung des empfohlenen Fensters oder der ausgeschlossenen Zeitpunkte. |
| `missing_inputs`, `missing_inputs_text` | Fehlende Temperatur-, Niederschlags-, Wind- oder Tauinformationen. |
| `leaf_wetness` | Vorhandener optionaler Blattnässe-Sensor: `wet`, `dry`, `unknown` oder `not_configured`. |
| `estimated`, `surface_dry_confirmed` | Die Wetterempfehlung bleibt eine Schätzung; trockener Rasen wird nicht als bestätigt behauptet. |

Unter **Optionen → Mähen** lassen sich Beginn und Ende des täglichen Mähzeitfensters einstellen, standardmäßig **09:00–20:00 Uhr**. Gleiche Uhrzeiten erlauben den ganzen Tag; ein früheres Ende erlaubt ein Fenster über Mitternacht. Diese Zeiten dienen ausschließlich Empfehlungen und steuern keinen Mäher.

Die Planung verwendet vorhandene, frische HA-Wetterdaten und den vorhandenen Stundenprognosecache. Sie berücksichtigt Intervallfälligkeit, Nassrasenpausen nach Regen/Bewässerung, laufende Bewässerung, Frost, Hitze ab 28 °C, Wind über 8 m/s sowie prognostizierten Regen oder Regenwahrscheinlichkeit ab 50 %. Jede Prognose deckt höchstens eine Stunde ab; Lücken werden nicht als trocken ausgefüllt. Aktuelle Wetterdaten werden höchstens für die nächste Stunde verwendet, niemals als Luftfeuchte für morgen.

Ein mitgelieferter Taupunkt wird bevorzugt; andernfalls wird er aus Temperatur und relativer Luftfeuchte nach der [Bolton-Umkehrformel](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.dewpoint.html) geschätzt. Ein Temperaturabstand bis 2 °C gilt als hohes, bis 4 °C als erhöhtes Taurisiko. Diese Grenzen sind Heuristiken, keine validierten Rasentemperaturen. Nach erkanntem Tau-, Nebel- oder Frostrisiko wird zunächst eine zusammenhängende trockene Prognosestunde mit geringem Risiko abgewartet. Ein frischer trockener Blattnässewert überschreibt nur die aktuelle Tau-Einschätzung, nicht Regen, Frost, künftige Tauwerte oder eine laufende Bewässerung. Ungültige oder zukünftige gespeicherte Nassrasen-Zeitstempel werden nicht als gültige Pause verwendet; ohne frischen trockenen Blattnässewert bleibt das Mähfenster dann unbekannt. Bei fehlender Luftfeuchte und fehlendem Taupunkt bleibt das Risiko unbekannt; Tagesprognosen werden nicht in erfundene Stundenwerte umgerechnet. Welche Prognosefelder verfügbar sind, hängt vom HA-Wetteranbieter ab ([HA-Prognosefelder](https://www.home-assistant.io/actions/weather.get_forecasts/)).

**Rasen vor dem Mähen vor Ort auf Nässe prüfen.** Die Lufttemperatur entspricht nicht zwingend der Grastemperatur; geringes Taurisiko bestätigt keine trockene Oberfläche ([NWS: Tauentwicklung](https://www.weather.gov/source/zhu/ZHU_Training_Page/fog_stuff/Dew_Frost/Dew_Frost.htm)). Automatische Mäherbefehle und zusätzliche regelmäßige OWM-Abfragen erfolgen nicht.

`prioritized_steps` enthält zusätzlich `availability`/`availability_text` (`now`, `later`, `blocked`, `not_needed`) und einen lesbaren Blockierungsgrund. Die Mähaktion verwendet den Wettertermin als `not_before`; abgelaufene Nassrasenzeiten erzeugen keine neue Warteempfehlung. Der Wochenvergleich enthält unter `changes` nachvollziehbare Regen-/Verdunstungs-/Verbrauchsdifferenzen; unvollständige Vergleichswerte bleiben unbekannt. Zyklusschätzungen berücksichtigen den Rest der aktuellen Zyklusphase, laufende Sickerpausen und die verbleibende Mindestlaufzeit einer manuellen Standardbewässerung. Bei einer Pause ohne bekanntes Ende bleibt die Gesamtdauer unbekannt.

Widersprüchliche Prognoseeinträge für denselben absoluten Zeitpunkt werden als unbekannter Datensatz erhalten. Sie werden weder addiert noch als trockene Stunde ausgewählt. Ist die relevante Bewässerungsprognose betroffen, wird deren Vertrauen auf niedrig gesetzt und der automatische Start gesperrt; die Datenqualität zeigt `forecast_conflict`.

Unter **Optionen → Mähen → Benötigte Mähdauer** lässt sich die erforderliche Dauer eines vollständigen Mähdurchgangs einstellen (0–1440 Minuten). Der Standardwert **0** behält die bisherige Planung ohne Mindestdauer bei. Mit beispielsweise **120 Minuten** werden nur zusammenhängende belegte Fenster von mindestens zwei echten Stunden empfohlen. Prognoselücken, Wetterhindernisse und das Ende des erlaubten Mähzeitfensters teilen die Fenster; Zeitumstellungen ändern nicht die benötigte echte Laufzeit.

`required_minutes` enthält die eingestellte Dauer, `available_minutes` die verfügbare Länge des empfohlenen Fensters. `alternative` zeigt das nächste getrennte ausreichend lange Fenster mit `start`, `end` und `available_minutes`; ohne zweiten geeigneten Termin bleibt es `null`. Es handelt sich um einen Ausweichtermin, nicht um einen zweiten Start innerhalb desselben Fensters.

`quality` ist `estimated` bei einer belegten Empfehlung und `insufficient` ohne ausreichendes Fenster. `quality_text` und `quality_reasons_text` erklären dies in der HA-Sprache. `missing_inputs_text` beschreibt fehlende Informationen im untersuchten Zeitraum; fehlende Werte außerhalb des empfohlenen Fensters machen dessen Qualität nicht automatisch unzureichend. Die Empfehlung bestätigt weiterhin keine trockene Rasenoberfläche. Mähdauer und Ausweichtermin erscheinen in den aktualisierten Mäh- und Pflegeplankarten.

### Mähtage, Dauer-Vorschlag und Änderungen

Unter **Optionen → Mähen** sind erlaubte Wochentage und optionale Wochenendzeiten einstellbar. Leere Wochenendfelder übernehmen die allgemeinen Zeiten; eine leere Tagesauswahl sperrt alle Empfehlungen. Nachtfenster gehören zum Starttag, auch beim Wechsel von Freitag auf Samstag. Es erfolgt keine Mähersteuerung.

`duration_suggestion` zeigt die typische Durchgangsdauer aus mindestens drei vergleichbaren Roboterbeobachtungen der letzten 90 Tage. Es werden höchstens zehn geeignete Durchgänge verwendet: aktive Zeit mindestens entsprechend der Erfassungsgrenze, mindestens 85 % der Gesamtdauer, höchstens eine Unterbrechung und gleiche Quelle/Erfassungseinstellungen. Stark schwankende, alte oder unvollständige Daten ergeben keinen Vorschlag. Neue Aufzeichnungen enthalten die nötigen Angaben; alte Datensätze werden nicht nachträglich als vollständige Beobachtungen gewertet. **Eine Rückkehr zur Ladestation bestätigt keine vollständige Fläche.** Kurze Rückkehr-/Pausenzeiten sind in der vorgeschlagenen Gesamtdauer enthalten. Der Vorschlag ist geschätzt und wird nicht automatisch als benötigte Mähdauer übernommen.

`forecast_updated_at`, `forecast_age_minutes` und `weather_age_minutes` zeigen die Aktualität; fehlende Werte bleiben unbekannt. `change` erklärt wesentliche Änderungen des empfohlenen Beginns seit dem laufenden HA-Start anhand von Wetter-/Tauinformationen, Datenlücken, Nassrasenpause oder Mähfälligkeit. Kleine Uhrverschiebungen unter 15 Minuten werden unterdrückt. Neustart/Neuladen setzt die Vergleichsbasis zurück; Attributabfragen ändern den Verlauf nicht.

Die Bodenmodell-Diagnose enthält unter `explanation` eine lesbare Bilanz des **letzten Rechenschritts**: Anfang + wirksamer Regen − Verdunstung − Drainage + Sensorkorrektur = Ende. Eine letzte Bewässerungsgutschrift steht separat, weil sie bereits im Anfangswert enthalten sein kann. Sie darf nicht erneut addiert werden. Die Werte beschreiben das Modell und bestätigen keine Messgenauigkeit im Boden.

## Erweiterte Modelldiagnose

Unter **Einstellungen → Geräte & Dienste → Rasenpflege-Assistent → Diagnose herunterladen** enthält der Export `inputs`, `soil_model`, `storage` und `updates`. Die Bodenfeuchteattribute zeigen zusätzlich `model_diagnostics`, `model_confidence_reasons`, deren lesbare Texte und `sensor_deviation_percentage_points`. Die Datenqualität enthält Speicher- und Aktualisierungsdiagnosen. Die Diagnose liest vorhandene Daten und schaltet keine Geräte.

`soil_model.last_balance` erklärt den letzten Berechnungsschritt: verstrichene und tatsächlich integrierte Stunden, Anfangsvorrat, korrigierten Regen, Blattbenetzung, wirksamen Regen, Abfluss, Drainage, tatsächliche Verdunstung und abschließende Sensorkorrektur in Millimetern. `balance_residual_mm` zeigt den Rundungsrest der Bilanz vor der separat ausgewiesenen Sensorkorrektur. Protokollierte Bewässerungen verändern den Speicher bei ihrer Buchung und sind keine zusätzlichen Regenmengen in diesem Berechnungsschritt.

Das Modellvertrauen ist eine Diagnoseheuristik. Unbekannter beobachteter Regen, veraltetes Wetter, Modellzeitlücken, saisonal geschätzte Verdunstung oder mindestens 20 Prozentpunkte Abweichung zwischen Sensor und Modell vor der Korrektur setzen es auf niedrig. Der Grenzwert ist kein statistisches Konfidenzintervall. Ohne gültigen Bodensensor ist das Vertrauen höchstens mittel. Auch hohes Vertrauen bestätigt keine vor Ort gemessene Modellgenauigkeit. Sensorkorrekturen erfordern eine neue Meldung und mindestens sechs Stunden seit der letzten Korrektur; derselbe unveränderte Messwert wird nicht wiederholt eingemischt.

`storage` zeigt letzte erfolgreiche Speicherung, letzte fehlgeschlagene Operation (`save` oder `verify`), Exception-Typ, aufeinanderfolgende Fehler und laufende Schreibvorgänge. `updates` zeigt die letzte erfolgreiche bzw. fehlgeschlagene Berechnung. Fehlerhistorie bleibt nach einer Erholung bis zum Neuladen sichtbar; diese Diagnosezähler werden nicht dauerhaft gespeichert. Fehlertexte und Dateipfade werden nicht exportiert.

## Bodenwasser und Grenzen

Das Modell führt einen virtuellen Wasserspeicher: wirksamer gemessener Regen
und protokollierte Bewässerung füllen ihn; geschätzte Verdunstung leert ihn.
Der Prozentwert bezeichnet den Anteil an der modellierten pflanzenverfügbaren Wurzelzonenkapazität, nicht den volumetrischen Wassergehalt eines Sensors. Das Ein-Speicher-Modell verwendet profilbasierte Bodenparameter und geschätzte Strahlung sowie Tages-/Nachtverteilung. Es ist nicht durch lokale Feldmessungen validiert. Die Wasserstressfunktion wird innerhalb eines Zeitschritts integriert, damit trockene Zeiträume bei unterschiedlichen Berechnungsintervallen vergleichbar bleiben.

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

### Nachvollziehbare Pflegehinweise und abgeschlossene Sitzungen

Der Pflegeplan ergänzt `summary`: die erste bereits priorisierte Handlung mit Verfügbarkeit, frühestem Zeitpunkt und Erklärung. Fehlende Belege, die ein Mähfenster verhindern, stehen in `mowing_window.evidence.blocking`; zusätzliche Unsicherheit über das Roboterprogramm steht separat unter `supporting_unknown`. Lücken außerhalb eines empfohlenen Fensters bleiben unter `excluded_horizon_inputs` sichtbar.

Der Dauer-Vorschlag zeigt die verwendeten Durchgänge, aktive/verstrichene Minuten, Minimum/Maximum und gezählte Ausschlussgründe. Fläche und Beobachtungsquellen müssen übereinstimmen. Programm-/Bereichsmerkmale werden nur berücksichtigt, wenn die Mäherquelle sie tatsächlich meldet. Änderungen während eines Durchgangs schließen ihn vom Dauervergleich aus. Fehlende Programmmerkmale bestätigen weder dasselbe Programm noch vollständige Flächenabdeckung. Ältere Einträge ohne Flächenkontext bleiben im Pflegeverlauf, dienen aber nicht als vergleichbare Dauermessung.

`retrospective` vergleicht beendete, zuvor gespeicherte Mähfenster mit später gemeldeten Wetterpunkten. Maximal zwölf Empfehlungen werden sieben Tage gespeichert; die Auswertung verwendet höchstens 96 vorhandene Wetteraufnahmen. Mindestens zwei verschiedene aktuelle Berichtszeitpunkte, höchstens 45 Minuten Abstand zwischen ihnen und zu den Fenstergrenzen sind erforderlich. Wiederverwendete, veraltete oder widersprüchliche Meldungen liefern keine vollständige Evidenz. Die Ergebnisse unterscheiden passende Wetterpunkte, beobachtete Hindernisse und unzureichende Belege. **Weder durchgehend passendes Wetter noch trockene Grashalme werden dadurch bestätigt.**

`water_balance` im Bewässerungsstatus und in der Bereitschaftsdiagnose trennt Sollmenge, erfasste Liter, Rest zum damaligen Soll und wirksame Modellgutschrift. Messlücken lassen die Restmenge unbekannt; durchflussbasierte Mengen sind als Schätzung gekennzeichnet. Modellliter werden nur mit der gespeicherten Sitzungsfläche berechnet; bei älteren Sitzungen kann diese Angabe fehlen. Ein Abbruch startet keine Restbewässerung. Vor einem neuen Start sind die aktuellen Sicherheitsbedingungen erneut zu prüfen.

`data_gaps.impact_text` erklärt die Wirkung früherer Modelllücken. Eine neue Bodenmessung kann den aktuellen Zustand stützen; fehlender historischer Regen und Verdunstung werden damit nicht rekonstruiert. Die [Diagnosekarte](docs/dashboard/diagnostics.de.yaml) zeigt diese Hinweise und die Wasserbilanz, die [Pflegeplankarte](docs/dashboard/care-plan.de.yaml) die kompakte nächste Handlung.
