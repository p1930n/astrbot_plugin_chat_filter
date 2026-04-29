from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from ..domain.models import PlatformEventSnapshot
from ..persistence.repository import ChatFilterRepository
from .report_formatting import (
    format_tsv_report as _format_tsv_report,
    is_valid_qq_group_id as _is_valid_qq_group_id,
    parse_report_days as _parse_report_days,
    report_file_name as _report_file_name,
)


MAX_REPORT_RECORDS = 5000
REPORTS_DIRECTORY_NAME = "reports"


class ReportLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...


@dataclass(frozen=True, slots=True)
class GeneratedReport:
    file_name: str
    record_count: int
    window_start: str
    window_end: str


class ViolationReportService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        *,
        data_root: str,
        default_report_days: int,
        logger: ReportLogger,
    ) -> None:
        self._repository = repository
        self._data_root = Path(data_root)
        self._default_report_days = default_report_days
        self._logger = logger

    async def generate_dry_run(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        listening_group_id: str,
        days: str,
    ) -> str:
        group_id = listening_group_id.strip() or snapshot.group_id
        if not _is_valid_qq_group_id(group_id):
            return (
                "Usage: .cf report-dry-run [group] [days] "
                "or /cf report-dry-run [group] [days]"
            )
        if not snapshot.platform:
            return "Chat Filter report dry-run failed: platform is unavailable."

        report_days = _parse_report_days(
            days,
            default=self._default_report_days,
        )
        if report_days is None:
            return "Invalid report days."

        try:
            report = await asyncio.to_thread(
                self._generate_report,
                platform=snapshot.platform,
                group_id=group_id,
                days=report_days,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter report dry-run failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter report dry-run failed."

        return (
            "Chat Filter report dry-run generated: "
            f"records={report.record_count}, file={report.file_name}, "
            f"window={report.window_start}..{report.window_end}."
        )

    def _generate_report(
        self,
        *,
        platform: str,
        group_id: str,
        days: int,
    ) -> GeneratedReport:
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=days)
        records = self._repository.list_unbatched_violation_report_records(
            platform=platform,
            group_id=group_id,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            limit=MAX_REPORT_RECORDS,
        )

        report_dir = self._data_root / REPORTS_DIRECTORY_NAME
        report_dir.mkdir(parents=True, exist_ok=True)
        file_name = _report_file_name(platform, group_id, window_end)
        report_path = report_dir / file_name
        content = _format_tsv_report(
            platform=platform,
            group_id=group_id,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            records=records,
        )
        report_path.write_text(content, encoding="utf-8")
        return GeneratedReport(
            file_name=file_name,
            record_count=len(records),
            window_start=window_start.isoformat(timespec="seconds"),
            window_end=window_end.isoformat(timespec="seconds"),
        )
