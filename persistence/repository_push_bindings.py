from __future__ import annotations

import sqlite3

from ..domain.models import PushBinding
from .repository_base import utc_now


class PushBindingRepositoryMixin:
    def add_push_binding(
        self,
        *,
        platform: str,
        listening_group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> int:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO group_push_bindings (
                        platform,
                        listening_group_id,
                        push_group_id,
                        enabled,
                        created_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT (platform, listening_group_id, push_group_id)
                    DO UPDATE SET
                        enabled = 1,
                        created_by = excluded.created_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        listening_group_id,
                        push_group_id,
                        created_by,
                        now,
                        now,
                    ),
                )
                return self.count_push_bindings(
                    connection,
                    platform=platform,
                    listening_group_id=listening_group_id,
                )

    def list_push_bindings(self, *, platform: str) -> list[PushBinding]:
        with self._connection() as connection:
            return [
                PushBinding(
                    platform=row[0],
                    listening_group_id=row[1],
                    push_group_id=row[2],
                    enabled=bool(row[3]),
                )
                for row in connection.execute(
                    """
                    SELECT platform, listening_group_id, push_group_id, enabled
                    FROM group_push_bindings
                    WHERE platform = ? AND enabled = 1
                    ORDER BY listening_group_id, push_group_id
                    """,
                    (platform,),
                )
            ]

    def list_enabled_push_bindings_for_group(
        self,
        *,
        platform: str,
        listening_group_id: str,
    ) -> list[PushBinding]:
        with self._connection() as connection:
            return [
                PushBinding(
                    platform=row[0],
                    listening_group_id=row[1],
                    push_group_id=row[2],
                    enabled=bool(row[3]),
                )
                for row in connection.execute(
                    """
                    SELECT platform, listening_group_id, push_group_id, enabled
                    FROM group_push_bindings
                    WHERE platform = ?
                        AND listening_group_id = ?
                        AND enabled = 1
                    ORDER BY push_group_id
                    """,
                    (platform, listening_group_id),
                )
            ]

    def count_push_bindings(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        listening_group_id: str,
    ) -> int:
        cursor = connection.execute(
            """
            SELECT COUNT(*)
            FROM group_push_bindings
            WHERE platform = ? AND listening_group_id = ? AND enabled = 1
            """,
            (platform, listening_group_id),
        )
        return int(cursor.fetchone()[0])
