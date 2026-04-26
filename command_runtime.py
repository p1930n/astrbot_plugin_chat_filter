from __future__ import annotations

from typing import Protocol

from .models import GroupPolicy, RuntimeState
from .repository import ChatFilterRepository, RepositorySchemaError


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

    async def try_save_state(self) -> bool:
        try:
            import asyncio

            await asyncio.to_thread(self._repository.save, self._state)
        except Exception as exc:
            self._logger.error(
                "Chat Filter state save failed: error_type=%s",
                type(exc).__name__,
            )
            return False
        return True

    def mutable_group_policy(self, group_key: str) -> GroupPolicy:
        policy = self._state.get_group_policy(group_key)
        return GroupPolicy(
            enabled=policy.enabled,
            inherit_global=policy.inherit_global,
            admin_exempt_enabled=policy.admin_exempt_enabled,
            custom_words=policy.custom_words,
        )
