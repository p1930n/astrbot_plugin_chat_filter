from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


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
REGEX_GAP_PLACEHOLDER = "{{GAP}}"
DEFAULT_REGEX_GAP_MAX = 8
MAX_REGEX_GAP_MAX = 64
DEFAULT_REGEX_SKIP_PREVIEW_LENGTH = 80

RegexRuleSkipReason = Literal[
    "empty",
    "too_long",
    "duplicate",
    "high_risk",
    "compile_error",
    "max_count",
    "non_string",
]


@dataclass(frozen=True, slots=True)
class RegexRule:
    pattern: str
    compiled: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class RegexRuleSkip:
    index: int
    reason: RegexRuleSkipReason
    pattern_preview: str
    pattern_length: int | None
    source_id: str | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RegexRuleNormalizationResult:
    rules: tuple[RegexRule, ...]
    skipped: tuple[RegexRuleSkip, ...]


@dataclass(frozen=True, slots=True)
class ChatFilterSettings:
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
    regex_gap_max: int = DEFAULT_REGEX_GAP_MAX

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
            case_sensitive=case_sensitive,
            stop_event=_as_bool(data.get("stop_event"), True),
            warn_user=_as_bool(data.get("warn_user"), True),
            warning_message=_safe_message(data.get("warning_message")),
            max_word_count=max_word_count,
            max_word_length=max_word_length,
            violation_records_enabled=_as_bool(
                data.get("violation_records_enabled"),
                True,
            ),
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
                data.get(
                    "default_report_days",
                    data.get("default_report_interval_days"),
                ),
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
            regex_gap_max=_bounded_int(
                data.get("regex_gap_max"),
                default=DEFAULT_REGEX_GAP_MAX,
                minimum=0,
                maximum=MAX_REGEX_GAP_MAX,
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
    regex_gap_max: int = DEFAULT_REGEX_GAP_MAX,
) -> tuple[RegexRule, ...]:
    return normalize_regex_rules_with_diagnostics(
        value,
        case_sensitive=case_sensitive,
        max_count=max_count,
        max_length=max_length,
        regex_gap_max=regex_gap_max,
    ).rules


def normalize_regex_rules_with_diagnostics(
    value: object,
    *,
    case_sensitive: bool,
    max_count: int,
    max_length: int,
    regex_gap_max: int = DEFAULT_REGEX_GAP_MAX,
    source_ids: tuple[str | None, ...] | None = None,
) -> RegexRuleNormalizationResult:
    if value is None:
        return RegexRuleNormalizationResult(rules=(), skipped=())
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple | set):
        items = list(value)
    else:
        return RegexRuleNormalizationResult(
            rules=(),
            skipped=(
                _regex_skip(
                    0,
                    "non_string",
                    value,
                    source_id=_source_id(source_ids, 0),
                ),
            ),
        )

    flags = 0 if case_sensitive else re.IGNORECASE
    normalized: list[RegexRule] = []
    skipped: list[RegexRuleSkip] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        source_id = _source_id(source_ids, index)
        if not isinstance(item, str):
            skipped.append(_regex_skip(index, "non_string", item, source_id=source_id))
            continue
        raw_pattern = item.strip()
        pattern = _expand_regex_gap_placeholder(raw_pattern, regex_gap_max)
        if not pattern:
            skipped.append(_regex_skip(index, "empty", pattern, source_id=source_id))
            continue
        if len(pattern) > max_length:
            skipped.append(
                _regex_skip(index, "too_long", pattern, source_id=source_id)
            )
            continue
        if pattern in seen:
            skipped.append(
                _regex_skip(index, "duplicate", pattern, source_id=source_id)
            )
            continue
        if len(normalized) >= max_count:
            skipped.append(
                _regex_skip(index, "max_count", pattern, source_id=source_id)
            )
            continue
        if _looks_like_high_risk_regex(pattern):
            skipped.append(
                _regex_skip(index, "high_risk", pattern, source_id=source_id)
            )
            continue
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            skipped.append(
                _regex_skip(
                    index,
                    "compile_error",
                    pattern,
                    source_id=source_id,
                    detail=str(exc),
                )
            )
            continue
        normalized.append(RegexRule(pattern=pattern, compiled=compiled))
        seen.add(pattern)
    return RegexRuleNormalizationResult(
        rules=tuple(normalized),
        skipped=tuple(skipped),
    )


def _expand_regex_gap_placeholder(pattern: str, regex_gap_max: int) -> str:
    if REGEX_GAP_PLACEHOLDER not in pattern:
        return pattern
    gap_pattern = rf"[\s\S]{{0,{regex_gap_max}}}"
    return pattern.replace(REGEX_GAP_PLACEHOLDER, gap_pattern)


def _looks_like_high_risk_regex(pattern: str) -> bool:
    if re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
        return True
    if re.search(r"(\.\*){2,}", pattern):
        return True
    if re.search(r"\\[1-9]", pattern):
        return True
    return False


def _regex_skip(
    index: int,
    reason: RegexRuleSkipReason,
    value: object,
    *,
    source_id: str | None,
    detail: str = "",
) -> RegexRuleSkip:
    pattern_length = len(value) if isinstance(value, str) else None
    return RegexRuleSkip(
        index=index,
        reason=reason,
        pattern_preview=_safe_pattern_preview(value),
        pattern_length=pattern_length,
        source_id=source_id,
        detail=_safe_pattern_preview(detail) if detail else "",
    )


def _source_id(
    source_ids: tuple[str | None, ...] | None,
    index: int,
) -> str | None:
    if source_ids is None or index >= len(source_ids):
        return None
    return source_ids[index]


def _safe_pattern_preview(value: object) -> str:
    if not isinstance(value, str):
        return f"<{type(value).__name__}>"
    cleaned = (
        value.replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    if not cleaned:
        return "<empty>"
    if len(cleaned) <= DEFAULT_REGEX_SKIP_PREVIEW_LENGTH:
        return cleaned
    return f"{cleaned[:DEFAULT_REGEX_SKIP_PREVIEW_LENGTH]}..."


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
