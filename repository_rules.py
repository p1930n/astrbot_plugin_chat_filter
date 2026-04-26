from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .repository_base import utc_now
from .rule_models import GlobalRule, RuleType


LEGACY_GLOBAL_RULE_SOURCE = "legacy_config"
LEGACY_IMPORT_META_PREFIX = "legacy_global_rules_imported:"
LEGACY_IMPORT_META_VALUE = "imported"


class RuleRepositoryMixin:
    def list_global_rules(self) -> list[GlobalRule]:
        with self._connection() as connection:
            return [
                GlobalRule(
                    id=int(row[0]),
                    rule_type=_rule_type(row[1]),
                    pattern=row[2],
                    position=int(row[3]),
                    enabled=bool(row[4]),
                    source=row[5],
                    created_at=row[6],
                )
                for row in connection.execute(
                    """
                    SELECT id, rule_type, pattern, position, enabled, source, created_at
                    FROM global_rules
                    ORDER BY position, id
                    """
                )
            ]

    def count_global_rules(self) -> int:
        with self._connection() as connection:
            cursor = connection.execute("SELECT COUNT(*) FROM global_rules")
            return int(cursor.fetchone()[0])

    def import_legacy_global_rules_once(
        self,
        words: Iterable[object],
        regex_patterns: Iterable[object],
        source_hash: str,
    ) -> int:
        word_values = list(words)
        regex_values = list(regex_patterns)
        meta_key = _legacy_import_meta_key(source_hash)
        now = utc_now()
        inserted_count = 0
        with self._connection() as connection:
            with connection:
                if self._legacy_import_done(connection, meta_key=meta_key):
                    return 0

                word_rows = self._legacy_rule_rows(
                    rule_type="word",
                    values=word_values,
                    starting_position=0,
                    now=now,
                )
                regex_rows = self._legacy_rule_rows(
                    rule_type="regex",
                    values=regex_values,
                    starting_position=len(word_rows),
                    now=now,
                )
                rules = [*word_rows, *regex_rows]
                for rule in rules:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO global_rules (
                            rule_type,
                            pattern,
                            position,
                            enabled,
                            source,
                            created_at
                        )
                        VALUES (?, ?, ?, 1, ?, ?)
                        """,
                        rule,
                    )
                    if cursor.rowcount == 1:
                        inserted_count += 1

                connection.execute(
                    """
                    INSERT INTO legacy_import_meta (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (key)
                    DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (meta_key, LEGACY_IMPORT_META_VALUE, now),
                )
        return inserted_count

    def _legacy_import_done(
        self,
        connection: sqlite3.Connection,
        *,
        meta_key: str,
    ) -> bool:
        cursor = connection.execute(
            """
            SELECT value
            FROM legacy_import_meta
            WHERE key = ?
            """,
            (meta_key,),
        )
        row = cursor.fetchone()
        return bool(row and row[0] == LEGACY_IMPORT_META_VALUE)

    def _legacy_rule_rows(
        self,
        *,
        rule_type: RuleType,
        values: Iterable[object],
        starting_position: int,
        now: str,
    ) -> list[tuple[str, str, int, str, str]]:
        rows: list[tuple[str, str, int, str, str]] = []
        for offset, value in enumerate(values):
            pattern = _pattern_text(value)
            if pattern is None:
                continue
            rows.append(
                (
                    rule_type,
                    pattern,
                    starting_position + offset,
                    LEGACY_GLOBAL_RULE_SOURCE,
                    now,
                )
            )
        return rows


def _legacy_import_meta_key(source_hash: str) -> str:
    return f"{LEGACY_IMPORT_META_PREFIX}{source_hash}"


def _pattern_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    pattern = getattr(value, "pattern", None)
    if isinstance(pattern, str):
        return pattern
    return None


def _rule_type(value: object) -> RuleType:
    if value == "word":
        return "word"
    if value == "regex":
        return "regex"
    raise ValueError(f"unsupported rule type from database: {value}")
