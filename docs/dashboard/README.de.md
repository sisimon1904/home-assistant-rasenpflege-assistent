<!-- File: docs/dashboard/README.de.md — Complete dashboard setup and entity mapping. -->
# Dashboard für den Rasenpflege-Assistenten

Die [vollständige deutsche Vorlage](dashboard.de.yaml) funktioniert mit Version **3.17.0 oder neuer** und verwendet ausschließlich Home-Assistant-Standardkarten. Eine [englische Vorlage](dashboard.en.yaml) ist ebenfalls vorhanden. Beide nutzen dieselben Beispiel-Entitätskennungen; die tatsächlichen Kennungen hängen von deiner Installation ab.

## Ansichten

| Ansicht | Inhalt |
| --- | --- |
| Übersicht | Rasenzustand, nächste Aktion, Wachstum, Bodenfeuchte mit 7-Tage-Verlauf, Mähen, Bewässerung und Datenqualität |
| Pflegeplan | Prioritäten, 48-Stunden-Ausblick, Voraussetzungen sowie Düngermenge, Dosierung und NPK |
| Mähen | Mähbeginn, Tauprüfung, Dauer, Ausweichtermin, Datenqualität und erfasste Robotersitzungen |
| Bewässerung | Empfehlung, Sitzungsfortschritt, Start/Stop, Automatik, zeitweise Sperre und Verbrauchsverlauf |
| Diagnose | Datenquellen, Bodenwasserbilanz, Modellkalibrierung, historische Lücken und Vergleichsdiagnosen |

## Einrichtung

1. Unter **Einstellungen → Dashboards** ein neues, leeres Dashboard anlegen. Die Vorlage ist ein komplettes Dashboard, keine einzelne manuelle Karte.
2. Die tatsächlichen Entitätskennungen unter **Entwicklerwerkzeuge → Zustände** nachsehen. Die Beispiele in der Tabelle unten durch die Kennungen deiner Rasenfläche ersetzen, jeweils überall in der YAML-Datei. Auch Entitätsnamen innerhalb von Templates ersetzen.
3. Für die Bewässerungsaktionen unter **Entwicklerwerkzeuge → Template** die Kennung deiner Integration ermitteln:

   ```jinja
   {{ config_entry_id('sensor.DEINE_RASEN_ENTITAET') }}
   ```

   Den ausgegebenen Wert überall für `REPLACE_WITH_ENTRY_ID` einsetzen. Hier muss dieselbe Rasenfläche wie in den Anzeigen ausgewählt sein.
4. Das neue Dashboard öffnen, **Dashboard bearbeiten → Drei-Punkte-Menü → Raw-Konfigurationseditor** wählen und den gesamten Inhalt von `dashboard.de.yaml` einfügen. Je nach Home-Assistant-Sprache heißt der Menüpunkt auch „Rohkonfigurationseditor“. Anschließend speichern.
5. Die fünf Ansichten prüfen. Wenn eine Karte eine fehlende Entität meldet, ihre Kennung mit der Entitätsliste abgleichen. Diagnoseentitäten gegebenenfalls auf der Geräteseite aktivieren.

## Entitätszuordnung

| Beispiel in der YAML | Entität/Funktion |
| --- | --- |
| `sensor.rasen_pflegestatus` | Pflegestatus mit Düngerattributen |
| `sensor.rasen_nachste_aktion` | Nächste Aktion |
| `sensor.rasen_wachstumsstatus` | Wachstumsstatus |
| `sensor.rasen_pflegeplan` | Pflegeplan und Ausblick |
| `sensor.rasen_modellierte_bodenfeuchte` | Modellierte Bodenfeuchte |
| `sensor.rasen_mahroboterstatus` | Mähroboterstatus/Mähempfehlung |
| `sensor.rasen_bewasserungsempfehlung` | Bewässerungsempfehlung |
| `sensor.rasen_datenqualitat` | Datenqualität |
| `sensor.rasen_wasserverbrauch_heute` | Wasserverbrauch heute |
| `sensor.rasen_erfasste_bewasserung_diese_woche` | Erfasste Bewässerung diese Woche |
| `sensor.rasen_erfasste_bewasserung_diesen_monat` | Erfasste Bewässerung diesen Monat |
| `sensor.rasen_bewasserungsstatus` | Optionaler Bewässerungsstatus |
| `sensor.rasen_bewasserung_diagnose` | Optionale Bewässerungsdiagnose |
| `sensor.rasen_nachster_automatischer_bewasserungsstart` | Optionaler nächster automatischer Start |
| `sensor.rasen_verbleibende_bewasserungsdauer` | Optionale verbleibende Bewässerungsdauer |
| `switch.rasen_automatische_bewasserung` | Optionale Automatikfreigabe |

## Bedienung und Anzeige

Ohne eingerichtetes Ventil werden die Steuerungssektion und die optionalen Bewässerungsdiagnosen ausgeblendet. Empfehlung und Verbrauch bleiben sichtbar. Die Startknöpfe verwenden die überwachten Integrationsaktionen, einschließlich der Sicherheitsprüfungen. Eine Automatikfreigabe kann die automatische Bewässerung aktivieren; Startknöpfe starten eine echte Sitzung. Die Vorlage steuert das zweite Ventil nicht.

Statusanzeigen verwenden Home Assistants übersetzte Zustände. Erklärungen mit `reason_text` stammen aus der Sprache deiner Home-Assistant-Konfiguration; für vollständig deutsche Texte dort Deutsch wählen. Fehlende Werte erscheinen als „—“. Bei nicht verfügbaren Entitäten bleiben Hinweise sichtbar; die Karte behauptet dann keine Startfreigabe.

Der 7-Tage-Verlauf benötigt Aufzeichnungen durch **Recorder**. Die Bodenfeuchte ist ein Modellwert; das Dashboard legt keine universellen Farbgrenzen für „trocken“ oder „nass“ fest. Ausblick und Mähfenster bleiben wetterabhängige Schätzungen. Das Dashboard erzeugt keine neuen Sensoren, keine regelmäßigen Wetterabfragen und keine automatische Installation in deiner HA-Instanz.

Die übrigen YAML-Dateien in diesem Ordner sind weiterhin einzelne Mushroom-Karten für bestehende Dashboards. Sie benötigen Mushroom und werden als manuelle Karten eingefügt.
