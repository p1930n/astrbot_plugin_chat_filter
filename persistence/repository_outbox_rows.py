from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..domain.models import ViolationOutboxJob


OUTBOX_ACTIVE_STATUSES = ("pending", "processing")
OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_PROCESSING = "processing"
OUTBOX_STATUS_DONE = "done"
OUTBOX_STATUS_FAILED = "failed"


def outbox_job_from_row(
    row: sqlite3.Row | tuple[object, ...],
    status: str,
) -> ViolationOutboxJob:
    return ViolationOutboxJob(
        job_id=int(row[0]),
        idempotency_key=str(row[1]),
        priority=int(row[2]),
        status=status,  # type: ignore[arg-type]
        platform=str(row[4]),
        group_id=str(row[5]),
        user_id=str(row[6]),
        message_text=str(row[7]),
        matched_word=str(row[8]) if row[8] is not None else None,
        message_id=str(row[9]),
        sender_role=str(row[10]),
        sender_display_name=str(row[11]),
        group_display_name=str(row[12]),
        violation_id=int(row[13]) if row[13] is not None else None,
        attempt_count=int(row[14]),
        max_attempts=int(row[15]),
        error_code=str(row[16]),
    )


def utc_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(seconds, 0))).isoformat()
