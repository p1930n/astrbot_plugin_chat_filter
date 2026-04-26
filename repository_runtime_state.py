from __future__ import annotations

import json
import sqlite3

from .models import GroupPolicy, RuntimeState
from .repository_base import (
    GLOBAL_ENABLED_KEY,
    bool_or_default,
    optional_bool,
    optional_bool_from_int,
    optional_bool_to_int,
    utc_now,
)
from .settings import normalize_words


class RuntimeStateRepositoryMixin:
    def load(self) -> RuntimeState:
        with self._connection() as connection:
            self._migrate_json_state_if_needed(connection)
            return self._load_from_database(connection)

    def save(self, state: RuntimeState) -> None:
        with self._connection() as connection:
            self._save_to_database(connection, state)

    def _migrate_json_state_if_needed(self, connection: sqlite3.Connection) -> None:
        if not self._state_path.exists() or self._has_database_state(connection):
            return

        with self._state_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            return

        state = RuntimeState(
            global_enabled=optional_bool(payload.get("global_enabled")),
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
        global_enabled = optional_bool_from_int(row[0]) if row else None

        groups: dict[str, GroupPolicy] = {}
        for (
            group_key,
            enabled,
            inherit_global,
            admin_exempt_enabled,
        ) in connection.execute(
            """
            SELECT group_key, enabled, inherit_global, admin_exempt_enabled
            FROM group_policies
            ORDER BY group_key
            """
        ):
            parsed_admin_exempt_enabled = optional_bool_from_int(admin_exempt_enabled)
            groups[group_key] = GroupPolicy(
                enabled=optional_bool_from_int(enabled),
                inherit_global=bool(inherit_global),
                admin_exempt_enabled=(
                    True
                    if parsed_admin_exempt_enabled is None
                    else parsed_admin_exempt_enabled
                ),
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
                admin_exempt_enabled=policy.admin_exempt_enabled,
                custom_words=normalize_words(
                    words,
                    max_count=self._max_word_count,
                    max_length=self._max_word_length,
                ),
            )

        return RuntimeState(global_enabled=global_enabled, groups=groups)

    def _save_to_database(self, connection: sqlite3.Connection, state: RuntimeState) -> None:
        now = utc_now()
        with connection:
            connection.execute("DELETE FROM group_words")
            connection.execute("DELETE FROM group_policies")
            connection.execute("DELETE FROM runtime_state")
            connection.execute(
                """
                INSERT INTO runtime_state (key, bool_value, updated_at)
                VALUES (?, ?, ?)
                """,
                (GLOBAL_ENABLED_KEY, optional_bool_to_int(state.global_enabled), now),
            )

            for group_key, policy in sorted(state.groups.items()):
                connection.execute(
                    """
                    INSERT INTO group_policies (
                        group_key,
                        enabled,
                        inherit_global,
                        admin_exempt_enabled,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        group_key,
                        optional_bool_to_int(policy.enabled),
                        int(policy.inherit_global),
                        int(policy.admin_exempt_enabled),
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
                enabled=optional_bool(raw_policy.get("enabled")),
                inherit_global=bool_or_default(raw_policy.get("inherit_global"), True),
                admin_exempt_enabled=bool_or_default(
                    raw_policy.get("admin_exempt_enabled"),
                    True,
                ),
                custom_words=normalize_words(
                    raw_policy.get("custom_words"),
                    max_count=self._max_word_count,
                    max_length=self._max_word_length,
                ),
            )
        return groups
