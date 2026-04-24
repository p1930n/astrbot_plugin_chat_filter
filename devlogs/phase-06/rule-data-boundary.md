# Rule Data Boundary

## Decision

Rule corpora are runtime data, not code defaults.

`settings.py` only owns feature switches, bounds, normalization, and validation.
It must not embed large keyword or regex corpora.

`_conf_schema.json` only describes configurable fields and safe empty defaults.
It must not ship sensitive or fast-changing rule data as default values.

## Runtime Data

Operators should maintain actual keyword and regex corpora in AstrBot runtime
configuration, such as:

```text
data/config/astrbot_plugin_chat_filter_config.json
```

Later, if rule management needs category metadata, import/export, auditing, or
frequent group-specific edits, move the corpus to a dedicated SQLite-backed rule
repository.

## Compatibility

Existing runtime JSON values continue to load normally. Explicit empty lists in
runtime configuration are respected as empty lists and will not fall back to code
defaults.
