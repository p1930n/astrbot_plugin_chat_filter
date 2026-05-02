from __future__ import annotations

from ..domain.models import PlatformEventSnapshot
from ..domain.settings import (
    MAX_MUTE_DURATION_SECONDS,
    MAX_MUTE_ESCALATION_MULTIPLIER,
    MAX_MUTE_ESCALATION_RESET_SECONDS,
    MIN_MUTE_DURATION_SECONDS,
    MIN_MUTE_ESCALATION_MULTIPLIER,
    MIN_MUTE_ESCALATION_RESET_SECONDS,
)


BIND_LIST_LIMIT = 20
MAX_QQ_GROUP_ID_LENGTH = 20
_ACTION_TOGGLE_VALUES = frozenset(
    {"on", "enable", "enabled", "true", "1", "off", "disable", "disabled", "false", "0"}
)


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


def build_group_key(snapshot: PlatformEventSnapshot) -> str | None:
    if not snapshot.platform or not snapshot.group_id:
        return None
    return f"{snapshot.platform}:{snapshot.group_id}"


def resolve_target_group_id(
    snapshot: PlatformEventSnapshot,
    group_id: str = "",
) -> str | None:
    target = group_id.strip()
    if not target:
        return snapshot.group_id if snapshot.group_id else None
    if not snapshot.platform or not is_valid_qq_group_id(target):
        return None
    return target


def resolve_target_group_key(
    snapshot: PlatformEventSnapshot,
    group_id: str = "",
) -> str | None:
    target = resolve_target_group_id(snapshot, group_id)
    if target is None or not snapshot.platform:
        return None
    return f"{snapshot.platform}:{target}"


def is_action_toggle_value(value: str) -> bool:
    return value.strip().casefold() in _ACTION_TOGGLE_VALUES
