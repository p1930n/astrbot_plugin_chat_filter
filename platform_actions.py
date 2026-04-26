from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, Sequence

from .models import PlatformEventSnapshot


ActionStatus = Literal["not_scheduled", "pending", "success", "failed", "unsupported"]

ACTION_STATUS_UNSUPPORTED: ActionStatus = "unsupported"
UNSUPPORTED_REASON_PHASE_03 = "phase_03_platform_api_unconfirmed"
UNSUPPORTED_REASON_NO_ACTION_CLIENT = "onebot_action_client_missing"
FAILED_REASON_ACTION_CALL_FAILED = "onebot_action_call_failed"
FAILED_REASON_INVALID_ACTION_SCOPE = "invalid_onebot_action_scope"
FAILED_REASON_INVALID_FILE_CONTENT = "invalid_onebot_file_content"
FAILED_REASON_INVALID_FORWARD_CONTENT = "invalid_onebot_forward_content"
FAILED_REASON_INVALID_TEXT_LOG_CONTENT = "invalid_onebot_text_log_content"
DEFAULT_FORWARD_NODE_NAME = "Chat Filter"


@dataclass(frozen=True, slots=True)
class PlatformActionCapabilities:
    mute_user: bool = False
    recall_message: bool = False
    send_forward_message: bool = False
    send_text_log: bool = False
    send_file: bool = False


@dataclass(frozen=True, slots=True)
class ViolationActionStatuses:
    mute: ActionStatus = ACTION_STATUS_UNSUPPORTED
    recall: ActionStatus = ACTION_STATUS_UNSUPPORTED
    forward: ActionStatus = ACTION_STATUS_UNSUPPORTED

    @classmethod
    def unsupported(cls) -> "ViolationActionStatuses":
        return cls(
            mute=ACTION_STATUS_UNSUPPORTED,
            recall=ACTION_STATUS_UNSUPPORTED,
            forward=ACTION_STATUS_UNSUPPORTED,
        )


@dataclass(frozen=True, slots=True)
class PlatformActionResult:
    status: ActionStatus
    reason: str = ""

    @classmethod
    def unsupported(cls) -> "PlatformActionResult":
        return cls(
            status=ACTION_STATUS_UNSUPPORTED,
            reason=UNSUPPORTED_REASON_PHASE_03,
        )

    @classmethod
    def failed(cls, reason: str) -> "PlatformActionResult":
        return cls(status="failed", reason=reason)


@dataclass(frozen=True, slots=True)
class MuteUserRequest:
    platform: str
    group_id: str
    user_id: str
    duration_seconds: int


@dataclass(frozen=True, slots=True)
class RecallMessageRequest:
    platform: str
    group_id: str
    message_id: str


@dataclass(frozen=True, slots=True)
class ForwardMessageNode:
    sender_id: str
    sender_display_name: str
    text: str


@dataclass(frozen=True, slots=True)
class SendForwardMessageRequest:
    platform: str
    target_group_id: str
    nodes: Sequence[ForwardMessageNode]


@dataclass(frozen=True, slots=True)
class SendTextLogRequest:
    platform: str
    target_group_id: str
    text: str


@dataclass(frozen=True, slots=True)
class SendFileRequest:
    platform: str
    target_group_id: str
    file_path: Path
    display_name: str


class PlatformActions(Protocol):
    def probe_capabilities(self, platform: str) -> PlatformActionCapabilities:
        ...

    def initial_violation_statuses(self, platform: str) -> ViolationActionStatuses:
        ...

    async def mute_user(self, request: MuteUserRequest) -> PlatformActionResult:
        ...

    async def recall_message(self, request: RecallMessageRequest) -> PlatformActionResult:
        ...

    async def send_forward_message(
        self,
        request: SendForwardMessageRequest,
    ) -> PlatformActionResult:
        ...

    async def send_text_log(self, request: SendTextLogRequest) -> PlatformActionResult:
        ...

    async def send_file(self, request: SendFileRequest) -> PlatformActionResult:
        ...


class ActionClient(Protocol):
    async def call_action(self, action: str, **params: Any) -> Any:
        ...


class QQPlatformActions:
    """Phase 03 platform boundary; real AstrBot/QQ calls are intentionally absent."""

    def probe_capabilities(self, platform: str) -> PlatformActionCapabilities:
        _ = platform
        return PlatformActionCapabilities()

    def initial_violation_statuses(self, platform: str) -> ViolationActionStatuses:
        _ = platform
        return ViolationActionStatuses.unsupported()

    async def mute_user(self, request: MuteUserRequest) -> PlatformActionResult:
        _ = request
        return PlatformActionResult.unsupported()

    async def recall_message(self, request: RecallMessageRequest) -> PlatformActionResult:
        _ = request
        return PlatformActionResult.unsupported()

    async def send_forward_message(
        self,
        request: SendForwardMessageRequest,
    ) -> PlatformActionResult:
        _ = request
        return PlatformActionResult.unsupported()

    async def send_text_log(self, request: SendTextLogRequest) -> PlatformActionResult:
        _ = request
        return PlatformActionResult.unsupported()

    async def send_file(self, request: SendFileRequest) -> PlatformActionResult:
        _ = request
        return PlatformActionResult.unsupported()


class OneBotV11PlatformActions:
    def __init__(self, action_client: ActionClient | None) -> None:
        self._action_client = action_client

    def probe_capabilities(self, platform: str) -> PlatformActionCapabilities:
        _ = platform
        has_client = self._action_client is not None
        return PlatformActionCapabilities(
            mute_user=has_client,
            recall_message=has_client,
            send_forward_message=has_client,
            send_text_log=has_client,
            send_file=has_client,
        )

    def initial_violation_statuses(self, platform: str) -> ViolationActionStatuses:
        _ = platform
        if self._action_client is None:
            return ViolationActionStatuses.unsupported()
        return ViolationActionStatuses(
            mute="pending",
            recall="pending",
            forward="pending",
        )

    async def mute_user(self, request: MuteUserRequest) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        group_id = _parse_positive_int(request.group_id)
        user_id = _parse_positive_int(request.user_id)
        if group_id is None or user_id is None:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_ACTION_SCOPE)

        return await self._call_action(
            "set_group_ban",
            group_id=group_id,
            user_id=user_id,
            duration=request.duration_seconds,
        )

    async def recall_message(self, request: RecallMessageRequest) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        message_id = _parse_positive_int(request.message_id)
        if message_id is None:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_ACTION_SCOPE)

        return await self._call_action(
            "delete_msg",
            message_id=message_id,
        )

    async def send_forward_message(
        self,
        request: SendForwardMessageRequest,
    ) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        group_id = _parse_positive_int(request.target_group_id)
        if group_id is None:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_ACTION_SCOPE)

        messages = _build_forward_messages(request.nodes)
        if not messages:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_FORWARD_CONTENT)

        return await self._call_action(
            "send_group_forward_msg",
            group_id=group_id,
            messages=messages,
        )

    async def send_text_log(self, request: SendTextLogRequest) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        group_id = _parse_positive_int(request.target_group_id)
        text = request.text.strip()
        if group_id is None:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_ACTION_SCOPE)
        if not text:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_TEXT_LOG_CONTENT)

        return await self._call_action(
            "send_group_msg",
            group_id=group_id,
            message=text,
            auto_escape=True,
        )

    async def send_file(self, request: SendFileRequest) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        group_id = _parse_positive_int(request.target_group_id)
        display_name = request.display_name.strip()
        if group_id is None:
            return PlatformActionResult.failed(FAILED_REASON_INVALID_ACTION_SCOPE)
        if not display_name or not request.file_path.is_file():
            return PlatformActionResult.failed(FAILED_REASON_INVALID_FILE_CONTENT)

        return await self._call_action(
            "upload_group_file",
            group_id=group_id,
            file=str(request.file_path),
            name=display_name,
        )

    async def _call_action(self, action: str, **params: Any) -> PlatformActionResult:
        if self._action_client is None:
            return PlatformActionResult(
                status=ACTION_STATUS_UNSUPPORTED,
                reason=UNSUPPORTED_REASON_NO_ACTION_CLIENT,
            )

        try:
            await self._action_client.call_action(action, **params)
        except Exception:
            return PlatformActionResult.failed(FAILED_REASON_ACTION_CALL_FAILED)
        return PlatformActionResult(status="success")


def format_platform_probe(
    snapshot: PlatformEventSnapshot,
    capabilities: PlatformActionCapabilities,
) -> str:
    return "\n".join(
        [
            "Chat Filter API probe:",
            f"platform={_field_state(snapshot.platform)}",
            f"group_id={_field_state(snapshot.group_id)}",
            f"sender_id={_field_state(snapshot.sender_id)}",
            f"message_id={_field_state(snapshot.message_id)}",
            f"sender_role={_field_state(snapshot.sender_role)}",
            f"sender_name={_field_state(snapshot.sender_display_name)}",
            f"group_name={_field_state(snapshot.group_display_name)}",
            f"mute_user={_capability_state(capabilities.mute_user)}",
            f"recall_message={_capability_state(capabilities.recall_message)}",
            f"send_forward_message={_capability_state(capabilities.send_forward_message)}",
            f"send_text_log={_capability_state(capabilities.send_text_log)}",
            f"send_file={_capability_state(capabilities.send_file)}",
        ]
    )


def _capability_state(enabled: bool) -> str:
    return "supported" if enabled else "unsupported"


def _field_state(value: str) -> str:
    return "present" if value else "missing"


def _parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _build_forward_messages(
    nodes: Sequence[ForwardMessageNode],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for node in nodes:
        user_id = _parse_positive_int(node.sender_id)
        text = node.text.strip()
        if user_id is None or not text:
            return []
        nickname = node.sender_display_name.strip() or DEFAULT_FORWARD_NODE_NAME
        messages.append(
            {
                "type": "node",
                "data": {
                    "user_id": user_id,
                    "nickname": nickname,
                    "content": [
                        {
                            "type": "text",
                            "data": {
                                "text": text,
                            },
                        }
                    ],
                },
            }
        )
    return messages
