from __future__ import annotations

import asyncio
from hashlib import sha256
from time import perf_counter
from typing import Protocol

from ..domain.models import ChatMessage, ViolationEvent
from ..persistence.repository import ChatFilterRepository
from ..runtime.metrics import ChatFilterMetrics, safe_increment, safe_observe_ms


VIOLATION_EXCERPT_LENGTH = 300
INITIAL_ACTION_STATUS = "pending"
METRIC_VIOLATION_RECORD_SUCCESS_TOTAL = "violation_record.success.total"
METRIC_VIOLATION_RECORD_FAILED_TOTAL = "violation_record.failed.total"
METRIC_VIOLATION_RECORD_MS = "violation_record.ms"


class ViolationRecordLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...


class ViolationRecorder:
    def __init__(
        self,
        repository: ChatFilterRepository,
        logger: ViolationRecordLogger,
        metrics: ChatFilterMetrics,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._metrics = metrics

    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
    ) -> int | None:
        if not matched_word:
            return None

        started_at = perf_counter()
        violation = ViolationEvent(
            platform=message.platform,
            group_id=message.group_id,
            user_id=message.user_id,
            sender_display_name_snapshot=message.sender_display_name,
            message_id=message.message_id,
            matched_keyword=matched_word,
            matched_content=_matched_excerpt(message.text, matched_word),
            raw_message_digest=_message_digest(message.text),
            action_mute_status=INITIAL_ACTION_STATUS,
            action_recall_status=INITIAL_ACTION_STATUS,
            action_forward_status=INITIAL_ACTION_STATUS,
        )
        try:
            violation_id = await asyncio.to_thread(
                self._repository.record_violation,
                violation,
            )
            safe_increment(self._metrics, METRIC_VIOLATION_RECORD_SUCCESS_TOTAL)
            return violation_id
        except Exception as exc:
            safe_increment(self._metrics, METRIC_VIOLATION_RECORD_FAILED_TOTAL)
            self._logger.error(
                "Chat Filter violation record failed: error_type=%s",
                type(exc).__name__,
            )
            return None
        finally:
            safe_observe_ms(
                self._metrics,
                METRIC_VIOLATION_RECORD_MS,
                (perf_counter() - started_at) * 1000,
            )


def _matched_excerpt(text: str, matched_word: str) -> str:
    if len(text) <= VIOLATION_EXCERPT_LENGTH:
        return text

    haystack = text.casefold()
    needle = matched_word.casefold()
    index = haystack.find(needle)
    if index < 0:
        return text[:VIOLATION_EXCERPT_LENGTH]

    half_window = max((VIOLATION_EXCERPT_LENGTH - len(matched_word)) // 2, 0)
    start = max(index - half_window, 0)
    end = min(start + VIOLATION_EXCERPT_LENGTH, len(text))
    if end - start < VIOLATION_EXCERPT_LENGTH:
        start = max(end - VIOLATION_EXCERPT_LENGTH, 0)
    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt[3:]
    if end < len(text):
        excerpt = excerpt[:-3] + "..."
    return excerpt


def _message_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
