from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings  # noqa: E402
from astrbot_plugin_chat_filter.runtime.metrics import ChatFilterMetrics  # noqa: E402
from astrbot_plugin_chat_filter.services.violation_records import (  # noqa: E402
    ViolationRecorder,
)
from _violation_job_queue_test_support import (  # noqa: E402
    Executor as _Executor,
    HangingRecorder as _HangingRecorder,
    Logger as _Logger,
    PlatformActions as _PlatformActions,
    Recorder as _Recorder,
    message as _message,
    outbox_entry as _outbox_entry,
    queue as _queue,
    repository as _repository,
    wait_for as _wait_for,
)


class ViolationJobQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_persists_then_processes_record_actions_and_warning(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            metrics = ChatFilterMetrics()
            executor = _Executor()
            platform_actions = _PlatformActions()
            queue = _queue(
                repository=repository,
                recorder=ViolationRecorder(repository, _Logger(), metrics),
                executor=executor,
                metrics=metrics,
                settings=ChatFilterSettings.from_config({"warning_message": "warn"}),
            )
            message = _message("blocked", message_id="msg-1")

            self.assertTrue(
                await queue.enqueue(
                    message=message,
                    matched_word="blocked",
                    platform_actions=platform_actions,
                )
            )
            await _wait_for(lambda: bool(platform_actions.text_logs))
            await _wait_for(
                lambda: metrics.snapshot().counters.get(
                    "violation_job.completed.total",
                )
                == 1
            )
            await queue.shutdown()

            job = repository.get_violation_outbox_job(1)
            self.assertIsNotNone(job)
            self.assertEqual(job.status, "done")
            self.assertIsNotNone(job.violation_id)
            self.assertEqual(len(executor.calls), 1)
            self.assertEqual(platform_actions.text_logs, [("qq", "100", "warn")])
            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.enqueued.total"], 1)
            self.assertEqual(snapshot.counters["violation_job.completed.total"], 1)
            self.assertEqual(snapshot.timings["violation_job.process.ms"].count, 1)

    async def test_records_disabled_runs_actions_without_recording(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            recorder = _Recorder(violation_id=42)
            executor = _Executor()
            queue = _queue(
                repository=repository,
                recorder=recorder,
                executor=executor,
                settings=ChatFilterSettings.from_config(
                    {
                        "violation_records_enabled": False,
                        "warn_user": False,
                    }
                ),
            )
            message = _message("blocked", message_id="msg-2")

            self.assertTrue(
                await queue.enqueue(
                    message=message,
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            await _wait_for(lambda: bool(executor.calls))
            await queue.shutdown()

            self.assertEqual(recorder.calls, [])
            self.assertEqual(executor.calls, [(None, message)])
            job = repository.get_violation_outbox_job(1)
            self.assertIsNotNone(job)
            self.assertEqual(job.status, "done")
            self.assertIsNone(job.violation_id)

    async def test_record_failure_retries_without_running_actions(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            recorder = _Recorder(violation_id=None)
            executor = _Executor()
            metrics = ChatFilterMetrics()
            queue = _queue(
                repository=repository,
                recorder=recorder,
                executor=executor,
                metrics=metrics,
                settings=ChatFilterSettings.from_config(
                    {
                        "warn_user": False,
                        "violation_outbox_rate_limit_per_second": 1000,
                    }
                ),
            )

            self.assertTrue(
                await queue.enqueue(
                    message=_message("blocked", message_id="msg-3"),
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            await _wait_for(lambda: bool(recorder.calls))
            await asyncio.sleep(0.05)
            await queue.shutdown()

            self.assertEqual(executor.calls, [])
            job = repository.get_violation_outbox_job(1)
            self.assertIsNotNone(job)
            self.assertEqual(job.status, "pending")
            self.assertEqual(job.attempt_count, 1)
            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.retried.total"], 1)

    async def test_duplicate_message_id_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            metrics = ChatFilterMetrics()
            queue = _queue(
                repository=repository,
                recorder=_Recorder(violation_id=None),
                executor=_Executor(),
                metrics=metrics,
                settings=ChatFilterSettings.from_config(
                    {
                        "violation_records_enabled": False,
                        "warn_user": False,
                    }
                ),
            )
            message = _message("blocked", message_id="same-message")

            self.assertTrue(
                await queue.enqueue(
                    message=message,
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            self.assertTrue(
                await queue.enqueue(
                    message=message,
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            await _wait_for(lambda: repository.get_violation_outbox_job(1) is not None)
            await queue.shutdown()

            self.assertIsNone(repository.get_violation_outbox_job(2))
            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.enqueued.total"], 1)
            self.assertEqual(snapshot.counters["violation_job.duplicate.total"], 1)

    async def test_warning_send_failure_is_logged_without_job_failure(self) -> None:
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
                settings=ChatFilterSettings.from_config(
                    {
                        "violation_records_enabled": False,
                        "warning_message": "warn",
                    }
                ),
            )

            self.assertTrue(
                await queue.enqueue(
                    message=_message("blocked", message_id="msg-4"),
                    matched_word="blocked",
                    platform_actions=_PlatformActions(
                        send_error=RuntimeError("boom"),
                    ),
                )
            )
            await _wait_for(lambda: bool(logger.warning_calls))
            await _wait_for(
                lambda: metrics.snapshot().counters.get(
                    "violation_job.completed.total",
                )
                == 1
            )
            await queue.shutdown()

            self.assertEqual(logger.warning_calls, [("RuntimeError",)])
            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.completed.total"], 1)
            self.assertNotIn("violation_job.failed.total", snapshot.counters)

    async def test_backpressure_rejects_when_active_outbox_is_full(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            repository.enqueue_violation_outbox(
                _outbox_entry("existing", "existing"),
                max_active_jobs=10,
            )
            logger = _Logger()
            metrics = ChatFilterMetrics()
            queue = _queue(
                repository=repository,
                recorder=_Recorder(violation_id=None),
                executor=_Executor(),
                metrics=metrics,
                logger=logger,
                settings=ChatFilterSettings.from_config(
                    {
                        "violation_outbox_max_pending": 100,
                        "violation_records_enabled": False,
                        "warn_user": False,
                    }
                ),
            )
            queue._settings = ChatFilterSettings(
                violation_records_enabled=False,
                warn_user=False,
                violation_outbox_max_pending=1,
            )

            accepted = await queue.enqueue(
                message=_message("blocked", message_id="new"),
                matched_word="blocked",
                platform_actions=_PlatformActions(),
            )
            await queue.shutdown()

            self.assertFalse(accepted)
            self.assertIsNone(repository.get_violation_outbox_job(2))
            snapshot = metrics.snapshot()
            self.assertEqual(snapshot.counters["violation_job.backpressure.total"], 1)
            self.assertEqual(
                logger.warning_calls,
                [("max_pending", "present", "present", "present")],
            )

    async def test_platform_actions_unavailable_defers_without_attempt_increment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            repository.enqueue_violation_outbox(
                _outbox_entry("recover", "recover"),
                max_active_jobs=10,
            )
            queue = _queue(
                repository=repository,
                recorder=_Recorder(violation_id=None),
                executor=_Executor(),
                settings=ChatFilterSettings.from_config(
                    {
                        "violation_records_enabled": False,
                        "warn_user": False,
                        "violation_outbox_rate_limit_per_second": 1000,
                    }
                ),
            )

            queue.start()
            await _wait_for(
                lambda: repository.get_violation_outbox_job(1).status == "pending"
                and repository.get_violation_outbox_job(1).attempt_count == 0
                and repository.get_violation_outbox_job(1).error_code
                == "platform_actions_unavailable"
            )
            await queue.shutdown()

    async def test_shutdown_cancels_hanging_worker(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = _repository(root)
            recorder = _HangingRecorder()
            queue = _queue(
                repository=repository,
                recorder=recorder,
                executor=_Executor(),
                settings=ChatFilterSettings.from_config({"warn_user": False}),
            )

            self.assertTrue(
                await queue.enqueue(
                    message=_message("blocked", message_id="msg-5"),
                    matched_word="blocked",
                    platform_actions=_PlatformActions(),
                )
            )
            await _wait_for(lambda: recorder.started)
            await asyncio.wait_for(queue.shutdown(), timeout=1.0)


if __name__ == "__main__":
    unittest.main()
