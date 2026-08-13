from __future__ import annotations

from pathlib import Path

from loguru import logger

from .connection import BaseDatabase

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def run_migrations(db: BaseDatabase) -> None:
    """Apply the SQL schema to the database (idempotent via IF NOT EXISTS)."""
    if not _SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema file not found: {_SCHEMA_FILE}")

    sql = _SCHEMA_FILE.read_text()
    db.execute_script(sql)
    logger.info("Database migrations applied successfully.")
