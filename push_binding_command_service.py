from __future__ import annotations

from collections import defaultdict

from .command_runtime import CommandLogger
from .command_validation import BIND_LIST_LIMIT, is_valid_qq_group_id
from .models import PlatformEventSnapshot, PushBinding
from .repository import ChatFilterRepository


class PushBindingCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def add_push_binding(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        listening_group_id: str,
        push_group_id: str,
    ) -> str:
        if not is_valid_qq_group_id(
            listening_group_id
        ) or not is_valid_qq_group_id(push_group_id):
            return (
                "Usage: .cf bind [listening group] [push group] "
                "or /cf bind [listening group] [push group]"
            )

        if not snapshot.platform:
            return "Chat Filter bind failed: platform is unavailable."

        try:
            import asyncio

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
            import asyncio

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
        grouped = group_push_bindings(bindings)
        lines = [
            f"{listening_group}: {', '.join(push_groups)}"
            for listening_group, push_groups in list(grouped.items())[:BIND_LIST_LIMIT]
        ]
        if len(grouped) > BIND_LIST_LIMIT:
            lines.append(f"... and {len(grouped) - BIND_LIST_LIMIT} more group(s).")
        return "Chat Filter bind list:\n" + "\n".join(lines)


def group_push_bindings(bindings: list[PushBinding]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for binding in bindings:
        grouped[binding.listening_group_id].append(binding.push_group_id)
    return dict(grouped)


def _group_push_bindings(bindings: list[PushBinding]) -> dict[str, list[str]]:
    return group_push_bindings(bindings)
