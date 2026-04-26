from __future__ import annotations

import sqlite3


CURRENT_SCHEMA_VERSION = 3


class RepositorySchemaError(RuntimeError):
    """Raised when the persisted SQLite schema cannot be used safely."""


V1_REQUIRED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "runtime_state": ("key", "bool_value", "updated_at"),
    "group_policies": ("group_key", "enabled", "inherit_global", "updated_at"),
    "group_words": ("group_key", "word", "position", "created_at"),
    "group_push_bindings": (
        "id",
        "platform",
        "listening_group_id",
        "push_group_id",
        "enabled",
        "created_by",
        "created_at",
        "updated_at",
    ),
    "group_report_policies": (
        "platform",
        "listening_group_id",
        "interval_value",
        "interval_unit",
        "next_run_at",
        "enabled",
        "updated_at",
    ),
    "group_mute_policies": (
        "platform",
        "group_id",
        "mute_duration_seconds",
        "enabled",
        "updated_by",
        "created_at",
        "updated_at",
    ),
    "group_mute_escalation_policies": (
        "platform",
        "group_id",
        "multiplier",
        "reset_seconds",
        "enabled",
        "updated_by",
        "created_at",
        "updated_at",
    ),
    "user_mute_escalation_states": (
        "platform",
        "group_id",
        "user_id",
        "violation_count",
        "last_violation_at",
        "updated_at",
    ),
    "violation_batches": (
        "id",
        "platform",
        "listening_group_id",
        "push_group_id",
        "window_start",
        "window_end",
        "record_count",
        "file_name",
        "send_status",
        "error_code",
        "created_at",
        "sent_at",
    ),
    "violation_events": (
        "id",
        "platform",
        "group_id",
        "user_id",
        "sender_display_name_snapshot",
        "message_id",
        "matched_keyword",
        "matched_content",
        "raw_message_digest",
        "action_mute_status",
        "action_recall_status",
        "action_forward_status",
        "file_batch_id",
        "created_at",
        "updated_at",
    ),
    "violation_push_deliveries": (
        "id",
        "violation_id",
        "platform",
        "listening_group_id",
        "push_group_id",
        "action_status",
        "error_code",
        "created_at",
        "updated_at",
    ),
}


V2_REQUIRED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    **V1_REQUIRED_TABLE_COLUMNS,
    "global_rules": (
        "id",
        "rule_type",
        "pattern",
        "position",
        "enabled",
        "source",
        "created_at",
    ),
    "legacy_import_meta": ("key", "value", "updated_at"),
}


REQUIRED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    **V2_REQUIRED_TABLE_COLUMNS,
    "group_policies": (
        "group_key",
        "enabled",
        "inherit_global",
        "admin_exempt_enabled",
        "updated_at",
    ),
}


def ensure_schema(connection: sqlite3.Connection) -> None:
    current_version = _schema_version(connection)
    if current_version > CURRENT_SCHEMA_VERSION:
        raise RepositorySchemaError(
            "chat filter database schema is newer than this plugin version: "
            f"{current_version} > {CURRENT_SCHEMA_VERSION}"
        )

    if current_version == CURRENT_SCHEMA_VERSION:
        _validate_required_schema(connection, REQUIRED_TABLE_COLUMNS)
        _create_schema_objects(connection)
        _validate_required_schema(connection, REQUIRED_TABLE_COLUMNS)
        return

    if current_version == 1:
        _validate_required_schema(connection, V1_REQUIRED_TABLE_COLUMNS)
    elif current_version == 2:
        _validate_required_schema(connection, V2_REQUIRED_TABLE_COLUMNS)

    _create_schema_objects(connection)
    _migrate_schema_objects(connection, current_version)
    _validate_required_schema(connection, REQUIRED_TABLE_COLUMNS)

    connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")


def _create_schema_objects(connection: sqlite3.Connection) -> None:
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
            admin_exempt_enabled INTEGER NOT NULL DEFAULT 1,
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

        CREATE TABLE IF NOT EXISTS group_mute_escalation_policies (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            multiplier INTEGER NOT NULL,
            reset_seconds INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, group_id)
        );

        CREATE TABLE IF NOT EXISTS user_mute_escalation_states (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            violation_count INTEGER NOT NULL,
            last_violation_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, group_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_mute_escalation_group
        ON user_mute_escalation_states (platform, group_id, updated_at);

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

        CREATE TABLE IF NOT EXISTS violation_push_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            listening_group_id TEXT NOT NULL,
            push_group_id TEXT NOT NULL,
            action_status TEXT NOT NULL,
            error_code TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (violation_id)
                REFERENCES violation_events(id)
                ON DELETE CASCADE,
            UNIQUE (violation_id, platform, push_group_id)
        );

        CREATE INDEX IF NOT EXISTS idx_violation_push_deliveries_status
        ON violation_push_deliveries (platform, action_status, updated_at);

        CREATE INDEX IF NOT EXISTS idx_violation_push_deliveries_push_group
        ON violation_push_deliveries (platform, push_group_id, updated_at);

        CREATE TABLE IF NOT EXISTS global_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL
                CHECK (rule_type IN ('word', 'regex')),
            pattern TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (rule_type, pattern)
        );

        CREATE INDEX IF NOT EXISTS idx_global_rules_enabled_position
        ON global_rules (enabled, position, id);

        CREATE TABLE IF NOT EXISTS legacy_import_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _migrate_schema_objects(
    connection: sqlite3.Connection,
    current_version: int,
) -> None:
    _ = current_version
    if "admin_exempt_enabled" not in _table_columns(connection, "group_policies"):
        connection.execute(
            """
            ALTER TABLE group_policies
            ADD COLUMN admin_exempt_enabled INTEGER NOT NULL DEFAULT 1
            """
        )


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if not row:
        return 0
    return int(row[0])


def _user_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _validate_required_schema(
    connection: sqlite3.Connection,
    required_table_columns: dict[str, tuple[str, ...]],
) -> None:
    table_names = _user_table_names(connection)
    missing_tables = sorted(set(required_table_columns) - table_names)
    if missing_tables:
        raise RepositorySchemaError(
            "chat filter database schema is missing required table(s): "
            f"{', '.join(missing_tables)}"
        )

    missing_columns: list[str] = []
    for table_name, required_columns in required_table_columns.items():
        actual_columns = _table_columns(connection, table_name)
        for column_name in required_columns:
            if column_name not in actual_columns:
                missing_columns.append(f"{table_name}.{column_name}")

    if missing_columns:
        raise RepositorySchemaError(
            "chat filter database schema is missing required column(s): "
            f"{', '.join(sorted(missing_columns))}"
        )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    escaped_table_name = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{escaped_table_name}")').fetchall()
    return {str(row[1]) for row in rows}
