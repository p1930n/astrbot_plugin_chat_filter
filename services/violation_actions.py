from __future__ import annotations

import asyncio
from time import perf_counter
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
from ..runtime.metrics import ChatFilterMetrics, safe_increment, safe_observe_ms
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
METRIC_ACTION_MUTE_MS = "violation_action.mute.ms"
METRIC_ACTION_RECALL_MS = "violation_action.recall.ms"
METRIC_ACTION_MUTE_TIMEOUT_TOTAL = "violation_action.mute.timeout.total"
METRIC_ACTION_RECALL_TIMEOUT_TOTAL = "violation_action.recall.timeout.total"
METRIC_ACTION_MUTE_FAILED_TOTAL = "violation_action.mute.failed.total"
METRIC_ACTION_RECALL_FAILED_TOTAL = "violation_action.recall.failed.total"
METRIC_ACTION_MUTE_SUCCESS_TOTAL = "violation_action.mute.success.total"
METRIC_ACTION_RECALL_SUCCESS_TOTAL = "violation_action.recall.success.total"
METRIC_ACTION_MUTE_UNSUPPORTED_TOTAL = "violation_action.mute.unsupported.total"
METRIC_ACTION_RECALL_UNSUPPORTED_TOTAL = "violation_action.recall.unsupported.total"
METRIC_ACTION_MUTE_NOT_SCHEDULED_TOTAL = (
    "violation_action.mute.not_scheduled.total"
)
METRIC_ACTION_RECALL_NOT_SCHEDULED_TOTAL = (
    "violation_action.recall.not_scheduled.total"
)

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
        metrics: ChatFilterMetrics,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._metrics = metrics
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
            metrics=metrics,
        )

    async def execute(
        self,
        *,
        violation_id: int | None,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        existing_statuses = await self._existing_action_statuses(violation_id)
        policy = await self._action_policy_for_group(message)
        if existing_statuses.get(ACTION_MUTE) == "success":
            mute_result = PlatformActionResult(status="success")
        else:
            mute_result = await self._maybe_mute_user(message, platform_actions, policy)
            await self._audit.update_status(
                violation_id=violation_id,
                action=ACTION_MUTE,
                result=mute_result,
            )

        if existing_statuses.get(ACTION_RECALL) == "success":
            recall_result = PlatformActionResult(status="success")
        else:
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

        if existing_statuses.get(ACTION_FORWARD) == "success":
            forward_result = PlatformActionResult(status="success")
        elif policy.forward_enabled:
            forward_result = await self._push_notifier.forward(
                violation_id=violation_id,
                message=message,
                platform_actions=platform_actions,
                mute_result=mute_result,
                recall_result=recall_result,
            )
        else:
            forward_result = _not_scheduled(REASON_ACTION_POLICY_DISABLED)
            self._push_notifier.record_forward_result(forward_result)
        await self._audit.update_status(
            violation_id=violation_id,
            action=ACTION_FORWARD,
            result=forward_result,
        )

    async def _existing_action_statuses(
        self,
        violation_id: int | None,
    ) -> dict[str, str]:
        if violation_id is None:
            return {}
        try:
            return await asyncio.to_thread(
                self._repository.get_violation_action_statuses,
                violation_id=violation_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation action status lookup failed: "
                "error_type=%s",
                type(exc).__name__,
            )
            return {}

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
            result = _not_scheduled(REASON_ACTION_POLICY_AUDIT_MODE)
            _record_action_result(self._metrics, ACTION_MUTE, result)
            return result
        if not policy.mute_enabled:
            result = _not_scheduled(REASON_ACTION_POLICY_DISABLED)
            _record_action_result(self._metrics, ACTION_MUTE, result)
            return result
        return await self._mute_user(message, platform_actions)

    async def _maybe_recall_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
        policy: GroupActionPolicy,
    ) -> PlatformActionResult:
        if policy.mode == "audit":
            result = _not_scheduled(REASON_ACTION_POLICY_AUDIT_MODE)
            _record_action_result(self._metrics, ACTION_RECALL, result)
            return result
        if not policy.recall_enabled:
            result = _not_scheduled(REASON_ACTION_POLICY_DISABLED)
            _record_action_result(self._metrics, ACTION_RECALL, result)
            return result
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
        started_at = perf_counter()
        try:
            result = await asyncio.wait_for(
                platform_actions.mute_user(request),
                timeout=MUTE_ACTION_TIMEOUT_SECONDS,
            )
            _record_action_result(self._metrics, ACTION_MUTE, result)
            return result
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter mute action timed out.")
            result = PlatformActionResult.failed(REASON_MUTE_ACTION_TIMEOUT)
            _record_action_result(self._metrics, ACTION_MUTE, result)
            safe_increment(self._metrics, METRIC_ACTION_MUTE_TIMEOUT_TOTAL)
            return result
        except Exception as exc:
            self._logger.error(
                "Chat Filter mute action failed: error_type=%s",
                type(exc).__name__,
            )
            result = PlatformActionResult.failed(REASON_MUTE_ACTION_FAILED)
            _record_action_result(self._metrics, ACTION_MUTE, result)
            return result
        finally:
            safe_observe_ms(
                self._metrics,
                METRIC_ACTION_MUTE_MS,
                (perf_counter() - started_at) * 1000,
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
            result = PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=REASON_MESSAGE_ID_MISSING,
            )
            _record_action_result(self._metrics, ACTION_RECALL, result)
            return result
        request = RecallMessageRequest(
            platform=message.platform,
            group_id=message.group_id,
            message_id=message.message_id,
        )
        started_at = perf_counter()
        try:
            result = await asyncio.wait_for(
                platform_actions.recall_message(request),
                timeout=RECALL_ACTION_TIMEOUT_SECONDS,
            )
            _record_action_result(self._metrics, ACTION_RECALL, result)
            return result
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter recall action timed out.")
            result = PlatformActionResult.failed(REASON_RECALL_ACTION_TIMEOUT)
            _record_action_result(self._metrics, ACTION_RECALL, result)
            safe_increment(self._metrics, METRIC_ACTION_RECALL_TIMEOUT_TOTAL)
            return result
        except Exception as exc:
            self._logger.error(
                "Chat Filter recall action failed: error_type=%s",
                type(exc).__name__,
            )
            result = PlatformActionResult.failed(REASON_RECALL_ACTION_FAILED)
            _record_action_result(self._metrics, ACTION_RECALL, result)
            return result
        finally:
            safe_observe_ms(
                self._metrics,
                METRIC_ACTION_RECALL_MS,
                (perf_counter() - started_at) * 1000,
            )


def _not_scheduled(reason: str) -> PlatformActionResult:
    return PlatformActionResult(status="not_scheduled", reason=reason)


def _record_action_result(
    metrics: ChatFilterMetrics,
    action: str,
    result: PlatformActionResult,
) -> None:
    counters = {
        (ACTION_MUTE, "failed"): METRIC_ACTION_MUTE_FAILED_TOTAL,
        (ACTION_MUTE, "success"): METRIC_ACTION_MUTE_SUCCESS_TOTAL,
        (ACTION_MUTE, "unsupported"): METRIC_ACTION_MUTE_UNSUPPORTED_TOTAL,
        (ACTION_MUTE, "not_scheduled"): METRIC_ACTION_MUTE_NOT_SCHEDULED_TOTAL,
        (ACTION_RECALL, "failed"): METRIC_ACTION_RECALL_FAILED_TOTAL,
        (ACTION_RECALL, "success"): METRIC_ACTION_RECALL_SUCCESS_TOTAL,
        (ACTION_RECALL, "unsupported"): METRIC_ACTION_RECALL_UNSUPPORTED_TOTAL,
        (ACTION_RECALL, "not_scheduled"): METRIC_ACTION_RECALL_NOT_SCHEDULED_TOTAL,
    }
    metric_name = counters.get((action, result.status))
    if metric_name is not None:
        safe_increment(metrics, metric_name)
