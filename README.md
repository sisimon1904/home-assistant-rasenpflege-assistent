# Rasenpflege-Assistent für Home Assistant

Version 1.2.0

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
- optional, aber empfohlen: der von OpenWeatherMap angelegte Regensensor

Es wird kein zusätzlicher OpenWeatherMap-API-Schlüssel benötigt. Die Integration
liest ausschließlich bereits in Home Assistant vorhandene Entitäten und ruft
Vorhersagen über `weather.get_forecasts` ab.

## Funktionen

- GUI-Einrichtung und GUI-Optionen
- Auswahl und Prüfung einer OpenWeatherMap-Wetterentität
- frei wählbarer Außentemperatursensor mit automatischem OpenWeatherMap-Fallback
- optionale Integration des OpenWeatherMap-Regensensors
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
- eigener Mähroboterstatus mit konkreten Handlungsanweisungen
- separater Binärsensor „Mähroboterstart empfohlen“
- separater Binärsensor „Mähroboter kann abgeschaltet werden“
- modellierte Bodenfeuchte in Prozent
- Bewässerungsempfehlung mit Zielmenge in mm und Litern
- saisonale NPK-Empfehlung und Produktmenge
- Diagnose-Download über Home Assistant
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

Mit ausgewähltem OpenWeatherMap-Regensensor wird dessen Regenrate über die Zeit
integriert. Ohne Regensensor verwendet das Modell ersatzweise den vorhergesagten
Tagesregen. Der Sensor stellt seine Modellqualität als Attribut `medium` oder
`low` bereit.

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
Trockenstress, meldet der Mähroboterstatus **Mähroboter wieder starten**. Danach die
Schaltfläche **Mähsaison als gestartet markieren** drücken. Der Hinweis bleibt
für den Rest des Kalenderjahres quittiert und wird am 1. Januar zurückgesetzt.

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
5. OpenWeatherMap-Wetterentität, optionalen Regensensor und Rasenparameter
   auswählen.

## Aktualisierung von Version 1.0.0

1. Den vorhandenen Ordner
   `/config/custom_components/rasenpflege_assistent` ersetzen.
2. Home Assistant neu starten.
3. Beim nächsten Start migriert Home Assistant den Konfigurationseintrag
   automatisch auf Version 2.
4. Danach unter **Einstellungen → Geräte & Dienste → Rasenpflege-Assistent →
   Konfigurieren** den OpenWeatherMap-Regensensor und die anfängliche
   Bodenfeuchte prüfen. Ab Version 1.2.0 kann dort zusätzlich ein lokaler
   Außentemperatursensor ausgewählt werden.

## Automatische Updates mit HACS

Neue stabile Versionen werden als GitHub-Releases wie `v1.2.0` veröffentlicht.
Eine über HACS installierte Kopie zeigt diese anschließend als Update an. Eine
nur manuell nach `custom_components` kopierte Integration kann Home Assistant
nicht selbst aus dem Internet aktualisieren.

## Wichtige Entitäten

- Status
- Wachstumsstatus
- Mähroboterstatus
- Modellierte Bodenfeuchte
- Grünlandtemperatursumme
- Bewässerungsempfehlung
- empfohlene Wassermenge
- Düngeempfehlung
- empfohlene Düngermenge
- Mähroboterstart empfohlen
- Mähroboter kann abgeschaltet werden
- Bewässerung fällig
- Düngung fällig
- Mähsaison als gestartet markieren
- Bewässerung protokollieren
- Düngung protokollieren

## Grenzen

Das Bodenmodell ist eine nachvollziehbare Schätzung, keine Messung. Die
Düngermenge bezeichnet die ungefähre Produktmenge und nicht die reine
Nährstoffmenge. Maßgeblich bleiben die Herstellerdosierung, eine Bodenanalyse
und örtliche Vorschriften. Nicht auf gefrorenem, ausgetrocknetem oder
wassergesättigtem Rasen düngen.
