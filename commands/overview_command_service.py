from __future__ import annotations

import asyncio
import csv
import io
from collections import defaultdict
from dataclasses import dataclass

from .command_runtime import CommandLogger
from ..domain.models import PushBinding, RuntimeState
from ..persistence.repository import ChatFilterRepository


OVERVIEW_CSV_FORMATS = frozenset(("csv", "table"))


class OverviewCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        state: RuntimeState,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._state = state
        self._logger = logger

    async def format_overview(self, platform: str, output_format: str = "") -> str:
        if not platform:
            return "Chat Filter overview failed: platform is unavailable."

        bindings = await self._list_push_bindings(platform)
        if bindings is None:
            return "Chat Filter overview failed."

        summary = self._overview_summary(platform, bindings)
        if output_format.strip().casefold() in OVERVIEW_CSV_FORMATS:
            return _format_csv(summary)
        return _format_summary(summary)

    async def _list_push_bindings(self, platform: str) -> list[PushBinding] | None:
        try:
            return await asyncio.to_thread(
                self._repository.list_push_bindings,
                platform=platform,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter overview bind list failed: error_type=%s",
                type(exc).__name__,
            )
            return None

    def _overview_summary(
        self,
        platform: str,
        bindings: list[PushBinding],
    ) -> "OverviewSummary":
        enabled_groups = _enabled_group_ids(self._state, platform)
        push_groups_by_listening = _push_groups_by_listening_group(bindings)
        row_group_ids = sorted(set(enabled_groups) | set(push_groups_by_listening))
        rows = tuple(
            OverviewRow(
                group_id=group_id,
                filter_enabled=group_id in enabled_groups,
                push_groups=tuple(push_groups_by_listening.get(group_id, ())),
            )
            for group_id in row_group_ids
        )
        return OverviewSummary(
            enabled_group_count=len(enabled_groups),
            listening_group_count=len(push_groups_by_listening),
            push_binding_count=len(bindings),
            rows=rows,
        )


@dataclass(frozen=True, slots=True)
class OverviewSummary:
    enabled_group_count: int
    listening_group_count: int
    push_binding_count: int
    rows: tuple["OverviewRow", ...]


@dataclass(frozen=True, slots=True)
class OverviewRow:
    group_id: str
    filter_enabled: bool
    push_groups: tuple[str, ...]


def _enabled_group_ids(state: RuntimeState, platform: str) -> set[str]:
    prefix = f"{platform}:"
    return {
        group_key.removeprefix(prefix)
        for group_key, policy in state.groups.items()
        if group_key.startswith(prefix) and policy.enabled is True
    }


def _push_groups_by_listening_group(
    bindings: list[PushBinding],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for binding in bindings:
        grouped[binding.listening_group_id].append(binding.push_group_id)
    return {
        listening_group: tuple(sorted(push_groups))
        for listening_group, push_groups in grouped.items()
    }


def _format_summary(summary: OverviewSummary) -> str:
    return "\n".join(
        [
            "Chat Filter overview:",
            f"enabled_groups={summary.enabled_group_count}",
            f"listening_groups={summary.listening_group_count}",
            f"push_bindings={summary.push_binding_count}",
            "Use .cf overview csv for details.",
        ]
    )


def _format_csv(summary: OverviewSummary) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("group_id", "filter_enabled", "push_groups"))
    for row in summary.rows:
        writer.writerow(
            (
                row.group_id,
                "true" if row.filter_enabled else "false",
                ";".join(row.push_groups),
            )
        )
    return output.getvalue().rstrip("\n")
