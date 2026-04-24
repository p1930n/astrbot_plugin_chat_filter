# Phase 04c Text Log Delivery

## Scope

Phase 04c adds separate plain-text log delivery after merged-forward delivery.

This phase includes:

- OneBot v11 `send_group_msg` support behind `send_text_log`;
- `/cf probe` reporting `send_text_log=supported` when an action client exists;
- one text log sent to each bound push group after the merged-forward attempt;
- timeout and exception degradation for text-log sends.

This phase does not include:

- putting violation content into the text log;
- storing text-log delivery status in SQLite;
- retry queues or background workers;
- file report generation.

## Content Boundary

Merged forward remains the only place where the triggering message content is
sent to the push group.

The text log must not include:

- triggering message text;
- matched keyword;
- message id;
- database id;
- exception details;
- SQL;
- token, cookie, or platform context payload.

The text log contains only:

- platform;
- listening group id;
- sender id and display-name snapshot;
- mute status;
- recall status;
- per-target forward status;
- handled timestamp.

## Platform API

OneBot v11 documents `send_group_msg` with:

- `group_id`;
- `message`;
- optional `auto_escape`.

NapCat also documents the same action shape. The adapter sends the text log
with `auto_escape=True` so display names cannot be interpreted as CQ code.

## Runtime Flow

For each bound push group:

1. upsert `violation_push_deliveries` as `pending`;
2. attempt merged-forward delivery;
3. upsert the delivery row with the forward result;
4. attempt plain-text log delivery;
5. log a sanitized error if text-log delivery fails.

Text-log failure does not change `violation_events.action_forward_status`.
Forward status remains dedicated to merged-forward delivery.

## Manual Acceptance

Preconditions:

1. `/cf probe` reports both:
   - `send_forward_message=supported`;
   - `send_text_log=supported`.
2. `/cf bind list` shows a listening group bound to a push group.
3. A test keyword is enabled in the listening group.

Steps:

1. Trigger the keyword from a non-admin test account.
2. Confirm the push group receives one merged-forward message containing only
   the user's triggering message content.
3. Confirm the push group receives a separate text log.
4. Confirm the text log contains action statuses and ids only.
5. Confirm the text log does not contain the triggering message text or matched
   keyword.

Expected text-log shape:

```text
Chat Filter violation log
platform=aiocqhttp
listening_group=<group id>
sender=<display name> (<user id>)
mute=<status>
recall=<status>
forward=<status>
handled_at=<utc timestamp>
```

SQLite checks stay the same as Phase 04b:

```sql
SELECT id, platform, group_id, user_id, message_id,
       matched_keyword,
       action_mute_status,
       action_recall_status,
       action_forward_status,
       created_at,
       updated_at
FROM violation_events
ORDER BY id DESC
LIMIT 3;
```

```sql
SELECT id, violation_id, platform, listening_group_id, push_group_id,
       action_status, error_code, created_at, updated_at
FROM violation_push_deliveries
ORDER BY id DESC
LIMIT 5;
```

## Validation

Automated validation should cover:

- OneBot `send_group_msg` payload with `auto_escape=True`;
- automatic text-log request after merged-forward delivery;
- text log containing no triggering message text or matched keyword;
- text-log failure not changing forward status;
- existing no-binding behavior remaining `not_scheduled`.

