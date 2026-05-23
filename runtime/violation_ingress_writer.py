from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from ..domain.models import ViolationOutboxEntry
from ..domain.settings import ChatFilterSettings
from ..persistence.repository import ChatFilterRepository
from .metrics import ChatFilterMetrics, safe_increment
from .violation_job_helpers import (
    METRIC_JOB_BACKPRESSURE_TOTAL,
    METRIC_JOB_DUPLICATE_TOTAL,
    METRIC_JOB_ENQUEUED_TOTAL,
    METRIC_JOB_INGRESS_ACCEPTED_TOTAL,
    METRIC_JOB_INGRESS_DROPPED_TOTAL,
    METRIC_JOB_INGRESS_RETRIED_TOTAL,
    METRIC_JOB_WRITER_FAILED_TOTAL,
    field_state,
    retry_after_seconds,
)


INGRESS_SHUTDOWN_DRAIN_TIMEOUT_SECONDS = 2.0


class ViolationIngressLogger(Protocol):
    def warning(self, message: str, *args: object) -> None:
        ...

    def error(self, message: str, *args: object) -> None:
        ...


@dataclass(slots=True)
class _IngressJob:
    entry: ViolationOutboxEntry
    attempt_count: int = 0


class ViolationIngressWriter:
    def __init__(
        self,
        *,
        settings: ChatFilterSettings,
        repository: ChatFilterRepository,
        metrics: ChatFilterMetrics,
        logger: ViolationIngressLogger,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._metrics = metrics
        self._logger = logger
        self._queue: asyncio.Queue[_IngressJob] = asyncio.Queue(
            maxsize=max(settings.violation_outbox_max_pending, 1),
        )
        self._pending_keys: set[str] = set()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def try_enqueue(self, entry: ViolationOutboxEntry) -> bool:
        if self._closed:
            self._record_backpressure(entry, "closed")
            return False
        if not self._has_running_loop():
            self._record_backpressure(entry, "runtime_unavailable")
            return False
        if entry.idempotency_key in self._pending_keys:
            safe_increment(self._metrics, METRIC_JOB_DUPLICATE_TOTAL)
            return True

        self._pending_keys.add(entry.idempotency_key)
        try:
            self._queue.put_nowait(_IngressJob(entry))
        except asyncio.QueueFull:
            self._pending_keys.discard(entry.idempotency_key)
            self._record_backpressure(entry, "memory_queue_full")
            return False

        self.start()
        safe_increment(self._metrics, METRIC_JOB_INGRESS_ACCEPTED_TOTAL)
        return True

    def start(self) -> None:
        if self._closed:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._logger.error(
                "Chat Filter violation outbox could not start without "
                "a running event loop."
            )
            return

        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._writer_loop(),
                name="chat-filter-violation-outbox-writer",
            )
            self._task.add_done_callback(self._handle_writer_done)

    async def shutdown(self) -> None:
        self._closed = True
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(
                    self._queue.join(),
                    timeout=INGRESS_SHUTDOWN_DRAIN_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                dropped_count = len(self._pending_keys)
                if dropped_count:
                    safe_increment(
                        self._metrics,
                        METRIC_JOB_INGRESS_DROPPED_TOTAL,
                        dropped_count,
                    )
                    self._logger.warning(
                        "Chat Filter violation ingress shutdown left buffered "
                        "jobs: count=%s",
                        dropped_count,
                    )
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._pending_keys.clear()

    async def _writer_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._persist(job)
            except asyncio.CancelledError:
                safe_increment(self._metrics, METRIC_JOB_INGRESS_DROPPED_TOTAL)
                raise
            except Exception as exc:
                safe_increment(self._metrics, METRIC_JOB_WRITER_FAILED_TOTAL)
                self._logger.error(
                    "Chat Filter violation ingress writer failed: error_type=%s",
                    type(exc).__name__,
                )
            finally:
                self._pending_keys.discard(job.entry.idempotency_key)
                self._queue.task_done()

    async def _persist(self, job: _IngressJob) -> None:
        while True:
            try:
                result = await asyncio.to_thread(
                    self._repository.enqueue_violation_outbox,
                    job.entry,
                    max_active_jobs=self._settings.violation_outbox_max_pending,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                job.attempt_count += 1
                if job.attempt_count >= self._settings.violation_outbox_max_attempts:
                    safe_increment(self._metrics, METRIC_JOB_WRITER_FAILED_TOTAL)
                    self._record_backpressure(job.entry, type(exc).__name__)
                    return
                safe_increment(self._metrics, METRIC_JOB_INGRESS_RETRIED_TOTAL)
                self._logger.warning(
                    "Chat Filter violation ingress write retry: "
                    "attempt=%s error_type=%s",
                    job.attempt_count,
                    type(exc).__name__,
                )
                await asyncio.sleep(retry_after_seconds(job.attempt_count))
                continue

            if result.status == "enqueued":
                safe_increment(self._metrics, METRIC_JOB_ENQUEUED_TOTAL)
                return
            if result.status == "duplicate":
                safe_increment(self._metrics, METRIC_JOB_DUPLICATE_TOTAL)
                return
            self._record_backpressure(job.entry, "max_pending")
            return

    def _handle_writer_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return
        safe_increment(self._metrics, METRIC_JOB_WRITER_FAILED_TOTAL)
        self._logger.error(
            "Chat Filter violation ingress writer stopped: error_type=%s",
            type(exc).__name__,
        )

    def _record_backpressure(
        self,
        entry: ViolationOutboxEntry,
        reason: str,
    ) -> None:
        safe_increment(self._metrics, METRIC_JOB_BACKPRESSURE_TOTAL)
        self._logger.warning(
            "Chat Filter violation outbox enqueue rejected: reason=%s "
            "platform=%s group_id=%s sender_id=%s",
            reason,
            field_state(entry.platform),
            field_state(entry.group_id),
            field_state(entry.user_id),
        )

    @staticmethod
    def _has_running_loop() -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True
