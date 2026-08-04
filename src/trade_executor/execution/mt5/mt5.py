import os
from pathlib import Path
from typing import Literal, Optional, Tuple

import MetaTrader5 as mt5
from loguru import logger
from pydantic import BaseModel

from trade_executor.execution import TradeExecutor, TradeOrder
from trade_executor.parser.base import ParsedData, PriceSignal, SignalAction

from trade_executor.execution.mt5.helper_functions import (
    build_order_prices,
    plan_market_entries,
    split_volume,
)


class OrderMT5(BaseModel):
    symbol: str
    volume: float
    direction: Literal["BUY", "SELL"]

    price: Optional[PriceSignal] = None
    sl: Optional[PriceSignal] = None
    tp: Optional[PriceSignal] = None

    comment: str = "trade-signal-executor"
    type_time: int = mt5.ORDER_TIME_GTC


class MT5Trader(TradeExecutor):
    def __init__(
        self,
        terminal_path: Path | str,
        login: int,
        password: str,
        server: str,
        max_orders: int = 3,
        trade_deviation: float = 20.0,
        magic_number: int = 67,
        filling: int = mt5.ORDER_FILLING_IOC,
    ):
        if not mt5.initialize(
            path=str(terminal_path),
            login=login,
            password=password,
            server=server,
        ):
            raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")

        self.max_orders = max_orders
        self.deviation = trade_deviation
        self.magic_number = magic_number
        self.filling = filling

    def close_connection(self):
        mt5.shutdown()

    def get_pip_size(self, info) -> float:
        """Calculates the absolute price value of 1 Pip for any given symbol."""
        # Forex JPY pairs or Gold/Silver often use 2 or 3 digits
        # Standard Forex pairs use 4 or 5 digits
        if info.digits in (2, 4):
            return info.point
        return info.point * 10

    def _norm(self, value: Optional[float], point: float) -> Optional[float]:
        if value is None:
            return None
        return round(round(value / point) * point, 8)

    def _order_type_and_action(
        self, is_buy: bool, price: float, market_norm: float
    ) -> Tuple[int, int]:
        """Pick the MT5 request action + order type for a single order.

        price == current market -> immediate market execution (DEAL).
        Otherwise it's a resting order (PENDING), chosen as LIMIT if the price
        is better than market or STOP if it's worse - not STOP_LIMIT, which is
        a distinct two-price order type this code doesn't populate.
        """
        if price == market_norm:
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            return mt5.TRADE_ACTION_DEAL, order_type

        if is_buy:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if price < market_norm else mt5.ORDER_TYPE_BUY_STOP
        else:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT if price > market_norm else mt5.ORDER_TYPE_SELL_STOP
        return mt5.TRADE_ACTION_PENDING, order_type

    def _open_orders(self, order: OrderMT5):
        info = mt5.symbol_info(order.symbol)
        if info is None:
            raise ValueError(f"Unknown symbol: {order.symbol}")
        if not info.visible and not mt5.symbol_select(order.symbol, True):
            raise ValueError(f"Failed to select symbol {order.symbol}")

        tick = mt5.symbol_info_tick(order.symbol)
        if tick is None:
            raise ValueError(f"No tick data for {order.symbol} (market closed?)")
        market = tick.ask if order.direction == "BUY" else tick.bid
        market_norm = self._norm(market, info.point)

        # No entry price -> execute instantly at market price. The price is
        # replicated when SL/TP spans multiple levels so each gets its own order.
        if order.price is None:
            order.price = PriceSignal(
                price=plan_market_entries(market, order.sl, order.tp, self.max_orders),
                unit="price",
                type="multiple",
            )

        orders = build_order_prices(
            order.price, order.sl, order.tp,
            order.direction, self.get_pip_size(info), self.max_orders,
        )

        step = info.volume_step or 0.01
        capacity = max(1, int(round(order.volume / step)))
        if len(orders) > capacity:
            logger.warning(
                "Volume {} only funds {} orders; skipping the rest",
                order.volume, capacity,
            )
            orders = orders[:capacity]
        volumes = split_volume(order.volume, len(orders), step)

        for i, (o, volume) in enumerate(zip(orders, volumes)):
            price = self._norm(o["price"], info.point)
            is_buy = order.direction == "BUY"

            action, order_type = self._order_type_and_action(is_buy, price, market_norm)

            request = {
                "action": action,
                "symbol": order.symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": self._norm(o["sl"], info.point),
                "tp": self._norm(o["tp"], info.point),
                "deviation": int(self.deviation),
                "magic": self.magic_number,
                "comment": order.comment,
                "type_time": order.type_time,
                "type_filling": self.filling,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error("Order {}/{} failed: {}", i + 1, len(orders), result)
            else:
                logger.info(
                    "{} {} {} @ {} [SL={} TP={}]",
                    order.direction, volume, order.symbol, price, o["sl"], o["tp"],
                )

    def _close_positions(self, order: TradeOrder, symbol: str):
        """Market-closes open positions. id=None closes every position on the symbol."""
        for pos in mt5.positions_get(symbol=symbol) or ():
            if order.id is not None and str(order.id) not in (pos.comment or ""):
                continue

            is_buy_pos = pos.type == mt5.POSITION_TYPE_BUY
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy_pos else mt5.ORDER_TYPE_BUY,
                "position": pos.ticket,
                "price": pos.bid if is_buy_pos else pos.ask,
                "deviation": int(self.deviation),
                "magic": self.magic_number,
                "comment": "close",
                "type_filling": self.filling,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error("Failed to close position {}: {}", pos.ticket, result)
            else:
                logger.info("Closed position {}", pos.ticket)

    def _cancel_order(self, order: TradeOrder, symbol: str):
        """Removes pending limit orders whose comment carries the order id."""
        self._remove_pending(order.id, symbol)

    def _cancel_all_orders(self, order: TradeOrder, symbol: str):
        self._remove_pending(None, symbol)

    def _remove_pending(self, order_id: Optional[int], symbol: str):
        for pending in mt5.orders_get(symbol=symbol) or ():
            if order_id is not None and str(order_id) not in (pending.comment or ""):
                continue

            result = mt5.order_send(
                {"action": mt5.TRADE_ACTION_REMOVE, "order": pending.ticket}
            )
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error("Failed to cancel order {}: {}", pending.ticket, result)
            else:
                logger.info("Cancelled pending order {}", pending.ticket)

    def place_order(self, order: TradeOrder, symbol: str):
        parsed = order.order
        comment = f"tse:{order.id}"

        match parsed.action:
            case SignalAction.BUY | SignalAction.SELL:
                self._open_orders(
                    OrderMT5(
                        symbol=symbol,
                        volume=parsed.size,
                        direction=parsed.action.value,
                        price=parsed.entry,
                        sl=parsed.stop_loss,
                        tp=parsed.take_profit,
                        comment=comment,
                    )
                )

            case SignalAction.CLOSE:
                self._close_positions(order, symbol)

            case SignalAction.CANCEL:
                self._cancel_order(order, symbol)


if __name__ == "__main__":
    trader = MT5Trader(
        os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        int(os.environ["MT5_LOGIN"]),
        os.environ["MT5_PASSWORD"],
        os.environ["MT5_SERVER"],
    )

    try:
        trader.place_order(
            TradeOrder(
                id=1,
                order=ParsedData(
                    resp_time=25.0,
                    size=0.03,
                    action=SignalAction.CANCEL,
                    entry=PriceSignal(price=[3900, 3950], unit="price", type="range"),
                    take_profit=PriceSignal(price=[3800, 3850], unit="price", type="range"),
                    stop_loss=PriceSignal(price=[4500, 4600], unit="price", type="range")
                ),
            ),
            symbol="XAUUSDm",
        )
    finally:
        trader.close_connection()