from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository_schema import ensure_schema


STATE_FILENAME = "state.json"
DATABASE_FILENAME = "chat_filter.db"
GLOBAL_ENABLED_KEY = "global_enabled"


class RepositoryBase:
    def __init__(self, root_path: str, *, max_word_count: int, max_word_length: int) -> None:
        self._root = Path(root_path)
        self._state_path = self._root / STATE_FILENAME
        self._database_path = self._root / DATABASE_FILENAME
        self._max_word_count = max_word_count
        self._max_word_length = max_word_length
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
            yield connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        _restrict_owner_access(self._database_path)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            ensure_schema(connection)
            self._schema_ready = True


def default_data_root() -> str:
    return os.path.join(os.getcwd(), "data", "astrbot_plugin_chat_filter")


def optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def bool_or_default(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def optional_bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def optional_bool_from_int(value: Any) -> bool | None:
    if value is None:
        return None
    if value == 1:
        return True
    if value == 0:
        return False
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _restrict_owner_access(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)
