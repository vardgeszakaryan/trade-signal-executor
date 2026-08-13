CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     INTEGER NOT NULL,
    ticket        INTEGER NOT NULL,
    symbol        TEXT    NOT NULL,
    direction     TEXT    NOT NULL,
    volume        REAL    NOT NULL,
    action        TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'OPEN',
    comment       TEXT    DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_signal_id ON orders(signal_id);
CREATE INDEX IF NOT EXISTS idx_orders_ticket    ON orders(ticket);
CREATE INDEX IF NOT EXISTS idx_orders_status    ON orders(status);