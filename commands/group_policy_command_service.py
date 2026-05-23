from __future__ import annotations

from .command_runtime import CommandRuntimeService
from ..domain.models import RuntimeState
from ..domain.settings import ChatFilterSettings, validate_single_word


class GroupPolicyCommandService:
    def __init__(
        self,
        state: RuntimeState,
        settings: ChatFilterSettings,
        runtime: CommandRuntimeService,
    ) -> None:
        self._state = state
        self._settings = settings
        self._runtime = runtime

    def format_group_status(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return (
            "Chat Filter group status: "
            f"group={'enabled' if policy.enabled is True else 'disabled'}, "
            f"inherit_global={'enabled' if policy.inherit_global else 'disabled'}, "
            f"admin_exempt={'enabled' if policy.admin_exempt_enabled else 'disabled'}, "
            f"custom_words={len(policy.custom_words)}, "
            f"bypass_global_words={len(policy.bypass_global_words)}."
        )

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        if not await self._runtime.set_group_enabled(group_key, enabled):
            return "Chat Filter state update failed."
        if enabled:
            return "Chat Filter enabled for this group."
        return "Chat Filter disabled for this group."

    async def set_group_admin_exempt_enabled(
        self,
        group_key: str | None,
        enabled: bool,
    ) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        if not await self._runtime.set_group_admin_exempt_enabled(group_key, enabled):
            return "Chat Filter state update failed."
        if enabled:
            return "Chat Filter admin exemption enabled for this group."
        return "Chat Filter admin exemption disabled for this group."

    def format_group_admin_exempt_status(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return (
            "Chat Filter group admin exemption: "
            f"{'enabled' if policy.admin_exempt_enabled else 'disabled'}."
        )

    async def add_group_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        cleaned = validate_single_word(
            word,
            max_length=self._settings.max_word_length,
        )
        if cleaned is None:
            return "Invalid word length."

        result = await self._runtime.add_group_word(
            group_key,
            cleaned,
            self._settings.max_word_count,
        )
        if result == "exists":
            return "Group word already exists."
        if result == "limit":
            return "Group word limit reached."
        if result == "save_failed":
            return "Chat Filter state update failed."
        return "Group word added."

    async def remove_group_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        result = await self._runtime.remove_group_word(group_key, word)
        if result == "not_found":
            return "Group word not found."
        if result == "save_failed":
            return "Chat Filter state update failed."
        return "Group word removed."

    async def add_group_bypass_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        cleaned = validate_single_word(
            word,
            max_length=self._settings.max_word_length,
        )
        if cleaned is None:
            return "Invalid word length."

        result = await self._runtime.add_group_bypass_word(
            group_key,
            cleaned,
            self._settings.max_word_count,
        )
        if result == "exists":
            return "Group bypass word already exists."
        if result == "limit":
            return "Group bypass word limit reached."
        if result == "save_failed":
            return "Chat Filter state update failed."
        return "Group bypass word added."

    async def remove_group_bypass_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        result = await self._runtime.remove_group_bypass_word(group_key, word)
        if result == "not_found":
            return "Group bypass word not found."
        if result == "save_failed":
            return "Chat Filter state update failed."
        return "Group bypass word removed."

    def format_group_words(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return f"Group custom word count: {len(policy.custom_words)}."

    def format_group_bypass_words(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return f"Group bypass word count: {len(policy.bypass_global_words)}."
