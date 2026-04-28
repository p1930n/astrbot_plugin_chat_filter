from __future__ import annotations

import asyncio
from typing import Literal, Protocol

from ..domain.models import GroupPolicy, RuntimeState
from ..persistence.repository import ChatFilterRepository, RepositorySchemaError

GroupWordAddResult = Literal["added", "exists", "limit", "save_failed"]
GroupWordRemoveResult = Literal["removed", "not_found", "save_failed"]


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
    except RepositorySchemaError:
        raise
    except Exception as exc:
        logger.warning(
            "Chat Filter state load failed; using empty runtime state: "
            "error_type=%s",
            type(exc).__name__,
        )
        return RuntimeState()


class CommandRuntimeService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        state: RuntimeState,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._state = state
        self._logger = logger
        self._state_lock = asyncio.Lock()

    async def try_save_state(self) -> bool:
        async with self._state_lock:
            return await self._try_save_state_unlocked()

    async def set_global_enabled(self, enabled: bool) -> bool:
        async with self._state_lock:
            self._state.global_enabled = enabled
            return await self._try_save_state_unlocked()

    async def set_group_enabled(self, group_key: str, enabled: bool) -> bool:
        async with self._state_lock:
            policy = self._copy_group_policy_unlocked(group_key)
            policy.enabled = enabled
            self._state.set_group_policy(group_key, policy)
            return await self._try_save_state_unlocked()

    async def set_group_admin_exempt_enabled(
        self,
        group_key: str,
        enabled: bool,
    ) -> bool:
        async with self._state_lock:
            policy = self._copy_group_policy_unlocked(group_key)
            policy.admin_exempt_enabled = enabled
            self._state.set_group_policy(group_key, policy)
            return await self._try_save_state_unlocked()

    async def add_group_word(
        self,
        group_key: str,
        word: str,
        max_word_count: int,
    ) -> GroupWordAddResult:
        async with self._state_lock:
            policy = self._copy_group_policy_unlocked(group_key)
            if word in policy.custom_words:
                return "exists"
            if len(policy.custom_words) >= max_word_count:
                return "limit"

            policy.custom_words = (*policy.custom_words, word)
            self._state.set_group_policy(group_key, policy)
            if not await self._try_save_state_unlocked():
                return "save_failed"
            return "added"

    async def remove_group_word(
        self,
        group_key: str,
        word: str,
    ) -> GroupWordRemoveResult:
        async with self._state_lock:
            policy = self._copy_group_policy_unlocked(group_key)
            remaining = tuple(
                item for item in policy.custom_words if item != word.strip()
            )
            if len(remaining) == len(policy.custom_words):
                return "not_found"

            policy.custom_words = remaining
            self._state.set_group_policy(group_key, policy)
            if not await self._try_save_state_unlocked():
                return "save_failed"
            return "removed"

    async def _try_save_state_unlocked(self) -> bool:
        try:
            await asyncio.to_thread(self._repository.save, self._state)
        except Exception as exc:
            self._logger.error(
                "Chat Filter state save failed: error_type=%s",
                type(exc).__name__,
            )
            return False
        return True

    def mutable_group_policy(self, group_key: str) -> GroupPolicy:
        return self._copy_group_policy_unlocked(group_key)

    def _copy_group_policy_unlocked(self, group_key: str) -> GroupPolicy:
        policy = self._state.get_group_policy(group_key)
        return GroupPolicy(
            enabled=policy.enabled,
            inherit_global=policy.inherit_global,
            admin_exempt_enabled=policy.admin_exempt_enabled,
            custom_words=policy.custom_words,
        )
