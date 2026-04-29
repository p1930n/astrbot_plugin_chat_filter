from __future__ import annotations

import csv
import re
from datetime import datetime
from io import StringIO

from ..domain.models import ViolationReportRecord


MAX_QQ_GROUP_ID_LENGTH = 20
MIN_REPORT_DAYS = 1
MAX_REPORT_DAYS = 366
REPORT_FILENAME_PREFIX = "chat-filter-report"
REPORT_FILE_EXTENSION = ".tsv"
DISPLAY_TEXT_MAX_LENGTH = 300


def format_tsv_report(
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
                mask_user_id(record.user_id),
                clean_cell(record.sender_display_name_snapshot),
                clean_cell(record.matched_keyword),
                clean_cell(record.matched_content),
                record.action_mute_status,
                record.action_recall_status,
                record.action_forward_status,
            ]
        )
    return buffer.getvalue()


def report_file_name(
    platform: str,
    group_id: str,
    generated_at: datetime,
) -> str:
    safe_platform = safe_file_component(platform)
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    return (
        f"{REPORT_FILENAME_PREFIX}-{safe_platform}-{group_id}-{timestamp}"
        f"{REPORT_FILE_EXTENSION}"
    )


def safe_file_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "unknown"


def mask_user_id(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) <= 4:
        return "***"
    return f"{cleaned[:3]}***{cleaned[-3:]}"


def clean_cell(value: str) -> str:
    cleaned = " ".join(value.replace("\x00", "").strip().split())
    if len(cleaned) <= DISPLAY_TEXT_MAX_LENGTH:
        return cleaned
    return cleaned[: DISPLAY_TEXT_MAX_LENGTH - 3] + "..."


def parse_report_days(value: str, *, default: int) -> int | None:
    raw_value = value.strip()
    if not raw_value:
        return clamp_report_days(default)
    try:
        parsed = int(raw_value, 10)
    except ValueError:
        return None
    return clamp_report_days(parsed)


def clamp_report_days(value: int) -> int | None:
    if value < MIN_REPORT_DAYS or value > MAX_REPORT_DAYS:
        return None
    return value


def is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH
