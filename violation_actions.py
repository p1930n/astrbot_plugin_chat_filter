from __future__ import annotations

import asyncio
from typing import Protocol

from .models import ChatMessage
from .platform_actions import (
    ACTION_STATUS_UNSUPPORTED,
    MuteUserRequest,
    PlatformActionResult,
    PlatformActions,
    RecallMessageRequest,
)
from .repository import ChatFilterRepository, ViolationActionName


ACTION_MUTE: ViolationActionName = "mute"
ACTION_RECALL: ViolationActionName = "recall"
REASON_MESSAGE_ID_MISSING = "message_id_missing"


class ActionLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...


class ViolationActionExecutor:
    def __init__(
        self,
        repository: ChatFilterRepository,
        *,
        logger: ActionLogger,
        default_mute_duration_seconds: int,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._default_mute_duration_seconds = default_mute_duration_seconds

    async def execute(
        self,
        *,
        violation_id: int,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        mute_result = await self._mute_user(message, platform_actions)
        await self._try_update_status(
            violation_id=violation_id,
            action=ACTION_MUTE,
            result=mute_result,
        )

        recall_result = await self._recall_message(message, platform_actions)
        await self._try_update_status(
            violation_id=violation_id,
            action=ACTION_RECALL,
            result=recall_result,
        )

    async def _mute_user(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> PlatformActionResult:
        duration = await self._mute_duration_for_group(message)
        return await platform_actions.mute_user(
            MuteUserRequest(
                platform=message.platform,
                group_id=message.group_id,
                user_id=message.user_id,
                duration_seconds=duration,
            )
        )

    async def _mute_duration_for_group(self, message: ChatMessage) -> int:
        try:
            policy = await asyncio.to_thread(
                self._repository.get_enabled_group_mute_policy,
                platform=message.platform,
                group_id=message.group_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute policy lookup failed: error_type=%s",
                type(exc).__name__,
            )
            return self._default_mute_duration_seconds

        if policy is None:
            return self._default_mute_duration_seconds
        return policy.mute_duration_seconds

    async def _recall_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> PlatformActionResult:
        if not message.message_id:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=REASON_MESSAGE_ID_MISSING,
            )
        return await platform_actions.recall_message(
            RecallMessageRequest(
                platform=message.platform,
                group_id=message.group_id,
                message_id=message.message_id,
            )
        )

    async def _try_update_status(
        self,
        *,
        violation_id: int,
        action: ViolationActionName,
        result: PlatformActionResult,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._repository.update_violation_action_status,
                violation_id=violation_id,
                action=action,
                status=result.status,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation action status update failed: "
                "action=%s error_type=%s",
                action,
                type(exc).__name__,
            )
