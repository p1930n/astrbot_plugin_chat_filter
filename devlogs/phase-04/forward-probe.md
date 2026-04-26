# Phase 04b Forward Probe

## Scope

Phase 04b-1 only confirms the merged-forward action boundary and adds the
future delivery-status persistence skeleton. It does not wire automatic
violation push delivery into the hit path yet.

Implemented:

- OneBot v11 `send_group_forward_msg` action formatting;
- `/cf forward-probe [group]` and `.cf forward-probe [group]`;
- `/cf probe` now reports `send_forward_message=supported` when an action
  client is present;
- `violation_push_deliveries` table and repository methods for per-target
  delivery status.

Not implemented:

- automatic push after a violation hit;
- text log push;
- periodic file generation or sending;
- retry, queue, timeout, or rate-limit orchestration.

## Content Boundary

Merged forward content must contain only the content sent by the user who
triggered the violation at that time.

Do not put these items inside the merged-forward message:

- mute result;
- recall result;
- push delivery status;
- database ids;
- operational audit text;
- bot-generated explanations.

Those fields belong in the database or later text-log delivery, not in the
merged-forward payload.

The current probe sends one custom node only. Later automatic delivery should
reuse this same shape with `matched_content` from the violation row and the
violating sender snapshot.

## Official API Baseline

References checked on 2026-04-24:

- `https://docs.astrbot.app/en/dev/star/guides/send-message.html`
- `https://www.napcat.wiki/onebot/api`
- `https://napcat.apifox.cn/226657396e0`

Confirmed baseline:

- AstrBot documents group forward messages and states current support is
  OneBot v11.
- NapCat's OneBot API list exposes `send_group_forward_msg` with `group_id`
  and `messages`.
- NapCat's API example uses `messages` containing `node` objects.

The direct OneBot v11 standard action list does not define
`send_group_forward_msg`; this is treated as a OneBot-compatible adapter
extension that must be live-probed before production push is enabled.

## Runtime Boundary

AstrBot-specific objects remain in:

- `main.py`
- `astrbot_event_adapter.py`

Native modules:

- `command_service.py` owns command validation and probe response text.
- `platform_actions.py` owns OneBot payload construction and action calls.
- `repository.py` owns SQLite schema and delivery-status persistence.

`main.py` only routes `/cf forward-probe`, dehydrates the event, picks the
platform action adapter, and returns `yield event.plain_result(...)`.

## Persistence

New SQLite table:

```sql
CREATE TABLE IF NOT EXISTS violation_push_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    violation_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    listening_group_id TEXT NOT NULL,
    push_group_id TEXT NOT NULL,
    action_status TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (violation_id)
        REFERENCES violation_events(id)
        ON DELETE CASCADE,
    UNIQUE (violation_id, platform, push_group_id)
);
```

Indexes:

- `idx_violation_push_deliveries_status`
- `idx_violation_push_deliveries_push_group`

Repository additions:

- `upsert_violation_push_delivery(delivery)`
- `list_violation_push_deliveries(violation_id=...)`

This table is intentionally per target push group. It avoids collapsing
multi-target delivery into the single `violation_events.action_forward_status`
field.

## Validation

Automated validation for this slice:

- Python syntax compilation for modified modules;
- fake OneBot client smoke test for `send_group_forward_msg` payload;
- repository smoke test for `violation_push_deliveries`;
- command-service smoke test for forward probe response;
- `git diff --check`;
- temporary file scan.

Manual validation in AstrBot:

1. Restart or hot-reload the plugin.
2. Run `/cf probe`.
3. Expect `send_forward_message=supported`.
4. Run `/cf forward-probe`.
5. Confirm a merged-forward message appears in the current group.
6. Optionally run `/cf forward-probe <push_group_id>` for a bound push group.
7. Confirm the command response is `Chat Filter forward probe: success.`
8. Confirm ordinary violation hits still only do mute and recall; they should
   not auto-push yet.

SQL check for the new table:

```sql
SELECT id, violation_id, platform, listening_group_id, push_group_id,
       action_status, error_code, created_at, updated_at
FROM violation_push_deliveries
ORDER BY id DESC
LIMIT 5;
```

It is acceptable for this query to return no rows before Phase 04b-2, because
the current slice only creates the table and repository boundary.

## Remaining Risks

- `send_group_forward_msg` is adapter-extension behavior, not a OneBot v11 core
  action. The target deployment must live-probe it before automatic push.
- The probe validates action availability, not push group permission policy.
- No timeout, retry, queue, or rate-limit layer is added yet.
- Automatic push remains disabled until the delivery table is live-validated.

## Commit / Push

- Commit: not performed.
- Push: not performed.
- Current state: ready for local validation; Hold before commit.
