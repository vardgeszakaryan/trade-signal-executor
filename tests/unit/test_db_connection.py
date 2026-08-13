"""Tests for BaseDatabase (ABC) and SQLiteDatabase (concrete)."""

import sqlite3

import pytest

from db.connection import BaseDatabase, SQLiteDatabase


class TestBaseDatabase:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            BaseDatabase()  # type: ignore


class TestSQLiteDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        """Provide a connected SQLiteDatabase using a temp directory."""
        db = SQLiteDatabase(db_path=tmp_path / "test.db")
        db.connect()
        yield db
        db.close()

    def test_connect_creates_file(self, tmp_path):
        path = tmp_path / "new.db"
        db = SQLiteDatabase(db_path=path)
        db.connect()
        assert path.exists()
        db.close()

    def test_double_connect_is_safe(self, db):
        db.connect()  # Should not raise

    def test_close_and_reopen(self, tmp_path):
        path = tmp_path / "reopen.db"
        db = SQLiteDatabase(db_path=path)
        db.connect()
        db.close()
        db.connect()
        db.execute("CREATE TABLE t (id INTEGER)")
        db.close()

    def test_execute_and_fetch_all(self, db):
        db.execute("CREATE TABLE items (id INTEGER, name TEXT)")
        db.execute("INSERT INTO items VALUES (1, 'alpha')")
        db.execute("INSERT INTO items VALUES (2, 'beta')")

        rows = db.fetch_all("SELECT * FROM items ORDER BY id")
        assert len(rows) == 2
        assert rows[0] == {"id": 1, "name": "alpha"}
        assert rows[1] == {"id": 2, "name": "beta"}

    def test_fetch_one_returns_dict(self, db):
        db.execute("CREATE TABLE single (val TEXT)")
        db.execute("INSERT INTO single VALUES ('hello')")

        row = db.fetch_one("SELECT * FROM single")
        assert row == {"val": "hello"}

    def test_fetch_one_returns_none_when_empty(self, db):
        db.execute("CREATE TABLE empty (val TEXT)")
        result = db.fetch_one("SELECT * FROM empty")
        assert result is None

    def test_fetch_all_returns_empty_list(self, db):
        db.execute("CREATE TABLE empty2 (val TEXT)")
        result = db.fetch_all("SELECT * FROM empty2")
        assert result == []

    def test_execute_with_params(self, db):
        db.execute("CREATE TABLE param_test (id INTEGER, name TEXT)")
        db.execute("INSERT INTO param_test VALUES (?, ?)", (42, "test"))

        row = db.fetch_one("SELECT * FROM param_test WHERE id = ?", (42,))
        assert row == {"id": 42, "name": "test"}

    def test_execute_script(self, db):
        sql = """
        CREATE TABLE a (id INTEGER);
        CREATE TABLE b (id INTEGER);
        INSERT INTO a VALUES (1);
        INSERT INTO b VALUES (2);
        """
        db.execute_script(sql)

        assert db.fetch_one("SELECT * FROM a") == {"id": 1}
        assert db.fetch_one("SELECT * FROM b") == {"id": 2}

    def test_last_insert_id(self, db):
        db.execute("CREATE TABLE auto (id INTEGER PRIMARY KEY AUTOINCREMENT, val TEXT)")
        db.execute("INSERT INTO auto (val) VALUES ('first')")
        assert db.last_insert_id() == 1

        db.execute("INSERT INTO auto (val) VALUES ('second')")
        assert db.last_insert_id() == 2

    def test_context_manager(self, tmp_path):
        path = tmp_path / "ctx.db"
        with SQLiteDatabase(db_path=path) as db:
            db.execute("CREATE TABLE ctx_test (id INTEGER)")
            db.execute("INSERT INTO ctx_test VALUES (1)")
            row = db.fetch_one("SELECT * FROM ctx_test")
            assert row == {"id": 1}

    def test_operations_fail_without_connect(self, tmp_path):
        db = SQLiteDatabase(db_path=tmp_path / "no_connect.db")
        with pytest.raises(RuntimeError, match="not connected"):
            db.execute("SELECT 1")

    def test_wal_mode_enabled(self, db):
        row = db.fetch_one("PRAGMA journal_mode")
        assert row is not None
        # WAL mode returns "wal" as the journal_mode value
        assert list(row.values())[0] == "wal"
