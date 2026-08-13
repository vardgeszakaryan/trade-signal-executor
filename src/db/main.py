from __future__ import annotations

from typing import Literal

from .connection import BaseDatabase, SQLiteDatabase


def get_database(backend: Literal["sqlite"] = "sqlite", **kwargs) -> BaseDatabase:
    """Factory for database backends.

    Only SQLite is implemented today; add PostgreSQL / others here later.
    """
    registry: dict[str, type[BaseDatabase]] = {
        "sqlite": SQLiteDatabase,
    }

    cls = registry.get(backend)
    if cls is None:
        raise ValueError(f"Unknown database backend: {backend!r}")

    return cls(**kwargs)
