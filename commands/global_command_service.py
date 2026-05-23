from __future__ import annotations

from ..domain.models import RuntimeState
from ..domain.settings import RegexRuleSkip
from ..domain.rule_snapshot import RuleSnapshot

REGEX_SKIP_DEFAULT_LIMIT = 20
REGEX_SKIP_MAX_LIMIT = 50
REGEX_SKIP_USAGE = "Usage: .cf regex-skips [limit]"


class GlobalCommandService:
    def __init__(
        self,
        state: RuntimeState,
        rule_snapshot: RuleSnapshot,
    ) -> None:
        self._state = state
        self._rule_snapshot = rule_snapshot

    def format_status(self) -> str:
        group_count = len(self._state.groups)
        global_word_count = self._rule_snapshot.global_word_count
        return (
            "Chat Filter status: "
            f"global_words={global_word_count}, groups={group_count}."
        )

    def format_regex_skips(self, limit: str = "") -> str:
        limit_count = _parse_regex_skip_limit(limit)
        if limit_count is None:
            return REGEX_SKIP_USAGE

        skipped = self._rule_snapshot.global_regex_rule_skips
        if not skipped:
            return "Chat Filter regex skips: none."

        visible = skipped[:limit_count]
        lines = [
            (
                "Chat Filter regex skips: "
                f"total={len(skipped)}, showing={len(visible)}."
            )
        ]
        lines.extend(_format_regex_skip(skip) for skip in visible)
        if len(skipped) > len(visible):
            next_limit = min(len(skipped), REGEX_SKIP_MAX_LIMIT)
            lines.append(f"Use .cf regex-skips {next_limit} for more.")
        return "\n".join(lines)

    def format_help(self) -> str:
        return (
            "Chat Filter commands: "
            ".cf status; .cf overview [csv]; .cf regex-skips [limit]; "
            ".cf enable [group id]; .cf disable [group id]; "
            ".cf group status|enable|disable|add|add-to|remove|list; "
            ".cf group admin-exempt status|enable|disable (alias: exempt); "
            ".cf action status|mute|recall|forward|mode|overview; "
            ".cf bind; .cf mute; .cf mute-stack; "
            ".cf probe; .cf forward-probe; .cf report-dry-run; .cf file-probe."
        )


def _parse_regex_skip_limit(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return REGEX_SKIP_DEFAULT_LIMIT
    try:
        parsed = int(cleaned, 10)
    except ValueError:
        return None
    if parsed < 1:
        return None
    return min(parsed, REGEX_SKIP_MAX_LIMIT)


def _format_regex_skip(skip: RegexRuleSkip) -> str:
    parts = [
        f"#{skip.index + 1}",
        f"reason={skip.reason}",
    ]
    if skip.source_id:
        parts.append(f"source={skip.source_id}")
    if skip.pattern_length is not None:
        parts.append(f"len={skip.pattern_length}")
    parts.append(f"pattern={skip.pattern_preview}")
    if skip.detail:
        parts.append(f"detail={skip.detail}")
    return " ".join(parts)
