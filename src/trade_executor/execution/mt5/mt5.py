from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

import MetaTrader5 as mt5
from loguru import logger
from pydantic import BaseModel

from db.repositories.store_orders import OrderRepository
from trade_executor.execution import TradeExecutor, TradeOrder
from trade_executor.execution.mt5.order_math import (
    build_order_prices,
    plan_market_entries,
    split_volume,
)
from trade_executor.parser.base import ParsedData, PriceSignal, SignalAction

# Every order/position we open is tagged "tse:<id>" in its comment for
# human-readable identification in the MT5 terminal.  Programmatic matching
# is done via the DB (OrderRepository), NOT by scanning comments.
COMMENT_PREFIX = "tse"


def _tag(order_id: int) -> str:
    return f"{COMMENT_PREFIX}:{order_id}"

    
def _single_price(signal: PriceSignal) -> float:
    """Reduce a PriceSignal to one concrete price, for a SL/TP/entry update."""
    price = signal.price
    if isinstance(price, (list, tuple)):
        if not price:
            raise ValueError("Update signal has an empty price list")
        return float(price[0])
    return float(price)


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

    # ---------------------------------------------------------------- prices

    def get_pip_size(self, info) -> float:
        """Absolute price value of 1 pip for a symbol (JPY/metals-aware)."""
        if info.digits in (2, 4):
            return info.point
        return info.point * 10

    def _norm(self, value: float | None, point: float) -> float | None:
        if value is None:
            return None
        return round(round(value / point) * point, 8)

    def _order_type_and_action(
        self, is_buy: bool, price: float, market_norm: float
    ) -> tuple[int, int]:
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
            order_type = (
                mt5.ORDER_TYPE_BUY_LIMIT
                if price < market_norm
                else mt5.ORDER_TYPE_BUY_STOP
            )
        else:
            order_type = (
                mt5.ORDER_TYPE_SELL_LIMIT
                if price > market_norm
                else mt5.ORDER_TYPE_SELL_STOP
            )
        return mt5.TRADE_ACTION_PENDING, order_type

    # -------------------------------------------------------------- plumbing

    def _send(self, request: dict, description: str) -> int | None:
        """Single choke point for order_send + result logging.

        Returns the MT5 ticket (``result.order``) on success, or ``None``.
        """
        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            logger.error("{} failed (result=None, last_error={}): request={}", description, err, request)
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("{} failed (retcode={}): {}", description, result.retcode, result)
            return None
        logger.info("{} ok: {}", description, result)
        return result.order

    def _ready_symbol(self, symbol: str):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"Unknown symbol: {symbol}")
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise ValueError(f"Failed to select symbol {symbol}")
        return info

    def _tick(self, symbol: str):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"No tick data for {symbol} (market closed?)")
        return tick

    # ------------------------------------------------------------------ open

    def _get_filling_type(self, info) -> int:
        """Pick a supported filling mode for the symbol (FOK / IOC / RETURN)."""
        filling_flags = getattr(info, "filling_mode", 0)
        if filling_flags & 1:
            return mt5.ORDER_FILLING_FOK
        if filling_flags & 2:
            return mt5.ORDER_FILLING_IOC
        return self.filling

    def _open_orders(self, order: OrderMT5) -> list[int]:
        """Place one or more MT5 orders and return the list of assigned tickets."""
        info = self._ready_symbol(order.symbol)
        tick = self._tick(order.symbol)
        market = tick.ask if order.direction == "BUY" else tick.bid
        market_norm = self._norm(market, info.point)

        # No entry price -> execute instantly at market price. The price is
        # replicated when SL/TP spans multiple levels so each gets its own order.
        entry_signal = order.price
        if entry_signal is None:
            entry_signal = PriceSignal(
                price=plan_market_entries(market, order.sl, order.tp, self.max_orders),
                unit="price",
                type="multiple",
            )

        orders = build_order_prices(
            entry_signal,
            order.sl,
            order.tp,
            order.direction,
            self.get_pip_size(info),
            self.max_orders,
        )

        step = info.volume_step or 0.01
        capacity = max(1, int(round(order.volume / step)))
        if len(orders) > capacity:
            logger.warning(
                "Volume {} only funds {} orders; skipping the rest",
                order.volume,
                capacity,
            )
            orders = orders[:capacity]
        volumes = split_volume(order.volume, len(orders), step)

        is_buy = order.direction == "BUY"
        filling_mode = self._get_filling_type(info)
        tickets: list[int] = []
        for i, (o, volume) in enumerate(zip(orders, volumes)):
            price = self._norm(o["price"], info.point)
            action, order_type = self._order_type_and_action(is_buy, price, market_norm)

            request = {
                "action": action,
                "symbol": order.symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": self._norm(o["sl"], info.point) or 0.0,
                "tp": self._norm(o["tp"], info.point) or 0.0,
                "deviation": int(self.deviation),
                "magic": self.magic_number,
                "comment": order.comment,
                "type_time": order.type_time,
                "type_filling": filling_mode,
            }
            ticket = self._send(
                request,
                f"Open {order.direction} {volume} {order.symbol} {i + 1}/{len(orders)} @ {price}",
            )
            if ticket is not None:
                tickets.append(ticket)

        return tickets

    # ------------------------------------------------------------- close/cancel

    def _close_positions(self, tickets: list[int], symbol: str):
        """Market-close open positions identified by their MT5 tickets."""
        if not tickets:
            logger.warning("No tickets to close on {}", symbol)
            return

        info = self._ready_symbol(symbol)
        tick = self._tick(symbol)
        filling_mode = self._get_filling_type(info)
        for ticket in tickets:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                logger.debug("Ticket {} is not an open position (may already be closed)", ticket)
                continue

            pos = positions[0]
            is_buy_pos = pos.type == mt5.POSITION_TYPE_BUY
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy_pos else mt5.ORDER_TYPE_BUY,
                "position": pos.ticket,
                "price": tick.bid if is_buy_pos else tick.ask,
                "deviation": int(self.deviation),
                "magic": self.magic_number,
                "comment": "close",
                "type_filling": filling_mode,
            }
            self._send(request, f"Close position {pos.ticket}")

    def _cancel_orders(self, tickets: list[int], symbol: str):
        """Remove pending orders identified by their MT5 tickets."""
        if not tickets:
            logger.warning("No tickets to cancel on {}", symbol)
            return

        for ticket in tickets:
            pending = mt5.orders_get(ticket=ticket)
            if not pending:
                logger.debug("Ticket {} is not a pending order (may already be filled/removed)", ticket)
                continue

            self._send(
                {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket},
                f"Cancel order {ticket}",
            )

    # ------------------------------------------------------------------ update

    def _update_orders(self, tickets: list[int], symbol: str, parsed: ParsedData):
        """Apply a signal update to positions/orders identified by tickets.

        - Open positions: only SL/TP can move -> TRADE_ACTION_SLTP.
        - Pending orders: price/SL/TP can all move -> TRADE_ACTION_MODIFY.
        """
        if not tickets:
            logger.warning("No tickets to update on {}", symbol)
            return

        info = self._ready_symbol(symbol)
        point = info.point

        new_sl = (
            self._norm(_single_price(parsed.stop_loss), point)
            if parsed.stop_loss is not None
            else None
        )
        new_tp = (
            self._norm(_single_price(parsed.take_profit), point)
            if parsed.take_profit is not None
            else None
        )
        new_entry = (
            self._norm(_single_price(parsed.entry), point)
            if parsed.entry is not None
            else None
        )

        for ticket in tickets:
            # Try as position first
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                pos = positions[0]
                if new_entry is not None:
                    logger.warning(
                        "Update includes a new entry price, but position {} is already "
                        "filled -- only its SL/TP will move.",
                        pos.ticket,
                    )
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": new_sl if new_sl is not None else pos.sl,
                    "tp": new_tp if new_tp is not None else pos.tp,
                }
                self._send(request, f"Update position {pos.ticket}")
                continue

            # Try as pending order
            pending = mt5.orders_get(ticket=ticket)
            if pending:
                p = pending[0]
                request = {
                    "action": mt5.TRADE_ACTION_MODIFY,
                    "order": p.ticket,
                    "price": new_entry if new_entry is not None else p.price_open,
                    "sl": new_sl if new_sl is not None else p.sl,
                    "tp": new_tp if new_tp is not None else p.tp,
                    "type_time": p.type_time,
                    "expiration": p.time_expiration,
                }
                self._send(request, f"Update order {p.ticket}")
                continue

            logger.warning("Ticket {} not found as position or pending order", ticket)

    # --------------------------------------------------------------- dispatch

    def place_order(
        self,
        order: TradeOrder,
        symbol: str,
        order_repo: OrderRepository | None = None,
    ):
        parsed = order.order
        comment = _tag(order.id)

        match parsed.action:
            case SignalAction.BUY | SignalAction.SELL:
                tickets = self._open_orders(
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
                # Record tickets in DB for later cancel/close/update
                if order_repo is not None:
                    for ticket in tickets:
                        order_repo.record_order(
                            signal_id=order.id,
                            ticket=ticket,
                            symbol=symbol,
                            direction=parsed.action.value,
                            volume=parsed.size,
                            action=parsed.action.value,
                            comment=comment,
                        )

            case SignalAction.CLOSE:
                tickets = (
                    order_repo.get_tickets_by_signal(order.id)
                    if order_repo is not None
                    else []
                )
                if not tickets:
                    logger.warning(
                        "No tickets found in DB for signal_id={} — cannot close", order.id
                    )
                    return
                self._close_positions(tickets, symbol)
                if order_repo is not None:
                    for t in tickets:
                        order_repo.update_status(t, "CLOSED")

            case SignalAction.CANCEL:
                tickets = (
                    order_repo.get_tickets_by_signal(order.id)
                    if order_repo is not None
                    else []
                )
                if not tickets:
                    logger.warning(
                        "No tickets found in DB for signal_id={} — cannot cancel", order.id
                    )
                    return
                self._cancel_orders(tickets, symbol)
                if order_repo is not None:
                    for t in tickets:
                        order_repo.update_status(t, "CANCELLED")

            case SignalAction.UPDATE:
                tickets = (
                    order_repo.get_tickets_by_signal(order.id)
                    if order_repo is not None
                    else []
                )
                if not tickets:
                    logger.warning(
                        "No tickets found in DB for signal_id={} — cannot update", order.id
                    )
                    return
                self._update_orders(tickets, symbol, parsed)

            case SignalAction.IGNORE:
                logger.info(
                    "Action {} requires no order placement; skipping",
                    parsed.action.value,
                )


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
                    take_profit=PriceSignal(
                        price=[3800, 3850], unit="price", type="range"
                    ),
                    stop_loss=PriceSignal(
                        price=[4500, 4600], unit="price", type="range"
                    ),
                ),
            ),
            symbol="XAUUSDm",
        )
    finally:
        trader.close_connection()
