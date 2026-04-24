# Phase 04a OneBot Mute And Recall

## Scope

Phase 04a wires real OneBot v11 mute and recall calls for the confirmed
`aiocqhttp` runtime only.

Implemented:

- use `event.bot.api.call_action(...)` through a narrow extracted action client;
- call `set_group_ban` for group mute;
- call `delete_msg` for message recall;
- keep merged forward, text log push, and file push as `unsupported`;
- update violation action statuses after each attempted action.

Not implemented in this slice:

- merged forward push;
- separate text log push;
- periodic file generation or file sending;
- retry, queue, timeout, or rate-limit orchestration.

## Official API Baseline

References checked on 2026-04-24:

- `https://docs.astrbot.app/dev/star/guides/listen-message-event.html`
- `https://docs.astrbot.app/platform/aiocqhttp.html`
- `https://docs.astrbot.app/dev/star/plugin.html`
- `https://onebots.pages.dev/v11/action`

Confirmed baseline:

- AstrBot documents `GROUP_MESSAGE` event filtering and standard
  `yield event.plain_result(...)` command responses.
- AstrBot documents OneBot v11 as the `aiocqhttp` adapter family.
- AstrBot's old plugin guide documents `event.bot.api.call_action(...)` for
  `delete_msg` on `aiocqhttp`.
- OneBot v11 documents `delete_msg` with numeric `message_id`.
- OneBot v11 documents `set_group_ban` with numeric `group_id`, numeric
  `user_id`, and `duration` in seconds.

## Boundary

AstrBot framework objects remain constrained to:

- `main.py`
- `astrbot_event_adapter.py`

`astrbot_event_adapter.py` extracts only `event.bot.api` as an opaque action
client. `platform_actions.py` receives that client through a protocol and does
not import AstrBot.

Native business/data modules:

- `command_service.py` owns admin command business logic, state mutation,
  validation, and command response text.
- `platform_actions.py` owns OneBot action call formatting and degradation.
- `violation_records.py` owns violation row assembly and insertion.
- `violation_actions.py` owns action orchestration after a persisted violation
  id exists.
- `repository.py` owns SQLite reads and status updates.

The executor receives the AstrBot logger through explicit dependency injection
from `main.py`, so it does not import AstrBot framework types.

After boundary review, `main.py` was reduced to the AstrBot-facing surface:

- plugin construction and dependency injection;
- AstrBot decorators and command/event routing;
- event dehydration;
- `event.stop_event()`;
- `yield event.plain_result(...)`;
- action-client extraction dispatch for the OneBot adapter.

Command business logic, SQLite command helpers, violation record assembly,
excerpt/digest generation, and action status probing are no longer implemented
inside `main.py`.

## Runtime Order

For a matched group message:

1. dehydrate the AstrBot event into native message fields;
2. match against the current policies;
3. insert the violation row with initial action statuses;
4. call `event.stop_event()` when configured;
5. if and only if the violation row exists, attempt mute;
6. write back `action_mute_status`;
7. attempt recall when `message_id` is present;
8. write back `action_recall_status`;
9. return the configured warning response when enabled.

If the violation record cannot be written, no platform action is attempted.
If a platform action fails, the violation row remains and only that action
status is updated to `failed` or `unsupported`.

## Persistence

No table, column, index, or storage path changes were added in this slice.

Repository additions:

- `get_enabled_group_mute_policy(platform, group_id)`
- `update_violation_action_status(violation_id, action, status)`

All SQL remains parameterized. The only dynamic SQL fragment is the status
column name selected from a fixed in-process allowlist:

- `mute -> action_mute_status`
- `recall -> action_recall_status`
- `forward -> action_forward_status`

## Degradation

OneBot actions degrade as follows:

- missing action client: `unsupported`
- invalid numeric OneBot scope: `failed`
- adapter call exception: `failed`
- missing message id for recall: `unsupported`

The normal log path records exception type only. It does not store raw platform
responses, SQL, stack traces, message text, token, cookie, or full event
context.

## Validation

Automated validation run locally:

- Python syntax compilation for modified plugin modules: passed.
- Smoke test for `OneBotV11PlatformActions`: passed.
- Smoke test for `ViolationActionExecutor`: passed.
- Smoke test for `ChatFilterCommandService`: passed.
- Smoke test for `ViolationRecorder`: passed.
- Smoke test for repository policy lookup and action status updates: passed.
- `main.py` size after boundary cleanup: 257 lines.
- Long-line scan over Python files: passed.
- Dangerous call scan for `print`, `requests`, `time.sleep`, `subprocess`,
  `eval`, and `exec`: no matches.

Not run:

- Ruff, because `python -m ruff check .` failed with `No module named ruff` in
  the local Python environment.
- Real AstrBot runtime validation after Phase 04a; this requires a live
  `aiocqhttp` connection and bot permissions.

## Manual Acceptance

Prerequisites:

- AstrBot v4.9.0 or the current target runtime loads the plugin without
  Traceback.
- `aiocqhttp(OneBot v11)` is connected.
- The bot has enough group permission to mute users and recall messages.
- Use a non-admin test account that can safely be muted.

Checks:

1. Restart or hot-reload the plugin and confirm it loads.
2. Run `/cf probe` in the target group.
3. Expect `mute_user=supported` and `recall_message=supported` when
   `event.bot.api` is available.
4. Run `/cf mute <listening_group> 60`.
5. Ensure the target group is enabled and contains a test keyword.
6. Send the test keyword from the test account.
7. Confirm the violation row exists before evaluating action results.
8. Confirm the sender is muted if the bot has permission.
9. Confirm the original message is recalled if the adapter permits recall.
10. Confirm the latest violation row records `success`, `failed`, or
    `unsupported` per action instead of losing the violation record.

If mute or recall fails because of bot permission, target role, adapter policy,
or recall time window, acceptance should treat the local persistence and
degradation path as valid when the row is retained and the action status is
`failed`.

## Remaining Risks

- `event.bot.api` was documented and previously probed indirectly, but Phase
  04a still needs live confirmation after this exact implementation.
- OneBot permission failures and adapter-specific return codes are currently
  collapsed to `failed`; finer error categories belong in a later hardening
  slice.
- There is no timeout, retry, rate-limit, or queue around platform actions yet.
  This slice keeps the call path direct and records degradation.
- `group_name` remains optional because Phase 03 live validation showed it was
  missing in the target runtime.
- Push and file delivery remain `unsupported`.

## Commit / Push

- Commit: not performed for Phase 04a.
- Push: not performed.
- Current state: ready for live acceptance; Hold before commit.
