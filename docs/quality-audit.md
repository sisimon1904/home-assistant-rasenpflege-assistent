# Qualitätsaudit – 3.16.1

Geprüft am 4. Oktober 2026 gegen die [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/). Dies ist eine Selbstauskunft für eine HACS-Integration, keine offizielle Einstufung. Fehlerfreiheit und vollständige Erfüllung sämtlicher Quality-Scale-Stufen werden nicht behauptet.

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
| Strict typing | Noch offen. Die ergänzten Config-Entry-Typen sind ein Teilfortschritt; Mypy prüft in 3.9.0 alle 17 Dateien ohne Befund; fünf Kernmodule nutzen zusätzliche strenge Optionen. Dynamische Payloads und Teile des Controllers verwenden weiterhin `Any`. Eine Platinum-Einstufung wäre falsch. |

Die Mindestversion bleibt Home Assistant 2026.4.0 gemäß `hacs.json`; der hier dokumentierte vollständige Testlauf wurde mit 2026.9.4 ausgeführt. Eine vollständige Versionsmatrix und echte Hardware-Dauertests sind nicht Teil dieses Nachweises. Schätzwerte für Bodenwasser, Mäherabdeckung und zeitliche Zuordnung bleiben Schätzwerte; fehlerfreie Hardware und sofortige Schalt-/Messrückmeldungen können durch Software nicht garantiert werden.

## Prüfung für 3.9.0

**491 Tests bestanden, 86,98 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Konfigurationsfluss: rund 92 % kombinierte Abdeckung; Speicher: 100 %. Die 83 zusätzlichen Fälle prüfen Konfigurations- und Fehlerpfade, lesenden Diagnoseexport, Speicherfehler und Wiederherstellung, Sensorabgleich sowie mehrtägige Wassererhaltung bei drei Bodenarten mit Trockenheit, Regen und Bewässerung.

Ein Intervallvergleich reproduzierte unterschiedliche Trockenverluste durch die bisherige Anwendung des anfänglichen Wasserstressfaktors auf den gesamten Schritt. Die bestehende lineare Stressfunktion wird jetzt innerhalb des Schritts integriert; Vergleiche zwischen 5/15/60 Minuten und 24 Stunden bestehen innerhalb der ausgewiesenen Rundungstoleranz. Das ist ein rechnerischer Konsistenznachweis, keine Feldvalidierung. Profilparameter, Strahlung und zeitliche Wetterverteilung bleiben Näherungen.

Modellvertrauen berücksichtigt Datenlücken und die Sensorabweichung vor der Korrektur; derselbe unveränderte Sensorbericht kann nicht wiederholt kalibrieren. Exportierte Bilanz-, Speicher- und Aktualisierungsdaten bleiben lesend und JSON-kompatibel. Beschädigte Sitzungszeitstempel verhindern die sichere Schließung nach Neustart nicht.

Mypy 2.4.0 prüft alle 17 Programmdateien ohne Befund. Strengere Prüfoptionen gelten für Berechnungen, Diagnoseverträge, Modelle, Zeitplanung und Speicherung. Die vollständige Strict-Typisierung sowie über 95 % Abdeckung jedes Moduls bleiben offene Anforderungen. Ruff, Python-Kompilierung, JSON/YAML, relative Dokumentationslinks und Git-Whitespace-Prüfung sind Bestandteil der Abschlussprüfung. CI enthält nun ebenfalls Mypy.

Zusätzliche Exportprüfung: NaN und positive/negative Unendlichkeit in Wetter-Rohattributen werden als Text ausgegeben. Drei Regressionen reproduzierten den JSON-Fehler vor der Korrektur und bestehen danach. Der abschließende Stand umfasst die oben genannten 491 Tests.

## Prüfung für 3.10.0

**554 Tests bestanden, 87,53 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Die 63 neuen Regressionen sichern die zwei Fehlerkorrekturen und neue Verlaufs-/Kalibrierungs-/Reaktionsdiagnosen ab. Historie: maximal 168 Stundenaufnahmen in sieben Tagen, höchstens 24 Aufnahmen in Sensorattributen. Wiederverwendete Sensorberichte gelten nicht als unabhängige Messungen. Konfigurationswechsel trennen die Vergleichsevidenz.

Die Eingangsdiagnose und alle Durchfluss-Sicherheitsprüfungen verwenden dieselbe Normalisierung/Frischeregel einschließlich der konfigurierten Startwartezeit. Wiederhergestellte Sitzungen mit fehlenden oder fehlerhaften Pflichtzeitstempeln werden geschlossen und mit sichtbarer Messlücke abgeschlossen. Die Testdoubles bestätigen Schließbefehle und Abschlusszustand, keine Hardwaregarantie.

Upgrade-Tests erhalten Einstellungen, Pflegehistorie, Verbrauch und bestehende Speicherfelder; die neuen optionalen Felder sind additiv und erfordern keine Konfigurationsversionserhöhung. Ungültige optionale Verlaufsdaten verhindern das Laden vorhandener Pflege-/Verbrauchsdaten nicht. Modellbeginn älterer Installationen wird nicht erfunden.

Kalibrierung und Reaktionsprüfung geben nachvollziehbare Hinweise, keine automatischen Parameteränderungen oder Wirkungsgradschätzungen. Regen, unvollständige Mengen und Verlaufszeitlücken begrenzen die Zuordnung. Zusätzliche Trockenheits-/Wiederbefeuchtungsreferenzen prüfen Wassererhaltung und Kapazitätsbegrenzung bei drei Bodenarten. Das Modell bleibt ohne lokale Feldvalidierung.

Mypy 2.4.0: alle 19 Programmdateien ohne Befund, strengere Optionen für sieben Kernmodule. Die neuen Verlaufshilfen erreichen rund 97 % kombinierte Abdeckung. Vollständige Strict-Typisierung, durchgehend über 95 % Abdeckung und echte Hardware-/Versionsmatrixprüfungen bleiben offen. Abschlussprüfungen umfassen Ruff, Kompilierung, JSON/YAML, tatsächliches HA-Rendern aller Dashboard-Vorlagen, Dokumentationslinks und Git-Whitespace.


## Ergänzende Prüfung für 3.11.0

Geprüft am 4. Oktober 2026. Sieben fehlschlagende Regressionen wurden vor der Korrektur reproduziert: zukünftige Durchflussmeldungen bei Start und Restlaufzeitanzeige, zukünftige Wetter-/Temperatur- und Regenmeldungen, verlorene ursprüngliche Modellabweichung bei wiederverwendeten Sensorberichten, doppelte Stunden durch verschiedene UTC-Offsets und zu viel aktive Mähzeit durch verspätete Ereignisse. Die Korrekturen sind durch `tests/test_release_3110_regressions.py` abgesichert. Prognosecache-Zeitstempel werden ebenfalls auf Zukunft geprüft.

`tests/test_release_3110.py` prüft zusätzlich Pflegeprioritäten bei fehlenden Daten, Frost, Regen und laufender Bewässerung; getrennte Wochenperioden mit bekannten Referenzsummen, Zeitumstellungen und Aufzeichnungslücken; unbekannte/geschätzte Verbrauchseinträge; unabhängige Sensorberichte und wiederholte Ausfälle; Zykluszeiten mit Pausen, eigenen Summen-/Ratenzählern und Rest-Sicherheitslaufzeit; Mäherunterbrechungen, Undo und Speicherrücknahme; optionale beschädigte Mäherdaten sowie JSON-kompatible, lokalisierte und ausschließlich lesende Diagnoseattribute. Der bestehende Aufbewahrungstest wurde gezielt auf 336 Stundenaufnahmen in 14 Tagen angepasst.

**606 Tests bestanden, 88,83 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Gegenüber 3.10.0 wurden 52 Tests ergänzt. Mypy 2.4.0 prüft alle 20 Programmdateien ohne Befund; neun Kernmodule verwenden strengere Prüfoptionen. Ruff-Formatierung, Ruff-Prüfung, Python-Kompilierung, JSON/YAML, tatsächliches HA-Rendern sämtlicher Dashboard-Vorlagen, Dateiheader, relative Dokumentationslinks und Git-Whitespace-Prüfung sind erfolgreich.

Die neuen Pflege- und Zyklushinweise sind Heuristiken und ändern keine Einstellungen oder Geräte. Fehlende historische Daten werden nicht ergänzt. Wochen-Regenwerte erscheinen nur bei ausreichender Aufzeichnung und bekannter Regenquelle; die Zuordnung von Verbrauch anhand lokaler Tage bleibt geschätzt. Flache Messwerte sind kein bestätigter Defekt; Mährobotersitzungen bestätigen keine Flächenabdeckung. Das Bodenmodell bleibt ein nicht vor Ort validiertes Profilmodell. Vollständige Strict-Typisierung, über 95 % Abdeckung in jedem Modul sowie Hardware- und Versionsmatrixprüfungen bleiben offen.

## Ergänzende Prüfung für 3.12.0

Acht zunächst fehlschlagende Regressionen wurden reproduziert und korrigiert: naive Prognosezeitpunkte, doppelte absolute Prognosestunden, ungültige Luftfeuchte einschließlich Boolean-Werten, widersprüchliche Prognosen derselben Stunde, Boolean-Werte im aktuellen Wetter, Boolean-Niederschlag, abgelaufene Nassrasen-Pflegesperren und naive gespeicherte Nassrasen-Zeitpunkte. Widersprüche bleiben als unbekannte Daten sichtbar und senken die Bewässerungs-Prognosesicherheit; sie werden nicht als trockene Stunde interpretiert.

Die beiden neuen Testdateien ergänzen 79 Fälle für Taupunktreferenzen, fehlende und ungültige Wetterdaten, Regen-/Tau-Trocknung, Frost, Hitze, Wind, Nebel, Prognoselücken, lokale und sekundengenaue Mähzeitfenster einschließlich Zeitumstellungen, vorhandene Blattnässe-Eingänge, Konfigurationsfehler, lokalisierte Diagnosen, Pflegeverfügbarkeit, laufende Bewässerungssegmente/Einweichpausen, Mindestlaufzeiten, unbekannte Pausenenden und beobachtete Wochenänderungen. Die deutschen und englischen Dashboard-Vorlagen werden mit Home Assistants tatsächlicher Template-Engine geprüft, einschließlich befüllter Mähfenster.

**685 Tests bestanden, 88,82 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Mypy 2.4.0 prüft alle 21 Programmdateien ohne Befund; zehn Kernmodule verwenden strengere Prüfoptionen. Ruff-Formatierung, Ruff-Prüfung, Python-Kompilierung, JSON/YAML, Dateiheader, relative Dokumentationslinks und Git-Whitespace-Prüfung sind erfolgreich.

Es entstehen keine neuen Entitäten. Mähzeitfenster und Tau-/Trocknungsregeln sind konservative Empfehlungen auf Basis vorhandener Wetterdaten, keine gemessene Bestätigung trockener Grasoberflächen. Ein vorhandener frischer Blattnässe-Eingang verbessert die aktuelle Einschätzung, ersetzt jedoch keine künftige Prognose. Das Bodenmodell wurde durch diese Änderung nicht neu kalibriert oder im Feld validiert. Zweites Ventil, bestehende Pflege-/Verbrauchsdaten und reguläre OWM-Abfragehäufigkeit bleiben unverändert. Die dokumentierten Hardware- und Versionsmatrix-Grenzen gelten weiter; vollständige Fehlerfreiheit wird nicht behauptet.


## Ergänzende Prüfung für 3.15.0

Geprüft am 5. Oktober 2026: **800 Tests bestanden, 89,30 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Die 46 zusätzlichen Fälle prüfen gespeicherte und neu geladene Empfehlungen, Begrenzung und fehlerhafte Zeitstempel, wiederholte/widersprüchliche Wetterberichte, unvollständige Wasserbilanzen, unveränderte abgeschlossene Sitzungsflächen, Programm-/Quellen-/Flächenvergleich, reine Attributänderungen des Mähers, Speicherrücknahme bei Fehler/Abbruch, zusätzliche Unsicherheit ohne Empfehlungssperre und tatsächliches HA-Rendern der befüllten deutschen/englischen Dashboard-Vorlagen.

Vier Fehlschläge wurden mit dem bisherigen Coordinator/Sensor aus 3.14.0 reproduziert: gespeicherte Wetterlisten als `null` oder Zahl, ungültige Zeilen innerhalb dieser Liste und ein fehlender Abschlussgrund im letzten Bewässerungsdatensatz. Die Korrekturen verwerfen ungültige optionale Verlaufsdaten und lokalisieren fehlende/fehlerhafte Abschlussgründe ohne Ausnahme. Der gespeicherte Pflege-/Verbrauchsverlauf wird dadurch nicht ersetzt.

Ruff-Formatierung, Ruff-Prüfung und Mypy 2.4.0 für alle 23 Programmdateien sind erfolgreich. `review.py` verwendet ebenfalls die strengeren Typoptionen. Python-Kompilierung, JSON/YAML, Dateiheader, relative Dokumentationslinks und Git-Whitespace-Prüfung sind erfolgreich. Empfehlungen bleiben auf zwölf Datensätze/sieben Tage begrenzt; Wetterpunkte auf die vorhandenen 96 Aufnahmen. Entitätsattribute erzeugen weder Verlaufseinträge noch Speicher-/Schaltaktionen.

Der Rückblick benötigt mindestens zwei unabhängige aktuelle Wetterberichte, höchstens 45 Minuten auseinander und von den Fenstergrenzen entfernt. Fehlende oder widersprüchliche Belege bleiben unzureichend. Auch ein passendes Stichprobenergebnis bestätigt weder durchgehend passendes Wetter noch trockene Grasoberflächen. Programm-/Bereichsmerkmale werden ausschließlich aus tatsächlich vorhandenen Quellattributen übernommen. Ältere Mähdatensätze ohne Flächenkontext bleiben erhalten, werden aber nicht als vergleichbare Dauermessungen verwendet. Modellliter älterer Bewässerungssitzungen ohne gespeicherte Fläche bleiben unbekannt.

Abgebrochene Bewässerung wird wegen einer Restmenge nicht automatisch fortgesetzt. Aktuelle Sicherheitsbedingungen sind vor einem neuen Start erneut zu prüfen. Historische Modelllücken werden durch eine neue Bodenmessung nicht rückwirkend gefüllt. Vorhandene Neustart-, Einweichpausen-, Sensorausfall- und Sicherheitsregressionen bestehen; das zweite Ventil bleibt lesend. Die dokumentierten Hardware-, Feldvalidierungs-, Versionsmatrix- und Quality-Scale-Grenzen gelten weiterhin.


## Ergänzende Prüfung für 3.16.0

Geprüft am 5. Oktober 2026: **905 Tests bestanden, 89,63 % kombinierte Zeilen-/Zweigabdeckung**. Python 3.14.7 / Home Assistant 2026.9.4. Die 105 zusätzlichen Fälle prüfen bedingte Pflegeketten und echte 48-Stunden-Horizonte an Zeitumstellungen, unbekannte/abgelaufene Zeitfenster, getrennte Rückblick-Zählungen, vollständige Mengenvergleiche mit Toleranzen und Abbruchgründen, Quellen-/Flächenwechsel, alte Metadaten, wiederholte/doppelte/widersprüchliche Sitzungen und ausschließlich lesende Diagnosen. Befüllte deutsche und englische Dashboard-Karten werden mit der tatsächlichen HA-Template-Engine gerendert. Ein älterer Dashboardtest findet die Mähdetailkarte jetzt anhand ihres Inhalts statt anhand der letzten Position im Stapel.

Sieben zunächst fehlschlagende Fälle wurden reproduziert: vier gespeicherte Kalibrierungszeitpunkte (ohne Zeitzone, Zahl, Objekt, Zukunft), Plattform-Entladen mit Ausnahme oder Abbruch und eine inzwischen veraltete Bodenmessung als angeblich aktuelle Lücken-Erholungsgrundlage. Die Korrekturen prüfen gespeicherte Uhren, stellen nach fehlgeschlagenem Plattform-Entladen die Controllerüberwachung wieder her und prüfen die aktuelle Bodenquelle. Zusätzliche Setup-/Unload-Tests erhalten Listener bei unbestätigter physischer Abschaltung.

Die Modellprüfung verwendet unabhängige analytische Referenzen für 30 Tage Trockenheit bei drei Böden, drei Wurzeltiefen und drei Intervallgrößen. Starkregenreferenzen berücksichtigen drei Hangneigungen und zwei Verdichtungszustände. Wiederholte Wasserzugaben erhalten bekannte Speicher-/Überlaufmengen. Ungültige und fehlende Bodenmessungen setzen die Modellfeuchte nicht auf null; eine wiederkehrende Messung wird anteilig und nicht wiederholt als dieselbe Meldung verrechnet. Diese Prüfungen verändern keine Bodenparameter und ersetzen keine Feldvalidierung.

Ruff, Mypy 2.4.0 für alle 24 Programmdateien, Python-Syntax/Kompilierung, JSON/YAML, Dateiheader, relative Dokumentationslinks und Git-Whitespace sind erfolgreich. Das neue `outlook.py` verwendet die strengen Typoptionen. Der Pflegeausblick ist keine Reservierung oder Simulation künftiger Bodenfeuchte; offene Vorgänger lassen den ausführbaren Termin unbekannt. Bewässerungsmengenvergleiche beschreiben Abweichungen ab 5 % beziehungsweise 1 Liter und verändern weder Sollmengen noch Sicherheitseinstellungen. Alte Verbrauchsdaten bleiben erhalten; fehlende Vergleichsmetadaten werden nicht erfunden. Überlappende Mähfenster können Wetterpunkte teilen und liefern keine Genauigkeitsquote oder bestätigte Rasentrockenheit.

Bestehende Neustart-, Einweichpausen-, Speicherkonkurrenz- und Sicherheitsregressionen bestehen. Es entstehen keine zusätzlichen Entitäten, regelmäßigen Wetterabfragen oder Mäherbefehle. Das zweite Ventil bleibt lesend. Die bisherigen Hardware-, Feldvalidierungs-, Versionsmatrix- und Quality-Scale-Grenzen gelten weiterhin.

## Ergänzende Prüfung für 3.16.1

Geprüft am 5. Oktober 2026: **939 Tests bestanden, 90,41 % kombinierte Zeilen-/Zweigabdeckung** unter Python 3.14.7 / Home Assistant 2026.9.4. Die 34 neuen Fälle laden die Entitätsübersetzungen mit Home Assistants tatsächlicher Übersetzungsschnittstelle in Deutsch und Englisch. Alle ausgegebenen obersten Sensorattribute einschließlich des bedingten Mähroboter-Schätzhinweises und sämtlicher Sensor-Enumwerte besitzen Beschriftungen. Beide Sprachdateien haben identische Schlüssel; die englische Datei stimmt mit `strings.json` überein.

Die Prüfung bestätigt feste übersetzte Ventilzustände, Sitzungsquellen und Abschaltgründe, acht saisonale Düngestatus sowie den kontextabhängigen Status `not_due`. Beim Düngen bedeutet dieser „Keine Düngung fällig“; der Bewässerungsstatus behält seine Bodenfeuchte-Erklärung. Verschachtelte Pflegepläne erhalten lesbare `status_text`-Felder. Der Bewässerungsstatus stellt wie die anderen Bewässerungsdiagnosen die Sperrgründe zusätzlich als Textliste bereit. Regionale Sprachkennungen werden in Erläuterungen und Handlungshinweisen konsistent aufgelöst. Unbekannte Codes und englischer Rückfall bleiben erhalten.

Ruff-Formatierung, Ruff-Prüfung, Mypy für alle 24 Programmdateien, Python-Syntax, JSON/YAML, relative Dokumentationslinks und Git-Whitespace sind erfolgreich. Lesende Attribute erhalten Rohcodes und gespeicherte Daten; die Tests bestätigen ausbleibende Service-/Prognoseaufrufe. Bestehende Sicherheits-, Speicher-, Neustart-, Entlade- und Modellregressionen bestehen ebenfalls. Keine neuen Entitäten, regelmäßigen Wetterabfragen oder Mäherbefehle; das zweite Ventil bleibt lesend.

Der Nachweis betrifft die tatsächliche HA-Übersetzungsladung und Python-/Template-Verträge, keinen visuellen Test sämtlicher Frontendkarten. Rohattribute in Entwicklerwerkzeugen/JSON bleiben technisch stabil; innere Objektschlüssel werden nicht rekursiv übersetzt. Gemeinsame Erklärungstexte folgen der allgemeinen HA-Sprache, während unterstützte Frontendbeschriftungen der jeweiligen Benutzersprache folgen. Die Hardware-, Feldvalidierungs-, Versionsmatrix- und Quality-Scale-Grenzen gelten weiter.


## Ergänzende Prüfung für 3.18.0

28 neue Serverregressionen prüfen Panel-Eigentum und gleichzeitige Registrierung, Leserechte und Administratoraktionen, veraltete Pflegeeinträge, geschützte physische/automatische Daten, Speicherfehler und optionale Benachrichtigungen einschließlich Neustart und Listener-Abmeldung. Alle 986 Python-Tests bestehen mit 89,83 % kombinierter Zeilen-/Zweigabdeckung. Ruff-Formatierung, Ruff-Lint und Mypy für 26 Programmmodule bestehen.

12 neue Chromium-Regressionen prüfen die tatsächliche JavaScript-Komponente mit lokalen HA-Doubles. Die sieben Desktop-/Smartphone-Ansichten, Flächenwechsel mit verspäteten Antworten, geöffnete Details, unbekannte Automatik, Literziele, historische Erfassung, Benachrichtigungseinstellungen, Lesemodus, Verbindungsunterbrechung, Direktlinks und sichere Textausgabe bestehen. Screenshots der Übersicht, Verläufe und Pflegeprotokolle wurden visuell geprüft. Die Tests laufen zusätzlich als eigener GitHub-Actions-Job. Sie ersetzen keine Prüfung mit einer echten HA-Frontend-Instanz und physischen Geräten.
