from __future__ import annotations

import asyncio
import csv
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Protocol

from ..domain.models import PlatformEventSnapshot, ViolationReportRecord
from ..persistence.repository import ChatFilterRepository


MAX_QQ_GROUP_ID_LENGTH = 20
MIN_REPORT_DAYS = 1
MAX_REPORT_DAYS = 366
MAX_REPORT_RECORDS = 5000
REPORTS_DIRECTORY_NAME = "reports"
REPORT_FILENAME_PREFIX = "chat-filter-report"
REPORT_FILE_EXTENSION = ".tsv"
DISPLAY_TEXT_MAX_LENGTH = 300


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


def _format_tsv_report(
    *,
    platform: str,
    group_id: str,
    window_start: str,
    window_end: str,
    records: list[ViolationReportRecord],
) -> str:
    buffer = StringIO()
    buffer.write(f"# platform\t{platform}\n")
    buffer.write(f"# listening_group\t{group_id}\n")
    buffer.write(f"# window_start\t{window_start}\n")
    buffer.write(f"# window_end\t{window_end}\n")
    buffer.write(f"# record_count\t{len(records)}\n")

    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(
        [
            "created_at",
            "group_id",
            "user_id_masked",
            "sender_name",
            "matched_keyword",
            "matched_content",
            "mute_status",
            "recall_status",
            "forward_status",
        ]
    )
    for record in records:
        writer.writerow(
            [
                record.created_at,
                record.group_id,
                _mask_user_id(record.user_id),
                _clean_cell(record.sender_display_name_snapshot),
                _clean_cell(record.matched_keyword),
                _clean_cell(record.matched_content),
                record.action_mute_status,
                record.action_recall_status,
                record.action_forward_status,
            ]
        )
    return buffer.getvalue()


def _report_file_name(
    platform: str,
    group_id: str,
    generated_at: datetime,
) -> str:
    safe_platform = _safe_file_component(platform)
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    return (
        f"{REPORT_FILENAME_PREFIX}-{safe_platform}-{group_id}-{timestamp}"
        f"{REPORT_FILE_EXTENSION}"
    )


def _safe_file_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "unknown"


def _mask_user_id(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) <= 4:
        return "***"
    return f"{cleaned[:3]}***{cleaned[-3:]}"


def _clean_cell(value: str) -> str:
    cleaned = " ".join(value.replace("\x00", "").strip().split())
    if len(cleaned) <= DISPLAY_TEXT_MAX_LENGTH:
        return cleaned
    return cleaned[: DISPLAY_TEXT_MAX_LENGTH - 3] + "..."


def _parse_report_days(value: str, *, default: int) -> int | None:
    raw_value = value.strip()
    if not raw_value:
        return _clamp_report_days(default)
    try:
        parsed = int(raw_value, 10)
    except ValueError:
        return None
    return _clamp_report_days(parsed)


def _clamp_report_days(value: int) -> int | None:
    if value < MIN_REPORT_DAYS or value > MAX_REPORT_DAYS:
        return None
    return value


def _is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH
