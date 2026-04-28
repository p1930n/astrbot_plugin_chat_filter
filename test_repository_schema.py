from __future__ import annotations

import json
import sqlite3
import shutil
import sys
import unittest
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.persistence.repository import (  # noqa: E402
    DATABASE_FILENAME,
    ChatFilterRepository,
    RepositorySchemaError,
    STATE_FILENAME,
)
from astrbot_plugin_chat_filter.domain.models import GroupPolicy, RuntimeState  # noqa: E402
from astrbot_plugin_chat_filter.persistence.repository_schema import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    REQUIRED_TABLE_COLUMNS,
    V1_REQUIRED_TABLE_COLUMNS,
    V2_REQUIRED_TABLE_COLUMNS,
)


class RepositorySchemaTests(unittest.TestCase):
    def test_v0_runtime_state_only_load_creates_missing_tables(self) -> None:
        with _temporary_directory() as root:
            database_path = Path(root) / DATABASE_FILENAME
            with _connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE runtime_state (
                        key TEXT PRIMARY KEY,
                        bool_value INTEGER NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO runtime_state (key, bool_value, updated_at)
                    VALUES ('global_enabled', 1, '2026-04-25T00:00:00+00:00')
                    """
                )

            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)
            state = repository.load()

            self.assertTrue(state.global_enabled)
            self.assert_schema_complete(database_path)
            with _connect(database_path) as connection:
                self.assertEqual(_schema_version(connection), CURRENT_SCHEMA_VERSION)

    def test_v0_missing_column_still_fails_fast(self) -> None:
        with _temporary_directory() as root:
            database_path = Path(root) / DATABASE_FILENAME
            with _connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE runtime_state (
                        key TEXT PRIMARY KEY,
                        updated_at TEXT NOT NULL
                    )
                    """
                )

            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            with self.assertRaisesRegex(RepositorySchemaError, "runtime_state.bool_value"):
                repository.load()

    def test_versioned_database_missing_table_fails_without_backfill(self) -> None:
        with _temporary_directory() as root:
            database_path = Path(root) / DATABASE_FILENAME
            with _connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE runtime_state (
                        key TEXT PRIMARY KEY,
                        bool_value INTEGER NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")

            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            with self.assertRaisesRegex(RepositorySchemaError, "group_policies"):
                repository.load()
            with _connect(database_path) as connection:
                self.assertNotIn("group_policies", _table_names(connection))

    def test_runtime_state_persists_group_admin_exemption(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)
            repository.save(
                RuntimeState(
                    groups={
                        "qq:100": GroupPolicy(
                            enabled=True,
                            admin_exempt_enabled=False,
                            custom_words=("local",),
                        )
                    }
                )
            )

            loaded = repository.load()

            self.assertFalse(loaded.groups["qq:100"].admin_exempt_enabled)
            self.assertEqual(loaded.groups["qq:100"].custom_words, ("local",))

    def test_versioned_group_policy_migration_defaults_admin_exemption_enabled(
        self,
    ) -> None:
        for version, required_columns in (
            (1, V1_REQUIRED_TABLE_COLUMNS),
            (2, V2_REQUIRED_TABLE_COLUMNS),
        ):
            with self.subTest(version=version):
                with _temporary_directory() as root:
                    database_path = Path(root) / DATABASE_FILENAME
                    with _connect(database_path) as connection:
                        _create_legacy_schema(
                            connection,
                            required_columns,
                            version=version,
                        )
                        connection.execute(
                            """
                            INSERT INTO group_policies (
                                group_key,
                                enabled,
                                inherit_global,
                                updated_at
                            )
                            VALUES ('qq:100', 1, 0, '2026-04-25T00:00:00+00:00')
                            """
                        )
                        connection.execute(
                            """
                            INSERT INTO group_words (
                                group_key,
                                word,
                                position,
                                created_at
                            )
                            VALUES ('qq:100', 'local', 0, '2026-04-25T00:00:00+00:00')
                            """
                        )

                    repository = ChatFilterRepository(
                        root,
                        max_word_count=20,
                        max_word_length=80,
                    )
                    state = repository.load()

                    self.assertTrue(state.groups["qq:100"].admin_exempt_enabled)
                    self.assertFalse(state.groups["qq:100"].inherit_global)
                    self.assertEqual(state.groups["qq:100"].custom_words, ("local",))
                    self.assert_schema_complete(database_path)
                    with _connect(database_path) as connection:
                        self.assertEqual(
                            _schema_version(connection),
                            CURRENT_SCHEMA_VERSION,
                        )
                        self.assertEqual(
                            _admin_exempt_enabled(connection, "qq:100"),
                            1,
                        )

    def test_json_state_missing_group_admin_exemption_defaults_enabled(self) -> None:
        with _temporary_directory() as root:
            state_path = Path(root) / STATE_FILENAME
            state_path.write_text(
                json.dumps(
                    {
                        "global_enabled": True,
                        "groups": {
                            "qq:100": {
                                "enabled": True,
                                "inherit_global": False,
                                "custom_words": ["local"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            state = repository.load()

            self.assertTrue(state.groups["qq:100"].admin_exempt_enabled)
            self.assertEqual(state.groups["qq:100"].custom_words, ("local",))
            with _connect(Path(root) / DATABASE_FILENAME) as connection:
                self.assertEqual(_admin_exempt_enabled(connection, "qq:100"), 1)

    def assert_schema_complete(self, database_path: Path) -> None:
        with _connect(database_path) as connection:
            self.assertTrue(set(REQUIRED_TABLE_COLUMNS).issubset(_table_names(connection)))
            for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
                actual_columns = _table_columns(connection, table_name)
                for column_name in required_columns:
                    self.assertIn(column_name, actual_columns)


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            yield connection


@contextmanager
def _temporary_directory() -> Iterator[str]:
    root = PACKAGE_DIR / f".schema-test-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield str(root)
    finally:
        shutil.rmtree(root)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _admin_exempt_enabled(connection: sqlite3.Connection, group_key: str) -> int | None:
    row = connection.execute(
        """
        SELECT admin_exempt_enabled
        FROM group_policies
        WHERE group_key = ?
        """,
        (group_key,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def _create_legacy_schema(
    connection: sqlite3.Connection,
    required_columns: dict[str, tuple[str, ...]],
    *,
    version: int,
) -> None:
    for table_name, columns in required_columns.items():
        if table_name == "runtime_state":
            connection.execute(
                """
                CREATE TABLE runtime_state (
                    key TEXT PRIMARY KEY,
                    bool_value INTEGER NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            continue
        if table_name == "group_policies":
            connection.execute(
                """
                CREATE TABLE group_policies (
                    group_key TEXT PRIMARY KEY,
                    enabled INTEGER NULL,
                    inherit_global INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            continue
        if table_name == "group_words":
            connection.execute(
                """
                CREATE TABLE group_words (
                    group_key TEXT NOT NULL,
                    word TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (group_key, word)
                )
                """
            )
            continue

        column_definitions = ", ".join(
            f'"{column_name}" TEXT NULL' for column_name in columns
        )
        connection.execute(f'CREATE TABLE "{table_name}" ({column_definitions})')

    connection.execute(f"PRAGMA user_version = {version}")


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    escaped_table_name = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{escaped_table_name}")').fetchall()
    return {str(row[1]) for row in rows}


if __name__ == "__main__":
    unittest.main()
