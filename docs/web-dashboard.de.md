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
