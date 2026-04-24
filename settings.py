from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_WARNING_MESSAGE = "消息触发聊天过滤策略，请调整后重试。"
DEFAULT_MAX_WORD_COUNT = 200
DEFAULT_MAX_WORD_LENGTH = 64
DEFAULT_MUTE_MIN_SECONDS = 60
DEFAULT_MUTE_MAX_SECONDS = 2_592_000
DEFAULT_MUTE_DURATION_SECONDS = 600
DEFAULT_REPORT_INTERVAL_DAYS = 7


@dataclass(frozen=True, slots=True)
class ChatFilterSettings:
    enabled: bool = True
    default_group_enabled: bool = False
    global_words: tuple[str, ...] = ()
    case_sensitive: bool = False
    stop_event: bool = True
    warn_user: bool = True
    warning_message: str = DEFAULT_WARNING_MESSAGE
    max_word_count: int = DEFAULT_MAX_WORD_COUNT
    max_word_length: int = DEFAULT_MAX_WORD_LENGTH
    violation_records_enabled: bool = True
    mute_duration_seconds: int = DEFAULT_MUTE_DURATION_SECONDS
    mute_min_seconds: int = DEFAULT_MUTE_MIN_SECONDS
    mute_max_seconds: int = DEFAULT_MUTE_MAX_SECONDS
    report_files_enabled: bool = False
    default_report_interval_days: int = DEFAULT_REPORT_INTERVAL_DAYS

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "ChatFilterSettings":
        data = config or {}
        max_word_count = _bounded_int(
            data.get("max_word_count"),
            default=DEFAULT_MAX_WORD_COUNT,
            minimum=1,
            maximum=5000,
        )
        max_word_length = _bounded_int(
            data.get("max_word_length"),
            default=DEFAULT_MAX_WORD_LENGTH,
            minimum=1,
            maximum=512,
        )
        mute_min_seconds = _bounded_int(
            data.get("mute_min_seconds"),
            default=DEFAULT_MUTE_MIN_SECONDS,
            minimum=1,
            maximum=DEFAULT_MUTE_MAX_SECONDS,
        )
        mute_max_seconds = _bounded_int(
            data.get("mute_max_seconds"),
            default=DEFAULT_MUTE_MAX_SECONDS,
            minimum=mute_min_seconds,
            maximum=DEFAULT_MUTE_MAX_SECONDS,
        )
        mute_duration_seconds = _bounded_int(
            data.get("mute_duration_seconds"),
            default=DEFAULT_MUTE_DURATION_SECONDS,
            minimum=mute_min_seconds,
            maximum=mute_max_seconds,
        )
        return cls(
            enabled=_as_bool(data.get("enabled"), True),
            default_group_enabled=_as_bool(data.get("default_group_enabled"), False),
            global_words=normalize_words(
                data.get("global_words"),
                max_count=max_word_count,
                max_length=max_word_length,
            ),
            case_sensitive=_as_bool(data.get("case_sensitive"), False),
            stop_event=_as_bool(data.get("stop_event"), True),
            warn_user=_as_bool(data.get("warn_user"), True),
            warning_message=_safe_message(data.get("warning_message")),
            max_word_count=max_word_count,
            max_word_length=max_word_length,
            violation_records_enabled=_as_bool(data.get("violation_records_enabled"), True),
            mute_duration_seconds=mute_duration_seconds,
            mute_min_seconds=mute_min_seconds,
            mute_max_seconds=mute_max_seconds,
            report_files_enabled=_as_bool(data.get("report_files_enabled"), False),
            default_report_interval_days=_bounded_int(
                data.get("default_report_interval_days"),
                default=DEFAULT_REPORT_INTERVAL_DAYS,
                minimum=1,
                maximum=366,
            ),
        )


def normalize_words(
    value: object,
    *,
    max_count: int,
    max_length: int,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple | set):
        items = list(value)
    else:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        word = item.strip()
        if not word or len(word) > max_length or word in seen:
            continue
        normalized.append(word)
        seen.add(word)
        if len(normalized) >= max_count:
            break
    return tuple(normalized)


def validate_single_word(word: str, *, max_length: int) -> str | None:
    cleaned = word.strip()
    if not cleaned or len(cleaned) > max_length:
        return None
    return cleaned


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip(), 10)
        except ValueError:
            return default
    else:
        return default
    return min(max(parsed, minimum), maximum)


def _safe_message(value: object) -> str:
    if not isinstance(value, str):
        return DEFAULT_WARNING_MESSAGE
    message = value.strip()
    if not message:
        return DEFAULT_WARNING_MESSAGE
    return message[:200]
