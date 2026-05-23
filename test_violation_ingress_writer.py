from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    ViolationOutboxEnqueueResult,
)
from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings  # noqa: E402
from astrbot_plugin_chat_filter.runtime.metrics import ChatFilterMetrics  # noqa: E402
from _violation_job_queue_test_support import (  # noqa: E402
    Executor as _Executor,
    Logger as _Logger,
    PlatformActions as _PlatformActions,
    Recorder as _Recorder,
    message as _message,
    queue as _queue,
    repository as _repository,
)


class ViolationIngressWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_returns_before_repository_write_completes(self) -> None:
        repository = _BlockingEnqueueRepository()
        metrics = ChatFilterMetrics()
        queue = _queue(
            repository=repository,
            recorder=_Recorder(violation_id=None),
            executor=_Executor(),
            metrics=metrics,
            settings=ChatFilterSettings(
                violation_records_enabled=False,
                warn_user=False,
                violation_outbox_worker_count=0,
            ),
        )

        accepted = await asyncio.wait_for(
            queue.enqueue(
                message=_message("blocked", message_id="fast-return"),
                matched_word="blocked",
                platform_actions=_PlatformActions(),
            ),
            timeout=0.05,
        )

        self.assertTrue(accepted)
        self.assertFalse(repository.write_finished.is_set())
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.counters["violation_job.ingress.accepted.total"], 1)
        repository.release()
        await queue.shutdown()

    async def test_ingress_queue_full_rejects_without_waiting_for_writer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            logger = _Logger()
            metrics = ChatFilterMetrics()
            queue = _queue(
                repository=repository,
                recorder=_Recorder(violation_id=None),
                executor=_Executor(),
                metrics=metrics,
                logger=logger,
                settings=ChatFilterSettings(
                    violation_records_enabled=False,
                    warn_user=False,
                    violation_outbox_max_pending=1,
                    violation_outbox_worker_count=0,
                ),
            )

            self.assertTrue(
                await queue.enqueue(
                    message=_message("blocked", message_id="first"),
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            self.assertFalse(
                await queue.enqueue(
                    message=_message("blocked", message_id="second"),
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            await queue.shutdown()

            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.backpressure.total"], 1)
            self.assertEqual(
                logger.warning_calls,
                [("memory_queue_full", "present", "present", "present")],
            )


class _BlockingEnqueueRepository:
    def __init__(self) -> None:
        self.write_started = threading.Event()
        self.write_finished = threading.Event()
        self._release = threading.Event()

    def enqueue_violation_outbox(
        self,
        _entry,
        *,
        max_active_jobs: int,
    ) -> ViolationOutboxEnqueueResult:
        _ = max_active_jobs
        self.write_started.set()
        self._release.wait(timeout=1)
        self.write_finished.set()
        return ViolationOutboxEnqueueResult(status="enqueued", job_id=1)

    def release(self) -> None:
        self._release.set()


if __name__ == "__main__":
    unittest.main()
