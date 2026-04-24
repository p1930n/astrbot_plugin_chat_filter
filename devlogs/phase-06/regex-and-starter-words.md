# Phase 06 Regex And Starter Words

## Scope

- Add a conservative default global word list for common spam, scam, and gray-market content.
- Add global regex rule support from WebUI configuration.
- Do not add QQ commands that echo word lists or regex rules.
- Do not add group-level regex persistence in this slice.

## Runtime Boundary

Regex rules are compiled during settings loading. Invalid, duplicate, too long,
or obviously high-risk rules are skipped.

The matcher caps regex input to the first 2000 characters of a message. This is
not a complete ReDoS proof, but it keeps this phase from adding unbounded regex
work to the high-frequency group-message path.

## Configuration

- `global_words`: default starter literal words; can be overwritten in WebUI.
- `global_regex_rules`: optional global regex rules; default is empty.

## Acceptance

1. Restart AstrBot and confirm the plugin loads.
2. Enable the target group.
3. Send a message containing one starter word from the WebUI-visible default
   list and confirm the normal violation path still runs.
4. Add a safe regex rule in WebUI, restart or reload config as AstrBot requires,
   and confirm a matching message is blocked.
5. Confirm QQ commands do not print the concrete word list or regex list.
