from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


DEFAULT_WARNING_MESSAGE = "消息触发聊天过滤策略，请调整后重试。"
DEFAULT_MAX_WORD_COUNT = 500
DEFAULT_MAX_WORD_LENGTH = 64
DEFAULT_MAX_REGEX_RULE_COUNT = 50
DEFAULT_MAX_REGEX_RULE_LENGTH = 500
DEFAULT_MUTE_DURATION_SECONDS = 600
DEFAULT_MUTE_ESCALATION_MULTIPLIER = 2
DEFAULT_MUTE_ESCALATION_RESET_SECONDS = 3600
MIN_MUTE_DURATION_SECONDS = 10
MAX_MUTE_DURATION_SECONDS = 2_592_000
MIN_MUTE_ESCALATION_MULTIPLIER = 1
MAX_MUTE_ESCALATION_MULTIPLIER = 10
MIN_MUTE_ESCALATION_RESET_SECONDS = 60
MAX_MUTE_ESCALATION_RESET_SECONDS = 2_592_000
DEFAULT_REPORT_DAYS = 7
DEFAULT_OBFUSCATED_WORD_MATCHING_ENABLED = True
DEFAULT_OBFUSCATED_WORD_MAX_GAP = 4
MAX_OBFUSCATED_WORD_MAX_GAP = 64


@dataclass(frozen=True, slots=True)
class RegexRule:
    pattern: str
    compiled: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class ChatFilterSettings:
    enabled: bool = True
    default_group_enabled: bool = False
    case_sensitive: bool = False
    stop_event: bool = True
    warn_user: bool = True
    warning_message: str = DEFAULT_WARNING_MESSAGE
    max_word_count: int = DEFAULT_MAX_WORD_COUNT
    max_word_length: int = DEFAULT_MAX_WORD_LENGTH
    violation_records_enabled: bool = True
    mute_duration_seconds: int = DEFAULT_MUTE_DURATION_SECONDS
    mute_escalation_multiplier: int = DEFAULT_MUTE_ESCALATION_MULTIPLIER
    mute_escalation_reset_seconds: int = DEFAULT_MUTE_ESCALATION_RESET_SECONDS
    default_report_days: int = DEFAULT_REPORT_DAYS
    obfuscated_word_matching_enabled: bool = (
        DEFAULT_OBFUSCATED_WORD_MATCHING_ENABLED
    )
    obfuscated_word_max_gap: int = DEFAULT_OBFUSCATED_WORD_MAX_GAP

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
        mute_duration_seconds = _bounded_int(
            data.get("mute_duration_seconds"),
            default=DEFAULT_MUTE_DURATION_SECONDS,
            minimum=MIN_MUTE_DURATION_SECONDS,
            maximum=MAX_MUTE_DURATION_SECONDS,
        )
        case_sensitive = _as_bool(data.get("case_sensitive"), False)
        return cls(
            enabled=_as_bool(data.get("enabled"), True),
            default_group_enabled=_as_bool(data.get("default_group_enabled"), False),
            case_sensitive=case_sensitive,
            stop_event=_as_bool(data.get("stop_event"), True),
            warn_user=_as_bool(data.get("warn_user"), True),
            warning_message=_safe_message(data.get("warning_message")),
            max_word_count=max_word_count,
            max_word_length=max_word_length,
            violation_records_enabled=_as_bool(data.get("violation_records_enabled"), True),
            mute_duration_seconds=mute_duration_seconds,
            mute_escalation_multiplier=_bounded_int(
                data.get("mute_escalation_multiplier"),
                default=DEFAULT_MUTE_ESCALATION_MULTIPLIER,
                minimum=MIN_MUTE_ESCALATION_MULTIPLIER,
                maximum=MAX_MUTE_ESCALATION_MULTIPLIER,
            ),
            mute_escalation_reset_seconds=_bounded_int(
                data.get("mute_escalation_reset_seconds"),
                default=DEFAULT_MUTE_ESCALATION_RESET_SECONDS,
                minimum=MIN_MUTE_ESCALATION_RESET_SECONDS,
                maximum=MAX_MUTE_ESCALATION_RESET_SECONDS,
            ),
            default_report_days=_bounded_int(
                data.get("default_report_days", data.get("default_report_interval_days")),
                default=DEFAULT_REPORT_DAYS,
                minimum=1,
                maximum=366,
            ),
            obfuscated_word_matching_enabled=_as_bool(
                data.get("obfuscated_word_matching_enabled"),
                DEFAULT_OBFUSCATED_WORD_MATCHING_ENABLED,
            ),
            obfuscated_word_max_gap=_bounded_int(
                data.get("obfuscated_word_max_gap"),
                default=DEFAULT_OBFUSCATED_WORD_MAX_GAP,
                minimum=0,
                maximum=MAX_OBFUSCATED_WORD_MAX_GAP,
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


def normalize_regex_rules(
    value: object,
    *,
    case_sensitive: bool,
    max_count: int,
    max_length: int,
) -> tuple[RegexRule, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple | set):
        items = list(value)
    else:
        return ()

    flags = 0 if case_sensitive else re.IGNORECASE
    normalized: list[RegexRule] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        pattern = item.strip()
        if (
            not pattern
            or len(pattern) > max_length
            or pattern in seen
            or _looks_like_high_risk_regex(pattern)
        ):
            continue
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            continue
        normalized.append(RegexRule(pattern=pattern, compiled=compiled))
        seen.add(pattern)
        if len(normalized) >= max_count:
            break
    return tuple(normalized)


def _looks_like_high_risk_regex(pattern: str) -> bool:
    if re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
        return True
    if re.search(r"(\.\*){2,}", pattern):
        return True
    if re.search(r"\\[1-9]", pattern):
        return True
    return False


def _config_list_or_default(
    data: dict[str, Any],
    *,
    key: str,
    default: tuple[str, ...],
) -> object:
    if key not in data:
        return default
    return data[key]


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
