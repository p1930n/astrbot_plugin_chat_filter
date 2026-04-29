from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from ..domain.models import ChatMessage, PushBinding, ViolationPushDelivery
from ..persistence.repository import ChatFilterRepository
from ..platform.platform_actions import (
    ACTION_STATUS_UNSUPPORTED,
    ActionStatus,
    ForwardMessageNode,
    PlatformActionResult,
    PlatformActions,
    SendForwardMessageRequest,
    SendTextLogRequest,
)
from .violation_action_audit import ViolationActionAudit


REASON_NO_PUSH_BINDINGS = "no_push_bindings"
REASON_PUSH_BINDING_LOOKUP_FAILED = "push_binding_lookup_failed"
REASON_FORWARD_ACTION_FAILED = "forward_action_failed"
REASON_FORWARD_ACTION_TIMEOUT = "forward_action_timeout"
REASON_TEXT_LOG_ACTION_FAILED = "text_log_action_failed"
REASON_TEXT_LOG_ACTION_TIMEOUT = "text_log_action_timeout"
FORWARD_ACTION_TIMEOUT_SECONDS = 10.0
TEXT_LOG_ACTION_TIMEOUT_SECONDS = 10.0
TEXT_LOG_DISPLAY_NAME_MAX_LENGTH = 80


class ViolationPushLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...


class ViolationPushNotifier:
    def __init__(
        self,
        repository: ChatFilterRepository,
        *,
        audit: ViolationActionAudit,
        logger: ViolationPushLogger,
    ) -> None:
        self._repository = repository
        self._audit = audit
        self._logger = logger

    async def forward(
        self,
        *,
        violation_id: int | None,
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
            if violation_id is not None:
                await self._audit.record_push_delivery(
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
            if violation_id is not None:
                await self._audit.record_push_delivery(
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
