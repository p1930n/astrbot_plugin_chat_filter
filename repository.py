from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import GroupPolicy, RuntimeState
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
