from collections.abc import Generator, Iterable
from typing import Any

from trade_executor.parser.base import PriceSignal


def linspace(
    start_number: float, end_number: float, count: int
) -> Generator[float, None, None]:
    if count <= 0:
        return
    if count == 1:
        yield start_number
        return
    step = (end_number - start_number) / (count - 1)
    for i in range(count):
        yield start_number + step * i


def _expand(signal: PriceSignal, max_orders: int) -> Iterable[float]:
    """Expand a PriceSignal into an ordered iterable of raw values."""
    if signal.type == "range":
        lo, hi = signal.price[0], signal.price[1]
        return linspace(lo, hi, max_orders)
    if isinstance(signal.price, (list, tuple)):
        return iter(signal.price)
    return iter([signal.price])


def split_volume(volume: float, parts: int, step: float = 0.01) -> list[float]:
    """Split a lot into step-aligned chunks; the remainder goes to the last order.
    e.g. volume=0.04, parts=3, step=0.01 -> [0.01, 0.01, 0.02].
    `parts` is clamped so no chunk falls below one `step`.
    """
    total_steps = max(1, int(round(volume / step)))
    parts = max(1, min(parts, total_steps))
    base = round((total_steps // parts) * step, 8)
    return [base] * (parts - 1) + [round(volume - base * (parts - 1), 8)]


def plan_market_entries(
    market: float,
    sl: PriceSignal | None,
    tp: PriceSignal | None,
    max_orders: int,
) -> list[float]:
    """Entry prices for a market execution.
    The market price is replicated when SL or TP spans multiple levels
    (type != "single") so each level becomes its own order.
    """
    split = any(s is not None and s.type != "single" for s in (sl, tp))
    return [market] * max_orders if split else [market]


def resolve_prices(
    signal: PriceSignal | None,
    pivot: float | None,
    sign: int,
    pip_size: float,
    max_orders: int = 3,
) -> list[float]:
    if signal is None:
        return []
    values = list(_expand(signal, max_orders))
    if signal.unit == "pips":
        if pivot is None:
            raise ValueError("pips-based SL/TP requires a pivot (entry) price")
        values = [pivot + sign * pip_size * v for v in values]
    return values


def build_order_prices(
    entry: PriceSignal | None,
    sl: PriceSignal | None,
    tp: PriceSignal | None,
    direction: str,
    pip_size: float,
    max_orders: int = 3,
) -> list[dict[str, Any]]:
    is_buy = direction == "BUY"
    # BUY: SL is below (-), TP is above (+)
    # SELL: SL is above (+), TP is below (-)
    sl_sign = -1 if is_buy else +1
    tp_sign = +1 if is_buy else -1

    entries = resolve_prices(entry, None, +1, pip_size, max_orders)
    if not entries:
        raise ValueError("entry PriceSignal is required")

    # SL/TP given as absolute prices don't depend on entry_price, so they come
    # out identical on every loop iteration - resolve once instead of
    # re-expanding (re-running linspace, etc.) per entry. Only "pips"-based
    # SL/TP genuinely need per-entry resolution, since they're relative to
    # entry_price.
    sl_is_pips = sl is not None and sl.unit == "pips"
    tp_is_pips = tp is not None and tp.unit == "pips"
    sl_fixed = None if sl_is_pips else resolve_prices(sl, None, sl_sign, pip_size, max_orders)
    tp_fixed = None if tp_is_pips else resolve_prices(tp, None, tp_sign, pip_size, max_orders)

    orders = []
    for i, entry_price in enumerate(entries):
        sl_list = (
            resolve_prices(sl, entry_price, sl_sign, pip_size, max_orders)
            if sl_is_pips
            else sl_fixed
        )
        tp_list = (
            resolve_prices(tp, entry_price, tp_sign, pip_size, max_orders)
            if tp_is_pips
            else tp_fixed
        )

        # Fallback to index matching or global fallback
        sl_val = sl_list[i] if i < len(sl_list) else (sl_list[0] if sl_list else None)
        tp_val = tp_list[i] if i < len(tp_list) else (tp_list[0] if tp_list else None)

        orders.append(
            {
                "direction": direction,
                "price": entry_price,
                "sl": sl_val,
                "tp": tp_val,
            }
        )
    return orders