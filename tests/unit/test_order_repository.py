"""Tests for OrderRepository CRUD operations."""

import pytest

from db.connection import SQLiteDatabase
from db.migrate import run_migrations
from db.repositories.store_orders import OrderRepository


@pytest.fixture
def repo(tmp_path):
    """Provide an OrderRepository backed by a fresh in-memory-like SQLite DB."""
    db = SQLiteDatabase(db_path=tmp_path / "test_orders.db")
    db.connect()
    run_migrations(db)
    yield OrderRepository(db)
    db.close()


class TestRecordOrder:
    def test_record_and_retrieve(self, repo):
        row_id = repo.record_order(
            signal_id=100,
            ticket=55555,
            symbol="XAUUSDm",
            direction="BUY",
            volume=0.03,
            action="BUY",
            comment="tse:100",
        )
        assert row_id is not None

        tickets = repo.get_tickets_by_signal(100)
        assert tickets == [55555]

    def test_multiple_orders_per_signal(self, repo):
        repo.record_order(
            signal_id=200, ticket=1001, symbol="BTCUSDTm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=200, ticket=1002, symbol="BTCUSDTm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=200, ticket=1003, symbol="BTCUSDTm",
            direction="BUY", volume=0.01, action="BUY",
        )

        tickets = repo.get_tickets_by_signal(200)
        assert sorted(tickets) == [1001, 1002, 1003]

    def test_different_signals_are_isolated(self, repo):
        repo.record_order(
            signal_id=1, ticket=111, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=2, ticket=222, symbol="XAUUSDm",
            direction="SELL", volume=0.02, action="SELL",
        )

        assert repo.get_tickets_by_signal(1) == [111]
        assert repo.get_tickets_by_signal(2) == [222]


class TestGetOpenOrders:
    def test_filter_by_signal_id(self, repo):
        repo.record_order(
            signal_id=10, ticket=100, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=20, ticket=200, symbol="XAUUSDm",
            direction="SELL", volume=0.02, action="SELL",
        )

        orders = repo.get_open_orders(signal_id=10)
        assert len(orders) == 1
        assert orders[0]["ticket"] == 100

    def test_filter_by_symbol(self, repo):
        repo.record_order(
            signal_id=30, ticket=300, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=31, ticket=301, symbol="BTCUSDTm",
            direction="BUY", volume=0.01, action="BUY",
        )

        orders = repo.get_open_orders(symbol="BTCUSDTm")
        assert len(orders) == 1
        assert orders[0]["ticket"] == 301

    def test_no_filters_returns_all_open(self, repo):
        repo.record_order(
            signal_id=40, ticket=400, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=41, ticket=401, symbol="BTCUSDTm",
            direction="SELL", volume=0.02, action="SELL",
        )

        orders = repo.get_open_orders()
        assert len(orders) == 2


class TestUpdateStatus:
    def test_update_to_closed(self, repo):
        repo.record_order(
            signal_id=50, ticket=500, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )

        repo.update_status(500, "CLOSED")

        # Should no longer appear in OPEN queries
        assert repo.get_tickets_by_signal(50, status="OPEN") == []
        # But should appear if we query CLOSED
        assert repo.get_tickets_by_signal(50, status="CLOSED") == [500]

    def test_update_to_cancelled(self, repo):
        repo.record_order(
            signal_id=60, ticket=600, symbol="XAUUSDm",
            direction="SELL", volume=0.01, action="SELL",
        )

        repo.update_status(600, "CANCELLED")

        assert repo.get_tickets_by_signal(60, status="OPEN") == []
        assert repo.get_tickets_by_signal(60, status="CANCELLED") == [600]

    def test_closed_orders_excluded_from_get_open_orders(self, repo):
        repo.record_order(
            signal_id=70, ticket=700, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )
        repo.record_order(
            signal_id=70, ticket=701, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY",
        )

        repo.update_status(700, "CLOSED")

        open_orders = repo.get_open_orders(signal_id=70)
        assert len(open_orders) == 1
        assert open_orders[0]["ticket"] == 701


class TestEdgeCases:
    def test_get_tickets_for_nonexistent_signal(self, repo):
        assert repo.get_tickets_by_signal(9999) == []

    def test_get_open_orders_empty_db(self, repo):
        assert repo.get_open_orders() == []

    def test_update_nonexistent_ticket(self, repo):
        # Should not raise, just a no-op
        repo.update_status(9999, "CLOSED")
