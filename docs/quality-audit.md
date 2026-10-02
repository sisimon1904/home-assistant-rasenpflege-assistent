# Qualitätsaudit – 3.8.7

Geprüft am 2. Oktober 2026 gegen die [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/). Dies ist eine Selbstauskunft für eine HACS-Integration, keine offizielle Einstufung. Fehlerfreiheit und vollständige Erfüllung sämtlicher Quality-Scale-Stufen werden nicht behauptet.

## Ergänzende Prüfung für 3.8.2

`tests/test_audit_381.py` ergänzt 16 Regressionen für physische Verbrauchserhaltung nach Undo, fehlgeschlagene und gleichzeitige Pflegeaktionen, Abbruch nach erfolgreichem Speichern, Ventilschließung bei blockiertem Speicher, Wiederaufnahme bei Regen, Zeitumstellungen und Wetterquellenvalidierung/-wechsel. Pflege- und Modelländerungen sowie Sitzungsabschlüsse werden gemeinsam serialisiert; physische Ventilschließung wartet nicht auf diesen Speicherzugriff. Die bestehenden Einschränkungen zu Typisierung, Modulabdeckung, Brands und Hardwareprüfungen gelten weiterhin.

## Ergänzende Prüfung für 3.8.3

`tests/test_audit_382.py` ergänzt 19 Regressionen für geänderte Sicherheitsbedingungen während der Speicherung, Zähleränderungen vor dem Öffnen, verzögertes Öffnen, Regen vor Wiederaufnahme sowie unmittelbare Sicherheitsstopps bei blockiertem Controllerspeicher. Der Watchdog prüft die physische Sicherheit vor einem erneuten Speicherzugriff. Beide READMEs enthalten Funktionsdokumentation; versionsbezogene Änderungen stehen im CHANGELOG.

## Ergänzende Prüfung für 3.8.4

`tests/test_audit_384.py` ergänzt 31 Regressionen. Sie prüfen parallele Stopps während des Abschlusses, Messlücken und Budgetfreigaben, Verbrauch vor Sicherheitsstopps und während verzögerter Schließbefehle, Endzeiten bei blockiertem Modellzugriff, Wetterausfall vor Start/Wiederaufnahme, Wettereinheiten und ungültige Messwerte, Sommerzeitfenster, Listener-Abmeldung beim HA-Stopp sowie übereinstimmende Versionsangaben in Manifest, Gerät und Diagnose. Bereits bestehende Wiederanlaufprüfungen bestätigen weiterhin, dass gemeinsame Zählerstände über einen HA-Neustart nicht dem Rasen zugerechnet werden.

## Ergänzende Prüfung für 3.8.5

Der veröffentlichte Commit `a0a0e5d1cd1c10e199781ddc753e635a9af78a0d` besteht die vorhandenen 324 Tests. Zusätzliche Fehler wurden zunächst durch elf fehlschlagende Regressionen reproduziert und anschließend lokal behoben. `tests/test_audit_385.py` ergänzt insgesamt 18 Fälle einschließlich weiterer Prüfungen für veränderte Startbedingungen, fehlgeschlagene Speicherung beim Abschalten und die Fortsetzung manueller Sitzungen:

- Automatik-Deaktivierung schließt eine gesteuerte Sitzung vor Speicherwartezeiten, auch bei bereits blockiertem Controllerzugriff.
- Ein aktueller Sicherheitscheck wird vor dem Speichern einer abgelaufenen Nachüberwachung ausgeführt.
- Automatische Erststarts prüfen nach der Speicherung erneut Pflegebedarf, Prognosequalität und das noch gültige Startfenster.
- Prognosefenster verwenden echte Zeitstunden über Sommerzeitwechsel hinweg; lokale Uhrzeiten bleiben für die Auswahl relevant.
- Bodentemperaturen außerhalb von −90 bis 70 °C werden nach der Umrechnung verworfen und in der Eingangsdiagnose als ungültig angezeigt.
- Bewässerungsdatum, Automatik-Tageskennung und Nassrasen-Zeitstempel bleiben an den physischen Abschluss gebunden, auch bei Speicherwartezeiten über Mitternacht. Die gemessene Wassermenge wird weiterhin dem Modell gutgeschrieben.

Prüfergebnis für 3.8.5: **342 Tests bestanden, 85,25 % kombinierte Zeilen-/Zweigabdeckung**. Ruff-Formatierung, Ruff-Prüfung, Python-Kompilierung und Git-Whitespace-Prüfung erfolgreich. Manifest, Geräte-/Diagnoseversion sowie beide README-Versionsangaben sind auf 3.8.5 aktualisiert. Dies erweitert den Testnachweis; die unten aufgeführten offenen Quality-Scale-Anforderungen und Hardware-/Versionsmatrix-Grenzen gelten weiter.

## Ergänzende Prüfung für 3.8.6

Ausgehend von Version 3.8.5 wurden acht weitere Fehlerbereiche reproduziert und korrigiert. `tests/test_audit_386.py`, `tests/test_audit_386_accounting.py` und `tests/test_audit_386_interactions.py` ergänzen zusammen 47 Prüffälle:

| Bereich | Korrektur und Prüfumfang |
| --- | --- |
| Zeitweise Automatiksperre | Physische Schließung vor Controller-/Modellspeicherwartezeiten; fehlgeschlagene Speicherung verhindert die Schließung nicht. Eine fehlgeschlagene Freigabe behält die Sperre. Manuelle Sitzungen laufen weiter. |
| Pausenschließung | Sicher zuordenbarer Verbrauch und aktive Laufzeit werden bis zur bestätigten Ventilschließung erfasst. Verzögerte und wiederholte Befehle verlieren keine Werte und buchen sie nicht doppelt. |
| Abschluss statt Wiederaufnahme | Am Schließrand erreichte Ziele, Laufzeit-/Mengenlimits, Wasserbudgets und Messfehler beenden die Sitzung. Bereits früher gespeicherte pausierte Sitzungen werden vor Wiederaufnahme erneut auf erfüllte Ziele und Limits geprüft. |
| Winterzeitfenster | Erneuter Eintritt in erlaubte Zeitfenster beim Rückstellen der Uhr, einschließlich Fenstern über Mitternacht. Eine unabhängige Suche über tatsächlich verstrichene Minuten prüft zwölf Kombinationen in Europe/Berlin und Australia/Lord_Howe, einschließlich 30-Minuten-Umstellungen. |
| Zählerzyklen | Anfangsreset je Ventilöffnungsabschnitt erhält vorherigen Verbrauch. Rücksetzungen nach bereits erfasstem Wasser im Abschnitt oder nach zwei Minuten bleiben Sicherheitsfehler. |
| Verbrauchsrundung | Sehr kleine letzte Tagesanteile werden durch Rundungsabzüge nicht negativ. Tagesanteile ergeben zusammen die gerundete Sitzungsmenge. |
| Abbruch beim Abschluss | Einfacher oder wiederholter Abbruch wartet auf den Speicherausgang. Erfolgreiche Abschlüsse werden einmal veröffentlicht; bei Speicherfehler bleiben geschlossene Sitzungen und unverbrauchte Modellgutschriften für einen erneuten Versuch erhalten. |
| Tatsächlicher HA-Speicherfehler | HA 2026.9.4 protokolliert bestimmte Schreib-/Serialisierungsfehler ohne Weitergabe an den Aufrufer. `VerifiedStore` vergleicht einen unabhängigen gespeicherten Datenstand über die öffentliche `async_load`-Schnittstelle. Abweichungen blockieren Starts/Aktivierung und lösen die vorhandene Rücknahme bzw. Wiederholungsbehandlung aus. |

Zusätzlich wurde außerhalb der gemockten Pytest-Speicherumgebung eine tatsächliche temporäre Datei geschrieben und gelesen. Ein am Schreibaufruf injizierter `WriteError` wurde erkannt; die zuvor gespeicherten Daten blieben erhalten. Dies prüft den Datei-/Fehlerpfad, keine realen Ventile oder Hardware-Dauertests.

**Ergebnis für 3.8.6: 389 Tests bestanden, 85,90 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Ruff-Formatierung, Ruff-Prüfung, Python-Kompilierung, JSON-/Dokumentationslink-Prüfung und Git-Whitespace-Prüfung erfolgreich. Manifest, Geräte-/Diagnoseversion und beide READMEs verwenden 3.8.6. Die Speicherbestätigung benötigt einen zusätzlichen lokalen Lesezugriff je Speicherung, ohne weitere Wetter-/OWM-Abfrage. Ventilschließung bleibt vor Speicherwartezeiten priorisiert. Das zweite Ventil bleibt ausschließlich eine Lesequelle. Die unten dokumentierten Hardware-, Versionsmatrix- und Quality-Scale-Grenzen gelten weiterhin.

## Ergänzende Prüfung für 3.8.7

Die Prüfung umfasst erneut Ventilsteuerung und Interlocks, Neustart-/Entladebehandlung, Pflegeaktionen und Speicherung, Zeitplanung, Wetterberechnungen, Konfigurationsänderungen sowie die vorhandenen Plattform-, Übersetzungs- und Dokumentationstests. Die nachfolgende Korrektur ist Bestandteil von Version 3.8.7.

Ein reproduzierbarer Fehler betraf wiederholte Abbrüche einer Pflege-Speichertransaktion: Nach dem ersten Abbruch wurde die laufende Speicherung ungeschützt abgewartet. Ein weiterer Abbruch konnte dadurch den Schreib-/Bestätigungsvorgang abbrechen und die Modellsperre zu früh freigeben. Ein bereits laufender Dateischreibvorgang kann dann trotzdem fortgesetzt werden, während die Transaktion ihre Modelländerungen zurücknimmt.

Die Speicherung wird jetzt bei jedem Abbruch abgeschirmt bis zum Abschluss abgewartet. Die Modellsperre bleibt bis dahin gehalten. Erfolgreich gespeicherte Änderungen bleiben erhalten; fehlgeschlagene Änderungen werden zurückgenommen. Anschließend wird der Abbruch an den Aufrufer weitergegeben. Erwartete Schreibfehler werden als Transaktionsergebnis verarbeitet, um unbehandelte Fehler des abgeschirmten Tasks zu vermeiden.

`tests/test_review_after_386.py` ergänzt 19 Regressionstestfälle: Bewässerung, Düngung, Mähen und Rückgängig mit einem, zwei und drei Abbrüchen; Schreibfehler mit und ohne Abbruch samt Rücknahme und Wiederholung; sowie eine zweite Pflegeaktion, die auf die erste Transaktion warten muss. Acht Fälle mit wiederholten Abbrüchen schlugen vor der Korrektur fehl. Zusätzlich wurde außerhalb der gemockten Pytest-Speicherung eine tatsächliche temporäre HA-Datei geschrieben: Auch nach drei Abbrüchen blieb die Sperre bis zum Speicherabschluss gehalten, und Dateiinhalte, geladene Daten und Modell stimmten überein.

**Ergebnis für 3.8.7: 408 Tests bestanden, 85,91 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Ruff-Formatierung, Ruff-Prüfung, Python-Kompilierung, JSON-Parsing, relative Dokumentationslinks und Git-Whitespace-Prüfung erfolgreich. Manifest, Geräte-/Diagnoseversion und beide READMEs verwenden 3.8.7. Die Grenzen bezüglich Hardware und Versionsmatrix gelten weiterhin.

## Quellcode-Kommentierung für 3.8.7

Nach der erneuten Fehlerprüfung wurden alle 37 Python-Dateien mit erklärenden Dateiheadern versehen und 101 zentrale Funktionen ausführlicher dokumentiert. Die Kommentare erläutern Zuständigkeiten, Datenfluss, Einheiten, Sperren, Abbruch-/Fehlerverhalten, physische Ventilzustände, Messlücken und Berechnungsannahmen. Alle 16 YAML-Dateien für Dienste, Dashboards und Workflows besitzen ebenfalls erklärende Header. Die [Quellcode-Übersicht](source-code.md) dokumentiert auch die JSON-Dateien, deren Format keine Kommentare erlaubt.

Ein Vergleich der Python-Syntaxbäume unter Auslassung der Docstrings bestätigt unveränderte ausführbare Logik gegenüber dem Stand mit der oben dokumentierten lokalen Fehlerkorrektur. Die geladenen YAML-Inhalte sind ebenfalls unverändert. Abschließender Testlauf nach der Kommentierung: **408 Tests bestanden, 85,91 % kombinierte Zeilen-/Zweigabdeckung**; Ruff, Python-Kompilierung und Git-Whitespace-Prüfung erfolgreich. Die Kommentierung ist Bestandteil von Version 3.8.7.

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
- 408 Tests bestanden; 85,91 % kombinierte Zeilen-/Zweigabdeckung im abschließenden Lauf für 3.8.7 (3.8.6: 389 Tests, 85,90 %).
- Ruff-Formatierung, Ruff-Prüfung und Python-Kompilierung.
- GitHub CI verwendet Python 3.14, einen festgelegten HA-Testpaketstand und ein Mindestniveau von 83 % kombinierter Zeilen-/Zweigabdeckung. Der Coverage-Bericht wird als Workflow-Artefakt bereitgestellt.
- Hassfest und HACS werden durch den Validate-Workflow geprüft. Deren Ergebnis ist am jeweiligen Commit abzulesen; es ersetzt keine Prüfung aller Quality-Scale-Regeln.

## Einordnung der Quality Scale

| Regeln / Gruppe | Stand |
| --- | --- |
| Einrichtung, Laufzeitdaten, IDs, Setup von Aktionen und Entitätsereignissen | Implementiert; typisierte Config-Entry-Laufzeitdaten, UI-Einrichtung, lokale Modellinitialisierung und getrennte Sicherheitsereignisse. |
| Test-before-configure | Die Wetterquelle muss von OpenWeatherMap stammen, vorhanden sein und eine endliche, plausible Temperatur in einer unterstützten Einheit liefern. Unbekannte/unverfügbare Zustände werden abgelehnt. |
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
