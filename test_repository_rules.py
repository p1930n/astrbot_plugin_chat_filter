from __future__ import annotations

import shutil
import sqlite3
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
)
from astrbot_plugin_chat_filter.persistence.repository_rules import (  # noqa: E402
    LEGACY_IMPORT_META_VALUE,
)
from astrbot_plugin_chat_filter.persistence.repository_schema import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
)


class RepositoryRuleTests(unittest.TestCase):
    def test_new_repository_initializes_rule_tables(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            self.assertEqual(repository.count_global_rules(), 0)

            database_path = Path(root) / DATABASE_FILENAME
            with _connect(database_path) as connection:
                self.assertIn("global_rules", _table_names(connection))
                self.assertIn("legacy_import_meta", _table_names(connection))
                self.assertEqual(_schema_version(connection), CURRENT_SCHEMA_VERSION)

    def test_v1_database_migrates_to_v2_rule_tables(self) -> None:
        with _temporary_directory() as root:
            database_path = Path(root) / DATABASE_FILENAME
            with _connect(database_path) as connection:
                _create_v1_schema(connection)
                connection.execute("PRAGMA user_version = 1")

            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            self.assertEqual(repository.count_global_rules(), 0)
            with _connect(database_path) as connection:
                self.assertIn("global_rules", _table_names(connection))
                self.assertIn("legacy_import_meta", _table_names(connection))
                self.assertEqual(_schema_version(connection), CURRENT_SCHEMA_VERSION)

    def test_legacy_import_is_idempotent_for_source_hash(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            inserted = repository.import_legacy_global_rules_once(
                ("alpha", "beta"),
                ("^admin$",),
                "hash-a",
            )
            repeated = repository.import_legacy_global_rules_once(
                ("gamma",),
                ("^root$",),
                "hash-a",
            )

            self.assertEqual(inserted, 3)
            self.assertEqual(repeated, 0)
            self.assertEqual(repository.count_global_rules(), 3)
            self.assertEqual(
                [(rule.rule_type, rule.pattern) for rule in repository.list_global_rules()],
                [("word", "alpha"), ("word", "beta"), ("regex", "^admin$")],
            )

    def test_empty_legacy_import_writes_meta(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            inserted = repository.import_legacy_global_rules_once((), (), "empty-hash")

            self.assertEqual(inserted, 0)
            self.assertEqual(repository.count_global_rules(), 0)
            with _connect(Path(root) / DATABASE_FILENAME) as connection:
                cursor = connection.execute(
                    """
                    SELECT value
                    FROM legacy_import_meta
                    WHERE key = ?
                    """,
                    ("legacy_global_rules_imported:empty-hash",),
                )
                self.assertEqual(cursor.fetchone()[0], LEGACY_IMPORT_META_VALUE)

    def test_imported_meta_prevents_empty_database_backfill(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)
            repository.import_legacy_global_rules_once(("alpha",), (), "hash-a")
            with _connect(Path(root) / DATABASE_FILENAME) as connection:
                connection.execute("DELETE FROM global_rules")

            inserted = repository.import_legacy_global_rules_once(("alpha",), (), "hash-a")

            self.assertEqual(inserted, 0)
            self.assertEqual(repository.count_global_rules(), 0)

    def test_duplicate_patterns_are_not_imported_twice_for_same_type(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            inserted = repository.import_legacy_global_rules_once(
                ("same", "same"),
                ("same", "same"),
                "hash-a",
            )

            self.assertEqual(inserted, 2)
            self.assertEqual(
                [(rule.rule_type, rule.pattern) for rule in repository.list_global_rules()],
                [("word", "same"), ("regex", "same")],
            )

    def test_import_preserves_raw_pattern_text_without_regex_compile(self) -> None:
        with _temporary_directory() as root:
            repository = ChatFilterRepository(root, max_word_count=20, max_word_length=80)

            inserted = repository.import_legacy_global_rules_once(
                ("  spaced word  ",),
                ("[",),
                "raw-hash",
            )

            self.assertEqual(inserted, 2)
            self.assertEqual(
                [(rule.rule_type, rule.pattern) for rule in repository.list_global_rules()],
                [("word", "  spaced word  "), ("regex", "[")],
            )


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
    root = PACKAGE_DIR / f".rules-test-{uuid.uuid4().hex}"
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


def _create_v1_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE runtime_state (
            key TEXT PRIMARY KEY,
            bool_value INTEGER NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE group_policies (
            group_key TEXT PRIMARY KEY,
            enabled INTEGER NULL,
            inherit_global INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE group_words (
            group_key TEXT NOT NULL,
            word TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE group_push_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            listening_group_id TEXT NOT NULL,
            push_group_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE group_report_policies (
            platform TEXT NOT NULL,
            listening_group_id TEXT NOT NULL,
            interval_value INTEGER NOT NULL,
            interval_unit TEXT NOT NULL,
            next_run_at TEXT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE group_mute_policies (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            mute_duration_seconds INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE group_mute_escalation_policies (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            multiplier INTEGER NOT NULL,
            reset_seconds INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE user_mute_escalation_states (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            violation_count INTEGER NOT NULL,
            last_violation_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE violation_batches (
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

        CREATE TABLE violation_events (
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
            updated_at TEXT NOT NULL
        );

        CREATE TABLE violation_push_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            listening_group_id TEXT NOT NULL,
            push_group_id TEXT NOT NULL,
            action_status TEXT NOT NULL,
            error_code TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


if __name__ == "__main__":
    unittest.main()
