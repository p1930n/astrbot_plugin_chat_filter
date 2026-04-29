from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.domain.rule_models import (  # noqa: E402
    GlobalRule,
    RuleType,
)
from astrbot_plugin_chat_filter.domain.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings  # noqa: E402


class RuleSnapshotTests(unittest.TestCase):
    def test_snapshot_loads_enabled_global_rules_and_compiles_regex(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "case_sensitive": False,
                "max_word_count": 2,
                "max_word_length": 5,
            }
        )
        repository = FakeRuleRepository(
            [
                _rule(1, "word", "Alpha", enabled=True),
                _rule(2, "word", "toolong", enabled=True),
                _rule(3, "word", "Beta", enabled=False),
                _rule(4, "word", "Gamma", enabled=True),
                _rule(5, "regex", "root", enabled=True),
                _rule(6, "regex", "[", enabled=True),
                _rule(7, "regex", "(a+)+$", enabled=True),
                _rule(8, "regex", "disabled", enabled=False),
            ]
        )

        snapshot = RuleSnapshot.from_repository(repository, settings=settings)

        self.assertEqual(repository.list_calls, 1)
        self.assertEqual(snapshot.global_words, ("Alpha", "Gamma"))
        self.assertEqual(snapshot.global_word_count, 2)
        self.assertEqual(snapshot.global_regex_rule_count, 1)
        self.assertEqual(snapshot.global_regex_rules[0].pattern, "root")
        self.assertIsNotNone(snapshot.global_regex_rules[0].compiled.search("ROOT"))
        self.assertEqual(
            [skip.reason for skip in snapshot.global_regex_rule_skips],
            ["compile_error", "high_risk"],
        )
        self.assertEqual(snapshot.global_regex_rule_skip_count, 2)

    def test_snapshot_expands_configured_regex_gap_placeholder(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "regex_gap_max": 2,
            }
        )
        repository = FakeRuleRepository(
            [_rule(1, "regex", r"a{{GAP}}b", enabled=True)]
        )

        snapshot = RuleSnapshot.from_repository(repository, settings=settings)
        regex_rule = snapshot.global_regex_rules[0]

        self.assertEqual(regex_rule.pattern, r"a[\s\S]{0,2}b")
        self.assertIsNotNone(regex_rule.compiled.search("aXXb"))
        self.assertIsNone(regex_rule.compiled.search("aXXXb"))

    def test_snapshot_records_skipped_regex_rule_reasons(self) -> None:
        settings = ChatFilterSettings.from_config({})
        repository = FakeRuleRepository(
            [
                _rule(1, "regex", "root", enabled=True),
                _rule(2, "regex", " ", enabled=True),
                _rule(3, "regex", "root", enabled=True),
                _rule(4, "regex", "x" * 501, enabled=True),
                _rule(5, "regex", 42, enabled=True),
            ]
        )

        snapshot = RuleSnapshot.from_repository(repository, settings=settings)

        self.assertEqual(snapshot.global_regex_rule_count, 1)
        self.assertEqual(
            [
                (skip.source_id, skip.reason)
                for skip in snapshot.global_regex_rule_skips
            ],
            [
                ("2", "empty"),
                ("3", "duplicate"),
                ("4", "too_long"),
                ("5", "non_string"),
            ],
        )
        self.assertEqual(snapshot.global_regex_rule_skips[3].pattern_preview, "<int>")

    def test_snapshot_records_regex_max_count_skips(self) -> None:
        settings = ChatFilterSettings.from_config({})
        repository = FakeRuleRepository(
            [
                _rule(rule_id, "regex", f"rule-{rule_id}", enabled=True)
                for rule_id in range(1, 52)
            ]
        )

        snapshot = RuleSnapshot.from_repository(repository, settings=settings)

        self.assertEqual(snapshot.global_regex_rule_count, 50)
        self.assertEqual(snapshot.global_regex_rule_skip_count, 1)
        self.assertEqual(snapshot.global_regex_rule_skips[0].source_id, "51")
        self.assertEqual(snapshot.global_regex_rule_skips[0].reason, "max_count")


class FakeRuleRepository:
    def __init__(self, rules: list[GlobalRule]) -> None:
        self._rules = rules
        self.list_calls = 0

    def list_global_rules(self) -> list[GlobalRule]:
        self.list_calls += 1
        return self._rules


def _rule(
    rule_id: int,
    rule_type: RuleType,
    pattern: object,
    *,
    enabled: bool,
) -> GlobalRule:
    return GlobalRule(
        id=rule_id,
        rule_type=rule_type,
        pattern=pattern,  # type: ignore[arg-type]
        position=rule_id,
        enabled=enabled,
        source="test",
        created_at="2026-04-25T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
