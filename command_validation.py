from __future__ import annotations

from .settings import (
    MAX_MUTE_DURATION_SECONDS,
    MAX_MUTE_ESCALATION_MULTIPLIER,
    MAX_MUTE_ESCALATION_RESET_SECONDS,
    MIN_MUTE_DURATION_SECONDS,
    MIN_MUTE_ESCALATION_MULTIPLIER,
    MIN_MUTE_ESCALATION_RESET_SECONDS,
)


BIND_LIST_LIMIT = 20
MAX_QQ_GROUP_ID_LENGTH = 20


def is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH


def parse_mute_duration(value: str) -> int | None:
    try:
        seconds = int(value.strip(), 10)
    except ValueError:
        return None
    if seconds < MIN_MUTE_DURATION_SECONDS or seconds > MAX_MUTE_DURATION_SECONDS:
        return None
    return seconds


def parse_mute_escalation_multiplier(value: str) -> int | None:
    try:
        multiplier = int(value.strip(), 10)
    except ValueError:
        return None
    if (
        multiplier < MIN_MUTE_ESCALATION_MULTIPLIER
        or multiplier > MAX_MUTE_ESCALATION_MULTIPLIER
    ):
        return None
    return multiplier


def parse_mute_escalation_reset_seconds(value: str) -> int | None:
    try:
        seconds = int(value.strip(), 10)
    except ValueError:
        return None
    if (
        seconds < MIN_MUTE_ESCALATION_RESET_SECONDS
        or seconds > MAX_MUTE_ESCALATION_RESET_SECONDS
    ):
        return None
    return seconds
