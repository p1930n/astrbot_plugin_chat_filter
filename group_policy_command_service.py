from __future__ import annotations

from .command_runtime import CommandRuntimeService
from .models import RuntimeState
from .settings import ChatFilterSettings, validate_single_word


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
        effective_enabled = (
            self._settings.default_group_enabled
            if policy.enabled is None
            else policy.enabled
        )
        return (
            "Chat Filter group status: "
            f"group={'enabled' if effective_enabled else 'disabled'}, "
            f"inherit_global={'enabled' if policy.inherit_global else 'disabled'}, "
            f"admin_exempt={'enabled' if policy.admin_exempt_enabled else 'disabled'}, "
            f"custom_words={len(policy.custom_words)}."
        )

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._runtime.mutable_group_policy(group_key)
        policy.enabled = enabled
        self._state.set_group_policy(group_key, policy)
        if not await self._runtime.try_save_state():
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

        policy = self._runtime.mutable_group_policy(group_key)
        policy.admin_exempt_enabled = enabled
        self._state.set_group_policy(group_key, policy)
        if not await self._runtime.try_save_state():
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

        policy = self._runtime.mutable_group_policy(group_key)
        if cleaned in policy.custom_words:
            return "Group word already exists."
        if len(policy.custom_words) >= self._settings.max_word_count:
            return "Group word limit reached."

        policy.custom_words = (*policy.custom_words, cleaned)
        self._state.set_group_policy(group_key, policy)
        if not await self._runtime.try_save_state():
            return "Chat Filter state update failed."
        return "Group word added."

    async def remove_group_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._runtime.mutable_group_policy(group_key)
        remaining = tuple(item for item in policy.custom_words if item != word.strip())
        if len(remaining) == len(policy.custom_words):
            return "Group word not found."

        policy.custom_words = remaining
        self._state.set_group_policy(group_key, policy)
        if not await self._runtime.try_save_state():
            return "Chat Filter state update failed."
        return "Group word removed."

    def format_group_words(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return f"Group custom word count: {len(policy.custom_words)}."
