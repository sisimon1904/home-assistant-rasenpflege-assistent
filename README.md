# Rasenpflege-Assistent für Home Assistant

**Deutsch** | [English](README.en.md)

Version 3.2.1 · [Änderungsverlauf](CHANGELOG.md)

[![Validate](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml/badge.svg)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sisimon1904/home-assistant-rasenpflege-assistent)](https://github.com/sisimon1904/home-assistant-rasenpflege-assistent/releases)

Diese Integration bewertet Wachstum und Pflegebedarf deines Rasens aus den
vorhandenen OpenWeatherMap-Daten in Home Assistant. Sie berechnet die
Grünlandtemperatursumme, modellierte Bodenfeuchte sowie Empfehlungen zum
Bewässern, Düngen und Mähen. Sie schaltet weder Bewässerung noch Mähroboter.

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
Optional sind Außentemperatur, Niederschlag, Bodentemperatur und Bodenfeuchte
als separate Sensoren wählbar. Fehlt ein Außentemperatursensor, verwendet die
Integration OpenWeatherMap. Ohne ausdrücklich ausgewählten Regensensor sucht
sie einen aktiven OpenWeatherMap-Regensensor derselben Wetterkonfiguration.

Ein physischer Bodenfeuchtesensor lässt sich mit Trocken- und Nassreferenzen
kalibrieren. Optionale Binärsensoren für **Rasen wurde gemäht** und **Rasen wurde
bewässert** protokollieren eine Aus→Ein-Flanke; ohne sie stehen die manuellen
Schaltflächen zur Verfügung. Bewässerung und Düngung lassen sich auch mit
tatsächlichen Mengen protokollieren und das letzte Ereignis rückgängig machen.

Die Integration benötigt keinen weiteren OpenWeatherMap-API-Schlüssel. Sie
liest vorhandene Entitäten und ruft Vorhersagen über Home Assistants
`weather.get_forecasts` ab, ohne OpenWeatherMap direkt anzufragen.

## Wichtige Entitäten

| Entität | Inhalt |
| --- | --- |
| Wachstumsstatus | Winterruhe, Erwachen, Wachstum, Herbst oder Trockenstress; Symbolfarbe als Attribut `icon_color` |
| Pflegestatus | Wichtigster Pflegebedarf mit Düngeempfehlung, NPK, Dosis und Produktmenge als Attributen |
| Mähroboterstatus | Start, regelmäßiges Mähen, Pause oder Winterabschaltung; nächstes Mähen als Attribut |
| Modellierte Bodenfeuchte | Geschätzte Feuchte, Wasservorrat und Wasserbilanz |
| Bewässerungsempfehlung | Zeitpunkt, mm, Liter, Regenprognose und empfohlenes Zeitfenster |
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
abweichen. Bei Bedarf die Bodenfeuchte über **Konfigurieren → Modellierte
Bodenfeuchte neu kalibrieren** korrigieren. NPK und Produktmenge sind
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
