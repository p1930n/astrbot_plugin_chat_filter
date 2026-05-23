from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True, slots=True)
class TimingSnapshot:
    count: int
    total_ms: float
    max_ms: float

    @property
    def avg_ms(self) -> float:
        if self.count <= 0:
            return 0.0
        return self.total_ms / self.count


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    counters: dict[str, int]
    timings: dict[str, TimingSnapshot]


class ChatFilterMetrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._timings: dict[str, TimingSnapshot] = {}

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def observe_ms(self, name: str, elapsed_ms: float) -> None:
        current = self._timings.get(name)
        if current is None:
            self._timings[name] = TimingSnapshot(
                count=1,
                total_ms=elapsed_ms,
                max_ms=elapsed_ms,
            )
            return
        self._timings[name] = TimingSnapshot(
            count=current.count + 1,
            total_ms=current.total_ms + elapsed_ms,
            max_ms=max(current.max_ms, elapsed_ms),
        )

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            counters=dict(sorted(self._counters.items())),
            timings=dict(sorted(self._timings.items())),
        )

    def format_snapshot(self) -> str:
        snapshot = self.snapshot()
        lines = ["Chat Filter metrics:"]
        if not snapshot.counters and not snapshot.timings:
            return "\n".join([*lines, "no samples"])

        if snapshot.counters:
            lines.append("Counters:")
            for name, value in snapshot.counters.items():
                lines.append(f"- {name}: {value}")

        if snapshot.timings:
            lines.append("Timings:")
            for name, timing in snapshot.timings.items():
                lines.append(
                    "- "
                    f"{name}: count={timing.count} "
                    f"avg_ms={timing.avg_ms:.3f} "
                    f"max_ms={timing.max_ms:.3f} "
                    f"total_ms={timing.total_ms:.3f}"
                )
        return "\n".join(lines)


class MetricsTimer:
    def __init__(self, metrics: ChatFilterMetrics, name: str) -> None:
        self._metrics = metrics
        self._name = name
        self._started_at = perf_counter()

    def stop(self) -> None:
        elapsed_ms = (perf_counter() - self._started_at) * 1000
        self._metrics.observe_ms(self._name, elapsed_ms)


def start_timer(metrics: ChatFilterMetrics, name: str) -> MetricsTimer:
    return MetricsTimer(metrics, name)


def safe_increment(metrics: ChatFilterMetrics, name: str, value: int = 1) -> None:
    try:
        metrics.increment(name, value)
    except Exception:
        pass


def safe_observe_ms(metrics: ChatFilterMetrics, name: str, elapsed_ms: float) -> None:
    try:
        metrics.observe_ms(name, elapsed_ms)
    except Exception:
        pass
