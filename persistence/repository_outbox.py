from __future__ import annotations

import sqlite3

from ..domain.models import (
    ViolationOutboxEnqueueResult,
    ViolationOutboxEntry,
    ViolationOutboxJob,
)
from .repository_base import utc_now
from .repository_outbox_rows import (
    OUTBOX_ACTIVE_STATUSES,
    OUTBOX_STATUS_DONE,
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSING,
    outbox_job_from_row,
    utc_after,
)


class OutboxRepositoryMixin:
    def enqueue_violation_outbox(
        self,
        entry: ViolationOutboxEntry,
        *,
        max_active_jobs: int,
    ) -> ViolationOutboxEnqueueResult:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                existing_id = self._find_outbox_id_by_key(
                    connection,
                    entry.idempotency_key,
                )
                if existing_id is not None:
                    return ViolationOutboxEnqueueResult(
                        status="duplicate",
                        job_id=existing_id,
                    )

                active_count = self._count_active_outbox_jobs(connection)
                if active_count >= max_active_jobs:
                    return ViolationOutboxEnqueueResult(status="backpressure")

                try:
                    cursor = connection.execute(
                        """
                        INSERT INTO violation_outbox (
                            idempotency_key,
                            priority,
                            status,
                            platform,
                            group_id,
                            user_id,
                            message_id,
                            sender_role,
                            sender_display_name,
                            group_display_name,
                            message_text,
                            matched_word,
                            attempt_count,
                            max_attempts,
                            available_at,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                        """,
                        (
                            entry.idempotency_key,
                            entry.priority,
                            OUTBOX_STATUS_PENDING,
                            entry.platform,
                            entry.group_id,
                            entry.user_id,
                            entry.message_id,
                            entry.sender_role,
                            entry.sender_display_name,
                            entry.group_display_name,
                            entry.message_text,
                            entry.matched_word,
                            entry.max_attempts,
                            now,
                            now,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError:
                    existing_id = self._find_outbox_id_by_key(
                        connection,
                        entry.idempotency_key,
                    )
                    return ViolationOutboxEnqueueResult(
                        status="duplicate",
                        job_id=existing_id,
                    )
                return ViolationOutboxEnqueueResult(
                    status="enqueued",
                    job_id=int(cursor.lastrowid),
                )

    def claim_next_violation_outbox_job(
        self,
        *,
        worker_id: str,
    ) -> ViolationOutboxJob | None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT
                        id,
                        idempotency_key,
                        priority,
                        status,
                        platform,
                        group_id,
                        user_id,
                        message_text,
                        matched_word,
                        message_id,
                        sender_role,
                        sender_display_name,
                        group_display_name,
                        violation_id,
                        attempt_count,
                        max_attempts,
                        error_code
                    FROM violation_outbox
                    WHERE status = ?
                        AND available_at <= ?
                        AND attempt_count < max_attempts
                    ORDER BY priority DESC, created_at ASC, id ASC
                    LIMIT 1
                    """,
                    (OUTBOX_STATUS_PENDING, now),
                ).fetchone()
                if row is None:
                    return None

                cursor = connection.execute(
                    """
                    UPDATE violation_outbox
                    SET status = ?,
                        locked_by = ?,
                        locked_at = ?,
                        updated_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        OUTBOX_STATUS_PROCESSING,
                        worker_id,
                        now,
                        now,
                        int(row[0]),
                        OUTBOX_STATUS_PENDING,
                    ),
                )
                if cursor.rowcount != 1:
                    return None
                return outbox_job_from_row(row, OUTBOX_STATUS_PROCESSING)

    def set_violation_outbox_violation_id(
        self,
        *,
        job_id: int,
        violation_id: int,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE violation_outbox
                    SET violation_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (violation_id, now, job_id),
                )

    def mark_violation_outbox_done(
        self,
        *,
        job_id: int,
        violation_id: int | None,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE violation_outbox
                    SET status = ?,
                        violation_id = COALESCE(?, violation_id),
                        error_code = '',
                        locked_by = '',
                        locked_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (OUTBOX_STATUS_DONE, violation_id, now, job_id),
                )

    def retry_violation_outbox_job(
        self,
        *,
        job_id: int,
        error_code: str,
        retry_after_seconds: int,
    ) -> str:
        now = utc_now()
        available_at = utc_after(retry_after_seconds)
        with self._connection() as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT attempt_count, max_attempts
                    FROM violation_outbox
                    WHERE id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError(f"violation outbox job not found: {job_id}")
                next_attempt_count = int(row[0]) + 1
                max_attempts = int(row[1])
                next_status = (
                    OUTBOX_STATUS_FAILED
                    if next_attempt_count >= max_attempts
                    else OUTBOX_STATUS_PENDING
                )
                connection.execute(
                    """
                    UPDATE violation_outbox
                    SET status = ?,
                        attempt_count = ?,
                        error_code = ?,
                        locked_by = '',
                        locked_at = NULL,
                        available_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        next_status,
                        next_attempt_count,
                        error_code,
                        available_at,
                        now,
                        job_id,
                    ),
                )
                return next_status

    def defer_violation_outbox_job(
        self,
        *,
        job_id: int,
        error_code: str,
        retry_after_seconds: int,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE violation_outbox
                    SET status = ?,
                        error_code = ?,
                        locked_by = '',
                        locked_at = NULL,
                        available_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        OUTBOX_STATUS_PENDING,
                        error_code,
                        utc_after(retry_after_seconds),
                        now,
                        job_id,
                    ),
                )

    def recover_processing_violation_outbox_jobs(self) -> int:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE violation_outbox
                    SET status = ?,
                        locked_by = '',
                        locked_at = NULL,
                        available_at = ?,
                        updated_at = ?
                    WHERE status = ?
                    """,
                    (
                        OUTBOX_STATUS_PENDING,
                        now,
                        now,
                        OUTBOX_STATUS_PROCESSING,
                    ),
                )
                return int(cursor.rowcount)

    def count_active_violation_outbox_jobs(self) -> int:
        with self._connection() as connection:
            return self._count_active_outbox_jobs(connection)

    def get_violation_outbox_job(self, job_id: int) -> ViolationOutboxJob | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    idempotency_key,
                    priority,
                    status,
                    platform,
                    group_id,
                    user_id,
                    message_text,
                    matched_word,
                    message_id,
                    sender_role,
                    sender_display_name,
                    group_display_name,
                    violation_id,
                    attempt_count,
                    max_attempts,
                    error_code
                FROM violation_outbox
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return outbox_job_from_row(row, str(row[3]))

    def _count_active_outbox_jobs(self, connection: sqlite3.Connection) -> int:
        placeholders = ", ".join("?" for _ in OUTBOX_ACTIVE_STATUSES)
        row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM violation_outbox
            WHERE status IN ({placeholders})
            """,
            OUTBOX_ACTIVE_STATUSES,
        ).fetchone()
        return int(row[0]) if row else 0

    def _find_outbox_id_by_key(
        self,
        connection: sqlite3.Connection,
        idempotency_key: str,
    ) -> int | None:
        row = connection.execute(
            """
            SELECT id
            FROM violation_outbox
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])
