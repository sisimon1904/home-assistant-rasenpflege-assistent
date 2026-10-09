<!-- File: docs/web-dashboard.de.md — Integrated web dashboard access and behavior. -->
# Webdashboard

Ab Version **3.17.0** stellt die Integration eine eigene Weboberfläche über den bestehenden Home-Assistant-Webserver bereit. Sie erscheint in der Seitenleiste als **Rasenpflege** und ist direkt erreichbar unter:

```text
http://DEINE-HA-ADRESSE:8123/rasenpflege-assistent
```

Wenn du Home Assistant über HTTPS, eine Domain, einen Reverse Proxy oder Home Assistant Cloud öffnest, verwende dieselbe Basisadresse und ergänze `/rasenpflege-assistent`. Es wird kein zusätzlicher Port oder Docker-Container benötigt. Die Adresse ist über dieselben Netzwerkwege erreichbar wie deine HA-Oberfläche.

## Einrichtung

1. Die aktualisierte Integration installieren und Home Assistant neu starten.
2. **Rasenpflege** in der HA-Seitenleiste öffnen oder den URL-Pfad direkt aufrufen.
3. Falls nötig mit deinem vorhandenen HA-Benutzer anmelden.
4. Bei mehreren Rasenflächen oben die gewünschte Fläche auswählen.

Die tatsächlichen Entitätskennungen werden automatisch aus Home Assistant ermittelt. Ein YAML-Import, weitere Karten, ein separater API-Token oder eine zusätzliche Anmeldung sind nicht nötig. Wenn die Integration nicht geladen ist oder dein Benutzer keine Rasenentitäten lesen darf, zeigt die Oberfläche einen entsprechenden Leerzustand. Nach dem Update bei einer alten Darstellung die Seite neu laden.

## Bereiche

| Bereich | Anzeigen und Funktionen |
| --- | --- |
| Übersicht | Rasenzustand, nächste Pflege, Wachstum, modellierte Bodenfeuchte, Regenprognose, erfasster Verbrauch und Datenqualität |
| Pflegeplan | Prioritäten, früheste Zeitpunkte, Voraussetzungen, bedingter 48-Stunden-Ausblick sowie NPK und Düngerdosierung |
| Mähen | Mähfenster mit Tauprüfung, Dauer, Ausweichtermin, Nässepause und manuelle Erfassung abgeschlossenen Mähens |
| Bewässerung | Empfehlung, Sitzungsfortschritt, Ziel-/Restmenge, Start/Stop, Automatikfreigabe und zeitweise Sperre |
| Verläufe | Modell- und Sensorwerte, erfasste Regenintervalle und Bewässerungsmengen |
| Pflegeprotokoll | Letzte Pflegeeinträge, manuelle Erfassung, Rücknahme und optionale Benachrichtigungen |
| Diagnose | Datenquellen, Messgrundlage, Modellwasserbilanz, Vergleichsdiagnosen und aufklappbare Detailattribute |

Die Oberfläche ist für Desktop und Smartphone ausgelegt. Die Sprache folgt der HA-Oberflächensprache; Deutsch und Englisch werden unterstützt. Erklärungsattribute folgen wie bisher der konfigurierten HA-Sprache. Nicht vorhandene Messwerte erscheinen als „—“ oder „Nicht verfügbar“.

## Anmeldung und Bedienung

Home Assistant übernimmt die Anmeldung und die authentifizierte Datenverbindung. Die Übersicht berücksichtigt die Leserechte deines Benutzers. Bedienaktionen erfordern einen **HA-Administrator**; diese Prüfung findet auf dem Server statt. Andere Benutzer erhalten eine reine Ansicht.

Starts, Automatikfreigaben und Pflegeerfassungen fragen zur Vermeidung versehentlicher Bedienung nach. **Stoppen** ist direkt verfügbar. Bei laufenden Aktionen ist die Rasenflächenauswahl gesperrt. Fehler der Sicherheitssteuerung oder Speicherung werden angezeigt.

Bewässerungsaktionen verwenden die vorhandene überwachte Steuerung mit deren Sicherheitsregeln. Das zweite Ventil bleibt eine reine Statusquelle. Die Oberfläche startet keinen Mähroboter. **Mähen erfassen** und **Düngung erfassen** protokollieren eine tatsächlich erledigte Pflege. Ohne eingerichtetes Ventil kannst du manuelle Bewässerung mit einer Menge erfassen.

## Verlauf und Datenlage

Statusänderungen kommen über die vorhandene HA-Verbindung; die Oberfläche führt keine regelmäßigen Wetter- oder Geräteabfragen aus. Für den Bodenfeuchteverlauf wird beim Öffnen, Wechseln oder Aktualisieren der Rasenfläche einmalig die vorhandene Recorder-Historie der letzten sieben Tage gelesen. Recorder muss diese Entität aufzeichnen. Nicht verfügbare Zustände unterbrechen die dargestellte Linie; fehlende Historie wird nicht erfunden.

Der letzte erfolgreiche Stand bleibt bei Verbindungsunterbrechung sichtbar und wird als unterbrochen markiert. Bedienaktionen sind dann gesperrt. Nach erneuter Verbindung werden die Rasenflächen neu ermittelt. „Rasenflächen aktualisieren“ lädt die Zuordnung und Historie erneut, ohne Wetterdaten abzurufen.

Bodenfeuchte, Tauprüfung und Pflegeausblick sind weiterhin Schätzungen mit den in der Diagnose erklärten Grenzen. Die [Lovelace-Vorlagen](dashboard/README.de.md) bleiben eine zusätzliche Darstellungsmöglichkeit. Auf einer bewusst ohne HA-Frontend betriebenen Installation stehen weiterhin Entitäten und Aktionen zur Verfügung; das Webdashboard benötigt das normale Home-Assistant-Frontend.

## Erweiterungen ab v3.18.0

| Erweiterung | Bedienung und Datenbasis |
| --- | --- |
| Tagesplan | Die Übersicht zeigt Pflegeprioritäten mit frühesten Zeitpunkten, Voraussetzungen und Sperrgründen. Zukünftige Vorschläge reservieren keine Aktionen. |
| Datenqualität | Berechnungszeit, Alter von Wetter und Vorhersage sowie vorhandene Vertrauensbewertungen werden angezeigt. „Live verbunden“ beschreibt die Verbindung, nicht die Frische der Wetterdaten. |
| Verläufe | Sieben Tage aus dem vorhandenen lokalen Modellverlauf: getrennte Diagramme für Modell- und Sensorwerte, erfasste Regenintervalle und zuletzt erfasste Bewässerungsmengen. |
| Pflegeprotokoll | Bis zu 20 Pflegeeinträge sowie manuelle Erfassung von Mähen, Bewässerung und Düngung mit Zeitpunkt, tatsächlichem NPK-Produkt und Menge. |
| Literziel | Das Bewässerungsziel lässt sich in mm oder Litern eingeben. Bestehende serverseitige Mengen- und Sicherheitsprüfungen gelten weiterhin. |
| Benachrichtigungen | Standardmäßig aus; ein Administrator kann lokale HA-Hinweise mit 1, 6 oder 24 Stunden Mindestabstand je Hinweisart aktivieren. |
| Ansicht merken | Rasenfläche und Bereich werden benutzerbezogen im Browser gespeichert; die URL enthält einen direkten Link zur aktuellen Ansicht. |

**Verläufe:** Sensorwerte verwenden den gespeicherten Messzeitpunkt. Regenbalken zeigen bekannte erfasste Intervalle, keine vollständigen Tagessummen. Bewässerungsbalken zeigen bis zu zehn verfügbare Verbrauchseinträge innerhalb der sieben Tage in Litern. Quellen, Schätzungen und Messlücken stehen beim Eintrag; unbekannte Mengen bedeuten nicht null. Modell-/Sensorlinien werden bei fehlenden Werten, Quellenwechseln und Abständen über einer Stunde unterbrochen. Die Diagramme sind Momentaufnahmen: Öffnen, Wechseln oder „Rasenflächen aktualisieren“ lädt den Stand neu. Der Pflegeverlauf benötigt vollständige Leserechte für die aktivierten Entitäten der Rasenfläche; bei eingeschränkten Rechten bleiben die erlaubten übrigen Dashboard-Anzeigen verfügbar.

**Zeitpunkte:** Ein leerer Zeitpunkt bedeutet jetzt. Ein eingegebener Zeitpunkt verwendet die lokale Zeitzone des bedienenden Geräts, wird mit Zeitzone übermittelt und muss in der Vergangenheit liegen. Historische Bewässerung braucht eine explizite Menge und füllt das heutige Bodenmodell nicht nachträglich auf. Ein Datum ohne Uhrzeit wird auch ohne Uhrzeit angezeigt.

**Zurücknehmen und neu erfassen:** Nur der neueste manuelle Pflegeeintrag kann zurückgenommen werden. Der Server prüft dessen Identität innerhalb der Modelltransaktion erneut. Hat sich der Verlauf inzwischen geändert, wird die Rücknahme abgelehnt. Automatische Mähbeobachtungen, Mäh-Fertigmeldungen und physische Bewässerung sind über diese Funktion geschützt. Während kontrollierter Bewässerung ist keine Rücknahme möglich. Nach erfolgreicher Rücknahme wird das Erfassungsformular vorausgefüllt; erst Speichern erfasst den korrigierten Vorgang. Rücknahme und neue Erfassung sind zwei getrennte Aktionen.

**Bewässerungsziel:** Bei bekanntem Flächenmaß begrenzt das Literformular zusätzlich auf höchstens 50 mm beziehungsweise 50.000 Liter. Der Sitzungsbereich zeigt den verfügbaren Durchfluss. Fehlt der Automatikstatus, erscheint „Unbekannt“; der Umschaltknopf ist dann gesperrt.

**Benachrichtigungen:** Hinweise erscheinen in der Home-Assistant-Glocke bei empfohlener Pflege und außergewöhnlichen Bewässerungsabbrüchen. Normale manuelle Stopps zählen nicht als Fehler. Die Hinweise behaupten keine überfällige Pflege, sondern verweisen auf die aktuelle Empfehlung. Einstellungen und Abstände bleiben nach Neustarts erhalten; sie ersetzen keine Sicherheitsabschaltung. Es werden keine Telefon-Pushs oder externen Nachrichten versendet. Einrichtung im Pflegeprotokoll.

**Direktlinks:** Beispiel: `/rasenpflege-assistent#view=water&lawn=DEINE_ENTRY_ID`. Erlaubte Bereiche: `overview`, `plan`, `mowing`, `water`, `trends`, `journal`, `diagnostics`. Es werden keine Zugangsdaten gespeichert. Geöffnete Diagnosedetails bleiben bei Live-Updates derselben Ansicht geöffnet.
## Erweiterungen ab 3.19.0

- **Pflege begründen:** Übersicht und Pflegeplan zeigen die vorhandenen Gründe für Mähen, Bewässern und Düngen direkt. Der zusätzliche Zeitpunktvergleich verwendet den bedingten 48-Stunden-Ausblick. Voraussetzungen und fehlende Zeiten bleiben sichtbar; es werden keine Aktionen reserviert oder automatisch gestartet.
- **Daten prüfen:** Nicht verfügbare, ungültige und veraltete konfigurierte Eingänge erhalten Prüfhilfen. Nicht konfigurierte optionale Sensoren gelten dabei nicht als Ausfall.
- **Verbrauch vergleichen:** Unter Verläufe stehen lokale Kalenderwoche (ab Montag) und Kalendermonat. Gemessene Ventilmengen, Durchflussschätzungen und Mengen mit unklarer Messgrundlage bleiben getrennt; manuelle Erfassungen/Schätzungen werden gesondert gezeigt. Unbekannte Mengen sind nicht als gemessene Null zu verstehen. l/m² teilt die erfasste Menge durch die heutige Fläche und ist nach Flächenänderungen nur ein Vergleichswert. Laufende Sitzungen sind nicht enthalten.
- **Protokoll exportieren:** Nach Mähen, Bewässern oder Düngen filtern und die sichtbaren, höchstens 20 Einträge als CSV herunterladen. Das funktioniert auch mit Leserechten. CSV-Zeitstempel behalten ihre Zeitzone; Benutzertexte werden zitiert und Tabellenformeln neutralisiert. Der Export ist kein vollständiges Jahresarchiv.
- **Benachrichtigungen:** Im Pflegeprotokoll optional Ruhezeiten als HH:MM in der Home-Assistant-Zeitzone einstellen; beide Felder leer deaktiviert sie. Ruhezeiten können über Mitternacht reichen, identische Start-/Endzeiten sind ungültig. Währenddessen entstehen keine neuen Hinweise; bestehende Hinweise bleiben sichtbar. Sicherheitsabschaltungen arbeiten unverändert. Nach Ablauf werden weiterhin aktuelle Empfehlungen und höchstens 24 Stunden alte Abbrüche beim nächsten erfolgreichen Update geprüft.
- **Nur Änderungen:** Optional wiederkehrende Pflegehinweise unterdrücken. Änderungen der empfohlenen Pflegearten und nach zwischenzeitlichem Wegfall wieder geeignete Mähbedingungen können einen neuen Hinweis auslösen. Der Mindestabstand je Kategorie gilt weiterhin; verschobene Prognosezeiten allein erzeugen keine Meldung. Ein identischer Bewässerungsabbruch wird auch nach Neustart nicht erneut gemeldet.

Protokoll und gespeicherte Modellverläufe werden bei Änderungen der Rasenentitäten gebündelt nachgeladen. Beim erneuten Einblenden wird der aktuelle Stand neu geladen. Es entstehen keine zusätzlichen Wetterabfragen. Recorder-Historie bleibt an Auswahl/erneutes Öffnen/manuelle Aktualisierung gebunden.

## Erweiterungen ab 3.20.0

- **Vollständiges Wasser-CSV:** In Verläufe alle vorhandenen abgeschlossenen Verbrauchseinträge herunterladen, üblicherweise bis zu einem Jahr, getrennt vom kurzen Pflegeprotokoll-Export. Laufende Sitzungen sind ausgeschlossen. Fehlende Liter bleiben leer; JSON-Spalten erhalten Datumsaufteilungen und Unsicherheitsdaten. Datum, Quelle und Qualitätsmerkmale werden ohne private Sitzungs-, Messgerät- oder Ventilkennungen exportiert. Lesende Nutzer mit vollständigen Entitätsrechten für die Fläche können exportieren; Administratorrechte sind dafür nicht nötig. CSV-Zellen werden zitiert und Tabellenformeln neutralisiert.
- **Tagesdiagramm:** 7 oder 30 lokale Kalendertage auswählen. Gestapelte Balken trennen gemessene Ventilmengen, Durchflussschätzungen, manuelle Erfassungen, manuelle Schätzungen und unklare Ventilmengen. Die ausklappbare Datentabelle zeigt Datum, Mengen und Qualitätszähler. Ein Fragezeichen kennzeichnet unbekannte Mengen oder Messlücken; eine bekannte Teilmenge ist keine vollständige Gesamtmenge. Kein Eintrag bedeutet keine erfasste Menge, keinen gemessenen Nullverbrauch. Bestehende Datumsaufteilungen können selbst geschätzt sein. Laufende Sitzungen sind ausgeschlossen.
- **Konkrete Diagnose:** Konfigurierte Eingänge zeigen Alter und verfügbare Frischegrenze, betroffene Pflegeentscheidungen und passende Prüfhinweise. Empfehlungen bleiben von ihrer bestehenden Datengrundlage abhängig.
- **Getrennte Hinweise:** Der globale Benachrichtigungsschalter bleibt standardmäßig aus. Pflegehinweise und ungewöhnliche Bewässerungsabbrüche erhalten jeweils einen eigenen Schalter und Mindestabstand von 1, 6 oder 24 Stunden. Ältere gespeicherte Einstellungen übernehmen den bisherigen Abstand für beide Kategorien. Ruhezeiten und der Modus für geänderte Empfehlungen bleiben gemeinsame Einstellungen. Änderungen des Pflegezustands werden auch während Ruhezeiten und Mindestabständen verfolgt: Die dann noch gültige zurückkehrende Empfehlung kann bei einer späteren erfolgreichen Aktualisierung gemeldet werden, auch nach Neustart; eine zurückgezogene Empfehlung wird verworfen. Sicherheitsabschaltungen sind von diesen Hinweisen unabhängig.
- **Kleine Mengen:** Einheitenabhängige Nachkommastellen verhindern, dass kleine positive Liter-, Kilogramm-, Millimeter- oder Liter-pro-Quadratmeter-Werte als null erscheinen. Sehr kleine Werte verwenden wissenschaftliche Schreibweise.

Diagramm und CSV verwenden das gespeicherte Wasserprotokoll und die bestehende authentifizierte Verbindung. Es entstehen keine regelmäßigen Wetter- oder Geräteabfragen. Das zweite Ventil bleibt lesend.
