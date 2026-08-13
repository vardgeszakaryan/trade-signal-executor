"""Tests for MT5Trader.place_order dispatch with mocked MT5 API and DB.

MetaTrader5 is mocked at the sys.modules level to avoid DLL loading during
test collection. All MT5 constants and functions are provided by the mock.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Install a mock MetaTrader5 module BEFORE importing any code that uses it.
_mt5_mock = MagicMock()
_mt5_mock.ORDER_TIME_GTC = 0
_mt5_mock.ORDER_FILLING_IOC = 1
_mt5_mock.TRADE_ACTION_DEAL = 1
_mt5_mock.TRADE_ACTION_PENDING = 5
_mt5_mock.TRADE_ACTION_REMOVE = 6
_mt5_mock.TRADE_ACTION_SLTP = 7
_mt5_mock.TRADE_ACTION_MODIFY = 8
_mt5_mock.ORDER_TYPE_BUY = 0
_mt5_mock.ORDER_TYPE_SELL = 1
_mt5_mock.ORDER_TYPE_BUY_LIMIT = 2
_mt5_mock.ORDER_TYPE_SELL_LIMIT = 3
_mt5_mock.ORDER_TYPE_BUY_STOP = 4
_mt5_mock.ORDER_TYPE_SELL_STOP = 5
_mt5_mock.POSITION_TYPE_BUY = 0
_mt5_mock.POSITION_TYPE_SELL = 1
_mt5_mock.TRADE_RETCODE_DONE = 10009
_mt5_mock.initialize.return_value = True

sys.modules["MetaTrader5"] = _mt5_mock

from db.connection import SQLiteDatabase
from db.migrate import run_migrations
from db.repositories.store_orders import OrderRepository
from trade_executor.execution import TradeOrder
from trade_executor.execution.mt5.mt5 import MT5Trader
from trade_executor.parser.base import ParsedData, PriceSignal, SignalAction


@pytest.fixture
def order_repo(tmp_path):
    """OrderRepository backed by a fresh SQLite DB with schema applied."""
    db = SQLiteDatabase(db_path=tmp_path / "dispatch_test.db")
    db.connect()
    run_migrations(db)
    yield OrderRepository(db)
    db.close()


@pytest.fixture(autouse=True)
def reset_mt5_mock():
    """Reset MT5 mock calls between tests."""
    _mt5_mock.reset_mock()
    _mt5_mock.initialize.return_value = True

    # symbol_info
    info = MagicMock()
    info.visible = True
    info.point = 0.01
    info.digits = 5
    info.volume_step = 0.01
    _mt5_mock.symbol_info.return_value = info

    # tick data
    tick = MagicMock()
    tick.ask = 4000.0
    tick.bid = 3999.0
    _mt5_mock.symbol_info_tick.return_value = tick

    yield


def _make_trader():
    """Create an MT5Trader with the mocked MT5 module."""
    return MT5Trader(
        terminal_path="C:\\fake\\terminal.exe",
        login=12345,
        password="password",
        server="TestServer",
    )


class TestBuySignalRecordsTickets:
    def test_buy_records_tickets_in_db(self, order_repo):
        result = MagicMock()
        result.retcode = 10009
        result.order = 77777
        _mt5_mock.order_send.return_value = result

        trader = _make_trader()
        order = TradeOrder(
            id=42,
            order=ParsedData(size=0.01, action=SignalAction.BUY),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)

        tickets = order_repo.get_tickets_by_signal(42)
        assert 77777 in tickets

    def test_sell_records_tickets_in_db(self, order_repo):
        result = MagicMock()
        result.retcode = 10009
        result.order = 88888
        _mt5_mock.order_send.return_value = result

        trader = _make_trader()
        order = TradeOrder(
            id=43,
            order=ParsedData(size=0.02, action=SignalAction.SELL),
        )
        trader.place_order(order, "BTCUSDTm", order_repo=order_repo)

        tickets = order_repo.get_tickets_by_signal(43)
        assert 88888 in tickets


class TestCancelLooksUpTicketsFromDB:
    def test_cancel_uses_db_tickets(self, order_repo):
        order_repo.record_order(
            signal_id=50, ticket=99999, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY", comment="tse:50",
        )

        pending = MagicMock()
        pending.ticket = 99999
        _mt5_mock.orders_get.return_value = [pending]

        cancel_result = MagicMock()
        cancel_result.retcode = 10009
        cancel_result.order = 99999
        _mt5_mock.order_send.return_value = cancel_result

        trader = _make_trader()
        order = TradeOrder(
            id=50,
            order=ParsedData(size=0.01, action=SignalAction.CANCEL),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)

        _mt5_mock.order_send.assert_called()
        call_args = _mt5_mock.order_send.call_args[0][0]
        assert call_args["action"] == 6  # TRADE_ACTION_REMOVE
        assert call_args["order"] == 99999

        assert order_repo.get_tickets_by_signal(50, status="CANCELLED") == [99999]

    def test_cancel_no_tickets_in_db_does_not_crash(self, order_repo):
        trader = _make_trader()
        order = TradeOrder(
            id=999,
            order=ParsedData(size=0.01, action=SignalAction.CANCEL),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)
        _mt5_mock.order_send.assert_not_called()


class TestCloseLooksUpTicketsFromDB:
    def test_close_uses_db_tickets(self, order_repo):
        order_repo.record_order(
            signal_id=60, ticket=11111, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY", comment="tse:60",
        )

        pos = MagicMock()
        pos.ticket = 11111
        pos.type = 0  # POSITION_TYPE_BUY
        pos.volume = 0.01
        _mt5_mock.positions_get.return_value = [pos]

        close_result = MagicMock()
        close_result.retcode = 10009
        close_result.order = 11111
        _mt5_mock.order_send.return_value = close_result

        trader = _make_trader()
        order = TradeOrder(
            id=60,
            order=ParsedData(size=0.01, action=SignalAction.CLOSE),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)

        _mt5_mock.order_send.assert_called()
        assert order_repo.get_tickets_by_signal(60, status="CLOSED") == [11111]


class TestUpdateLooksUpTicketsFromDB:
    def test_update_modifies_position(self, order_repo):
        order_repo.record_order(
            signal_id=70, ticket=22222, symbol="XAUUSDm",
            direction="BUY", volume=0.01, action="BUY", comment="tse:70",
        )

        pos = MagicMock()
        pos.ticket = 22222
        pos.sl = 3900.0
        pos.tp = 4100.0
        _mt5_mock.positions_get.return_value = [pos]

        update_result = MagicMock()
        update_result.retcode = 10009
        update_result.order = 22222
        _mt5_mock.order_send.return_value = update_result

        trader = _make_trader()
        order = TradeOrder(
            id=70,
            order=ParsedData(
                size=0.01,
                action=SignalAction.UPDATE,
                stop_loss=PriceSignal(price=[3850.0], unit="price", type="single"),
            ),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)

        _mt5_mock.order_send.assert_called()
        call_args = _mt5_mock.order_send.call_args[0][0]
        assert call_args["action"] == 7  # TRADE_ACTION_SLTP


class TestIgnoreAction:
    def test_ignore_does_nothing(self, order_repo):
        trader = _make_trader()
        order = TradeOrder(
            id=80,
            order=ParsedData(size=0.0, action=SignalAction.IGNORE),
        )
        trader.place_order(order, "XAUUSDm", order_repo=order_repo)
        _mt5_mock.order_send.assert_not_called()


class TestWithoutOrderRepo:
    def test_buy_without_repo_still_works(self):
        result = MagicMock()
        result.retcode = 10009
        result.order = 44444
        _mt5_mock.order_send.return_value = result

        trader = _make_trader()
        order = TradeOrder(
            id=90,
            order=ParsedData(size=0.01, action=SignalAction.BUY),
        )
        trader.place_order(order, "XAUUSDm", order_repo=None)
        _mt5_mock.order_send.assert_called()

    def test_cancel_without_repo_warns(self):
        trader = _make_trader()
        order = TradeOrder(
            id=91,
            order=ParsedData(size=0.01, action=SignalAction.CANCEL),
        )
        trader.place_order(order, "XAUUSDm", order_repo=None)
        _mt5_mock.order_send.assert_not_called()
