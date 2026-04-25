# Rule Storage Boundary

## Hard Rule

Do not store prohibited words, regex rules, starter corpora, seed corpora, or
any other rule data in JSON configuration files.

All rule data belongs in SQLite.

## Allowed JSON Content

`data/config/astrbot_plugin_chat_filter_config.json` is only for feature
configuration, for example:

- enable/disable switches
- warning text
- size and safety limits
- mute/report settings
- matcher behavior knobs such as `obfuscated_word_max_gap`
- regex behavior knobs such as `regex_gap_max`

JSON config must not contain:

- `global_words`
- `global_regex_rules`
- keyword lists
- regex rule lists
- initial rule seeds
- backup copies of SQLite rule data

## SQLite Ownership

The authoritative rule store is:

```text
data/astrbot_plugin_chat_filter/chat_filter.db
```

Rule data is stored in the `global_rules` table. Code that needs global words or
regex rules must read them through the rule repository and `RuleSnapshot`, not
through AstrBot config.

## Maintenance Notes

If new rule management features are added, implement them against SQLite first.
Do not add compatibility fallbacks that silently repopulate rules from JSON.

If import/export is needed later, use explicit operator actions and dedicated
files outside AstrBot runtime config. Import/export files are transfer artifacts,
not the source of truth.
