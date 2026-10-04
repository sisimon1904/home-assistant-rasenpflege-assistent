# Quellcode und Kommentierung

Alle Python-Dateien besitzen einen englischen Modulheader mit Dateipfad, Zweck und Zuständigkeit. Die zentralen Funktionen erläutern zusätzlich Datenfluss, Einheiten, Fehlerbehandlung und Sicherheitsregeln. Kommentare stehen im Quellcode auf Englisch; diese Übersicht ist auf Deutsch.

## Einstieg in den Programmablauf

| Datei in `custom_components/rasenpflege_assistent/` | Zuständigkeit |
| --- | --- |
| `__init__.py` | HA-Einrichtung, Aktionen, Migrationen, Listener und sicheres Entladen. |
| `config_flow.py` | Eingabeformulare, Optionsseiten und Validierung vorhandener Datenquellen. |
| `const.py` | Stabile Konfigurationsschlüssel, Standardwerte, Intervalle und Versionskennungen. |
| `inputs.py` | Gemeinsame Durchflussnormalisierung und Altersprüfung für Controller und Diagnose. |
| `insights.py` | Begrenzter Diagnoseverlauf, validierte Wiederherstellung und konservative Kalibrierungs-/Reaktionshinweise. |
| `diagnostic_types.py` | Typverträge für Wasserbilanz, Modellvertrauen und Speicherdiagnose. |
| `everyday.py` | Lesende Pflegeprioritäten, zwei Wochenperioden, Sensorhinweise und Zyklusschätzungen. |
| `models.py` | Berechnete `LawnData` und dauerhaft gespeicherte `RuntimeState`. |
| `coordinator.py` | Messwertnormalisierung, Vorhersagecache, Bodenmodell und Pflege-Transaktionen. |
| `calculations.py` | Reine Berechnungen für Wachstum, Verdunstung, Wasserbilanz und Empfehlungen. |
| `planning.py` | Lokale Zeitfenster, Sommerzeit, Verbrauchsperioden und Tageszuordnung. |
| `irrigation.py` | Ventilbesitz, Start/Pause/Fortsetzung/Stopp, Sicherheitsprüfungen und Abrechnung. |
| `storage.py` | Speichern und anschließendes Bestätigen der gespeicherten Momentaufnahme. |
| `mowing.py` | Ausschließlich lesende Beobachtung geschätzter Mährobotersitzungen. |
| `entity.py` | Gemeinsame Identität, virtuelles Rasengerät und Coordinator-Anbindung. |
| `sensor.py` | Zustände, Einheiten, Attribute und lesbare Diagnoseinformationen. |
| `button.py` | Delegation von Bedienaktionen an Modell oder Bewässerungscontroller. |
| `switch.py` | Gespeicherter Automatikschalter mit Sicherheitsbehandlung im Controller. |
| `explanations.py` | Deutsche/englische Erläuterungen stabiler maschinenlesbarer Grundcodes. |
| `diagnostics.py` | JSON-kompatible Diagnose für genau einen Konfigurationseintrag. |

Die Python-Tests tragen ebenfalls Dateiheader. YAML-Header erläutern die Aktionsdefinitionen, Dashboard-Vorlagen und GitHub-Workflows. Die vorhandenen Beispielentitäten müssen weiterhin an die eigene HA-Installation angepasst werden.

## JSON-Dateien

JSON erlaubt keine Kommentare oder Header. Zusätzliche Kommentar-Schlüssel würden die HA-/HACS-Schemata verändern. Die folgenden Dateibeschreibungen dokumentieren deshalb ihre Zuständigkeit, ohne ungültige JSON-Dateien zu erzeugen.

| Datei | Zweck und Pflegehinweis |
| --- | --- |
| `custom_components/rasenpflege_assistent/manifest.json` | HA-Metadaten, Integrationstyp, Abhängigkeiten und Version; Versionsänderungen mit `const.py` abstimmen. |
| `custom_components/rasenpflege_assistent/strings.json` | Basisdefinition der HA-Texte und Übersetzungsschlüssel; Schlüssel mit Plattformen, Formularen und Aktionen abstimmen. |
| `custom_components/rasenpflege_assistent/translations/de.json` | Deutsche UI-Texte, Zustandsübersetzungen und Fehlermeldungen. |
| `custom_components/rasenpflege_assistent/translations/en.json` | Englische UI-Texte, Zustandsübersetzungen und Fehlermeldungen. |
| `custom_components/rasenpflege_assistent/icons.json` | HA-Icon-Zuordnung anhand der Übersetzungsschlüssel. |
| `hacs.json` | HACS-Paketinformationen einschließlich der Mindestversion von Home Assistant. |

PNG-Dateien unter `brand/` sind Bilddateien und erhalten keinen Textheader.

## Regeln für weitere Änderungen

Der Controller serialisiert Sitzungsübergänge; der Coordinator serialisiert Modelländerungen und Speichertransaktionen. Wenn beide Sperren benötigt werden, wird zuerst die Controllersperre und danach die Modellsperre genommen. Die unmittelbare Sicherheitsabschaltung darf während einer Speicherwartezeit physisch schließen. Eine Rücknahme fehlgeschlagener Modelländerungen muss diese Sicherheitsänderung erhalten.

Die zweite Ventilquelle bleibt ausschließlich lesend. Eine erfolgreiche Schaltaktion beweist noch keine physische Ventilschließung. Verbrauch und aktive Dauer werden bis zur bestätigten Schließung betrachtet; unvollständige Messungen bleiben sichtbar. Eine Zielsollmenge wird nicht bereits beim Start als geliefertes Wasser verbucht.

Berechnungen verwenden Celsius, Millimeter und m/s; die Bewässerung verwendet Liter und Liter/Minute. Ein Millimeter auf einem Quadratmeter entspricht einem Liter. Lokale Tage und Wochentage richten sich nach der HA-Zeitzone; für tatsächliche Zeitabstände an Sommerzeitgrenzen werden UTC-Zeitpunkte verwendet. Vorhersagen stammen aus vorhandenen HA-Wetterquellen und deren Cache.

Bei reinen Kommentaränderungen lassen sich Python-Syntaxbäume ohne Docstrings sowie geladene YAML-Inhalte vergleichen. Ergänzend sichern Ruff und die vollständige Testsuite Syntax, Formatierung und Verhalten ab. Das Ergebnis der aktuellen lokalen Prüfung steht im [Qualitätsaudit](quality-audit.md).

## Typprüfung und Regressionen

`python -m mypy` verwendet `mypy.ini` und prüft alle 20 Programmdateien einschließlich bisher untypisierter Funktionskörper. Berechnungen, Diagnoseverträge, Datenmodelle, Zeitplanung, Speicherung, Eingangsprüfung, Verlaufshilfen, Alltagshinweise und Mäherbeobachtung verwenden zusätzlich strenge Prüfoptionen. Dynamische HA-/Provider-Payloads und Teile des Controllers verwenden weiterhin `Any`; eine vollständige Strict-Typisierung des gesamten Pakets ist damit nicht behauptet. Die GitHub-Tests führen dieselbe Prüfung mit Mypy 2.4.0 aus.

Die neuen Regressionen in `test_release_390_model.py`, `test_release_390_diagnostics.py` und `test_release_390_config.py` prüfen mehrtägige Wassererhaltung, Intervallvergleich, Modellvertrauen, Sensorabgleich, Speicherfehler, Diagnoseexport und unabhängige Optionsseiten. Sie ergänzen die bisherigen Geräte-/Lebenszyklustests.

`test_release_3100.py` prüft die additive Speicherung des Diagnoseverlaufs, unveränderte Einstellungen/Pflege-/Verbrauchsdatensätze beim Update, getrennte Brutto-/Bodenwassermengen, gemeinsame Durchflussfrische und den sicheren Sitzungsabschluss bei fehlenden Startzeiten. Der optionale Verlauf verwendet typisierte Beobachtungen und wird beim Laden validiert; ungültige Zeilen werden verworfen. Sitzungs- und Provider-Payloads an bestehenden dynamischen Grenzen bleiben teilweise `Any`.
