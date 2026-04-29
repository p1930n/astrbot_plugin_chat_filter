from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from ..domain.models import (
    ChatMessage,
    ViolationOutboxJob,
)
from ..domain.settings import ChatFilterSettings
from ..persistence.repository import ChatFilterRepository
from ..platform.platform_actions import PlatformActions, SendTextLogRequest
from .metrics import ChatFilterMetrics, safe_increment, safe_observe_ms
from .violation_job_helpers import (
    METRIC_JOB_BACKPRESSURE_TOTAL,
    METRIC_JOB_COMPLETED_TOTAL,
    METRIC_JOB_DEFERRED_TOTAL,
    METRIC_JOB_DUPLICATE_TOTAL,
    METRIC_JOB_ENQUEUED_TOTAL,
    METRIC_JOB_FAILED_TOTAL,
    METRIC_JOB_PROCESS_MS,
    METRIC_JOB_RETRIED_TOTAL,
    OUTBOX_DEFER_SECONDS,
    OUTBOX_IDLE_POLL_SECONDS,
    AsyncRateLimiter,
    RetryableViolationJobError,
    build_outbox_entry,
    field_state,
    retry_after_seconds,
)


class ViolationRecorderProtocol(Protocol):
    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
    ) -> int | None:
        ...


class ViolationActionExecutorProtocol(Protocol):
    async def execute(
        self,
        *,
        violation_id: int | None,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> None:
        ...


class ViolationJobLogger(Protocol):
    def warning(self, message: str, *args: object) -> None:
        ...

    def error(self, message: str, *args: object) -> None:
        ...


class ViolationJobQueue:
    def __init__(
        self,
        *,
        settings: ChatFilterSettings,
        repository: ChatFilterRepository,
        violation_recorder: ViolationRecorderProtocol,
        violation_action_executor: ViolationActionExecutorProtocol,
        metrics: ChatFilterMetrics,
        logger: ViolationJobLogger,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._violation_recorder = violation_recorder
        self._violation_action_executor = violation_action_executor
        self._metrics = metrics
        self._logger = logger
        self._worker_id = f"chat-filter-{uuid4().hex}"
        self._workers: set[asyncio.Task[None]] = set()
        self._closed = False
        self._recovered = False
        self._recover_lock = asyncio.Lock()
        self._enqueue_lock = asyncio.Lock()
        self._rate_limiter = AsyncRateLimiter(
            settings.violation_outbox_rate_limit_per_second,
        )
        self._platform_actions_by_platform: dict[str, PlatformActions] = {}

    async def enqueue(
        self,
        *,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: PlatformActions,
    ) -> bool:
        self.register_platform_actions(message.platform, platform_actions)
        if self._closed:
            self._record_enqueue_backpressure(message, "closed")
            return False

        entry = build_outbox_entry(
            message,
            matched_word,
            max_attempts=self._settings.violation_outbox_max_attempts,
        )
        try:
            async with self._enqueue_lock:
                result = await asyncio.to_thread(
                    self._repository.enqueue_violation_outbox,
                    entry,
                    max_active_jobs=self._settings.violation_outbox_max_pending,
                )
        except Exception as exc:
            self._record_enqueue_backpressure(message, type(exc).__name__)
            return False

        self.start()
        if result.status == "enqueued":
            safe_increment(self._metrics, METRIC_JOB_ENQUEUED_TOTAL)
            return True
        if result.status == "duplicate":
            safe_increment(self._metrics, METRIC_JOB_DUPLICATE_TOTAL)
            return True

        self._record_enqueue_backpressure(message, "max_pending")
        return False

    def register_platform_actions(
        self,
        platform: str,
        platform_actions: PlatformActions,
    ) -> None:
        if platform:
            self._platform_actions_by_platform[platform] = platform_actions

    def start(self) -> None:
        if self._closed or self._workers:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._logger.error(
                "Chat Filter violation outbox could not start without "
                "a running event loop."
            )
            return

        for index in range(self._settings.violation_outbox_worker_count):
            task = asyncio.create_task(
                self._worker_loop(),
                name=f"chat-filter-violation-outbox-{index + 1}",
            )
            self._workers.add(task)
            task.add_done_callback(self._workers.discard)

    async def shutdown(self) -> None:
        self._closed = True
        for task in tuple(self._workers):
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker_loop(self) -> None:
        await self._recover_processing_jobs_once()
        while True:
            await self._rate_limiter.wait()
            job = await asyncio.to_thread(
                self._repository.claim_next_violation_outbox_job,
                worker_id=self._worker_id,
            )
            if job is None:
                await asyncio.sleep(OUTBOX_IDLE_POLL_SECONDS)
                continue
            await self._process_claimed_job(job)

    async def _recover_processing_jobs_once(self) -> None:
        async with self._recover_lock:
            if self._recovered:
                return
            try:
                recovered = await asyncio.to_thread(
                    self._repository.recover_processing_violation_outbox_jobs,
                )
                if recovered:
                    safe_increment(self._metrics, METRIC_JOB_DEFERRED_TOTAL, recovered)
                    self._logger.warning(
                        "Chat Filter recovered processing violation outbox jobs: "
                        "count=%s",
                        recovered,
                    )
            except Exception as exc:
                self._logger.error(
                    "Chat Filter violation outbox recovery failed: error_type=%s",
                    type(exc).__name__,
                )
            self._recovered = True

    async def _process_claimed_job(self, job: ViolationOutboxJob) -> None:
        platform_actions = self._platform_actions_by_platform.get(job.platform)
        if platform_actions is None:
            await self._defer_job(job, "platform_actions_unavailable")
            return

        started_at = perf_counter()
        violation_id = job.violation_id
        try:
            message = job.to_chat_message()
            if self._settings.violation_records_enabled and violation_id is None:
                violation_id = await self._violation_recorder.record(
                    message,
                    job.matched_word,
                )
                if violation_id is None:
                    raise RetryableViolationJobError("violation_record_failed")
                await asyncio.to_thread(
                    self._repository.set_violation_outbox_violation_id,
                    job_id=job.job_id,
                    violation_id=violation_id,
                )

            await self._violation_action_executor.execute(
                violation_id=violation_id,
                message=message,
                platform_actions=platform_actions,
            )

            if self._settings.warn_user:
                await self._send_warning_message(message, platform_actions)

            await asyncio.to_thread(
                self._repository.mark_violation_outbox_done,
                job_id=job.job_id,
                violation_id=violation_id,
            )
            safe_increment(self._metrics, METRIC_JOB_COMPLETED_TOTAL)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._retry_job(job, type(exc).__name__)
        finally:
            safe_observe_ms(
                self._metrics,
                METRIC_JOB_PROCESS_MS,
                (perf_counter() - started_at) * 1000,
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

    async def _defer_job(self, job: ViolationOutboxJob, error_code: str) -> None:
        try:
            await asyncio.to_thread(
                self._repository.defer_violation_outbox_job,
                job_id=job.job_id,
                error_code=error_code,
                retry_after_seconds=OUTBOX_DEFER_SECONDS,
            )
            safe_increment(self._metrics, METRIC_JOB_DEFERRED_TOTAL)
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation outbox defer failed: error_type=%s",
                type(exc).__name__,
            )

    async def _retry_job(self, job: ViolationOutboxJob, error_code: str) -> None:
        try:
            status = await asyncio.to_thread(
                self._repository.retry_violation_outbox_job,
                job_id=job.job_id,
                error_code=error_code,
                retry_after_seconds=retry_after_seconds(job.attempt_count + 1),
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation outbox retry update failed: "
                "error_type=%s",
                type(exc).__name__,
            )
            return

        if status == "failed":
            safe_increment(self._metrics, METRIC_JOB_FAILED_TOTAL)
            self._logger.error(
                "Chat Filter violation outbox job failed permanently: "
                "job_id=%s error_code=%s",
                job.job_id,
                error_code,
            )
            return
        safe_increment(self._metrics, METRIC_JOB_RETRIED_TOTAL)

    def _record_enqueue_backpressure(
        self,
        message: ChatMessage,
        reason: str,
    ) -> None:
        safe_increment(self._metrics, METRIC_JOB_BACKPRESSURE_TOTAL)
        self._logger.warning(
            "Chat Filter violation outbox enqueue rejected: reason=%s "
            "platform=%s group_id=%s sender_id=%s",
            reason,
            field_state(message.platform),
            field_state(message.group_id),
            field_state(message.user_id),
        )
