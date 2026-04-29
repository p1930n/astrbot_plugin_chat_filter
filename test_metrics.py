from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


from astrbot_plugin_chat_filter.runtime.metrics import (  # noqa: E402
    ChatFilterMetrics,
    safe_increment,
    safe_observe_ms,
)


class ChatFilterMetricsTests(unittest.TestCase):
    def test_counters_timings_snapshot_and_format_are_aggregate_only(self) -> None:
        metrics = ChatFilterMetrics()

        metrics.increment("message.matched.total")
        metrics.increment("message.matched.total")
        metrics.observe_ms("message.matcher.ms", 2.0)
        metrics.observe_ms("message.matcher.ms", 4.0)

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.counters, {"message.matched.total": 2})
        self.assertEqual(snapshot.timings["message.matcher.ms"].count, 2)
        self.assertEqual(snapshot.timings["message.matcher.ms"].total_ms, 6.0)
        self.assertEqual(snapshot.timings["message.matcher.ms"].max_ms, 4.0)

        formatted = metrics.format_snapshot()
        self.assertIn("message.matched.total: 2", formatted)
        self.assertIn("message.matcher.ms: count=2 avg_ms=3.000", formatted)

    def test_safe_helpers_do_not_raise_when_provider_fails(self) -> None:
        metrics = _FailingMetrics()

        safe_increment(metrics, "message.matched.total")
        safe_observe_ms(metrics, "message.matcher.ms", 1.0)


class _FailingMetrics(ChatFilterMetrics):
    def increment(self, name: str, value: int = 1) -> None:
        _ = name, value
        raise RuntimeError("boom")

    def observe_ms(self, name: str, elapsed_ms: float) -> None:
        _ = name, elapsed_ms
        raise RuntimeError("boom")


if __name__ == "__main__":
    unittest.main()
