from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from ..domain.models import ChatMessage, MatchResult, RuntimeState
from ..platform.platform_actions import PlatformActions
from ..domain.rule_snapshot import RuleSnapshot
from ..domain.settings import ChatFilterSettings
from .metrics import ChatFilterMetrics, safe_increment, safe_observe_ms


METRIC_HANDLE_GROUP_MESSAGE_TOTAL = "message.handle_group_message.total"
METRIC_HANDLE_GROUP_MESSAGE_MS = "message.handle_group_message.ms"
METRIC_MATCHER_MS = "message.matcher.ms"
METRIC_SCOPE_MISSING_TOTAL = "message.scope_missing.total"
METRIC_MATCHED_TOTAL = "message.matched.total"
METRIC_UNMATCHED_TOTAL = "message.unmatched.total"


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


class ViolationJobQueueProtocol(Protocol):
    async def enqueue(
        self,
        *,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: PlatformActions,
    ) -> bool:
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
        violation_job_queue: ViolationJobQueueProtocol,
        metrics: ChatFilterMetrics,
        logger: MessageFilterLogger,
    ) -> None:
        self._matcher = matcher
        self._settings = settings
        self._state = state
        self._rule_snapshot = rule_snapshot
        self._violation_job_queue = violation_job_queue
        self._metrics = metrics
        self._logger = logger

    async def handle_group_message(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> MessageFilterResult:
        started_at = perf_counter()
        safe_increment(self._metrics, METRIC_HANDLE_GROUP_MESSAGE_TOTAL)
        try:
            if not _has_required_message_scope(message):
                safe_increment(self._metrics, METRIC_SCOPE_MISSING_TOTAL)
                self._logger.warning(
                    "Chat Filter skipped message with incomplete event scope: "
                    "platform=%s group_id=%s sender_id=%s",
                    _field_state(message.platform),
                    _field_state(message.group_id),
                    _field_state(message.user_id),
                )
                return MessageFilterResult()

            matcher_started_at = perf_counter()
            try:
                result = self._matcher.detect(
                    message,
                    self._settings,
                    self._state,
                    self._rule_snapshot,
                )
            finally:
                safe_observe_ms(
                    self._metrics,
                    METRIC_MATCHER_MS,
                    (perf_counter() - matcher_started_at) * 1000,
                )
            if not result.matched:
                safe_increment(self._metrics, METRIC_UNMATCHED_TOTAL)
                return MessageFilterResult()

            safe_increment(self._metrics, METRIC_MATCHED_TOTAL)
            await self._violation_job_queue.enqueue(
                message=message,
                matched_word=result.matched_word,
                platform_actions=platform_actions,
            )

            return MessageFilterResult(
                stop_event=self._settings.stop_event,
            )
        finally:
            safe_observe_ms(
                self._metrics,
                METRIC_HANDLE_GROUP_MESSAGE_MS,
                (perf_counter() - started_at) * 1000,
            )


def _has_required_message_scope(message: ChatMessage) -> bool:
    return bool(message.platform and message.group_id and message.user_id)


def _field_state(value: str) -> str:
    return "present" if value else "missing"
