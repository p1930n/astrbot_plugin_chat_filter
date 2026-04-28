from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from ..domain.models import ChatMessage, PushBinding, ViolationPushDelivery
from ..platform.platform_actions import (
    ACTION_STATUS_UNSUPPORTED,
    ActionStatus,
    ForwardMessageNode,
    MuteUserRequest,
    PlatformActionResult,
    PlatformActions,
    RecallMessageRequest,
    SendForwardMessageRequest,
    SendTextLogRequest,
)
from ..persistence.repository import ChatFilterRepository, ViolationActionName
from ..domain.settings import MAX_MUTE_DURATION_SECONDS


ACTION_MUTE: ViolationActionName = "mute"
ACTION_RECALL: ViolationActionName = "recall"
ACTION_FORWARD: ViolationActionName = "forward"
REASON_MESSAGE_ID_MISSING = "message_id_missing"
REASON_NO_PUSH_BINDINGS = "no_push_bindings"
REASON_PUSH_BINDING_LOOKUP_FAILED = "push_binding_lookup_failed"
REASON_MUTE_ACTION_FAILED = "mute_action_failed"
REASON_MUTE_ACTION_TIMEOUT = "mute_action_timeout"
REASON_RECALL_ACTION_FAILED = "recall_action_failed"
REASON_RECALL_ACTION_TIMEOUT = "recall_action_timeout"
REASON_FORWARD_ACTION_FAILED = "forward_action_failed"
REASON_FORWARD_ACTION_TIMEOUT = "forward_action_timeout"
REASON_TEXT_LOG_ACTION_FAILED = "text_log_action_failed"
REASON_TEXT_LOG_ACTION_TIMEOUT = "text_log_action_timeout"
MUTE_ACTION_TIMEOUT_SECONDS = 10.0
RECALL_ACTION_TIMEOUT_SECONDS = 10.0
FORWARD_ACTION_TIMEOUT_SECONDS = 10.0
TEXT_LOG_ACTION_TIMEOUT_SECONDS = 10.0
TEXT_LOG_DISPLAY_NAME_MAX_LENGTH = 80


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

        forward_result = await self._forward_message(
            violation_id=violation_id,
            message=message,
            platform_actions=platform_actions,
            mute_result=mute_result,
            recall_result=recall_result,
        )
        await self._try_update_status(
            violation_id=violation_id,
            action=ACTION_FORWARD,
            result=forward_result,
        )

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

    async def _forward_message(
        self,
        *,
        violation_id: int,
        message: ChatMessage,
        platform_actions: PlatformActions,
        mute_result: PlatformActionResult,
        recall_result: PlatformActionResult,
    ) -> PlatformActionResult:
        bindings = await self._push_bindings_for_group(message)
        if bindings is None:
            return PlatformActionResult.failed(REASON_PUSH_BINDING_LOOKUP_FAILED)
        if not bindings:
            return PlatformActionResult(
                status="not_scheduled",
                reason=REASON_NO_PUSH_BINDINGS,
            )

        results: list[PlatformActionResult] = []
        for binding in bindings:
            await self._try_record_push_delivery(
                ViolationPushDelivery(
                    violation_id=violation_id,
                    platform=message.platform,
                    listening_group_id=message.group_id,
                    push_group_id=binding.push_group_id,
                    action_status="pending",
                )
            )
            result = await self._send_forward_message(
                message=message,
                platform_actions=platform_actions,
                push_group_id=binding.push_group_id,
            )
            results.append(result)
            await self._try_record_push_delivery(
                ViolationPushDelivery(
                    violation_id=violation_id,
                    platform=message.platform,
                    listening_group_id=message.group_id,
                    push_group_id=binding.push_group_id,
                    action_status=result.status,
                    error_code=result.reason,
                )
            )
            text_log_result = await self._send_text_log(
                message=message,
                platform_actions=platform_actions,
                push_group_id=binding.push_group_id,
                mute_result=mute_result,
                recall_result=recall_result,
                forward_result=result,
            )
            if text_log_result.status != "success":
                self._logger.error(
                    "Chat Filter text log delivery failed: "
                    "push_group_id=%s status=%s reason=%s",
                    binding.push_group_id,
                    text_log_result.status,
                    text_log_result.reason,
                )

        return PlatformActionResult(status=_aggregate_forward_status(results))

    async def _push_bindings_for_group(
        self,
        message: ChatMessage,
    ) -> list[PushBinding] | None:
        try:
            return await asyncio.to_thread(
                self._repository.list_enabled_push_bindings_for_group,
                platform=message.platform,
                listening_group_id=message.group_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter push binding lookup failed: error_type=%s",
                type(exc).__name__,
            )
            return None

    async def _send_forward_message(
        self,
        *,
        message: ChatMessage,
        platform_actions: PlatformActions,
        push_group_id: str,
    ) -> PlatformActionResult:
        request = SendForwardMessageRequest(
            platform=message.platform,
            target_group_id=push_group_id,
            nodes=(
                ForwardMessageNode(
                    sender_id=message.user_id,
                    sender_display_name=message.sender_display_name,
                    text=message.text,
                ),
            ),
        )
        try:
            return await asyncio.wait_for(
                platform_actions.send_forward_message(request),
                timeout=FORWARD_ACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter forward message timed out.")
            return PlatformActionResult.failed(REASON_FORWARD_ACTION_TIMEOUT)
        except Exception as exc:
            self._logger.error(
                "Chat Filter forward message failed: error_type=%s",
                type(exc).__name__,
            )
            return PlatformActionResult.failed(REASON_FORWARD_ACTION_FAILED)

    async def _send_text_log(
        self,
        *,
        message: ChatMessage,
        platform_actions: PlatformActions,
        push_group_id: str,
        mute_result: PlatformActionResult,
        recall_result: PlatformActionResult,
        forward_result: PlatformActionResult,
    ) -> PlatformActionResult:
        request = SendTextLogRequest(
            platform=message.platform,
            target_group_id=push_group_id,
            text=_format_text_log(
                message=message,
                mute_result=mute_result,
                recall_result=recall_result,
                forward_result=forward_result,
            ),
        )
        try:
            return await asyncio.wait_for(
                platform_actions.send_text_log(request),
                timeout=TEXT_LOG_ACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.error("Chat Filter text log send timed out.")
            return PlatformActionResult.failed(REASON_TEXT_LOG_ACTION_TIMEOUT)
        except Exception as exc:
            self._logger.error(
                "Chat Filter text log send failed: error_type=%s",
                type(exc).__name__,
            )
            return PlatformActionResult.failed(REASON_TEXT_LOG_ACTION_FAILED)

    async def _try_record_push_delivery(
        self,
        delivery: ViolationPushDelivery,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._repository.upsert_violation_push_delivery,
                delivery,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation push delivery update failed: "
                "push_group_id=%s error_type=%s",
                delivery.push_group_id,
                type(exc).__name__,
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


def _aggregate_forward_status(results: list[PlatformActionResult]) -> ActionStatus:
    if not results:
        return "not_scheduled"
    if all(result.status == "success" for result in results):
        return "success"
    if all(result.status == ACTION_STATUS_UNSUPPORTED for result in results):
        return ACTION_STATUS_UNSUPPORTED
    return "failed"


def _format_text_log(
    *,
    message: ChatMessage,
    mute_result: PlatformActionResult,
    recall_result: PlatformActionResult,
    forward_result: PlatformActionResult,
) -> str:
    sender_name = _sanitize_text_log_value(message.sender_display_name) or "未知"
    handled_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return "\n".join(
        [
            "聊天过滤命中日志",
            f"平台：{message.platform}",
            f"监听群：{message.group_id}",
            f"发送者：{sender_name}（{message.user_id}）",
            f"禁言状态：{mute_result.status}",
            f"撤回状态：{recall_result.status}",
            f"转发状态：{forward_result.status}",
            f"处理时间：{handled_at}",
        ]
    )


def _sanitize_text_log_value(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= TEXT_LOG_DISPLAY_NAME_MAX_LENGTH:
        return cleaned
    return cleaned[: TEXT_LOG_DISPLAY_NAME_MAX_LENGTH - 3] + "..."
