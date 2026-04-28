from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.domain.matcher import ChatFilterMatcher  # noqa: E402
from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    ChatMessage,
    GroupPolicy,
    RuntimeState,
)
from astrbot_plugin_chat_filter.domain.rule_models import GlobalRule, RuleType  # noqa: E402
from astrbot_plugin_chat_filter.domain.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings  # noqa: E402


class MatcherRuleSnapshotTests(unittest.TestCase):
    def test_matcher_uses_snapshot_and_respects_inherit_global_false(self) -> None:
        settings = ChatFilterSettings.from_config({})
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
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [
                _rule(1, "word", "blocked"),
                _rule(2, "regex", "^root$"),
            ],
            settings=settings,
        )
        state = _enabled_state()
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

    def test_legacy_global_disabled_state_no_longer_blocks_enabled_group(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "blocked")],
            settings=settings,
        )
        state = _enabled_state(global_enabled=False)

        result = ChatFilterMatcher().detect(
            _message("blocked"),
            settings,
            state,
            snapshot,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.matched_word, "blocked")

    def test_matcher_skips_group_manager_when_admin_exemption_enabled(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "blocked")],
            settings=settings,
        )
        matcher = ChatFilterMatcher()

        owner_result = matcher.detect(
            _message("blocked", sender_role="owner"),
            settings,
            _enabled_state(),
            snapshot,
        )
        admin_result = matcher.detect(
            _message("blocked", sender_role="admin"),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertFalse(owner_result.matched)
        self.assertFalse(admin_result.matched)

    def test_matcher_checks_group_manager_when_admin_exemption_disabled(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "blocked")],
            settings=settings,
        )
        state = RuntimeState(
            groups={
                "qq:200": GroupPolicy(
                    enabled=True,
                    admin_exempt_enabled=False,
                )
            }
        )

        result = ChatFilterMatcher().detect(
            _message("blocked", sender_role="admin"),
            settings,
            state,
            snapshot,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.matched_word, "blocked")

    def test_matcher_applies_admin_exemption_per_group(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "blocked")],
            settings=settings,
        )
        state = RuntimeState(
            groups={
                "qq:200": GroupPolicy(
                    enabled=True,
                    admin_exempt_enabled=False,
                ),
                "qq:201": GroupPolicy(
                    enabled=True,
                    admin_exempt_enabled=True,
                ),
            }
        )
        matcher = ChatFilterMatcher()

        disabled_group_result = matcher.detect(
            _message("blocked", group_id="200", sender_role="admin"),
            settings,
            state,
            snapshot,
        )
        enabled_group_result = matcher.detect(
            _message("blocked", group_id="201", sender_role="admin"),
            settings,
            state,
            snapshot,
        )

        self.assertTrue(disabled_group_result.matched)
        self.assertFalse(enabled_group_result.matched)

    def test_matcher_detects_obfuscated_words_with_short_gaps(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [
                _rule(1, "word", "脑残"),
                _rule(2, "word", "加微信"),
            ],
            settings=settings,
        )
        state = _enabled_state()
        matcher = ChatFilterMatcher()

        insult_result = matcher.detect(
            _message("脑u残"),
            settings,
            state,
            snapshot,
        )
        contact_result = matcher.detect(
            _message("加XX微信"),
            settings,
            state,
            snapshot,
        )

        self.assertTrue(insult_result.matched)
        self.assertEqual(insult_result.matched_word, "脑残")
        self.assertTrue(contact_result.matched)
        self.assertEqual(contact_result.matched_word, "加微信")

    def test_obfuscated_word_matching_can_be_disabled(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "obfuscated_word_matching_enabled": False,
            }
        )
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "脑残")],
            settings=settings,
        )
        result = ChatFilterMatcher().detect(
            _message("脑u残"),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertFalse(result.matched)

    def test_obfuscated_word_matching_respects_gap_limit(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "obfuscated_word_max_gap": 1,
            }
        )
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "脑残")],
            settings=settings,
        )
        matcher = ChatFilterMatcher()

        short_gap = matcher.detect(
            _message("脑u残"),
            settings,
            _enabled_state(),
            snapshot,
        )
        long_gap = matcher.detect(
            _message("脑uv残"),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertTrue(short_gap.matched)
        self.assertFalse(long_gap.matched)

    def test_obfuscated_word_matching_respects_case_sensitive_mode(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "case_sensitive": True,
            }
        )
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "Ab")],
            settings=settings,
        )
        matcher = ChatFilterMatcher()

        exact_case = matcher.detect(
            _message("Axb"),
            settings,
            _enabled_state(),
            snapshot,
        )
        wrong_case = matcher.detect(
            _message("axb"),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertTrue(exact_case.matched)
        self.assertFalse(wrong_case.matched)

    def test_single_character_words_do_not_use_obfuscated_matching(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "坏")],
            settings=settings,
        )

        direct_result = ChatFilterMatcher().detect(
            _message("坏"),
            settings,
            _enabled_state(),
            snapshot,
        )
        unrelated_result = ChatFilterMatcher().detect(
            _message("不"),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertTrue(direct_result.matched)
        self.assertFalse(unrelated_result.matched)

    def test_obfuscated_word_matching_uses_2000_character_scan_limit(self) -> None:
        settings = ChatFilterSettings.from_config({})
        snapshot = RuleSnapshot.from_rules(
            [_rule(1, "word", "脑残")],
            settings=settings,
        )
        text = ("x" * 2000) + "脑u残"

        result = ChatFilterMatcher().detect(
            _message(text),
            settings,
            _enabled_state(),
            snapshot,
        )

        self.assertFalse(result.matched)

    def test_settings_parse_obfuscated_word_matching_defaults_and_bounds(self) -> None:
        defaults = ChatFilterSettings.from_config({})
        disabled = ChatFilterSettings.from_config(
            {
                "obfuscated_word_matching_enabled": False,
                "obfuscated_word_max_gap": "2",
                "regex_gap_max": "3",
            }
        )
        too_large = ChatFilterSettings.from_config(
            {
                "obfuscated_word_max_gap": 999,
                "regex_gap_max": 999,
            }
        )
        bool_gap = ChatFilterSettings.from_config(
            {
                "obfuscated_word_max_gap": True,
                "regex_gap_max": True,
            }
        )

        self.assertTrue(defaults.obfuscated_word_matching_enabled)
        self.assertEqual(defaults.obfuscated_word_max_gap, 4)
        self.assertEqual(defaults.regex_gap_max, 8)
        self.assertFalse(disabled.obfuscated_word_matching_enabled)
        self.assertEqual(disabled.obfuscated_word_max_gap, 2)
        self.assertEqual(disabled.regex_gap_max, 3)
        self.assertEqual(too_large.obfuscated_word_max_gap, 64)
        self.assertEqual(too_large.regex_gap_max, 64)
        self.assertEqual(bool_gap.obfuscated_word_max_gap, 4)
        self.assertEqual(bool_gap.regex_gap_max, 8)

    def test_status_uses_snapshot_summary_not_settings_global_words(self) -> None:
        from astrbot_plugin_chat_filter.commands.command_service import (  # noqa: E402
            ChatFilterCommandService,
        )

        settings = ChatFilterSettings.from_config({})
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
        self.assertNotIn("global=", service.format_status())


class FakeLogger:
    def error(self, message: str, *args: object) -> None:
        raise AssertionError("format_status should not log errors")

    def warning(self, message: str, *args: object) -> None:
        raise AssertionError("format_status should not log warnings")


def _message(
    text: str,
    *,
    group_id: str = "200",
    sender_role: str = "",
) -> ChatMessage:
    return ChatMessage(
        platform="qq",
        group_id=group_id,
        user_id="u1",
        text=text,
        sender_role=sender_role,
    )


def _enabled_state(*, global_enabled: bool | None = None) -> RuntimeState:
    return RuntimeState(
        global_enabled=global_enabled,
        groups={"qq:200": GroupPolicy(enabled=True)},
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
