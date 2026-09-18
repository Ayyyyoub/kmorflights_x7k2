"""SQLite state: remembers the lowest price seen per route so we only alert
on genuinely new/better deals, not the same price every run.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS best_price (
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    best_price REAL NOT NULL,
    currency TEXT NOT NULL,
    last_alerted_price REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (origin, destination)
);
"""


@contextmanager
def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.commit()
        yield conn
    finally:
        conn.close()


def get_best(conn: sqlite3.Connection, origin: str, destination: str) -> tuple[float, float | None] | None:
    row = conn.execute(
        "SELECT best_price, last_alerted_price FROM best_price WHERE origin=? AND destination=?",
        (origin, destination),
    ).fetchone()
    return tuple(row) if row else None


def upsert_best(
    conn: sqlite3.Connection,
    origin: str,
    destination: str,
    price: float,
    currency: str,
    alerted: bool,
    now_iso: str,
) -> None:
    existing = get_best(conn, origin, destination)
    if existing is None:
        conn.execute(
            "INSERT INTO best_price (origin, destination, best_price, currency, last_alerted_price, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (origin, destination, price, currency, price if alerted else None, now_iso),
        )
    else:
        last_alerted = price if alerted else existing[1]
        conn.execute(
            "UPDATE best_price SET best_price=?, currency=?, last_alerted_price=?, updated_at=? "
            "WHERE origin=? AND destination=?",
            (price, currency, last_alerted, now_iso, origin, destination),
        )
    conn.commit()
