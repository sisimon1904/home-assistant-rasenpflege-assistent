# Qualitätsaudit – 3.8.1

Geprüft am 1. Oktober 2026 gegen die [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/). Dies ist eine Selbstauskunft für eine HACS-Integration, keine offizielle Einstufung. Fehlerfreiheit und vollständige Erfüllung sämtlicher Quality-Scale-Stufen werden nicht behauptet.

## Behobene Befunde

| Bereich | Ergebnis und Nachweis |
| --- | --- |
| Vorhersagen | Celsius, Millimeter und m/s werden vor den Berechnungen vereinheitlicht. Wind wird bei der Fensterwahl nur einmal umgerechnet. Ungültige Zeilen, Wahrscheinlichkeiten, Zeitpunkte und Einheiten werden verworfen. `test_quality.py` prüft metrische/imperiale Werte und starke Winde. |
| Messwerte | NaN, Unendlich, negative Niederschläge, unbekannte Niederschlagseinheiten und unplausible Temperaturen werden nicht als brauchbare Messungen behandelt. |
| Lebenszyklus | Fehlgeschlagenes Plattform-Entladen behält die Sicherheitsüberwachung. Erfolgreiches Entladen entfernt Listener idempotent. Fehlgeschlagene Einrichtung räumt die Controller-Listener auf. Timer werden beim HA-Stopp abgemeldet. |
| Ventilbefehle | Abbruch beim Öffnen/Weiterlaufen schließt das eigene Ventil. Das zweite Ventil bleibt ausschließlich eine Lesequelle. Bestehende Tests prüfen Starts, Pausen, Wiederanlauf und Stopps. |
| Automatikschalter | Fehlgeschlagenes Aktivieren wird zurückgenommen und gemeldet; fehlgeschlagenes Deaktivieren bleibt im Speicher sicher ausgeschaltet und meldet den Speicherfehler. |
| Aktionen | Nicht geladene Einträge werden erkannt. Eigene Validierungsfehler verwenden `ServiceValidationError` und deutsche/englische Exception-Übersetzungen. Ein direkter Wasser-Pflegeeintrag ist während einer gesteuerten Sitzung gesperrt. |
| Konfiguration | Neu konfigurieren tauscht die vorhandene HA-Wetterquelle aus, erhält die Eintragsidentität und entfernt einen alten Options-Override. Zukünftige Eintragsversionen werden nicht heruntergestuft. Nicht endliche Einstellungszahlen und ungültige importierte Zeitpläne werden gesperrt. |
| Entitäten | Eindeutige IDs, Gerätezuordnung, `has_entity_name`, übersetzte Zustände und Namen, Icon-Übersetzungen und explizite Parallel-Updates aller Plattformen. Tatsächliche HA-Einrichtung/Entladung sowie Plattformaktionen und Diagnosen werden getestet. |
| Verfügbarkeit | `CoordinatorEntity` übernimmt Coordinator-Fehler. Fehlende Teilmessungen liefern unbekannte Werte bzw. ausdrückliche Datenqualitätsgründe. Fehlende/wiederhergestellte Temperatur wird einmal je Übergang protokolliert. |
| Datenzugriff | Bestehende HA-Entitäten und der HA-Vorhersagedienst, Cache für Vorhersagen. Keine eigene HTTP-Verbindung, keine weiteren regelmäßigen OWM-API-Abfragen. |

## Prüfungen

- Python 3.14.7 / Home Assistant 2026.9.4; zusätzlich wurde die Umgebung 2026.10.0b0 vor den letzten Korrekturen geprüft.
- Pytest einschließlich echter HA-Plattform-Einrichtung und -Entladung, Dienstaktionen, Diagnose-JSON, fehlgeschlagenem Speichern, ungültigen Daten und Abbruch von Schaltbefehlen.
- 258 Tests bestanden; 83,57 % kombinierte Zeilen-/Zweigabdeckung im abschließenden Lauf mit bereinigtem Python-Cache. Frühere Zwischenstände mit älterem Cache wurden verworfen.
- Ruff-Formatierung, Ruff-Prüfung und Python-Kompilierung.
- GitHub CI verwendet Python 3.14, einen festgelegten HA-Testpaketstand und ein Mindestniveau von 83 % kombinierter Zeilen-/Zweigabdeckung. Der Coverage-Bericht wird als Workflow-Artefakt bereitgestellt.
- Hassfest und HACS werden durch den Validate-Workflow geprüft. Deren Ergebnis ist am jeweiligen Commit abzulesen; es ersetzt keine Prüfung aller Quality-Scale-Regeln.

## Einordnung der Quality Scale

| Regeln / Gruppe | Stand |
| --- | --- |
| Einrichtung, Laufzeitdaten, IDs, Setup von Aktionen und Entitätsereignissen | Implementiert; typisierte Config-Entry-Laufzeitdaten, UI-Einrichtung, lokale Modellinitialisierung und getrennte Sicherheitsereignisse. |
| Test-before-configure | Die Wetterquelle muss von OpenWeatherMap stammen, vorhanden sein und Temperaturattribute liefern. Unbekannte/unverfügbare Zustände werden abgelehnt. |
| Test-before-setup | Das Modell benötigt keinen eigenen Cloud-Login. Fehlende Wetterdaten sind zulässig für einen vorhandenen Eintrag, werden sichtbar gemacht und sperren automatische Bewässerung. Speicher-/Coordinator-Fehler werden durch HA gemeldet. |
| Polling und Netzwerkabhängigkeit | Die zentrale Berechnung nutzt den Coordinator; schnelle Geräteinterlocks nutzen Zustandsereignisse und den lokalen Watchdog. Kein eigener Netzwerkclient. |
| Geräte, Kategorien, Device Classes, optionale Diagnoseentitäten | Implementiert; geeignete Kategorien/Klassen und abgeschaltete Diagnoseentitäten. |
| Actions, Entity-/Exception-/Icon-Übersetzungen, Reconfiguration, Diagnosen, Reparaturmeldungen | Implementiert und im aktuellen Regressionstestumfang überprüft. |
| Installations-, Datenquellen-, Funktions-, Aktions-, Beispiel-, Limitierungs-, Anwendungsfall-, Entfernungs- und Problemdokumentation | README DE/EN, services.yaml und Dashboard-Vorlagen. Einstellungsfelder besitzen DE/EN-Beschreibungen. |
| Eigene Authentifizierung / Reauthentication | Nicht anwendbar: Anmeldung und OWM-Schlüssel gehören zur separaten HA-OpenWeatherMap-Integration. |
| Discovery, Discovery-Update-Info, dynamische/stale Geräte | Nicht anwendbar: konfigurierte virtuelle Rasenflächen, keine eigene physische Gerätediscovery. |
| Eigene Device-Automation-Triggers/-Conditions | Nicht anwendbar: keine eigenen Gerätetrigger oder Gerätebedingungen. Zustandsentitäten und dokumentierte Busereignisse sind verwendbar. |
| Async dependency / inject-websession | Nicht anwendbar: keine eigene externe API-Bibliothek bzw. kein HTTP-Client. HA-Komponenten besitzen ihre eigenen Verbindungen. |
| Brands | Kein vollständiger Nachweis im separaten Home-Assistant-Brands-Repository. HACS-Validierung ist keine Brands-Zertifizierung. |
| Vollständige Config-Flow-Abdeckung | Noch offen: einzelne Fehler-/Optionspfade sind nicht vollständig abgedeckt. |
| Über 95 % Abdeckung in jedem Modul | Noch offen. Das CI-Mindestniveau von 83 % insgesamt erfüllt diese strengere Silver-Anforderung nicht. |
| Strict typing | Noch offen. Die ergänzten Config-Entry-Typen sind ein Teilfortschritt; Mypy meldet noch fehlende Optional-Eingrenzungen und Hilfsfunktionstypen. Eine Platinum-Einstufung wäre falsch. |

Die Mindestversion bleibt Home Assistant 2026.4.0 gemäß `hacs.json`; der hier dokumentierte vollständige Testlauf wurde mit 2026.9.4 ausgeführt. Eine vollständige Versionsmatrix und echte Hardware-Dauertests sind nicht Teil dieses Nachweises. Schätzwerte für Bodenwasser, Mäherabdeckung und zeitliche Zuordnung bleiben Schätzwerte; fehlerfreie Hardware und sofortige Schalt-/Messrückmeldungen können durch Software nicht garantiert werden.
