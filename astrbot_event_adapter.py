from __future__ import annotations

from collections.abc import Mapping

from astrbot.api.event import AstrMessageEvent

from .models import ChatMessage, PlatformEventSnapshot, normalize_sender_role


MESSAGE_ID_FIELD_CANDIDATES = ("get_message_id", "message_id")
MESSAGE_TEXT_FIELD_CANDIDATES = ("get_message_str", "message_str")
PLATFORM_FIELD_CANDIDATES = ("get_platform_name", "platform_name")
GROUP_ID_FIELD_CANDIDATES = ("get_group_id", "group_id")
SENDER_ID_FIELD_CANDIDATES = ("get_sender_id", "sender_id", "user_id")
SENDER_ROLE_FIELD_CANDIDATES = (
    "get_sender_role",
    "sender_role",
    "group_role",
    "member_role",
)
SENDER_NESTED_ROLE_FIELD_CANDIDATES = (
    *SENDER_ROLE_FIELD_CANDIDATES,
    "role",
)
SENDER_OWNER_BOOL_FIELD_CANDIDATES = (
    "is_group_owner",
    "sender_is_group_owner",
    "is_owner",
)
SENDER_ADMIN_BOOL_FIELD_CANDIDATES = (
    "is_group_admin",
    "sender_is_group_admin",
    "is_admin",
)
SENDER_DISPLAY_FIELD_CANDIDATES = (
    "get_sender_name",
    "sender_name",
    "sender_display_name",
    "nickname",
)
GROUP_DISPLAY_FIELD_CANDIDATES = (
    "get_group_name",
    "group_name",
    "group_display_name",
)


def dehydrate_group_message(event: AstrMessageEvent) -> ChatMessage:
    snapshot = dehydrate_event_snapshot(event)
    return ChatMessage(
        platform=snapshot.platform,
        group_id=snapshot.group_id,
        user_id=snapshot.sender_id,
        text=_event_value(event, *MESSAGE_TEXT_FIELD_CANDIDATES),
        message_id=snapshot.message_id,
        sender_role=snapshot.sender_role,
        sender_display_name=snapshot.sender_display_name,
        group_display_name=snapshot.group_display_name,
    )


def dehydrate_event_snapshot(event: AstrMessageEvent) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform=_event_value(event, *PLATFORM_FIELD_CANDIDATES),
        group_id=_event_value(event, *GROUP_ID_FIELD_CANDIDATES),
        sender_id=_event_value(event, *SENDER_ID_FIELD_CANDIDATES),
        message_id=_event_value(event, *MESSAGE_ID_FIELD_CANDIDATES),
        sender_role=_sender_role_from_event(event),
        sender_display_name=_event_value(event, *SENDER_DISPLAY_FIELD_CANDIDATES),
        group_display_name=_event_value(event, *GROUP_DISPLAY_FIELD_CANDIDATES),
    )


def current_group_key_from_event(event: AstrMessageEvent) -> str | None:
    snapshot = dehydrate_event_snapshot(event)
    if not snapshot.platform or not snapshot.group_id:
        return None
    return f"{snapshot.platform}:{snapshot.group_id}"


def extract_onebot_action_client(event: AstrMessageEvent) -> object | None:
    try:
        bot = getattr(event, "bot", None)
    except Exception:
        return None
    if bot is None:
        return None

    try:
        action_client = getattr(bot, "api", None)
    except Exception:
        return None
    if action_client is None:
        return None
    return action_client


def has_required_message_scope(message: ChatMessage) -> bool:
    return bool(message.platform and message.group_id and message.user_id)


def field_state(value: str) -> str:
    return "present" if value else "missing"


def _event_value(event: AstrMessageEvent, *names: str) -> str:
    for source in _event_sources(event):
        for name in names:
            value = _source_value(source, name)
            if value:
                return str(value)
    return ""


def _sender_role_from_event(event: AstrMessageEvent) -> str:
    for source, allow_plain_role, _allow_manager_bool in _sender_role_sources(event):
        field_candidates = (
            SENDER_NESTED_ROLE_FIELD_CANDIDATES
            if allow_plain_role
            else SENDER_ROLE_FIELD_CANDIDATES
        )
        for name in field_candidates:
            value = _source_value(source, name)
            if value:
                return normalize_sender_role(str(value))
    for source, _allow_plain_role, allow_manager_bool in _sender_role_sources(event):
        if not allow_manager_bool:
            continue
        if _source_bool(source, *SENDER_OWNER_BOOL_FIELD_CANDIDATES):
            return "owner"
        if _source_bool(source, *SENDER_ADMIN_BOOL_FIELD_CANDIDATES):
            return "admin"
    return ""


def _source_bool(source: object, *names: str) -> bool:
    for name in names:
        value = _source_value(source, name)
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in ("1", "true", "yes", "y", "on"):
                return True
            if normalized in ("0", "false", "no", "n", "off"):
                return False
    return False


def _source_value(source: object, name: str) -> object:
    if isinstance(source, Mapping):
        value = source.get(name)
    else:
        try:
            value = getattr(source, name, None)
        except Exception:
            return None
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _sender_role_sources(event: AstrMessageEvent) -> tuple[tuple[object, bool, bool], ...]:
    sources: list[tuple[object, bool, bool]] = []
    message_obj = _message_obj_from_event(event)
    if message_obj is not None:
        for raw_name in ("raw_message", "raw_event", "raw"):
            raw_source = _source_value(message_obj, raw_name)
            if raw_source is not None:
                raw_sender = _source_value(raw_source, "sender")
                if raw_sender is not None:
                    sources.append((raw_sender, True, True))
                sources.append((raw_source, False, True))
        sender = _source_value(message_obj, "sender")
        if sender is not None:
            sources.append((sender, True, True))
        sources.append((message_obj, False, True))
    sources.append((event, False, False))
    return tuple(sources)


def _event_sources(event: AstrMessageEvent) -> tuple[object, ...]:
    sources: list[object] = [event]
    message_obj = _message_obj_from_event(event)
    if message_obj is None:
        return tuple(sources)

    sources.append(message_obj)
    for raw_name in ("raw_message", "raw_event", "raw"):
        raw_source = _source_value(message_obj, raw_name)
        if raw_source is not None:
            sources.append(raw_source)
            if isinstance(raw_source, Mapping):
                raw_sender = raw_source.get("sender")
                if raw_sender is not None:
                    sources.append(raw_sender)
    sender = _source_value(message_obj, "sender")
    if sender is not None:
        sources.append(sender)
    return tuple(sources)


def _message_obj_from_event(event: AstrMessageEvent) -> object | None:
    try:
        message_obj = getattr(event, "message_obj", None)
    except Exception:
        return None
    return message_obj
