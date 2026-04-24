# Phase 07 Mute Escalation

## Scope

- Add per-group mute escalation policies.
- Track repeat violations by `platform`, `group_id`, and `user_id`.
- Default multiplier is `2x`.
- Default reset window is `3600` seconds.
- If the same user violates again within the reset window, mute duration is
  multiplied by `multiplier ** (violation_count - 1)`.
- If the user has no violation within the reset window, the next violation is
  treated as the first violation again.

## Commands

```text
/cf mute-stack [group] [multiplier] [reset_seconds]
.cf mute-stack [group] [multiplier] [reset_seconds]
/cf mute-stack list
.cf mute-stack list
```

The command only shows group ids and numeric policy values. It does not echo
word lists, regex rules, or matched message content.

## Persistence

SQLite owns this state:

- `group_mute_escalation_policies`: explicit per-group overrides.
- `user_mute_escalation_states`: current repeat count and last violation time
  for each user in each group.

No background timer is introduced. Reset is calculated lazily during the next
violation, so plugin reload does not need to cancel scheduler tasks.

## Runtime Boundary

The high-frequency violation path performs one SQLite transaction to read the
policy, update the user state, and return the effective duration. The call is
wrapped with `asyncio.to_thread` so it does not block the event loop directly.

If escalation calculation fails, mute falls back to the base group/default mute
duration and the violation flow continues.

## Acceptance

1. Configure a group:

```text
/cf mute-stack 1091645414 2 3600
```

2. Trigger one violation from the same user in that group. Expected mute:
   base duration.
3. Trigger a second violation from the same user within 3600 seconds. Expected
   mute: base duration multiplied by 2.
4. Trigger a third violation within 3600 seconds. Expected mute: base duration
   multiplied by 4, capped by platform max duration.
5. After more than 3600 seconds without a violation, the next violation should
   return to the base duration.
