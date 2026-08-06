"""Every [direction, entry, tp, sl] combination for order construction.

Pure unit tests: no MT5 terminal required. `entry=None` simulates market
execution the same way MT5Trader._open_orders does (plan_market_entries).
"""

import itertools

import pytest

from trade_executor.execution.mt5.order_math import (
    build_order_prices,
    linspace,
    plan_market_entries,
    split_volume,
)
from trade_executor.parser.base import PriceSignal

MARKET = 4000.0
PIP = 0.01
MAX_ORDERS = 3

DIRECTIONS = ["BUY", "SELL"]
ENTRY_KINDS = [None, "single", "multiple", "range"]
LEVEL_KINDS = [None, "single", "multiple", "range", "pips"]
MULTI_LEVEL = ("multiple", "range")

ENTRIES = {"single": [3995.0], "multiple": [3990.0, 3995.0], "range": [3990.0, 4000.0]}

LEVELS = {
    "BUY": {
        "sl": {"price": [3950.0, 3960.0], "pips": [15.0]},
        "tp": {"price": [4050.0, 4060.0], "pips": [15.0]},
    },
    "SELL": {
        "sl": {"price": [4040.0, 4050.0], "pips": [15.0]},
        "tp": {"price": [3940.0, 3950.0], "pips": [15.0]},
    },
}


def level_signal(kind, direction, field):
    if kind is None:
        return None
    unit = "pips" if kind == "pips" else "price"
    prices = LEVELS[direction][field][unit]
    sig_type = "single" if kind in ("single", "pips") else kind
    return PriceSignal(price=list(prices), unit=unit, type=sig_type)


def entry_signal(kind):
    prices = ENTRIES[kind]
    sig_type = "single" if kind == "single" else kind
    return PriceSignal(price=list(prices), unit="price", type=sig_type)


@pytest.mark.parametrize(
    ("direction", "entry_kind", "sl_kind", "tp_kind"),
    list(itertools.product(DIRECTIONS, ENTRY_KINDS, LEVEL_KINDS, LEVEL_KINDS)),
)
def test_direction_entry_sl_tp_combination(direction, entry_kind, sl_kind, tp_kind):
    sl = level_signal(sl_kind, direction, "sl")
    tp = level_signal(tp_kind, direction, "tp")

    if entry_kind is None:
        # market execution: MT5Trader replicates the market price
        prices = plan_market_entries(MARKET, sl, tp, MAX_ORDERS)
        entry = PriceSignal(price=prices, unit="price", type="multiple")
    else:
        entry = entry_signal(entry_kind)

    orders = build_order_prices(entry, sl, tp, direction, PIP, MAX_ORDERS)

    # --- order count -----------------------------------------------------
    if entry_kind is None:
        split = sl_kind in MULTI_LEVEL or tp_kind in MULTI_LEVEL
        assert len(orders) == (MAX_ORDERS if split else 1)
    elif entry_kind == "single":
        assert len(orders) == 1
    elif entry_kind == "multiple":
        assert len(orders) == 2
    else:  # range
        assert len(orders) == MAX_ORDERS

    for i, o in enumerate(orders):
        assert o["direction"] == direction

        # --- entry price --------------------------------------------------
        if entry_kind is None:
            assert o["price"] == pytest.approx(MARKET)
        elif entry_kind == "single":
            assert o["price"] == pytest.approx(3995.0)
        elif entry_kind == "multiple":
            assert o["price"] == pytest.approx(ENTRIES["multiple"][i])
        else:
            expected = linspace(*ENTRIES["range"], MAX_ORDERS)
            assert o["price"] == pytest.approx(list(expected)[i])

        # --- SL -----------------------------------------------------------
        if sl_kind is None:
            assert o["sl"] is None
        else:
            assert isinstance(o["sl"], float)
            if direction == "BUY":
                assert o["sl"] < o["price"]
            else:
                assert o["sl"] > o["price"]
            if sl_kind == "pips":
                sign = -1 if direction == "BUY" else +1
                assert o["sl"] == pytest.approx(o["price"] + sign * 15.0 * PIP)
            else:
                assert min(LEVELS[direction]["sl"]["price"]) <= o["sl"] <= max(
                    LEVELS[direction]["sl"]["price"]
                )

        # --- TP -----------------------------------------------------------
        if tp_kind is None:
            assert o["tp"] is None
        else:
            assert isinstance(o["tp"], float)
            if direction == "BUY":
                assert o["tp"] > o["price"]
            else:
                assert o["tp"] < o["price"]
            if tp_kind == "pips":
                sign = +1 if direction == "BUY" else -1
                assert o["tp"] == pytest.approx(o["price"] + sign * 15.0 * PIP)
            else:
                assert min(LEVELS[direction]["tp"]["price"]) <= o["tp"] <= max(
                    LEVELS[direction]["tp"]["price"]
                )


def test_market_execution_does_not_split_small_lot():
    """lot = 0.01 stays a single market order even with range SL/TP."""
    assert split_volume(0.01, MAX_ORDERS) == [0.01]


def test_market_execution_does_not_split_single_levels():
    single = PriceSignal(price=[10.0], unit="pips", type="single")
    assert plan_market_entries(MARKET, single, single, MAX_ORDERS) == [MARKET]
    assert plan_market_entries(MARKET, None, None, MAX_ORDERS) == [MARKET]


@pytest.mark.parametrize(
    ("volume", "parts", "expected"),
    [
        (0.04, 3, [0.01, 0.01, 0.02]),  # remainder goes to the last order
        (0.03, 3, [0.01, 0.01, 0.01]),
        (0.06, 3, [0.02, 0.02, 0.02]),  # even splits stay even
        (0.02, 3, [0.01, 0.01]),  # lot cannot fund 3 orders -> only 2
        (0.01, 3, [0.01]),  # minimal lot never splits
        (0.05, 1, [0.05]),
    ],
)
def test_split_volume(volume, parts, expected):
    result = split_volume(volume, parts)
    assert [round(v, 8) for v in result] == expected
    assert round(sum(result), 8) == volume  # nothing is lost


@pytest.mark.parametrize("kind", ["multiple", "range"])
def test_market_execution_splits_on_multi_level(kind):
    sig = PriceSignal(price=[4050.0, 4060.0], unit="price", type=kind)
    assert plan_market_entries(MARKET, sig, None, MAX_ORDERS) == [MARKET] * MAX_ORDERS
    assert plan_market_entries(MARKET, None, sig, MAX_ORDERS) == [MARKET] * MAX_ORDERS
