from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlite3


class BaseDatabase(ABC):
    """Abstract database interface.

    Subclass for SQLite, PostgreSQL, or any other backend.
    """

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Execute a write statement (INSERT / UPDATE / DELETE)."""
        ...

    @abstractmethod
    def execute_script(self, sql: str) -> None:
        """Execute a multi-statement SQL script (e.g. migrations)."""
        ...

    @abstractmethod
    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Return a single row as a dict, or None."""
        ...

    @abstractmethod
    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Return all matching rows as a list of dicts."""
        ...

    @abstractmethod
    def last_insert_id(self) -> int | None:
        """Return the rowid of the most recent INSERT."""
        ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class SQLiteDatabase(BaseDatabase):
    """Concrete SQLite implementation using the stdlib ``sqlite3`` module."""

    def __init__(self, db_path: str | Path = "trade_executor.db"):
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ---------------------------------------------------------------- lifecycle

    def connect(self) -> None:
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ helpers

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    # -------------------------------------------------------------- operations

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._connection.execute(sql, params)
        self._connection.commit()

    def execute_script(self, sql: str) -> None:
        self._connection.executescript(sql)

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = self._connection.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = self._connection.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    def last_insert_id(self) -> int | None:
        cursor = self._connection.execute("SELECT last_insert_rowid()")
        row = cursor.fetchone()
        return row[0] if row else None
