from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .models import ChatMessage, PlatformEventSnapshot


MESSAGE_ID_FIELD_CANDIDATES = ("get_message_id", "message_id")
MESSAGE_TEXT_FIELD_CANDIDATES = ("get_message_str", "message_str")
PLATFORM_FIELD_CANDIDATES = ("get_platform_name", "platform_name")
GROUP_ID_FIELD_CANDIDATES = ("get_group_id", "group_id")
SENDER_ID_FIELD_CANDIDATES = ("get_sender_id", "sender_id", "user_id")
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
        sender_display_name=snapshot.sender_display_name,
        group_display_name=snapshot.group_display_name,
    )


def dehydrate_event_snapshot(event: AstrMessageEvent) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform=_event_value(event, *PLATFORM_FIELD_CANDIDATES),
        group_id=_event_value(event, *GROUP_ID_FIELD_CANDIDATES),
        sender_id=_event_value(event, *SENDER_ID_FIELD_CANDIDATES),
        message_id=_event_value(event, *MESSAGE_ID_FIELD_CANDIDATES),
        sender_display_name=_event_value(event, *SENDER_DISPLAY_FIELD_CANDIDATES),
        group_display_name=_event_value(event, *GROUP_DISPLAY_FIELD_CANDIDATES),
    )


def current_group_key_from_event(event: AstrMessageEvent) -> str | None:
    snapshot = dehydrate_event_snapshot(event)
    if not snapshot.platform or not snapshot.group_id:
        return None
    return f"{snapshot.platform}:{snapshot.group_id}"


def has_required_message_scope(message: ChatMessage) -> bool:
    return bool(message.platform and message.group_id and message.user_id)


def field_state(value: str) -> str:
    return "present" if value else "missing"


def _event_value(event: AstrMessageEvent, *names: str) -> str:
    for source in _event_sources(event):
        for name in names:
            try:
                value = getattr(source, name, None)
            except Exception:
                continue
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if value:
                return str(value)
    return ""


def _event_sources(event: AstrMessageEvent) -> tuple[object, ...]:
    sources: list[object] = [event]
    try:
        message_obj = getattr(event, "message_obj", None)
    except Exception:
        message_obj = None

    if message_obj is None:
        return tuple(sources)

    sources.append(message_obj)
    try:
        sender = getattr(message_obj, "sender", None)
    except Exception:
        sender = None
    if sender is not None:
        sources.append(sender)
    return tuple(sources)
