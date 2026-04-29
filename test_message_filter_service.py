from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.runtime.message_filter_service import (  # noqa: E402
    MessageFilterResult,
    MessageFilterService,
)
from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    ChatMessage,
    MatchResult,
    RuntimeState,
)
from astrbot_plugin_chat_filter.domain.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings  # noqa: E402
from astrbot_plugin_chat_filter.runtime.metrics import ChatFilterMetrics  # noqa: E402


class MessageFilterServiceTests(unittest.TestCase):
    def test_match_enqueues_job_and_returns_entry_decision(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        job_queue = _JobQueue()
        service = _service(
            matcher=matcher,
            job_queue=job_queue,
            settings=ChatFilterSettings.from_config(
                {
                    "warning_message": "warn",
                }
            ),
        )
        message = _message("blocked text")
        platform_actions = _PlatformActions()

        result = asyncio.run(service.handle_group_message(message, platform_actions))

        self.assertEqual(
            result,
            MessageFilterResult(
                stop_event=True,
            ),
        )
        self.assertEqual(len(matcher.calls), 1)
        self.assertEqual(job_queue.calls, [(message, "blocked", platform_actions)])

    def test_no_match_skips_job_enqueue(self) -> None:
        matcher = _Matcher(MatchResult(matched=False))
        job_queue = _JobQueue()
        service = _service(matcher=matcher, job_queue=job_queue)

        result = asyncio.run(
            service.handle_group_message(_message("clean"), _PlatformActions())
        )

        self.assertEqual(result, MessageFilterResult())
        self.assertEqual(len(matcher.calls), 1)
        self.assertEqual(job_queue.calls, [])

    def test_metrics_count_matched_unmatched_and_scope_missing(self) -> None:
        metrics = ChatFilterMetrics()
        matched_service = _service(
            matcher=_Matcher(MatchResult(matched=True, matched_word="blocked")),
            metrics=metrics,
        )
        unmatched_service = _service(
            matcher=_Matcher(MatchResult(matched=False)),
            metrics=metrics,
        )
        scope_service = _service(
            matcher=_Matcher(MatchResult(matched=True, matched_word="blocked")),
            metrics=metrics,
        )

        asyncio.run(
            matched_service.handle_group_message(_message("blocked"), _PlatformActions())
        )
        asyncio.run(
            unmatched_service.handle_group_message(_message("clean"), _PlatformActions())
        )
        asyncio.run(
            scope_service.handle_group_message(
                ChatMessage(platform="", group_id="100", user_id="200", text="x"),
                _PlatformActions(),
            )
        )

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.counters["message.handle_group_message.total"], 3)
        self.assertEqual(snapshot.counters["message.matched.total"], 1)
        self.assertEqual(snapshot.counters["message.unmatched.total"], 1)
        self.assertEqual(snapshot.counters["message.scope_missing.total"], 1)
        self.assertEqual(snapshot.timings["message.handle_group_message.ms"].count, 3)
        self.assertEqual(snapshot.timings["message.matcher.ms"].count, 2)

    def test_records_disabled_still_enqueues_matched_job(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        job_queue = _JobQueue()
        platform_actions = _PlatformActions()
        service = _service(
            matcher=matcher,
            job_queue=job_queue,
            settings=ChatFilterSettings.from_config(
                {
                    "violation_records_enabled": False,
                    "warning_message": "warn",
                }
            ),
        )
        message = _message("blocked")

        result = asyncio.run(service.handle_group_message(message, platform_actions))

        self.assertEqual(
            result,
            MessageFilterResult(
                stop_event=True,
            ),
        )
        self.assertEqual(job_queue.calls, [(message, "blocked", platform_actions)])

    def test_queue_rejection_still_returns_entry_decision(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        job_queue = _JobQueue(accepted=False)
        platform_actions = _PlatformActions()
        service = _service(
            matcher=matcher,
            job_queue=job_queue,
        )
        message = _message("blocked")

        result = asyncio.run(service.handle_group_message(message, platform_actions))

        self.assertEqual(result, MessageFilterResult(stop_event=True))
        self.assertEqual(job_queue.calls, [(message, "blocked", platform_actions)])

    def test_incomplete_scope_logs_and_skips_matcher(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        logger = _Logger()
        service = _service(
            matcher=matcher,
            logger=logger,
        )

        result = asyncio.run(
            service.handle_group_message(
                ChatMessage(platform="", group_id="100", user_id="200", text="x"),
                _PlatformActions(),
            )
        )

        self.assertEqual(result, MessageFilterResult())
        self.assertEqual(matcher.calls, [])
        self.assertEqual(
            logger.warning_calls,
            [("missing", "present", "present")],
        )


class _Matcher:
    def __init__(self, result: MatchResult) -> None:
        self._result = result
        self.calls: list[
            tuple[ChatMessage, ChatFilterSettings, RuntimeState, RuleSnapshot]
        ] = []

    def detect(
        self,
        message: ChatMessage,
        settings: ChatFilterSettings,
        state: RuntimeState,
        rule_snapshot: RuleSnapshot,
    ) -> MatchResult:
        self.calls.append((message, settings, state, rule_snapshot))
        return self._result


class _JobQueue:
    def __init__(self, accepted: bool = True) -> None:
        self._accepted = accepted
        self.calls: list[tuple[ChatMessage, str | None, _PlatformActions]] = []

    async def enqueue(
        self,
        *,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: "_PlatformActions",
    ) -> bool:
        self.calls.append((message, matched_word, platform_actions))
        return self._accepted


class _Logger:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[object, ...]] = []

    def warning(self, message: str, *args: object) -> None:
        _ = message
        self.warning_calls.append(args)


class _PlatformActions:
    pass


def _service(
    *,
    matcher: _Matcher,
    job_queue: _JobQueue | None = None,
    settings: ChatFilterSettings | None = None,
    logger: _Logger | None = None,
    metrics: ChatFilterMetrics | None = None,
) -> MessageFilterService:
    return MessageFilterService(
        matcher=matcher,
        settings=settings
        or ChatFilterSettings.from_config({}),
        state=RuntimeState(),
        rule_snapshot=RuleSnapshot(
            global_words=(),
            global_regex_rules=(),
            case_sensitive=False,
        ),
        violation_job_queue=job_queue or _JobQueue(),
        metrics=metrics or ChatFilterMetrics(),
        logger=logger or _Logger(),
    )


def _message(text: str) -> ChatMessage:
    return ChatMessage(
        platform="qq",
        group_id="100",
        user_id="200",
        text=text,
    )


if __name__ == "__main__":
    unittest.main()
