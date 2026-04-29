from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.commands.global_command_service import (  # noqa: E402
    REGEX_SKIP_USAGE,
    GlobalCommandService,
)
from astrbot_plugin_chat_filter.domain.models import RuntimeState  # noqa: E402
from astrbot_plugin_chat_filter.domain.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.domain.settings import RegexRuleSkip  # noqa: E402


class GlobalCommandServiceTests(unittest.TestCase):
    def test_regex_skip_diagnostics_format_reasons_and_truncated_preview(self) -> None:
        service = GlobalCommandService(
            RuntimeState(),
            RuleSnapshot(
                global_words=(),
                global_regex_rules=(),
                case_sensitive=False,
                global_regex_rule_skips=(
                    RegexRuleSkip(
                        index=0,
                        reason="compile_error",
                        pattern_preview="[",
                        pattern_length=1,
                        source_id="6",
                        detail="unterminated character set at position 0",
                    ),
                    RegexRuleSkip(
                        index=1,
                        reason="too_long",
                        pattern_preview=("x" * 80) + "...",
                        pattern_length=501,
                        source_id="7",
                    ),
                ),
            ),
        )

        result = service.format_regex_skips("1")

        self.assertEqual(
            result,
            (
                "Chat Filter regex skips: total=2, showing=1.\n"
                "#1 reason=compile_error source=6 len=1 pattern=[ "
                "detail=unterminated character set at position 0\n"
                "Use .cf regex-skips 2 for more."
            ),
        )
        self.assertNotIn("x" * 100, result)

    def test_regex_skip_diagnostics_handles_none_and_invalid_limit(self) -> None:
        service = GlobalCommandService(
            RuntimeState(),
            RuleSnapshot(
                global_words=(),
                global_regex_rules=(),
                case_sensitive=False,
            ),
        )

        self.assertEqual(service.format_regex_skips(), "Chat Filter regex skips: none.")
        self.assertEqual(service.format_regex_skips("abc"), REGEX_SKIP_USAGE)


if __name__ == "__main__":
    unittest.main()
