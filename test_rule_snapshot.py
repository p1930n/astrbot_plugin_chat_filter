from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.rule_models import GlobalRule, RuleType  # noqa: E402
from astrbot_plugin_chat_filter.rule_snapshot import (  # noqa: E402
    LegacyRuleSeed,
    RuleSnapshot,
)
from astrbot_plugin_chat_filter.settings import ChatFilterSettings  # noqa: E402


class RuleSnapshotTests(unittest.TestCase):
    def test_legacy_seed_normalizes_old_config_fields(self) -> None:
        settings = ChatFilterSettings.from_config(
            {
                "case_sensitive": False,
                "max_word_count": 2,
                "max_word_length": 5,
            }
        )

        seed = LegacyRuleSeed.from_config(
            {
                "global_words": [" alpha ", "toolong", "alpha", 123, "beta"],
                "global_regex_rules": [
                    "^admin$",
                    "[",
                    "(a+)+$",
                    "^root$",
                    "^admin$",
                ],
            },
            settings=settings,
        )

        self.assertFalse(hasattr(settings, "global_words"))
        self.assertFalse(hasattr(settings, "global_regex_rules"))
        self.assertEqual(seed.words, ("alpha", "beta"))
        self.assertEqual(seed.regex_patterns, ("^admin$", "^root$"))
        self.assertTrue(
            all(isinstance(pattern, str) for pattern in seed.regex_patterns)
        )
        self.assertEqual(
            seed.source_hash,
            LegacyRuleSeed(seed.words, seed.regex_patterns).source_hash,
        )

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
    pattern: str,
    *,
    enabled: bool,
) -> GlobalRule:
    return GlobalRule(
        id=rule_id,
        rule_type=rule_type,
        pattern=pattern,
        position=rule_id,
        enabled=enabled,
        source="test",
        created_at="2026-04-25T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
