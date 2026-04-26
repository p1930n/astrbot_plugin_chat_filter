from __future__ import annotations

from .command_runtime import CommandRuntimeService
from .models import RuntimeState
from .rule_snapshot import RuleSnapshot
from .settings import ChatFilterSettings


class GlobalCommandService:
    def __init__(
        self,
        state: RuntimeState,
        settings: ChatFilterSettings,
        rule_snapshot: RuleSnapshot,
        runtime: CommandRuntimeService,
    ) -> None:
        self._state = state
        self._settings = settings
        self._rule_snapshot = rule_snapshot
        self._runtime = runtime

    def format_status(self) -> str:
        enabled = self._state.effective_global_enabled(self._settings.enabled)
        group_count = len(self._state.groups)
        global_word_count = self._rule_snapshot.global_word_count
        return (
            "Chat Filter status: "
            f"global={'enabled' if enabled else 'disabled'}, "
            f"default_group={'enabled' if self._settings.default_group_enabled else 'disabled'}, "
            f"global_words={global_word_count}, groups={group_count}."
        )

    def format_help(self) -> str:
        return (
            "Chat Filter commands: "
            ".cf status; .cf enable; .cf disable; "
            ".cf group status|enable|disable|add|remove|list; "
            ".cf group admin-exempt status|enable|disable (alias: exempt); "
            "/chatfilter group admin-exempt status|enable|disable; "
            ".cf bind; .cf mute; .cf mute-stack; "
            ".cf probe; .cf forward-probe; .cf report-dry-run; .cf file-probe."
        )

    async def set_global_enabled(self, enabled: bool) -> str:
        self._state.global_enabled = enabled
        if not await self._runtime.try_save_state():
            return "Chat Filter state update failed."
        if enabled:
            return "Chat Filter enabled globally."
        return "Chat Filter disabled globally."
