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


class MessageFilterServiceTests(unittest.TestCase):
    def test_match_records_executes_actions_and_returns_entry_decision(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        recorder = _Recorder(violation_id=42)
        executor = _Executor()
        service = _service(
            matcher=matcher,
            recorder=recorder,
            executor=executor,
            settings=ChatFilterSettings.from_config(
                {
                    "default_group_enabled": True,
                    "warning_message": "warn",
                }
            ),
        )
        message = _message("blocked text")
        platform_actions = _PlatformActions()

        result = asyncio.run(
            service.handle_group_message(message, platform_actions)
        )

        self.assertEqual(
            result,
            MessageFilterResult(
                stop_event=True,
                warn_user=True,
                warning_message="warn",
            ),
        )
        self.assertEqual(len(matcher.calls), 1)
        self.assertEqual(recorder.calls, [(message, "blocked", platform_actions)])
        self.assertEqual(executor.calls, [(42, message, platform_actions)])

    def test_no_match_skips_recording_and_actions(self) -> None:
        matcher = _Matcher(MatchResult(matched=False))
        recorder = _Recorder(violation_id=42)
        executor = _Executor()
        service = _service(
            matcher=matcher,
            recorder=recorder,
            executor=executor,
        )

        result = asyncio.run(
            service.handle_group_message(_message("clean"), _PlatformActions())
        )

        self.assertEqual(result, MessageFilterResult())
        self.assertEqual(len(matcher.calls), 1)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(executor.calls, [])

    def test_records_disabled_preserves_stop_and_warn_without_actions(self) -> None:
        matcher = _Matcher(MatchResult(matched=True, matched_word="blocked"))
        recorder = _Recorder(violation_id=42)
        executor = _Executor()
        service = _service(
            matcher=matcher,
            recorder=recorder,
            executor=executor,
            settings=ChatFilterSettings.from_config(
                {
                    "default_group_enabled": True,
                    "violation_records_enabled": False,
                    "warning_message": "warn",
                }
            ),
        )

        result = asyncio.run(
            service.handle_group_message(_message("blocked"), _PlatformActions())
        )

        self.assertEqual(
            result,
            MessageFilterResult(
                stop_event=True,
                warn_user=True,
                warning_message="warn",
            ),
        )
        self.assertEqual(recorder.calls, [])
        self.assertEqual(executor.calls, [])

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


class _Recorder:
    def __init__(self, violation_id: int | None) -> None:
        self._violation_id = violation_id
        self.calls: list[tuple[ChatMessage, str | None, _PlatformActions]] = []

    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: "_PlatformActions",
    ) -> int | None:
        self.calls.append((message, matched_word, platform_actions))
        return self._violation_id


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[int, ChatMessage, _PlatformActions]] = []

    async def execute(
        self,
        *,
        violation_id: int,
        message: ChatMessage,
        platform_actions: "_PlatformActions",
    ) -> None:
        self.calls.append((violation_id, message, platform_actions))


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
    recorder: _Recorder | None = None,
    executor: _Executor | None = None,
    settings: ChatFilterSettings | None = None,
    logger: _Logger | None = None,
) -> MessageFilterService:
    return MessageFilterService(
        matcher=matcher,
        settings=settings
        or ChatFilterSettings.from_config({"default_group_enabled": True}),
        state=RuntimeState(),
        rule_snapshot=RuleSnapshot(
            global_words=(),
            global_regex_rules=(),
            case_sensitive=False,
        ),
        violation_recorder=recorder or _Recorder(violation_id=None),
        violation_action_executor=executor or _Executor(),
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
