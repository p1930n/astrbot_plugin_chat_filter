# Rule Data Boundary

## Decision

Rule corpora are runtime data, not code defaults.

`settings.py` only owns feature switches, bounds, normalization, and validation.
It must not embed large keyword or regex corpora.

`_conf_schema.json` only describes configurable fields and safe empty defaults.
It must not ship sensitive or fast-changing rule data as default values.

`data/config/astrbot_plugin_chat_filter_config.json` is also not a rule store.
It may only contain feature configuration. It must not contain keyword corpora,
regex corpora, starter rules, migration seeds, or backup copies of rule data.

## Runtime Data

Operators should maintain actual keyword and regex corpora in SQLite:

```text
data/astrbot_plugin_chat_filter/chat_filter.db
```

The authoritative global rule table is `global_rules`. Code should read global
words and regex rules through the rule repository and `RuleSnapshot`.

## Compatibility

Legacy JSON rule loading has been removed. Do not reintroduce silent fallback
imports from `global_words` or `global_regex_rules`.
