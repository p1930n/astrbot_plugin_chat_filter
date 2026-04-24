# Phase 04b Forward Delivery

## Scope

Phase 04b-2 enables automatic merged-forward delivery after a violation is
recorded.

This phase includes:

- looking up enabled push bindings for the listening group;
- sending one merged-forward node to each bound push group;
- recording per-target delivery rows in `violation_push_deliveries`;
- aggregating delivery results back to `violation_events.action_forward_status`.

This phase does not include:

- text log delivery;
- file report delivery;
- WebUI configuration;
- retry queues or background workers.

## Forward Content Boundary

The merged-forward payload contains only one node:

- sender id: the user who triggered the violation;
- nickname: the sender display-name snapshot from the triggering event;
- content: the triggering user's message text.

Do not add audit fields, database ids, action statuses, bot explanations,
matched keywords, message ids, mute results, recall results, or delivery
diagnostics to the merged-forward content.

Those fields stay in SQLite or later text-log/report channels.

## Runtime Flow

`main.py` remains the AstrBot boundary. It dehydrates the event, records the
violation, stops the event when configured, and calls `ViolationActionExecutor`.

`ViolationActionExecutor` now runs:

1. mute;
2. recall;
3. merged-forward delivery.

Each platform action failure is degraded into a status update. A delivery
failure must not prevent warning the user, nor should it roll back the
violation event row.

Forward delivery uses a bounded `asyncio.wait_for` timeout around the platform
send call. SQLite reads/writes continue to run through `asyncio.to_thread`.

## Persistence

`list_enabled_push_bindings_for_group(platform, listening_group_id)` returns
only active bindings for the exact platform and listening group. This avoids
loading unrelated group bindings on the high-frequency violation path.

Before each send, a delivery row is upserted as `pending`. After the platform
call returns or times out, the same row is upserted with the final status and
error code.

Aggregate forward status:

- no bindings: `not_scheduled`;
- all deliveries `success`: `success`;
- all deliveries `unsupported`: `unsupported`;
- any mixed or failed delivery: `failed`;
- binding lookup failure: `failed`.

## Manual Acceptance

Preconditions:

1. `/cf probe` reports `send_forward_message=supported`.
2. `/cf bind list` shows the listening group bound to a push group.
3. `/cf forward-probe <push_group_id>` succeeds.
4. The listening group has a test keyword enabled.

Steps:

1. Trigger the keyword from a non-admin test account in the listening group.
2. Confirm the original group still receives the user warning if configured.
3. Confirm mute and recall behavior still follows the Phase 04a behavior.
4. Confirm the bound push group receives one merged-forward message.
5. Open the merged-forward message and confirm it contains only the violating
   user's triggering message content.
6. Confirm no status text, database id, message id, mute result, recall result,
   or audit explanation appears inside the merged-forward message.

SQLite checks:

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

Expected result for a successful single push group:

- `violation_events.action_forward_status = success`;
- one delivery row for the bound push group;
- `violation_push_deliveries.action_status = success`;
- `violation_push_deliveries.error_code = ''`.

Expected result with no binding:

- `violation_events.action_forward_status = not_scheduled`;
- no delivery rows for that violation.

Expected result when the platform action is unavailable or fails:

- violation event remains recorded;
- mute/recall status remains independently recorded;
- forward status becomes `unsupported` or `failed`;
- delivery row stores the per-target status and error code when a target group
  was known.

## Validation

Automated validation should cover:

- repository scoped binding lookup;
- successful single-target delivery;
- no-binding `not_scheduled` path;
- per-target delivery upsert;
- aggregate forward status update;
- payload content containing only the triggering user's message text.

