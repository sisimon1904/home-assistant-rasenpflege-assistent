# Attribute language

The integration provides attribute labels and known fixed attribute values in German and English. Supported Home Assistant views display them in the viewing user's language. Restart Home Assistant after updating the integration and reload the frontend if necessary.

| Technical value | German display | English display |
| --- | --- | --- |
| `model_confidence: high` | Vertrauen in das Bodenmodell: Hoch | Soil model confidence: High |
| `valve_state: on` | Status des Rasenventils: Offen | Lawn valve state: Open |
| `session_source: auto` | Sitzungsstartquelle: Automatisch | Session start source: Automatic |
| `fertilizer_status: not_due` | Düngestatus: Keine Düngung fällig | Fertilizing status: No fertilizing due |

Translations preserve attribute keys and raw values. An automation still uses, for example, `state_attr(entity, 'valve_state') == 'on'`. Developer Tools, JSON diagnostics and direct template access may therefore show English keys and codes. Entity IDs, numbers, units and timestamps are not converted into translated prose.

HA does not automatically translate every inner field of nested diagnostic objects. The integration supplies readable fields such as `reason_text`, `status_text`, `quality_text` or `scope_text`. For example, `mowing.status` retains its code and `mowing.status_text` contains its explanation. Existing dashboard templates use these text fields.

These explanations are shared entity attributes and use the general HA language under **Settings → System → General**, rather than each viewer's preference. A user's frontend language may therefore differ from the language of these texts. German and English are supported, with English fallback for other languages. Unknown new codes remain visible for diagnosis.

Mushroom and other template cards do not automatically translate raw values. Use `state_translated(entity)` for the entity state and the corresponding text field for diagnostic attributes. Templates in [dashboard](dashboard/) provide German and English labels.
