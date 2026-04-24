from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import GroupMutePolicy, GroupPolicy, PushBinding, RuntimeState, ViolationEvent
from .settings import normalize_words


STATE_FILENAME = "state.json"
DATABASE_FILENAME = "chat_filter.db"
GLOBAL_ENABLED_KEY = "global_enabled"


class ChatFilterRepository:
    def __init__(self, root_path: str, *, max_word_count: int, max_word_length: int) -> None:
        self._root = Path(root_path)
        self._state_path = self._root / STATE_FILENAME
        self._database_path = self._root / DATABASE_FILENAME
        self._max_word_count = max_word_count
        self._max_word_length = max_word_length

    def load(self) -> RuntimeState:
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
            self._migrate_json_state_if_needed(connection)
            return self._load_from_database(connection)

    def save(self, state: RuntimeState) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
            self._save_to_database(connection, state)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        _restrict_owner_access(self._database_path)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
                key TEXT PRIMARY KEY,
                bool_value INTEGER NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_policies (
                group_key TEXT PRIMARY KEY,
                enabled INTEGER NULL,
                inherit_global INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_words (
                group_key TEXT NOT NULL,
                word TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (group_key, word),
                FOREIGN KEY (group_key)
                    REFERENCES group_policies(group_key)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS group_push_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                listening_group_id TEXT NOT NULL,
                push_group_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (platform, listening_group_id, push_group_id)
            );

            CREATE INDEX IF NOT EXISTS idx_group_push_bindings_push_group
            ON group_push_bindings (platform, push_group_id);

            CREATE TABLE IF NOT EXISTS group_report_policies (
                platform TEXT NOT NULL,
                listening_group_id TEXT NOT NULL,
                interval_value INTEGER NOT NULL,
                interval_unit TEXT NOT NULL,
                next_run_at TEXT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, listening_group_id)
            );

            CREATE TABLE IF NOT EXISTS group_mute_policies (
                platform TEXT NOT NULL,
                group_id TEXT NOT NULL,
                mute_duration_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, group_id)
            );

            CREATE TABLE IF NOT EXISTS violation_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                listening_group_id TEXT NOT NULL,
                push_group_id TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                file_name TEXT NOT NULL DEFAULT '',
                send_status TEXT NOT NULL,
                error_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                sent_at TEXT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_violation_batches_window
            ON violation_batches (
                platform,
                listening_group_id,
                push_group_id,
                window_start,
                window_end
            );

            CREATE INDEX IF NOT EXISTS idx_violation_batches_send_status
            ON violation_batches (send_status, created_at);

            CREATE TABLE IF NOT EXISTS violation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                sender_display_name_snapshot TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL DEFAULT '',
                matched_keyword TEXT NOT NULL,
                matched_content TEXT NOT NULL,
                raw_message_digest TEXT NOT NULL,
                action_mute_status TEXT NOT NULL,
                action_recall_status TEXT NOT NULL,
                action_forward_status TEXT NOT NULL,
                file_batch_id INTEGER NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (file_batch_id)
                    REFERENCES violation_batches(id)
                    ON DELETE SET NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_violation_events_message
            ON violation_events (platform, group_id, message_id)
            WHERE message_id <> '';

            CREATE INDEX IF NOT EXISTS idx_violation_events_group_time
            ON violation_events (platform, group_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_violation_events_file_batch
            ON violation_events (file_batch_id);
            """
        )

    def _migrate_json_state_if_needed(self, connection: sqlite3.Connection) -> None:
        if not self._state_path.exists() or self._has_database_state(connection):
            return

        with self._state_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            return

        state = RuntimeState(
            global_enabled=_optional_bool(payload.get("global_enabled")),
            groups=self._load_groups(payload.get("groups")),
        )
        self._save_to_database(connection, state)

    def _has_database_state(self, connection: sqlite3.Connection) -> bool:
        cursor = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM runtime_state
                UNION ALL
                SELECT 1 FROM group_policies
                UNION ALL
                SELECT 1 FROM group_words
            )
            """
        )
        return bool(cursor.fetchone()[0])

    def _load_from_database(self, connection: sqlite3.Connection) -> RuntimeState:
        cursor = connection.execute(
            "SELECT bool_value FROM runtime_state WHERE key = ?",
            (GLOBAL_ENABLED_KEY,),
        )
        row = cursor.fetchone()
        global_enabled = _optional_bool_from_int(row[0]) if row else None

        groups: dict[str, GroupPolicy] = {}
        for group_key, enabled, inherit_global in connection.execute(
            """
            SELECT group_key, enabled, inherit_global
            FROM group_policies
            ORDER BY group_key
            """
        ):
            groups[group_key] = GroupPolicy(
                enabled=_optional_bool_from_int(enabled),
                inherit_global=bool(inherit_global),
            )

        raw_words: dict[str, list[str]] = {}
        for group_key, word in connection.execute(
            """
            SELECT group_key, word
            FROM group_words
            ORDER BY group_key, position, word
            """
        ):
            raw_words.setdefault(group_key, []).append(word)

        for group_key, words in raw_words.items():
            policy = groups.get(group_key, GroupPolicy())
            groups[group_key] = GroupPolicy(
                enabled=policy.enabled,
                inherit_global=policy.inherit_global,
                custom_words=normalize_words(
                    words,
                    max_count=self._max_word_count,
                    max_length=self._max_word_length,
                ),
            )

        return RuntimeState(global_enabled=global_enabled, groups=groups)

    def _save_to_database(self, connection: sqlite3.Connection, state: RuntimeState) -> None:
        now = _utc_now()
        with connection:
            connection.execute("DELETE FROM group_words")
            connection.execute("DELETE FROM group_policies")
            connection.execute("DELETE FROM runtime_state")
            connection.execute(
                """
                INSERT INTO runtime_state (key, bool_value, updated_at)
                VALUES (?, ?, ?)
                """,
                (GLOBAL_ENABLED_KEY, _optional_bool_to_int(state.global_enabled), now),
            )

            for group_key, policy in sorted(state.groups.items()):
                connection.execute(
                    """
                    INSERT INTO group_policies (
                        group_key,
                        enabled,
                        inherit_global,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        group_key,
                        _optional_bool_to_int(policy.enabled),
                        int(policy.inherit_global),
                        now,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO group_words (group_key, word, position, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (group_key, word, position, now)
                        for position, word in enumerate(policy.custom_words)
                    ],
                )

    def add_push_binding(
        self,
        *,
        platform: str,
        listening_group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        now = _utc_now()
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
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
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
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

    def set_group_mute_duration(
        self,
        *,
        platform: str,
        group_id: str,
        mute_duration_seconds: int,
        updated_by: str,
    ) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        now = _utc_now()
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
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
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
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

    def record_violation(self, violation: ViolationEvent) -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        now = _utc_now()
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
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

    def _load_groups(self, value: object) -> dict[str, GroupPolicy]:
        if not isinstance(value, dict):
            return {}
        groups: dict[str, GroupPolicy] = {}
        for key, raw_policy in value.items():
            if not isinstance(key, str) or not isinstance(raw_policy, dict):
                continue
            groups[key] = GroupPolicy(
                enabled=_optional_bool(raw_policy.get("enabled")),
                inherit_global=_bool_or_default(raw_policy.get("inherit_global"), True),
                custom_words=normalize_words(
                    raw_policy.get("custom_words"),
                    max_count=self._max_word_count,
                    max_length=self._max_word_length,
                ),
            )
        return groups


def default_data_root() -> str:
    return os.path.join(os.getcwd(), "data", "astrbot_plugin_chat_filter")


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _bool_or_default(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _optional_bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_bool_from_int(value: Any) -> bool | None:
    if value is None:
        return None
    if value == 1:
        return True
    if value == 0:
        return False
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _restrict_owner_access(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)
