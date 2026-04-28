from __future__ import annotations

import sqlite3
from typing import Literal

from ..domain.models import ViolationEvent, ViolationPushDelivery, ViolationReportRecord
from .repository_base import utc_now


ViolationActionName = Literal["mute", "recall", "forward"]
_VIOLATION_ACTION_STATUS_COLUMNS: dict[ViolationActionName, str] = {
    "mute": "action_mute_status",
    "recall": "action_recall_status",
    "forward": "action_forward_status",
}


class ViolationRepositoryMixin:
    def record_violation(self, violation: ViolationEvent) -> int:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO violation_events (
                        platform,
                        group_id,
                        user_id,
                        sender_display_name_snapshot,
                        message_id,
                        matched_keyword,
                        matched_content,
                        raw_message_digest,
                        action_mute_status,
                        action_recall_status,
                        action_forward_status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        violation.platform,
                        violation.group_id,
                        violation.user_id,
                        violation.sender_display_name_snapshot,
                        violation.message_id,
                        violation.matched_keyword,
                        violation.matched_content,
                        violation.raw_message_digest,
                        violation.action_mute_status,
                        violation.action_recall_status,
                        violation.action_forward_status,
                        now,
                        now,
                    ),
                )
                if cursor.lastrowid:
                    return int(cursor.lastrowid)
                return self._find_violation_id(connection, violation)

    def update_violation_action_status(
        self,
        *,
        violation_id: int,
        action: ViolationActionName,
        status: str,
    ) -> None:
        column = _VIOLATION_ACTION_STATUS_COLUMNS.get(action)
        if column is None:
            raise ValueError(f"unsupported violation action: {action}")

        now = utc_now()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    f"""
                    UPDATE violation_events
                    SET {column} = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, violation_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "violation action status update affected "
                        f"{cursor.rowcount} rows"
                    )

    def upsert_violation_push_delivery(
        self,
        delivery: ViolationPushDelivery,
    ) -> int:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO violation_push_deliveries (
                        violation_id,
                        platform,
                        listening_group_id,
                        push_group_id,
                        action_status,
                        error_code,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (violation_id, platform, push_group_id)
                    DO UPDATE SET
                        listening_group_id = excluded.listening_group_id,
                        action_status = excluded.action_status,
                        error_code = excluded.error_code,
                        updated_at = excluded.updated_at
                    """,
                    (
                        delivery.violation_id,
                        delivery.platform,
                        delivery.listening_group_id,
                        delivery.push_group_id,
                        delivery.action_status,
                        delivery.error_code,
                        now,
                        now,
                    ),
                )
                return self._find_violation_push_delivery_id(connection, delivery)

    def list_violation_push_deliveries(
        self,
        *,
        violation_id: int,
    ) -> list[ViolationPushDelivery]:
        with self._connection() as connection:
            return [
                ViolationPushDelivery(
                    violation_id=int(row[0]),
                    platform=row[1],
                    listening_group_id=row[2],
                    push_group_id=row[3],
                    action_status=row[4],
                    error_code=row[5],
                )
                for row in connection.execute(
                    """
                    SELECT
                        violation_id,
                        platform,
                        listening_group_id,
                        push_group_id,
                        action_status,
                        error_code
                    FROM violation_push_deliveries
                    WHERE violation_id = ?
                    ORDER BY push_group_id
                    """,
                    (violation_id,),
                )
            ]

    def list_unbatched_violation_report_records(
        self,
        *,
        platform: str,
        group_id: str,
        window_start: str,
        window_end: str,
        limit: int,
    ) -> list[ViolationReportRecord]:
        with self._connection() as connection:
            return [
                ViolationReportRecord(
                    violation_id=int(row[0]),
                    created_at=row[1],
                    platform=row[2],
                    group_id=row[3],
                    user_id=row[4],
                    sender_display_name_snapshot=row[5],
                    matched_keyword=row[6],
                    matched_content=row[7],
                    action_mute_status=row[8],
                    action_recall_status=row[9],
                    action_forward_status=row[10],
                )
                for row in connection.execute(
                    """
                    SELECT
                        id,
                        created_at,
                        platform,
                        group_id,
                        user_id,
                        sender_display_name_snapshot,
                        matched_keyword,
                        matched_content,
                        action_mute_status,
                        action_recall_status,
                        action_forward_status
                    FROM violation_events
                    WHERE platform = ?
                        AND group_id = ?
                        AND created_at >= ?
                        AND created_at < ?
                        AND file_batch_id IS NULL
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (platform, group_id, window_start, window_end, limit),
                )
            ]

    def _find_violation_id(
        self,
        connection: sqlite3.Connection,
        violation: ViolationEvent,
    ) -> int:
        if violation.message_id:
            cursor = connection.execute(
                """
                SELECT id
                FROM violation_events
                WHERE platform = ? AND group_id = ? AND message_id = ?
                """,
                (violation.platform, violation.group_id, violation.message_id),
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

        cursor = connection.execute(
            """
            SELECT id
            FROM violation_events
            WHERE platform = ?
                AND group_id = ?
                AND raw_message_digest = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (violation.platform, violation.group_id, violation.raw_message_digest),
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
        raise RuntimeError("violation insert did not return an id")

    def _find_violation_push_delivery_id(
        self,
        connection: sqlite3.Connection,
        delivery: ViolationPushDelivery,
    ) -> int:
        cursor = connection.execute(
            """
            SELECT id
            FROM violation_push_deliveries
            WHERE violation_id = ? AND platform = ? AND push_group_id = ?
            """,
            (
                delivery.violation_id,
                delivery.platform,
                delivery.push_group_id,
            ),
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
        raise RuntimeError("violation push delivery upsert did not return an id")
