from __future__ import annotations

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

from astrbot_plugin_chat_filter.repository import (  # noqa: E402
    DATABASE_FILENAME,
    ChatFilterRepository,
    RepositorySchemaError,
)
from astrbot_plugin_chat_filter.repository_schema import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    REQUIRED_TABLE_COLUMNS,
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


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    escaped_table_name = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{escaped_table_name}")').fetchall()
    return {str(row[1]) for row in rows}


if __name__ == "__main__":
    unittest.main()
