# Sprache der Attribute

Die Integration stellt Attributbeschriftungen und bekannte feste Attributwerte auf Deutsch und Englisch bereit. In unterstützten Home-Assistant-Ansichten richtet sich ihre Anzeige nach der Sprache des jeweiligen Benutzers. Nach einem Integrationsupdate Home Assistant neu starten und gegebenenfalls die Oberfläche neu laden.

| Technischer Wert | Deutsche Anzeige | Englische Anzeige |
| --- | --- | --- |
| `model_confidence: high` | Vertrauen in das Bodenmodell: Hoch | Soil model confidence: High |
| `valve_state: on` | Status des Rasenventils: Offen | Lawn valve state: Open |
| `session_source: auto` | Sitzungsstartquelle: Automatisch | Session start source: Automatic |
| `fertilizer_status: not_due` | Düngestatus: Keine Düngung fällig | Fertilizing status: No fertilizing due |

Die Schlüssel und Rohwerte ändern sich durch Übersetzungen nicht. Eine Automation verwendet weiterhin beispielsweise `state_attr(entity, 'valve_state') == 'on'`. Entwicklerwerkzeuge, JSON-Diagnosen und direkte Template-Zugriffe können deshalb weiterhin englische Schlüssel und Codes zeigen. Entitäts-IDs, Zahlen, Einheiten und Zeitstempel werden nicht in übersetzte Freitexte umgewandelt.

Für verschachtelte Diagnoseobjekte bietet HA keine automatische rekursive Übersetzung jedes inneren Feldes. Die Integration stellt dafür lesbare Felder wie `reason_text`, `status_text`, `quality_text` oder `scope_text` bereit. Beispielsweise enthält `mowing.status` weiterhin den Code und `mowing.status_text` dessen Erklärung. Bestehende Dashboard-Vorlagen verwenden solche Textfelder.

Diese Erklärungstexte sind gemeinsame Entitätsattribute und richten sich nach der allgemeinen HA-Sprache in **Einstellungen → System → Allgemein**, nicht individuell nach jedem Betrachter. Die Oberflächensprache eines Benutzers kann daher von der Sprache dieser Texte abweichen. Deutsch und Englisch werden unterstützt; für andere Sprachen gilt Englisch als Rückfall. Unbekannte neue Codes bleiben zur Diagnose sichtbar.

Mushroom- und andere Template-Karten übersetzen Rohwerte nicht automatisch. Für den Entitätszustand `state_translated(entity)` verwenden; bei Diagnoseattributen das passende Textfeld. Vorlagen in [dashboard](dashboard/) enthalten deutsche und englische Beschriftungen.
