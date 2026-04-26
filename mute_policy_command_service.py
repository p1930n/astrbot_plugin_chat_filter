from __future__ import annotations

from .command_runtime import CommandLogger
from .command_validation import (
    BIND_LIST_LIMIT,
    is_valid_qq_group_id,
    parse_mute_duration,
    parse_mute_escalation_multiplier,
    parse_mute_escalation_reset_seconds,
)
from .models import PlatformEventSnapshot
from .repository import ChatFilterRepository
from .settings import ChatFilterSettings


class MutePolicyCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        settings: ChatFilterSettings,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._logger = logger

    async def set_group_mute_duration(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        group_id: str,
        seconds: str,
    ) -> str:
        if not is_valid_qq_group_id(group_id):
            return "Usage: .cf mute [group] [seconds] or /cf mute [group] [seconds]"

        duration = parse_mute_duration(seconds)
        if duration is None:
            return "Invalid mute duration seconds."

        if not snapshot.platform:
            return "Chat Filter mute policy update failed: platform is unavailable."

        try:
            import asyncio

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
            import asyncio

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

    async def set_group_mute_escalation(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        group_id: str,
        multiplier: str,
        reset_seconds: str,
    ) -> str:
        if not is_valid_qq_group_id(group_id):
            return (
                "Usage: .cf mute-stack [group] [multiplier] [reset_seconds] "
                "or /cf mute-stack [group] [multiplier] [reset_seconds]"
            )

        parsed_multiplier = parse_mute_escalation_multiplier(multiplier)
        parsed_reset_seconds = parse_mute_escalation_reset_seconds(reset_seconds)
        if parsed_multiplier is None:
            return "Invalid mute escalation multiplier."
        if parsed_reset_seconds is None:
            return "Invalid mute escalation reset seconds."

        if not snapshot.platform:
            return "Chat Filter mute escalation update failed: platform is unavailable."

        try:
            import asyncio

            await asyncio.to_thread(
                self._repository.set_group_mute_escalation_policy,
                platform=snapshot.platform,
                group_id=group_id,
                multiplier=parsed_multiplier,
                reset_seconds=parsed_reset_seconds,
                updated_by=snapshot.sender_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute escalation policy update failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter mute escalation update failed."

        return (
            "Chat Filter mute escalation updated: "
            f"{group_id} -> {parsed_multiplier}x, reset {parsed_reset_seconds}s."
        )

    async def format_group_mute_escalation_policies(self, platform: str) -> str:
        if not platform:
            return "Chat Filter mute escalation list failed: platform is unavailable."
        try:
            import asyncio

            policies = await asyncio.to_thread(
                self._repository.list_group_mute_escalation_policies,
                platform=platform,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute escalation policy list failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter mute escalation list failed."

        if not policies:
            return (
                "Chat Filter mute escalation policy list is empty; "
                f"default is {self._settings.mute_escalation_multiplier}x, "
                f"reset {self._settings.mute_escalation_reset_seconds}s."
            )
        lines = [
            f"{policy.group_id}: {policy.multiplier}x, reset {policy.reset_seconds}s"
            for policy in policies[:BIND_LIST_LIMIT]
        ]
        if len(policies) > BIND_LIST_LIMIT:
            lines.append(f"... and {len(policies) - BIND_LIST_LIMIT} more group(s).")
        return "Chat Filter mute escalation policy list:\n" + "\n".join(lines)
