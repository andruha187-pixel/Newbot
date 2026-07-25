import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

from config import DB_FILE

_LOCK = threading.RLock()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


@contextmanager
def transaction():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    with _LOCK, transaction() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_key TEXT NOT NULL UNIQUE,
                wallet TEXT NOT NULL,
                transaction_hash TEXT,
                timestamp INTEGER NOT NULL,
                detected_timestamp REAL NOT NULL,
                api_delay_seconds REAL NOT NULL,
                datetime_utc TEXT NOT NULL,
                side TEXT NOT NULL,
                outcome TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                usdc_value REAL NOT NULL,
                title TEXT,
                slug TEXT,
                event_slug TEXT,
                condition_id TEXT,
                asset_id TEXT,
                outcome_index INTEGER,
                coin TEXT,
                market_start_timestamp INTEGER,
                market_end_timestamp INTEGER,
                market_second INTEGER,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_key TEXT NOT NULL UNIQUE,
                wallet TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                datetime_utc TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                transaction_hash TEXT,
                condition_id TEXT,
                asset_id TEXT,
                side TEXT,
                outcome TEXT,
                price REAL,
                size REAL,
                usdc_value REAL,
                title TEXT,
                slug TEXT,
                event_slug TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS markets (
                condition_id TEXT PRIMARY KEY,
                title TEXT,
                slug TEXT,
                event_slug TEXT,
                coin TEXT,
                start_timestamp INTEGER,
                end_timestamp INTEGER,
                up_token_id TEXT,
                down_token_id TEXT,
                closed INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                winner TEXT,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                datetime_utc TEXT NOT NULL,
                condition_id TEXT NOT NULL,
                coin TEXT,
                market_second REAL,
                reference_price REAL,
                reference_change_1s REAL,
                reference_change_5s REAL,
                reference_change_15s REAL,
                reference_change_30s REAL,
                up_best_bid REAL,
                up_best_ask REAL,
                up_mid REAL,
                up_spread REAL,
                up_bid_size REAL,
                up_ask_size REAL,
                down_best_bid REAL,
                down_best_ask REAL,
                down_mid REAL,
                down_spread REAL,
                down_bid_size REAL,
                down_ask_size REAL,
                FOREIGN KEY(condition_id) REFERENCES markets(condition_id)
            );

            CREATE TABLE IF NOT EXISTS reference_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp REAL NOT NULL,
                datetime_utc TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL,
                trade_id TEXT,
                UNIQUE(symbol, trade_id)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                condition_id TEXT PRIMARY KEY,
                title TEXT,
                coin TEXT,
                start_timestamp INTEGER,
                end_timestamp INTEGER,
                closed INTEGER NOT NULL DEFAULT 0,
                winner TEXT,
                trade_count INTEGER NOT NULL DEFAULT 0,
                buy_count INTEGER NOT NULL DEFAULT 0,
                sell_count INTEGER NOT NULL DEFAULT 0,
                up_bought REAL NOT NULL DEFAULT 0,
                up_sold REAL NOT NULL DEFAULT 0,
                up_remaining REAL NOT NULL DEFAULT 0,
                down_bought REAL NOT NULL DEFAULT 0,
                down_sold REAL NOT NULL DEFAULT 0,
                down_remaining REAL NOT NULL DEFAULT 0,
                buy_cost REAL NOT NULL DEFAULT 0,
                sell_revenue REAL NOT NULL DEFAULT 0,
                cash_flow REAL NOT NULL DEFAULT 0,
                pnl_if_up REAL,
                pnl_if_down REAL,
                realized_pnl REAL,
                first_trade_second INTEGER,
                last_trade_second INTEGER,
                switches INTEGER NOT NULL DEFAULT 0,
                max_streak INTEGER NOT NULL DEFAULT 0,
                strategy_type TEXT,
                final_position TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
            CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activities(timestamp);
            CREATE INDEX IF NOT EXISTS idx_activity_condition ON activities(condition_id);
            CREATE INDEX IF NOT EXISTS idx_snapshots_condition_time ON snapshots(condition_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_reference_symbol_time ON reference_prices(symbol, timestamp);
            """
        )


def execute(query: str, params: Iterable[Any] = ()) -> int:
    with _LOCK, transaction() as con:
        cursor = con.execute(query, tuple(params))
        return cursor.rowcount


def fetch_one(query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with _LOCK, transaction() as con:
        row = con.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None


def fetch_all(query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with _LOCK, transaction() as con:
        rows = con.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def insert_trade(row: dict[str, Any]) -> bool:
    columns = [
        "trade_key", "wallet", "transaction_hash", "timestamp",
        "detected_timestamp", "api_delay_seconds", "datetime_utc",
        "side", "outcome", "price", "size", "usdc_value", "title",
        "slug", "event_slug", "condition_id", "asset_id",
        "outcome_index", "coin", "market_start_timestamp",
        "market_end_timestamp", "market_second", "raw_json",
    ]
    sql = (
        f"INSERT OR IGNORE INTO trades ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})"
    )
    return execute(sql, [row.get(column) for column in columns]) > 0


def insert_activity(row: dict[str, Any]) -> bool:
    columns = [
        "activity_key", "wallet", "timestamp", "datetime_utc",
        "activity_type", "transaction_hash", "condition_id", "asset_id",
        "side", "outcome", "price", "size", "usdc_value", "title",
        "slug", "event_slug", "raw_json",
    ]
    sql = (
        f"INSERT OR IGNORE INTO activities ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})"
    )
    return execute(sql, [row.get(column) for column in columns]) > 0


def upsert_market(row: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO markets (
            condition_id,title,slug,event_slug,coin,start_timestamp,end_timestamp,
            up_token_id,down_token_id,closed,resolved,winner,first_seen,last_seen,raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(condition_id) DO UPDATE SET
            title=excluded.title, slug=excluded.slug, event_slug=excluded.event_slug,
            coin=excluded.coin, start_timestamp=COALESCE(excluded.start_timestamp,markets.start_timestamp),
            end_timestamp=COALESCE(excluded.end_timestamp,markets.end_timestamp),
            up_token_id=COALESCE(excluded.up_token_id,markets.up_token_id),
            down_token_id=COALESCE(excluded.down_token_id,markets.down_token_id),
            closed=excluded.closed, resolved=excluded.resolved,
            winner=COALESCE(excluded.winner,markets.winner),
            last_seen=excluded.last_seen, raw_json=excluded.raw_json
        """,
        (
            row.get("condition_id"), row.get("title"), row.get("slug"),
            row.get("event_slug"), row.get("coin"), row.get("start_timestamp"),
            row.get("end_timestamp"), row.get("up_token_id"),
            row.get("down_token_id"), int(bool(row.get("closed"))),
            int(bool(row.get("resolved"))), row.get("winner"),
            row.get("first_seen"), row.get("last_seen"), row.get("raw_json"),
        ),
    )


def insert_snapshot(row: dict[str, Any]) -> bool:
    columns = [
        "timestamp", "datetime_utc", "condition_id", "coin", "market_second",
        "reference_price", "reference_change_1s", "reference_change_5s",
        "reference_change_15s", "reference_change_30s", "up_best_bid",
        "up_best_ask", "up_mid", "up_spread", "up_bid_size", "up_ask_size",
        "down_best_bid", "down_best_ask", "down_mid", "down_spread",
        "down_bid_size", "down_ask_size",
    ]
    sql = f"INSERT INTO snapshots ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
    return execute(sql, [row.get(column) for column in columns]) > 0


def insert_reference_price(row: dict[str, Any]) -> bool:
    return execute(
        """
        INSERT OR IGNORE INTO reference_prices
        (symbol,timestamp,datetime_utc,price,quantity,trade_id)
        VALUES (?,?,?,?,?,?)
        """,
        (
            row.get("symbol"), row.get("timestamp"), row.get("datetime_utc"),
            row.get("price"), row.get("quantity"), row.get("trade_id"),
        ),
    ) > 0


def upsert_analysis(row: dict[str, Any]) -> None:
    columns = [
        "condition_id", "title", "coin", "start_timestamp", "end_timestamp",
        "closed", "winner", "trade_count", "buy_count", "sell_count",
        "up_bought", "up_sold", "up_remaining", "down_bought", "down_sold",
        "down_remaining", "buy_cost", "sell_revenue", "cash_flow",
        "pnl_if_up", "pnl_if_down", "realized_pnl", "first_trade_second",
        "last_trade_second", "switches", "max_streak", "strategy_type",
        "final_position", "updated_at",
    ]
    assignments = ",".join(f"{c}=excluded.{c}" for c in columns[1:])
    sql = (
        f"INSERT INTO analyses ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)}) "
        f"ON CONFLICT(condition_id) DO UPDATE SET {assignments}"
    )
    execute(sql, [row.get(column) for column in columns])


def set_state(key: str, value: str) -> None:
    execute(
        "INSERT INTO system_state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_state(key: str, default: str = "") -> str:
    row = fetch_one("SELECT value FROM system_state WHERE key=?", (key,))
    return str(row["value"]) if row else default


def statistics() -> dict[str, int]:
    result = {}
    for table in ("trades", "activities", "markets", "snapshots", "reference_prices", "analyses"):
        row = fetch_one(f"SELECT COUNT(*) AS count FROM {table}")
        result[table] = int(row["count"]) if row else 0
    return result
