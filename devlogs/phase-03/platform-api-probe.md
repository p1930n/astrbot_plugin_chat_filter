# Phase 03 Platform API Probe

## Scope

Phase 03 only fixes the AstrBot/QQ adapter boundary. It does not execute mute,
recall, merged forward, text log push, or file push actions.

This phase adds:

- a dedicated AstrBot event dehydration boundary for group message events;
- a QQ platform action adapter skeleton;
- an admin probe command for live field and capability checks;
- default `unsupported` action statuses for new violation records.

## Official API Baseline

References checked on 2026-04-24:

- `https://docs-v3.astrbot.app/dev/star/resources/astr_message_event.html`
- `https://docs.astrbot.app/dev/star/guides/listen-message-event.html`
- `https://docs.astrbot.app/dev/star/guides/send-message.html`

Confirmed from official docs:

- `event.message_str` / `event.get_message_str()` provide plain text.
- `event.get_platform_name()` provides the platform name.
- `event.get_sender_id()` provides the sender id.
- `event.get_sender_name()` provides the sender nickname and may be empty.
- `event.get_group_id()` provides the group id for group messages.
- `event.message_obj.message_id` and `event.message_obj.group_id` are documented
  on `AstrBotMessage`.
- `event.message_obj.sender.nickname` is documented through `MessageMember`.
- `@filter.command_group("cf")` with subcommands maps to the documented command
  group style, whose examples use `/cf <subcommand>` style invocation.
- merged forward messages are documented as mostly unsupported, with current
  support called out for OneBot v11.

Not confirmed by local runtime:

- the exact QQ adapter platform string in this deployment;
- whether `.cf bind` and `.cf mute` are accepted by the target AstrBot command
  prefix configuration;
- whether QQ group message `message_id` is always non-empty;
- whether the target QQ adapter exposes a stable group name field;
- whether mute, recall, merged forward, text log push, or file push APIs are
  available to this plugin without adapter-specific calls.

## Command Probe

Existing command entries remain:

- `.cf bind [listening group] [push group]`
- `.cf mute [group] [seconds]`
- `/cf bind [listening group] [push group]`
- `/cf mute [group] [seconds]`

Safe live checks:

- `.cf bind list`
- `/cf bind list`
- `.cf mute list`
- `/cf mute list`

Phase 03 adds:

- `.cf probe`
- `/cf probe`

The probe response only reports `present`, `missing`, `supported`, or
`unsupported`. It does not echo raw group ids, user ids, message ids, tokens, or
message content.

## Event Field Boundary

`astrbot_event_adapter.py` is the only Phase 03 module that touches AstrBot
event fields for this plugin's platform boundary. `main.py` only calls the
adapter and routes native dataclasses into business code.

The snapshot contains:

- `platform`
- `group_id`
- `sender_id`
- `message_id`
- `sender_display_name`
- `group_display_name`

Field candidates are intentionally conservative:

- platform: `get_platform_name`, `platform_name`
- group id: `get_group_id`, `group_id`
- sender id: `get_sender_id`, `sender_id`, `user_id`
- message id: `get_message_id`, `message_id`
- sender display name: `get_sender_name`, `sender_name`,
  `sender_display_name`, `nickname`
- group display name: `get_group_name`, `group_name`, `group_display_name`

The adapter also checks `event.message_obj` and `event.message_obj.sender` for
the same field names. It does not synthesize fake ids. If `platform`,
`group_id`, or `sender_id` is missing on a group message, `main.py` skips the
message with a presence-only warning.

## Platform Actions

`platform_actions.py` defines the adapter contract and request/result objects:

- `mute_user`
- `recall_message`
- `send_forward_message`
- `send_text_log`
- `send_file`

`QQPlatformActions` currently returns `unsupported` for all five actions. This
is intentional. Phase 04 can replace individual methods with real adapter calls
after live API confirmation.

New violation rows now receive:

- `action_mute_status = unsupported`
- `action_recall_status = unsupported`
- `action_forward_status = unsupported`

The status probe is wrapped so that adapter-boundary failures fall back to
`unsupported` and do not block violation persistence.

## Validation

Automated validation for this phase:

- run Python syntax compilation for modified plugin modules;
- run a smoke check for `QQPlatformActions` returning `unsupported`;
- inspect that no real platform action method calls AstrBot or QQ APIs.

Manual validation still required in a real AstrBot + QQ adapter runtime:

- run `.cf bind list` and `/cf bind list`;
- run `.cf mute list` and `/cf mute list`;
- run `.cf probe` and `/cf probe` in a QQ group;
- capture whether `platform`, `group_id`, `sender_id`, `message_id`,
  `sender_name`, and `group_name` are `present` or `missing`;
- confirm that a violation record is written before any future platform action
  attempt;
- confirm hot reload still loads the plugin after adding
  `astrbot_event_adapter.py` and `platform_actions.py`.

## Live Validation 2026-04-24

Runtime:

- AstrBot: v4.9.0.
- QQ adapter: `aiocqhttp` / OneBot v11.
- Plugin load: passed; `astrbot_plugin_chat_filter` loaded without Traceback.

Command and field checks:

- `/cf probe`: passed.
- `.cf mute list`: passed, so dot-prefixed `cf` command routing is at least
  partially confirmed in this runtime.
- `/cf bind list`: passed.
- `/cf mute list`: passed.
- `/cf mute <group> 60`: passed with policy persisted.
- `/chatfilter group enable`: passed.
- `/chatfilter group add phase03probe`: passed.

Probe result:

- `platform`: present.
- `group_id`: present.
- `sender_id`: present.
- `message_id`: present.
- `sender_name`: present.
- `group_name`: missing.
- `mute_user`: unsupported.
- `recall_message`: unsupported.
- `send_forward_message`: unsupported.
- `send_text_log`: unsupported.
- `send_file`: unsupported.

Violation persistence check:

- A test message containing `phase03probe` triggered the warning response.
- Latest persisted violation row has platform present, group id present,
  sender id present, message id present, and sender display name present.
- Latest action statuses are all `unsupported`.

Conclusion:

- Phase 03 live validation passed for the API probe and safe degradation
  boundary.
- Group name remains unavailable in this runtime and must stay optional.
- Phase 04 may use `message_id` for recall design, but real recall still needs
  adapter API and permission-error confirmation before implementation.

## Remaining Risks

- `.cf` command prefix support is partially confirmed by `.cf mute list`; direct
  `.cf probe` and `.cf bind list` checks can still be run if exact parity with
  `/cf` is required. The official command-group examples use `/` invocation, so
  `/cf` remains the primary documented route.
- Group name is still unconfirmed. The current code only records a snapshot
  field if the adapter exposes one through the conservative candidate names.
- `message_id` is documented on `AstrBotMessage`, but target QQ adapter
  stability must still be checked before recall is implemented.
- Mute and recall require adapter-specific permission and error-code behavior
  confirmation before Phase 04.

## Commit / Push

- Commit: recorded in Git history for this phase.
- Push: not performed.
- Current state: Phase 03 accepted; Hold before Phase 04 implementation.
