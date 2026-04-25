from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.command_service import (  # noqa: E402
    ChatFilterCommandService,
)
from astrbot_plugin_chat_filter.matcher import ChatFilterMatcher  # noqa: E402
from astrbot_plugin_chat_filter.models import (  # noqa: E402
    ChatMessage,
    GroupPolicy,
    RuntimeState,
)
from astrbot_plugin_chat_filter.rule_models import GlobalRule, RuleType  # noqa: E402
from astrbot_plugin_chat_filter.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.settings import ChatFilterSettings  # noqa: E402


class MatcherRuleSnapshotTests(unittest.TestCase):
    def test_matcher_uses_snapshot_and_respects_inherit_global_false(self) -> None:
        settings = ChatFilterSettings.from_config(
            {"enabled": True, "default_group_enabled": True}
        )
        snapshot = RuleSnapshot.from_rules(
            [
                _rule(1, "word", "blocked"),
                _rule(2, "regex", "^root$"),
            ],
            settings=settings,
        )
        state = RuntimeState(
            groups={
                "qq:100": GroupPolicy(
                    enabled=True,
                    inherit_global=False,
                    custom_words=("local",),
                )
            }
        )
        matcher = ChatFilterMatcher()

        global_result = matcher.detect(
            _message("blocked", group_id="100"),
            settings,
            state,
            snapshot,
        )
        local_result = matcher.detect(
            _message("LOCAL", group_id="100"),
            settings,
            state,
            snapshot,
        )

        self.assertFalse(global_result.matched)
        self.assertTrue(local_result.matched)
        self.assertEqual(local_result.matched_word, "local")
        self.assertEqual(local_result.word_count, 1)

    def test_matcher_keeps_word_priority_and_regex_match_prefix(self) -> None:
        settings = ChatFilterSettings.from_config(
            {"enabled": True, "default_group_enabled": True}
        )
        snapshot = RuleSnapshot.from_rules(
            [
                _rule(1, "word", "blocked"),
                _rule(2, "regex", "^root$"),
            ],
            settings=settings,
        )
        state = RuntimeState()
        matcher = ChatFilterMatcher()

        word_result = matcher.detect(
            _message("BLOCKED"),
            settings,
            state,
            snapshot,
        )
        regex_result = matcher.detect(
            _message("ROOT"),
            settings,
            state,
            snapshot,
        )

        self.assertTrue(word_result.matched)
        self.assertEqual(word_result.matched_word, "blocked")
        self.assertEqual(word_result.word_count, 2)
        self.assertTrue(regex_result.matched)
        self.assertEqual(regex_result.matched_word, "regex:^root$")
        self.assertEqual(regex_result.word_count, 2)

    def test_status_uses_snapshot_summary_not_settings_global_words(self) -> None:
        settings = ChatFilterSettings.from_config({"default_group_enabled": True})
        snapshot = RuleSnapshot(
            global_words=("alpha", "beta"),
            global_regex_rules=(),
            case_sensitive=False,
        )
        service = ChatFilterCommandService(
            repository=object(),  # type: ignore[arg-type]
            state=RuntimeState(),
            settings=settings,
            rule_snapshot=snapshot,
            logger=FakeLogger(),
        )

        self.assertFalse(hasattr(settings, "global_words"))
        self.assertIn("global_words=2", service.format_status())


class FakeLogger:
    def error(self, message: str, *args: object) -> None:
        raise AssertionError("format_status should not log errors")

    def warning(self, message: str, *args: object) -> None:
        raise AssertionError("format_status should not log warnings")


def _message(text: str, *, group_id: str = "200") -> ChatMessage:
    return ChatMessage(
        platform="qq",
        group_id=group_id,
        user_id="u1",
        text=text,
    )


def _rule(rule_id: int, rule_type: RuleType, pattern: str) -> GlobalRule:
    return GlobalRule(
        id=rule_id,
        rule_type=rule_type,
        pattern=pattern,
        position=rule_id,
        enabled=True,
        source="test",
        created_at="2026-04-25T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
