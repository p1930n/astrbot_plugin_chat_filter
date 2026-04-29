from __future__ import annotations

import asyncio
from typing import Protocol

from ..domain.models import ChatMessage, GroupActionPolicy
from ..platform.platform_actions import (
    ACTION_STATUS_UNSUPPORTED,
    MuteUserRequest,
    PlatformActionResult,
    PlatformActions,
    RecallMessageRequest,
)
from ..persistence.repository import ChatFilterRepository
from ..domain.settings import MAX_MUTE_DURATION_SECONDS
from .violation_action_audit import (
    ACTION_FORWARD,
    ACTION_MUTE,
    ACTION_RECALL,
    ViolationActionAudit,
)
from .violation_push_notifications import (
    FORWARD_ACTION_TIMEOUT_SECONDS,
    REASON_FORWARD_ACTION_FAILED,
    REASON_FORWARD_ACTION_TIMEOUT,
    REASON_NO_PUSH_BINDINGS,
    REASON_PUSH_BINDING_LOOKUP_FAILED,
    REASON_TEXT_LOG_ACTION_FAILED,
    REASON_TEXT_LOG_ACTION_TIMEOUT,
    TEXT_LOG_ACTION_TIMEOUT_SECONDS,
    TEXT_LOG_DISPLAY_NAME_MAX_LENGTH,
    ViolationPushNotifier,
)


REASON_MESSAGE_ID_MISSING = "message_id_missing"
REASON_MUTE_ACTION_FAILED = "mute_action_failed"
REASON_MUTE_ACTION_TIMEOUT = "mute_action_timeout"
REASON_RECALL_ACTION_FAILED = "recall_action_failed"
REASON_RECALL_ACTION_TIMEOUT = "recall_action_timeout"
REASON_ACTION_POLICY_AUDIT_MODE = "action_policy_audit_mode"
REASON_ACTION_POLICY_DISABLED = "action_policy_disabled"
MUTE_ACTION_TIMEOUT_SECONDS = 10.0
RECALL_ACTION_TIMEOUT_SECONDS = 10.0

__all__ = (
    "ACTION_FORWARD",
    "ACTION_MUTE",
    "ACTION_RECALL",
    "FORWARD_ACTION_TIMEOUT_SECONDS",
    "MUTE_ACTION_TIMEOUT_SECONDS",
    "REASON_FORWARD_ACTION_FAILED",
    "REASON_FORWARD_ACTION_TIMEOUT",
    "REASON_MESSAGE_ID_MISSING",
    "REASON_MUTE_ACTION_FAILED",
    "REASON_MUTE_ACTION_TIMEOUT",
    "REASON_NO_PUSH_BINDINGS",
    "REASON_PUSH_BINDING_LOOKUP_FAILED",
    "REASON_RECALL_ACTION_FAILED",
    "REASON_RECALL_ACTION_TIMEOUT",
    "REASON_ACTION_POLICY_AUDIT_MODE",
    "REASON_ACTION_POLICY_DISABLED",
    "REASON_TEXT_LOG_ACTION_FAILED",
    "REASON_TEXT_LOG_ACTION_TIMEOUT",
    "RECALL_ACTION_TIMEOUT_SECONDS",
    "TEXT_LOG_ACTION_TIMEOUT_SECONDS",
    "TEXT_LOG_DISPLAY_NAME_MAX_LENGTH",
    "ViolationActionExecutor",
)


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
        default_mute_escalation_multiplier: int,
        default_mute_escalation_reset_seconds: int,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._default_mute_duration_seconds = default_mute_duration_seconds
        self._default_mute_escalation_multiplier = default_mute_escalation_multiplier
        self._default_mute_escalation_reset_seconds = (
            default_mute_escalation_reset_seconds
        )
        self._audit = ViolationActionAudit(repository, logger)
        self._push_notifier = ViolationPushNotifier(
            repository,
            audit=self._audit,
            logger=logger,
        )

    async def execute(
        self,
        *,
        violation_id: int | None,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        policy = await self._action_policy_for_group(message)
        mute_result = await self._maybe_mute_user(message, platform_actions, policy)
        await self._audit.update_status(
            violation_id=violation_id,
            action=ACTION_MUTE,
            result=mute_result,
        )

        recall_result = await self._maybe_recall_message(
            message,
            platform_actions,
            policy,
        )
        await self._audit.update_status(
            violation_id=violation_id,
            action=ACTION_RECALL,
            result=recall_result,
        )

        if policy.forward_enabled:
            forward_result = await self._push_notifier.forward(
                violation_id=violation_id,
                message=message,
                platform_actions=platform_actions,
                mute_result=mute_result,
                recall_result=recall_result,
            )
        else:
            forward_result = _not_scheduled(REASON_ACTION_POLICY_DISABLED)
        await self._audit.update_status(
            violation_id=violation_id,
            action=ACTION_FORWARD,
            result=forward_result,
        )

    async def _action_policy_for_group(self, message: ChatMessage) -> GroupActionPolicy:
        try:
            policy = await asyncio.to_thread(
                self._repository.get_group_action_policy,
                platform=message.platform,
                group_id=message.group_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter action policy lookup failed: error_type=%s",
                type(exc).__name__,
            )
            policy = None
        if policy is None:
            return GroupActionPolicy(
                platform=message.platform,
                group_id=message.group_id,
            )
        return policy

    async def _maybe_mute_user(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
        policy: GroupActionPolicy,
    ) -> PlatformActionResult:
        if policy.mode == "audit":
            return _not_scheduled(REASON_ACTION_POLICY_AUDIT_MODE)
        if not policy.mute_enabled:
            return _not_scheduled(REASON_ACTION_POLICY_DISABLED)
        return await self._mute_user(message, platform_actions)

    async def _maybe_recall_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
        policy: GroupActionPolicy,
    ) -> PlatformActionResult:
        if policy.mode == "audit":
            return _not_scheduled(REASON_ACTION_POLICY_AUDIT_MODE)
        if not policy.recall_enabled:
            return _not_scheduled(REASON_ACTION_POLICY_DISABLED)
        return await self._recall_message(message, platform_actions)

    async def _mute_user(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> PlatformActionResult:
        base_duration = await self._mute_duration_for_group(message)
        duration = await self._escalated_mute_duration(
            message,
            base_duration_seconds=base_duration,
        )
        request = MuteUserRequest(
            platform=message.platform,
            group_id=message.group_id,
            user_id=message.user_id,
            duration_seconds=duration,
        )
        try:
            return await asyncio.wait_for(
                platform_actions.mute_user(request),
                timeout=MUTE_ACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter mute action timed out.")
            return PlatformActionResult.failed(REASON_MUTE_ACTION_TIMEOUT)
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute action failed: error_type=%s",
                type(exc).__name__,
            )
            return PlatformActionResult.failed(REASON_MUTE_ACTION_FAILED)

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

    async def _escalated_mute_duration(
        self,
        message: ChatMessage,
        *,
        base_duration_seconds: int,
    ) -> int:
        try:
            decision = await asyncio.to_thread(
                self._repository.calculate_mute_escalation,
                platform=message.platform,
                group_id=message.group_id,
                user_id=message.user_id,
                base_duration_seconds=base_duration_seconds,
                default_multiplier=self._default_mute_escalation_multiplier,
                default_reset_seconds=self._default_mute_escalation_reset_seconds,
                max_duration_seconds=MAX_MUTE_DURATION_SECONDS,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute escalation calculation failed: error_type=%s",
                type(exc).__name__,
            )
            return base_duration_seconds
        return decision.duration_seconds

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
        request = RecallMessageRequest(
            platform=message.platform,
            group_id=message.group_id,
            message_id=message.message_id,
        )
        try:
            return await asyncio.wait_for(
                platform_actions.recall_message(request),
                timeout=RECALL_ACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter recall action timed out.")
            return PlatformActionResult.failed(REASON_RECALL_ACTION_TIMEOUT)
        except Exception as exc:
            self._logger.error(
                "Chat Filter recall action failed: error_type=%s",
                type(exc).__name__,
            )
            return PlatformActionResult.failed(REASON_RECALL_ACTION_FAILED)


def _not_scheduled(reason: str) -> PlatformActionResult:
    return PlatformActionResult(status="not_scheduled", reason=reason)
