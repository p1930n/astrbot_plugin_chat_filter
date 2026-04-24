from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Sequence

from .models import PlatformEventSnapshot


ActionStatus = Literal["not_scheduled", "pending", "success", "failed", "unsupported"]

ACTION_STATUS_UNSUPPORTED: ActionStatus = "unsupported"
UNSUPPORTED_REASON_PHASE_03 = "phase_03_platform_api_unconfirmed"


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
