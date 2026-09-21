# Rasenpflege-Assistent für Home Assistant

**Deutsch** | [English](README.en.md)

Version 2.1.0

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

Diese Custom Integration bewertet einen Rasen aus den vorhandenen Daten der
Home-Assistant-Integration **OpenWeatherMap**. Sie berechnet Wachstum,
Grünlandtemperatursumme, eine modellierte Bodenfeuchte sowie Empfehlungen für
Bewässerung und Düngung. Sie steuert weder Bewässerung noch Mähroboter selbst.

## Voraussetzungen

- Home Assistant 2026.4.0 oder neuer
- eingerichtete OpenWeatherMap-Integration
- empfohlen: OpenWeatherMap-Modus `v3.0`, weil dieser aktuelle Wetterdaten,
  stündliche und tägliche Vorhersagen gemeinsam bereitstellt

Es wird kein zusätzlicher OpenWeatherMap-API-Schlüssel benötigt. Die Integration
liest ausschließlich bereits in Home Assistant vorhandene Entitäten und ruft
Vorhersagen über `weather.get_forecasts` ab.

## Funktionen

- GUI-Einrichtung und GUI-Optionen
- Auswahl und Prüfung einer OpenWeatherMap-Wetterentität
- frei wählbarer Außentemperatursensor mit automatischem OpenWeatherMap-Fallback
- optionaler Sensor für gemessene Niederschlagsmenge oder -intensität
- optionaler physischer Bodenfeuchtesensor zur sanften Modellkalibrierung
- OpenWeatherMap-Tagesvorhersage als automatisch gekennzeichneter Fallback
- stündliche Regenauswertung für 24, 48 und 72 Stunden
- optionale Binärsensoren für „Rasen wurde gemäht“ und „Rasen wurde bewässert“
- Grünlandtemperatursumme mit der Gewichtung Januar 0,5, Februar 0,75 und ab
  März 1,0
- Wachstumsstatus:
  - Daten werden gesammelt
  - Winterruhe (Wachstumsstopp)
  - Erstes Erwachen (zaghaftes Wachstum)
  - Nachhaltiger Vegetationsbeginn (volles Wachstum)
  - Aktives Wachstum
  - Langsames Wachstum
  - Wachstum verlangsamt (Herbst)
  - Hitze- oder Trockenstress
- eigener Mähroboterstatus mit konkreten Handlungsanweisungen, Saisonhinweisen
  und dem letzten Mähdatum als Attribute
- modellierte Bodenfeuchte in Prozent
- Bewässerungsempfehlung mit Zielmenge in mm und Litern
- saisonale NPK-Empfehlung und Produktmenge
- Diagnose-Download über Home Assistant
- eigener Diagnosebereich mit Datenqualität, Modellvertrauen und Datenquellen
- Sensor „Nächste Aktion“ als kompakte Handlungsempfehlung
- Reparaturhinweise bei fehlenden Wetter- oder konfigurierten Eingangsdaten
- automatische Migration einer Konfiguration aus Version 1.0.0
- HACS-kompatible Repository-Struktur und Release-Workflow

## Modellierte Bodenfeuchte

Das Modell verwendet einen virtuellen Wasserspeicher in der durchwurzelten
Bodenschicht:

```text
neuer Wasserstand = alter Wasserstand
                    + wirksamer Regen
                    + protokollierte Bewässerung
                    - geschätzte Rasenverdunstung
```

Die Speichergröße hängt von der Bodenart ab. Die tägliche
Referenzverdunstung wird mit der Hargreaves-Samani-Methode aus Minimum,
Maximum, Datum und geografischer Breite geschätzt. Ein Rasenfaktor reduziert
die Verdunstung im Winter.

Mit einem optionalen Niederschlagssensor verwendet das Modell tatsächlich
gemessene Niederschlagswerte. Ohne Sensor dient die bereits von Home Assistant
zwischengespeicherte OpenWeatherMap-Tagesvorhersage als Schätzung. Die
Modellqualität wird abhängig von der verfügbaren Datenquelle als `high`,
`medium` oder `low` gekennzeichnet. Wird der optionale
Binärsensor „Rasen wurde bewässert“ eingeschaltet, ergänzt die Integration die
berechnete Wassermenge beziehungsweise die konfigurierbare Standardmenge im
virtuellen Speicher.

Der Wert `forecast_rain_mm` bezeichnet die Summe der ersten drei täglichen
Vorhersagezeiträume. Die Integration ruft OpenWeatherMap nicht selbst auf:
`weather.get_forecasts` liest den Cache der offiziellen Home-Assistant-
Integration. Der Forecast wird im Rasenpflege-Assistenten zusätzlich eine
Stunde lang zwischengespeichert.

Die modellierte Bodenfeuchte ist kein Ersatz für einen Bodensensor. Schatten,
Gefälle, Bodenverdichtung, Dachüberstände und lokale Schauer können zu
Abweichungen führen. Über **Konfigurieren → Modellierte Bodenfeuchte neu
kalibrieren** kann der virtuelle Speicher korrigiert werden.

## Wachstums- und Mähroboterlogik

Der Wachstumsstatus kombiniert:

- Grünlandtemperatursumme
- mittlere Temperatur der letzten sieben vollständigen Tage
- Jahreszeit
- modellierte Bodenfeuchte
- Bestätigung, ob die Mähsaison bereits gestartet wurde

Als Frühjahrsrichtwert dient eine Grünlandtemperatursumme von 200. Werden
zusätzlich etwa 8 °C im Sieben-Tage-Mittel erreicht und besteht kein
Trockenstress, meldet der Mähroboterstatus **Mähroboter wieder starten**. Danach
entweder die Schaltfläche **Mähen protokollieren** drücken oder den optionalen
Binärsensor „Rasen wurde gemäht“ kurz einschalten. Das Ereignis speichert zugleich
das letzte Mähdatum und bestätigt den Saisonstart. Der Hinweis bleibt für den
Rest des Kalenderjahres quittiert und wird am 1. Januar zurückgesetzt.

Im Herbst wird bei sinkender Sieben-Tage-Temperatur zunächst
**Mähhäufigkeit im Herbst reduzieren** gemeldet. Bei einem Wachstumsstopp folgt
**Für den Winter abschalten**. Trockenstress führt unabhängig von der
Jahreszeit zur Empfehlung, das Mähen vorübergehend zu pausieren.

## Außentemperaturquelle

Unter **Konfigurieren** kann ein beliebiger Home-Assistant-Temperatursensor als
lokale Außentemperatur gewählt werden. Solange dieser einen gültigen Wert
liefert, hat er Vorrang. Ohne Auswahl oder bei `unavailable`/`unknown` verwendet
die Integration automatisch die aktuelle Temperatur der ausgewählten
OpenWeatherMap-Wetterentität. Die tatsächlich verwendete Entität steht als
Attribut `temperature_source` am Wachstums- und Mähroboterstatus.

## Installation

### Installation über HACS

1. In HACS **Integrationen** öffnen.
2. Über das Drei-Punkte-Menü **Benutzerdefinierte Repositories** wählen.
3. Als Repository
   `https://github.com/sisimon1904/home-assistant-rasenpflege-assistent`
   und als Kategorie **Integration** eintragen.
4. Den Rasenpflege-Assistenten herunterladen und Home Assistant neu starten.
5. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **Rasenpflege-Assistent** suchen.

### Manuelle Installation

1. Den Ordner `custom_components/rasenpflege_assistent` vollständig nach
   `/config/custom_components/rasenpflege_assistent` kopieren.
2. Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
4. Nach **Rasenpflege-Assistent** suchen.
5. OpenWeatherMap-Wetterentität, optionale Ereignissensoren und Rasenparameter
   auswählen.

## Aktualisierung von Version 1.0.0

1. Den vorhandenen Ordner
   `/config/custom_components/rasenpflege_assistent` ersetzen.
2. Home Assistant neu starten.
3. Beim nächsten Start migriert Home Assistant den Konfigurationseintrag
   automatisch auf Version 5.
4. Danach unter **Einstellungen → Geräte & Dienste → Rasenpflege-Assistent →
   Konfigurieren** die anfängliche Bodenfeuchte prüfen. Ab Version 1.2.0 kann
   dort zusätzlich ein lokaler Außentemperatursensor ausgewählt werden.

## Änderungen in Version 1.3.0

- Die früheren Entitäten „Düngeempfehlung“ und „Status“ sind im neuen
  **Pflegestatus** zusammengeführt. NPK-Typ, Dosierung, Gesamtmenge, Zeitfenster
  und Begründungen bleiben als Attribute erhalten.
- „Mähroboterstart empfohlen“ und „Mähroboter kann abgeschaltet werden“ sind nun
  Attribute des **Mähroboterstatus**. Die alten doppelten Entitäten werden beim
  Start entfernt.
- Wachstums-, Pflege- und Mähroboterstatus liefern das Attribut `icon_color` für
  Dashboard-Karten, die dynamische Symbolfarben unterstützen. Das normale
  Home-Assistant-Entitätsmodell kann eine Symbolfarbe nicht selbst erzwingen.
- Optionale Binärsensoren protokollieren Mähen und Bewässern automatisch bei
  einer Aus→Ein-Flanke. Ist ein Sensor nicht konfiguriert, bleibt die passende
  manuelle Schaltfläche erhalten.

## Fehlerbehebung in Version 1.3.1

- Behebt einen Einrichtungsfehler durch die irrtümliche Übergabe von
  `last_mowing` an die Berechnung der Düngeempfehlung.

## Automatische Updates mit HACS

Neue stabile Versionen werden als GitHub-Releases wie `v2.0.0` veröffentlicht.
Eine über HACS installierte Kopie zeigt diese anschließend als Update an. Eine
nur manuell nach `custom_components` kopierte Integration kann Home Assistant
nicht selbst aus dem Internet aktualisieren.

## Wichtige Entitäten

- Pflegestatus
- Wachstumsstatus
- Mähroboterstatus
- Modellierte Bodenfeuchte
- Grünlandtemperatursumme
- Bewässerungsempfehlung
- empfohlene Wassermenge
- empfohlene Düngermenge
- Bewässerung fällig
- Düngung fällig
- Mähen protokollieren (wenn kein automatischer Binärsensor gewählt ist)
- Bewässerung protokollieren (wenn kein automatischer Binärsensor gewählt ist)
- Düngung protokollieren

## Änderungen in Version 2.0.0

- Python-Quellcode und interne Zustände sind vollständig englisch. Deutsche und
  englische Anzeigen werden über Home-Assistant-Übersetzungen bereitgestellt.
- Gemessener und vorhergesagter Niederschlag werden getrennt behandelt.
- Optionaler Niederschlagssensor für `mm` oder `mm/h`; ohne Sensor bleibt die
  OpenWeatherMap-Tagesvorhersage als gekennzeichnete Schätzung aktiv.
- Die Bewässerungsmenge wird aus dem modellierten Wasserdefizit berechnet.
- Die Standardmenge einer protokollierten Bewässerung ist konfigurierbar.
- Der Mähroboterstatus berücksichtigt das letzte Mähen und liefert empfohlenes
  Intervall sowie nächsten Mähtermin.
- Wetterdatenquelle, Forecast-Zeitpunkt und Modellvertrauen sind als Attribute
  verfügbar.
- Bestehende Konfigurationen werden automatisch auf Konfigurationsversion 4
  migriert. Durch die neuen englischen Rohzustände müssen Automationen, die
  bisher deutsche Zustandstexte verglichen haben, angepasst werden.

### Dynamische Symbolfarben mit Mushroom

Die Attribute `icon_color` können beispielsweise so verwendet werden:

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

`states(entity)` liefert bei übersetzbaren Enum-Sensoren den stabilen englischen
Rohzustand. `state_translated(entity)` zeigt dagegen den zur Sprache des
Home-Assistant-Benutzers passenden Zustand an.

## Änderungen in Version 2.0.1

- Deutsche README bleibt die Standardansicht auf GitHub und in HACS.
- Eine vollständige englische README ist über die Sprachauswahl erreichbar.
- Statische Metadaten verwenden den englischen Namen `Lawn Care Assistant`;
  Home Assistant zeigt über seine Übersetzungen weiterhin
  **Rasenpflege-Assistent** an.
- Veraltete Angaben zur Konfigurationsversion und Standard-Bewässerungsmenge
  wurden korrigiert.
- Das Mushroom-Beispiel verwendet den übersetzten Zustand.

## Änderungen in Version 2.1.0

- Stündliche OpenWeatherMap-Vorhersagen werden für die kommenden 24, 48 und
  72 Stunden ausgewertet, ohne OpenWeatherMap direkt abzufragen.
- Ein optionaler physischer Bodenfeuchtesensor gleicht das Bodenmodell höchstens
  alle sechs Stunden mit 25 % Annäherung an den Messwert an.
- Der neue Sensor **Nächste Aktion** fasst die wichtigste anstehende Maßnahme
  zusammen.
- Diagnose-Entitäten zeigen Datenqualität, Modellvertrauen, Forecast-Alter,
  Niederschlag, Datenquellen, Bodenwasservorrat und Verdunstung.
- Home Assistant erzeugt Reparaturhinweise, wenn Temperatur, Vorhersagen oder
  konfigurierte Eingangssensoren nicht verfügbar sind.
- Bestehende Konfigurationen werden automatisch auf Konfigurationsversion 5
  migriert.

## Grenzen

Das Bodenmodell ist eine nachvollziehbare Schätzung, keine Messung. Die
Düngermenge bezeichnet die ungefähre Produktmenge und nicht die reine
Nährstoffmenge. Maßgeblich bleiben die Herstellerdosierung, eine Bodenanalyse
und örtliche Vorschriften. Nicht auf gefrorenem, ausgetrocknetem oder
wassergesättigtem Rasen düngen.
