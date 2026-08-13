from __future__ import annotations

from db.connection import BaseDatabase


class OrderRepository:
    """CRUD operations for the ``orders`` table."""

    def __init__(self, db: BaseDatabase):
        self._db = db

    def record_order(
        self,
        *,
        signal_id: int,
        ticket: int,
        symbol: str,
        direction: str,
        volume: float,
        action: str,
        comment: str = "",
    ) -> int | None:
        """Insert a new order record and return its auto-generated id."""
        self._db.execute(
            "INSERT INTO orders (signal_id, ticket, symbol, direction, volume, action, comment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (signal_id, ticket, symbol, direction, volume, action, comment),
        )
        return self._db.last_insert_id()

    def get_tickets_by_signal(self, signal_id: int, status: str = "OPEN") -> list[int]:
        """Return MT5 ticket numbers for a given signal message id."""
        rows = self._db.fetch_all(
            "SELECT ticket FROM orders WHERE signal_id = ? AND status = ?",
            (signal_id, status),
        )
        return [r["ticket"] for r in rows]

    def get_open_orders(
        self,
        signal_id: int | None = None,
        symbol: str | None = None,
    ) -> list[dict]:
        """Return open order records, optionally filtered."""
        clauses: list[str] = ["status = 'OPEN'"]
        params: list = []

        if signal_id is not None:
            clauses.append("signal_id = ?")
            params.append(signal_id)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)

        where = " AND ".join(clauses)
        return self._db.fetch_all(
            f"SELECT * FROM orders WHERE {where}",
            tuple(params),
        )

    def update_status(self, ticket: int, status: str) -> None:
        """Update the status of an order by its MT5 ticket."""
        self._db.execute(
            "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE ticket = ?",
            (status, ticket),
        )
