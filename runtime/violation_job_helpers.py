from __future__ import annotations

import asyncio
from hashlib import sha256
from time import monotonic, time_ns

from ..domain.models import ChatMessage, ViolationOutboxEntry


OUTBOX_DEFER_SECONDS = 5
OUTBOX_IDLE_POLL_SECONDS = 0.2
OUTBOX_MESSAGE_ID_PRIORITY = 100
OUTBOX_FALLBACK_PRIORITY = 50
METRIC_JOB_ENQUEUED_TOTAL = "violation_job.enqueued.total"
METRIC_JOB_DUPLICATE_TOTAL = "violation_job.duplicate.total"
METRIC_JOB_BACKPRESSURE_TOTAL = "violation_job.backpressure.total"
METRIC_JOB_INGRESS_ACCEPTED_TOTAL = "violation_job.ingress.accepted.total"
METRIC_JOB_INGRESS_DROPPED_TOTAL = "violation_job.ingress.dropped.total"
METRIC_JOB_INGRESS_RETRIED_TOTAL = "violation_job.ingress.retried.total"
METRIC_JOB_WRITER_FAILED_TOTAL = "violation_job.writer.failed.total"
METRIC_JOB_DEFERRED_TOTAL = "violation_job.deferred.total"
METRIC_JOB_RETRIED_TOTAL = "violation_job.retried.total"
METRIC_JOB_FAILED_TOTAL = "violation_job.failed.total"
METRIC_JOB_COMPLETED_TOTAL = "violation_job.completed.total"
METRIC_JOB_PROCESS_MS = "violation_job.process.ms"


class AsyncRateLimiter:
    def __init__(self, rate_per_second: int) -> None:
        self._interval_seconds = 1.0 / max(rate_per_second, 1)
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = monotonic()
            if now < self._next_allowed_at:
                await asyncio.sleep(self._next_allowed_at - now)
                now = monotonic()
            self._next_allowed_at = max(now, self._next_allowed_at) + (
                self._interval_seconds
            )


class RetryableViolationJobError(RuntimeError):
    pass


def build_outbox_entry(
    message: ChatMessage,
    matched_word: str | None,
    *,
    max_attempts: int,
) -> ViolationOutboxEntry:
    return ViolationOutboxEntry(
        idempotency_key=idempotency_key(message, matched_word),
        priority=priority_for_message(message),
        platform=message.platform,
        group_id=message.group_id,
        user_id=message.user_id,
        message_id=message.message_id,
        sender_role=message.sender_role,
        sender_display_name=message.sender_display_name,
        group_display_name=message.group_display_name,
        message_text=message.text,
        matched_word=matched_word,
        max_attempts=max_attempts,
    )


def idempotency_key(message: ChatMessage, matched_word: str | None) -> str:
    if message.message_id:
        source = f"message:{message.platform}:{message.group_id}:{message.message_id}"
    else:
        digest = sha256(message.text.encode("utf-8")).hexdigest()
        source = (
            "synthetic:"
            f"{message.platform}:{message.group_id}:{message.user_id}:"
            f"{matched_word or ''}:{digest}:{time_ns()}"
        )
    return sha256(source.encode("utf-8")).hexdigest()


def priority_for_message(message: ChatMessage) -> int:
    if message.message_id:
        return OUTBOX_MESSAGE_ID_PRIORITY
    return OUTBOX_FALLBACK_PRIORITY


def retry_after_seconds(attempt_count: int) -> int:
    return min(60, 2 ** max(attempt_count - 1, 0))


def field_state(value: str) -> str:
    return "present" if value else "missing"
