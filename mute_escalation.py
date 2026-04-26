from __future__ import annotations

from datetime import datetime


def next_violation_count(
    *,
    previous_count: int,
    previous_at: datetime | None,
    now: datetime,
    reset_seconds: int,
) -> int:
    if previous_at is None:
        return 1
    if (now - previous_at).total_seconds() > reset_seconds:
        return 1
    return max(previous_count, 0) + 1


def scaled_mute_duration(
    *,
    base_duration_seconds: int,
    multiplier: int,
    violation_count: int,
    max_duration_seconds: int,
) -> int:
    duration = max(base_duration_seconds, 0)
    for _ in range(max(violation_count - 1, 0)):
        duration *= multiplier
        if duration >= max_duration_seconds:
            return max_duration_seconds
    return min(duration, max_duration_seconds)
