from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.models import ChatMessage, MatchResult, RuntimeState
from ..platform.platform_actions import PlatformActions, SendTextLogRequest
from ..domain.rule_snapshot import RuleSnapshot
from ..domain.settings import ChatFilterSettings


class MessageFilterLogger(Protocol):
    def warning(self, message: str, *args: object) -> None:
        ...


class MessageMatcher(Protocol):
    def detect(
        self,
        message: ChatMessage,
        settings: ChatFilterSettings,
        state: RuntimeState,
        rule_snapshot: RuleSnapshot,
    ) -> MatchResult:
        ...


class ViolationRecorderProtocol(Protocol):
    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: PlatformActions,
    ) -> int | None:
        ...


class ViolationActionExecutorProtocol(Protocol):
    async def execute(
        self,
        *,
        violation_id: int,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class MessageFilterResult:
    stop_event: bool = False
    warn_user: bool = False
    warning_message: str = ""


class MessageFilterService:
    def __init__(
        self,
        *,
        matcher: MessageMatcher,
        settings: ChatFilterSettings,
        state: RuntimeState,
        rule_snapshot: RuleSnapshot,
        violation_recorder: ViolationRecorderProtocol,
        violation_action_executor: ViolationActionExecutorProtocol,
        logger: MessageFilterLogger,
    ) -> None:
        self._matcher = matcher
        self._settings = settings
        self._state = state
        self._rule_snapshot = rule_snapshot
        self._violation_recorder = violation_recorder
        self._violation_action_executor = violation_action_executor
        self._logger = logger

    async def handle_group_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> MessageFilterResult:
        if not _has_required_message_scope(message):
            self._logger.warning(
                "Chat Filter skipped message with incomplete event scope: "
                "platform=%s group_id=%s sender_id=%s",
                _field_state(message.platform),
                _field_state(message.group_id),
                _field_state(message.user_id),
            )
            return MessageFilterResult()

        result = self._matcher.detect(
            message,
            self._settings,
            self._state,
            self._rule_snapshot,
        )
        if not result.matched:
            return MessageFilterResult()

        violation_id: int | None = None
        if self._settings.violation_records_enabled:
            violation_id = await self._violation_recorder.record(
                message,
                result.matched_word,
                platform_actions,
            )

        if violation_id is not None:
            await self._violation_action_executor.execute(
                violation_id=violation_id,
                message=message,
                platform_actions=platform_actions,
            )

        if self._settings.warn_user:
            await self._send_warning_message(message, platform_actions)

        return MessageFilterResult(
            stop_event=self._settings.stop_event,
        )

    async def _send_warning_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        try:
            await platform_actions.send_text_log(
                SendTextLogRequest(
                    platform=message.platform,
                    target_group_id=message.group_id,
                    text=self._settings.warning_message,
                )
            )
        except Exception as exc:
            self._logger.warning(
                "Chat Filter warning message send failed: error_type=%s",
                type(exc).__name__,
            )


def _has_required_message_scope(message: ChatMessage) -> bool:
    return bool(message.platform and message.group_id and message.user_id)


def _field_state(value: str) -> str:
    return "present" if value else "missing"
