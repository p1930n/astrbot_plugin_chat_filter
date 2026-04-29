from __future__ import annotations

from ..domain.models import GroupActionPolicy
from .repository_base import utc_now


ACTION_POLICY_MODE_AUDIT = "audit"
ACTION_POLICY_MODE_STRICT = "strict"
ACTION_POLICY_MODES = frozenset((ACTION_POLICY_MODE_AUDIT, ACTION_POLICY_MODE_STRICT))


class ActionPolicyRepositoryMixin:
    def set_group_action_toggle(
        self,
        *,
        platform: str,
        group_id: str,
        action: str,
        enabled: bool,
        updated_by: str,
    ) -> GroupActionPolicy:
        column = _toggle_column(action)
        if column is None:
            raise ValueError(f"unsupported action policy toggle: {action}")

        now = utc_now()
        with self._connection() as connection:
            with connection:
                self._ensure_group_action_policy(
                    connection,
                    platform=platform,
                    group_id=group_id,
                    updated_by=updated_by,
                    now=now,
                )
                connection.execute(
                    f"""
                    UPDATE group_action_policies
                    SET {column} = ?, updated_by = ?, updated_at = ?
                    WHERE platform = ? AND group_id = ?
                    """,
                    (int(enabled), updated_by, now, platform, group_id),
                )
                return self._group_action_policy_for_group(
                    connection,
                    platform=platform,
                    group_id=group_id,
                )

    def set_group_action_mode(
        self,
        *,
        platform: str,
        group_id: str,
        mode: str,
        updated_by: str,
    ) -> GroupActionPolicy:
        if mode not in ACTION_POLICY_MODES:
            raise ValueError(f"unsupported action policy mode: {mode}")

        now = utc_now()
        with self._connection() as connection:
            with connection:
                self._ensure_group_action_policy(
                    connection,
                    platform=platform,
                    group_id=group_id,
                    updated_by=updated_by,
                    now=now,
                )
                connection.execute(
                    """
                    UPDATE group_action_policies
                    SET mode = ?, updated_by = ?, updated_at = ?
                    WHERE platform = ? AND group_id = ?
                    """,
                    (mode, updated_by, now, platform, group_id),
                )
                return self._group_action_policy_for_group(
                    connection,
                    platform=platform,
                    group_id=group_id,
                )

    def get_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> GroupActionPolicy | None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                SELECT
                    platform,
                    group_id,
                    mute_enabled,
                    recall_enabled,
                    forward_enabled,
                    mode
                FROM group_action_policies
                WHERE platform = ? AND group_id = ?
                """,
                (platform, group_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _policy_from_row(row)

    def list_group_action_policies(self, *, platform: str) -> list[GroupActionPolicy]:
        with self._connection() as connection:
            return [
                _policy_from_row(row)
                for row in connection.execute(
                    """
                    SELECT
                        platform,
                        group_id,
                        mute_enabled,
                        recall_enabled,
                        forward_enabled,
                        mode
                    FROM group_action_policies
                    WHERE platform = ?
                    ORDER BY group_id
                    """,
                    (platform,),
                )
            ]

    def _ensure_group_action_policy(
        self,
        connection,
        *,
        platform: str,
        group_id: str,
        updated_by: str,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO group_action_policies (
                platform,
                group_id,
                mute_enabled,
                recall_enabled,
                forward_enabled,
                mode,
                updated_by,
                created_at,
                updated_at
            )
            VALUES (?, ?, 1, 1, 1, 'strict', ?, ?, ?)
            """,
            (platform, group_id, updated_by, now, now),
        )

    def _group_action_policy_for_group(
        self,
        connection,
        *,
        platform: str,
        group_id: str,
    ) -> GroupActionPolicy:
        row = connection.execute(
            """
            SELECT
                platform,
                group_id,
                mute_enabled,
                recall_enabled,
                forward_enabled,
                mode
            FROM group_action_policies
            WHERE platform = ? AND group_id = ?
            """,
            (platform, group_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("group action policy row was not created")
        return _policy_from_row(row)


def _toggle_column(action: str) -> str | None:
    return {
        "mute": "mute_enabled",
        "recall": "recall_enabled",
        "forward": "forward_enabled",
    }.get(action)


def _policy_from_row(row: object) -> GroupActionPolicy:
    return GroupActionPolicy(
        platform=row[0],
        group_id=row[1],
        mute_enabled=bool(row[2]),
        recall_enabled=bool(row[3]),
        forward_enabled=bool(row[4]),
        mode=row[5],
    )
