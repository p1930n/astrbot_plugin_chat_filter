from __future__ import annotations

from ..domain.models import RuntimeState
from ..domain.rule_snapshot import RuleSnapshot
from ..domain.settings import ChatFilterSettings


class GlobalCommandService:
    def __init__(
        self,
        state: RuntimeState,
        settings: ChatFilterSettings,
        rule_snapshot: RuleSnapshot,
    ) -> None:
        self._state = state
        self._settings = settings
        self._rule_snapshot = rule_snapshot

    def format_status(self) -> str:
        group_count = len(self._state.groups)
        global_word_count = self._rule_snapshot.global_word_count
        return (
            "Chat Filter status: "
            f"default_group={'enabled' if self._settings.default_group_enabled else 'disabled'}, "
            f"global_words={global_word_count}, groups={group_count}."
        )

    def format_help(self) -> str:
        return (
            "Chat Filter commands: "
            ".cf status; .cf enable [group id]; .cf disable [group id]; "
            ".cf group status|enable|disable|add|remove|list; "
            ".cf group admin-exempt status|enable|disable (alias: exempt); "
            "/chatfilter group admin-exempt status|enable|disable; "
            ".cf bind; .cf mute; .cf mute-stack; "
            ".cf probe; .cf forward-probe; .cf report-dry-run; .cf file-probe."
        )
