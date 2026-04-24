from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Protocol

from .models import GroupPolicy, PlatformEventSnapshot, PushBinding, RuntimeState
from .repository import ChatFilterRepository
from .settings import (
    MAX_MUTE_DURATION_SECONDS,
    MIN_MUTE_DURATION_SECONDS,
    ChatFilterSettings,
    validate_single_word,
)


BIND_LIST_LIMIT = 20
MAX_QQ_GROUP_ID_LENGTH = 20


class CommandLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...

    def warning(self, message: str, *args: object) -> None:
        ...


def load_runtime_state(
    repository: ChatFilterRepository,
    logger: CommandLogger,
) -> RuntimeState:
    try:
        return repository.load()
    except Exception as exc:
        logger.warning(
            "Chat Filter state load failed; using empty runtime state: "
            "error_type=%s",
            type(exc).__name__,
        )
        return RuntimeState()


class ChatFilterCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        state: RuntimeState,
        settings: ChatFilterSettings,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._state = state
        self._settings = settings
        self._logger = logger

    def format_status(self) -> str:
        enabled = self._state.effective_global_enabled(self._settings.enabled)
        group_count = len(self._state.groups)
        global_word_count = len(self._settings.global_words)
        return (
            "Chat Filter status: "
            f"global={'enabled' if enabled else 'disabled'}, "
            f"default_group={'enabled' if self._settings.default_group_enabled else 'disabled'}, "
            f"global_words={global_word_count}, groups={group_count}."
        )

    async def set_global_enabled(self, enabled: bool) -> str:
        self._state.global_enabled = enabled
        if not await self._try_save_state():
            return "Chat Filter state update failed."
        if enabled:
            return "Chat Filter enabled globally."
        return "Chat Filter disabled globally."

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
            f"custom_words={len(policy.custom_words)}."
        )

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._mutable_group_policy(group_key)
        policy.enabled = enabled
        self._state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            return "Chat Filter state update failed."
        if enabled:
            return "Chat Filter enabled for this group."
        return "Chat Filter disabled for this group."

    async def add_group_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        cleaned = validate_single_word(
            word,
            max_length=self._settings.max_word_length,
        )
        if cleaned is None:
            return "Invalid word length."

        policy = self._mutable_group_policy(group_key)
        if cleaned in policy.custom_words:
            return "Group word already exists."
        if len(policy.custom_words) >= self._settings.max_word_count:
            return "Group word limit reached."

        policy.custom_words = (*policy.custom_words, cleaned)
        self._state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            return "Chat Filter state update failed."
        return "Group word added."

    async def remove_group_word(self, group_key: str | None, word: str) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._mutable_group_policy(group_key)
        remaining = tuple(item for item in policy.custom_words if item != word.strip())
        if len(remaining) == len(policy.custom_words):
            return "Group word not found."

        policy.custom_words = remaining
        self._state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            return "Chat Filter state update failed."
        return "Group word removed."

    def format_group_words(self, group_key: str | None) -> str:
        if group_key is None:
            return "This command must be used in a group chat."

        policy = self._state.get_group_policy(group_key)
        return f"Group custom word count: {len(policy.custom_words)}."

    async def add_push_binding(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        listening_group_id: str,
        push_group_id: str,
    ) -> str:
        if not _is_valid_qq_group_id(listening_group_id) or not _is_valid_qq_group_id(
            push_group_id
        ):
            return (
                "Usage: .cf bind [listening group] [push group] "
                "or /cf bind [listening group] [push group]"
            )

        if not snapshot.platform:
            return "Chat Filter bind failed: platform is unavailable."

        try:
            count = await asyncio.to_thread(
                self._repository.add_push_binding,
                platform=snapshot.platform,
                listening_group_id=listening_group_id,
                push_group_id=push_group_id,
                created_by=snapshot.sender_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter push binding update failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter bind failed."

        return (
            "Chat Filter bind updated: "
            f"{listening_group_id} has {count} push group(s)."
        )

    async def format_push_bindings(self, platform: str) -> str:
        if not platform:
            return "Chat Filter bind list failed: platform is unavailable."
        try:
            bindings = await asyncio.to_thread(
                self._repository.list_push_bindings,
                platform=platform,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter push binding list failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter bind list failed."

        if not bindings:
            return "Chat Filter bind list is empty."
        grouped = _group_push_bindings(bindings)
        lines = [
            f"{listening_group}: {', '.join(push_groups)}"
            for listening_group, push_groups in list(grouped.items())[:BIND_LIST_LIMIT]
        ]
        if len(grouped) > BIND_LIST_LIMIT:
            lines.append(f"... and {len(grouped) - BIND_LIST_LIMIT} more group(s).")
        return "Chat Filter bind list:\n" + "\n".join(lines)

    async def set_group_mute_duration(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        group_id: str,
        seconds: str,
    ) -> str:
        if not _is_valid_qq_group_id(group_id):
            return "Usage: .cf mute [group] [seconds] or /cf mute [group] [seconds]"

        duration = _parse_mute_duration(seconds)
        if duration is None:
            return "Invalid mute duration seconds."

        if not snapshot.platform:
            return "Chat Filter mute policy update failed: platform is unavailable."

        try:
            await asyncio.to_thread(
                self._repository.set_group_mute_duration,
                platform=snapshot.platform,
                group_id=group_id,
                mute_duration_seconds=duration,
                updated_by=snapshot.sender_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter group mute policy update failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter mute policy update failed."

        return (
            "Chat Filter mute policy updated: "
            f"{group_id} -> {duration} second(s)."
        )

    async def format_group_mute_policies(self, platform: str) -> str:
        if not platform:
            return "Chat Filter mute policy list failed: platform is unavailable."
        try:
            policies = await asyncio.to_thread(
                self._repository.list_group_mute_policies,
                platform=platform,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter group mute policy list failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter mute policy list failed."

        if not policies:
            return "Chat Filter mute policy list is empty."
        lines = [
            f"{policy.group_id}: {policy.mute_duration_seconds} second(s)"
            for policy in policies[:BIND_LIST_LIMIT]
        ]
        if len(policies) > BIND_LIST_LIMIT:
            lines.append(f"... and {len(policies) - BIND_LIST_LIMIT} more group(s).")
        return "Chat Filter mute policy list:\n" + "\n".join(lines)

    async def _try_save_state(self) -> bool:
        try:
            await asyncio.to_thread(self._repository.save, self._state)
        except Exception as exc:
            self._logger.error(
                "Chat Filter state save failed: error_type=%s",
                type(exc).__name__,
            )
            return False
        return True

    def _mutable_group_policy(self, group_key: str) -> GroupPolicy:
        policy = self._state.get_group_policy(group_key)
        return GroupPolicy(
            enabled=policy.enabled,
            inherit_global=policy.inherit_global,
            custom_words=policy.custom_words,
        )


def _is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH


def _group_push_bindings(bindings: list[PushBinding]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for binding in bindings:
        grouped[binding.listening_group_id].append(binding.push_group_id)
    return dict(grouped)


def _parse_mute_duration(value: str) -> int | None:
    try:
        seconds = int(value.strip(), 10)
    except ValueError:
        return None
    if seconds < MIN_MUTE_DURATION_SECONDS or seconds > MAX_MUTE_DURATION_SECONDS:
        return None
    return seconds
