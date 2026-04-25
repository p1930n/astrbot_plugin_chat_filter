from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .models import (
    GroupMuteEscalationPolicy,
    GroupMutePolicy,
    MuteEscalationDecision,
)
from .mute_escalation import next_violation_count, scaled_mute_duration
from .repository_base import utc_now


class MutePolicyRepositoryMixin:
    def set_group_mute_duration(
        self,
        *,
        platform: str,
        group_id: str,
        mute_duration_seconds: int,
        updated_by: str,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO group_mute_policies (
                        platform,
                        group_id,
                        mute_duration_seconds,
                        enabled,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        mute_duration_seconds = excluded.mute_duration_seconds,
                        enabled = 1,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        mute_duration_seconds,
                        updated_by,
                        now,
                        now,
                    ),
                )

    def list_group_mute_policies(self, *, platform: str) -> list[GroupMutePolicy]:
        with self._connection() as connection:
            return [
                GroupMutePolicy(
                    platform=row[0],
                    group_id=row[1],
                    mute_duration_seconds=int(row[2]),
                    enabled=bool(row[3]),
                )
                for row in connection.execute(
                    """
                    SELECT platform, group_id, mute_duration_seconds, enabled
                    FROM group_mute_policies
                    WHERE platform = ? AND enabled = 1
                    ORDER BY group_id
                    """,
                    (platform,),
                )
            ]

    def get_enabled_group_mute_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> GroupMutePolicy | None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                SELECT platform, group_id, mute_duration_seconds, enabled
                FROM group_mute_policies
                WHERE platform = ? AND group_id = ? AND enabled = 1
                """,
                (platform, group_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return GroupMutePolicy(
                platform=row[0],
                group_id=row[1],
                mute_duration_seconds=int(row[2]),
                enabled=bool(row[3]),
            )

    def set_group_mute_escalation_policy(
        self,
        *,
        platform: str,
        group_id: str,
        multiplier: int,
        reset_seconds: int,
        updated_by: str,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO group_mute_escalation_policies (
                        platform,
                        group_id,
                        multiplier,
                        reset_seconds,
                        enabled,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        multiplier = excluded.multiplier,
                        reset_seconds = excluded.reset_seconds,
                        enabled = 1,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        multiplier,
                        reset_seconds,
                        updated_by,
                        now,
                        now,
                    ),
                )

    def list_group_mute_escalation_policies(
        self,
        *,
        platform: str,
    ) -> list[GroupMuteEscalationPolicy]:
        with self._connection() as connection:
            return [
                GroupMuteEscalationPolicy(
                    platform=row[0],
                    group_id=row[1],
                    multiplier=int(row[2]),
                    reset_seconds=int(row[3]),
                    enabled=bool(row[4]),
                )
                for row in connection.execute(
                    """
                    SELECT platform, group_id, multiplier, reset_seconds, enabled
                    FROM group_mute_escalation_policies
                    WHERE platform = ? AND enabled = 1
                    ORDER BY group_id
                    """,
                    (platform,),
                )
            ]

    def calculate_mute_escalation(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        base_duration_seconds: int,
        default_multiplier: int,
        default_reset_seconds: int,
        max_duration_seconds: int,
    ) -> MuteEscalationDecision:
        now_datetime = datetime.now(timezone.utc)
        now = now_datetime.isoformat()
        with self._connection() as connection:
            with connection:
                policy = self._mute_escalation_policy_for_group(
                    connection,
                    platform=platform,
                    group_id=group_id,
                    default_multiplier=default_multiplier,
                    default_reset_seconds=default_reset_seconds,
                )
                if policy is None:
                    return MuteEscalationDecision(
                        duration_seconds=base_duration_seconds,
                        violation_count=1,
                        multiplier=1,
                        reset_seconds=default_reset_seconds,
                    )

                previous_count, previous_at = self._mute_escalation_state_for_user(
                    connection,
                    platform=platform,
                    group_id=group_id,
                    user_id=user_id,
                )
                violation_count = next_violation_count(
                    previous_count=previous_count,
                    previous_at=previous_at,
                    now=now_datetime,
                    reset_seconds=policy.reset_seconds,
                )
                duration = scaled_mute_duration(
                    base_duration_seconds=base_duration_seconds,
                    multiplier=policy.multiplier,
                    violation_count=violation_count,
                    max_duration_seconds=max_duration_seconds,
                )
                connection.execute(
                    """
                    INSERT INTO user_mute_escalation_states (
                        platform,
                        group_id,
                        user_id,
                        violation_count,
                        last_violation_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id, user_id)
                    DO UPDATE SET
                        violation_count = excluded.violation_count,
                        last_violation_at = excluded.last_violation_at,
                        updated_at = excluded.updated_at
                    """,
                    (platform, group_id, user_id, violation_count, now, now),
                )
                return MuteEscalationDecision(
                    duration_seconds=duration,
                    violation_count=violation_count,
                    multiplier=policy.multiplier,
                    reset_seconds=policy.reset_seconds,
                )

    def _mute_escalation_policy_for_group(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        group_id: str,
        default_multiplier: int,
        default_reset_seconds: int,
    ) -> GroupMuteEscalationPolicy | None:
        cursor = connection.execute(
            """
            SELECT platform, group_id, multiplier, reset_seconds, enabled
            FROM group_mute_escalation_policies
            WHERE platform = ? AND group_id = ?
            """,
            (platform, group_id),
        )
        row = cursor.fetchone()
        if not row:
            return GroupMuteEscalationPolicy(
                platform=platform,
                group_id=group_id,
                multiplier=default_multiplier,
                reset_seconds=default_reset_seconds,
                enabled=True,
            )
        if not bool(row[4]):
            return None
        return GroupMuteEscalationPolicy(
            platform=row[0],
            group_id=row[1],
            multiplier=int(row[2]),
            reset_seconds=int(row[3]),
            enabled=True,
        )

    def _mute_escalation_state_for_user(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> tuple[int, datetime | None]:
        cursor = connection.execute(
            """
            SELECT violation_count, last_violation_at
            FROM user_mute_escalation_states
            WHERE platform = ? AND group_id = ? AND user_id = ?
            """,
            (platform, group_id, user_id),
        )
        row = cursor.fetchone()
        if not row:
            return 0, None
        try:
            previous_at = datetime.fromisoformat(row[1])
        except ValueError:
            previous_at = None
        return int(row[0]), previous_at
