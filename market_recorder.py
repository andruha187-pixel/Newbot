import logging
import threading
import time
from collections import deque
from typing import Any

import websocket

from config import BINANCE_WS_URL
from database import (
    fetch_all, fetch_one, insert_reference_price, insert_snapshot, upsert_market,
)
from polymarket_client import fetch_active_events, fetch_books, fetch_event_by_slug, fetch_market_by_condition
from utils import decode_list, detect_coin, json_text, safe_float, safe_int, utc_iso

logger = logging.getLogger("MARKET_RECORDER")

_LOCK = threading.RLock()
_STOP = threading.Event()
_CURRENT: dict[str, dict[str, Any]] = {}
_LATEST: dict[str, tuple[float, float]] = {}
_HISTORY: dict[str, deque[tuple[float, float]]] = {
    "BTC": deque(maxlen=20000),
    "ETH": deque(maxlen=20000),
}


def _parse_market(market: dict[str, Any], event: dict[str, Any] | None = None) -> dict[str, Any] | None:
    condition_id = market.get("conditionId") or market.get("condition_id")
    if not condition_id:
        return None

    title = market.get("question") or market.get("title") or (event or {}).get("title")
    slug = market.get("slug")
    event_slug = (event or {}).get("slug") or market.get("eventSlug")
    coin = detect_coin(title, slug, event_slug)
    if coin not in {"BTC", "ETH"}:
        return None

    outcomes = [str(x).upper() for x in decode_list(market.get("outcomes"))]
    tokens = [str(x) for x in decode_list(market.get("clobTokenIds"))]
    up_token = down_token = None
    for index, outcome in enumerate(outcomes):
        if index >= len(tokens):
            continue
        if outcome in {"UP", "YES"}:
            up_token = tokens[index]
        elif outcome in {"DOWN", "NO"}:
            down_token = tokens[index]
    if not up_token and len(tokens) >= 1:
        up_token = tokens[0]
    if not down_token and len(tokens) >= 2:
        down_token = tokens[1]

    start = None
    end = None
    for value in (market.get("startDate"), (event or {}).get("startDate")):
        if isinstance(value, str):
            try:
                from datetime import datetime
                start = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
                break
            except ValueError:
                pass
    for value in (market.get("endDate"), (event or {}).get("endDate")):
        if isinstance(value, str):
            try:
                from datetime import datetime
                end = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
                break
            except ValueError:
                pass

    # Для крипто-5m Gamma иногда не даёт точное начало. Восстанавливаем по концу.
    if end and not start:
        start = end - 300
    if start and not end:
        end = start + 300

    prices = decode_list(market.get("outcomePrices"))
    winner = None
    if len(prices) >= 2:
        numeric = [safe_float(x, -1) for x in prices]
        if max(numeric) >= 0.99:
            winner = "UP" if numeric[0] > numeric[1] else "DOWN"

    now = time.time()
    return {
        "condition_id": str(condition_id),
        "title": title,
        "slug": slug,
        "event_slug": event_slug,
        "coin": coin,
        "start_timestamp": start,
        "end_timestamp": end,
        "up_token_id": up_token,
        "down_token_id": down_token,
        "closed": bool(market.get("closed") or (event or {}).get("closed")),
        "resolved": winner is not None,
        "winner": winner,
        "first_seen": now,
        "last_seen": now,
        "raw_json": json_text({"event": event, "market": market}),
    }


def discover_from_recent_trades() -> None:
    rows = fetch_all(
        """
        SELECT condition_id, event_slug FROM trades
        WHERE condition_id IS NOT NULL
        GROUP BY condition_id ORDER BY MAX(timestamp) DESC LIMIT 20
        """
    )
    for row in rows:
        condition_id = row["condition_id"]
        if fetch_one("SELECT condition_id FROM markets WHERE condition_id=?", (condition_id,)):
            continue
        market = None
        try:
            raw = fetch_market_by_condition(condition_id)
            if raw:
                market = _parse_market(raw)
            if not market and row.get("event_slug"):
                event = fetch_event_by_slug(row["event_slug"])
                for candidate in (event or {}).get("markets", []):
                    parsed = _parse_market(candidate, event)
                    if parsed and parsed["condition_id"] == condition_id:
                        market = parsed
                        break
        except Exception as exc:
            logger.warning("Market lookup failed %s: %s", condition_id, exc)
        if market:
            upsert_market(market)


def discover_active_markets() -> None:
    try:
        events = fetch_active_events(200)
    except Exception as exc:
        logger.warning("Active event discovery failed: %s", exc)
        return
    now = time.time()
    found: dict[str, dict[str, Any]] = {}
    for event in events:
        for raw_market in event.get("markets", []):
            if not isinstance(raw_market, dict):
                continue
            parsed = _parse_market(raw_market, event)
            if not parsed or not parsed.get("up_token_id") or not parsed.get("down_token_id"):
                continue
            start = parsed.get("start_timestamp")
            end = parsed.get("end_timestamp")
            if start and end and not (start - 120 <= now <= end + 120):
                continue
            found[parsed["coin"]] = parsed
            upsert_market(parsed)
    with _LOCK:
        _CURRENT.update(found)


def refresh_markets() -> None:
    discover_from_recent_trades()
    discover_active_markets()
    now = time.time()
    rows = fetch_all(
        """
        SELECT * FROM markets
        WHERE closed=0 AND (end_timestamp IS NULL OR end_timestamp>=?)
        ORDER BY last_seen DESC
        """,
        (int(now) - 120,),
    )
    with _LOCK:
        for row in rows:
            if row.get("up_token_id") and row.get("down_token_id"):
                _CURRENT[row["coin"]] = row


def _book_summary(book: dict[str, Any] | None) -> dict[str, float | None]:
    if not book:
        return {"bid": None, "ask": None, "mid": None, "spread": None, "bid_size": None, "ask_size": None}
    bids = [
        (safe_float(level.get("price")), safe_float(level.get("size")))
        for level in book.get("bids", []) if isinstance(level, dict)
    ]
    asks = [
        (safe_float(level.get("price")), safe_float(level.get("size")))
        for level in book.get("asks", []) if isinstance(level, dict)
    ]
    bid = max((p for p, _ in bids), default=None)
    ask = min((p for p, _ in asks), default=None)
    return {
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2 if bid is not None and ask is not None else None,
        "spread": ask - bid if bid is not None and ask is not None else None,
        "bid_size": sum(size for _, size in bids) if bids else None,
        "ask_size": sum(size for _, size in asks) if asks else None,
    }


def _price_change(coin: str, seconds: float) -> float | None:
    with _LOCK:
        latest = _LATEST.get(coin)
        history = list(_HISTORY[coin])
    if not latest or not history:
        return None
    target = latest[0] - seconds
    old = min(history, key=lambda item: abs(item[0] - target))
    return latest[1] - old[1]


def record_snapshots() -> int:
    with _LOCK:
        markets = [dict(item) for item in _CURRENT.values()]
        latest = dict(_LATEST)
    token_ids = []
    for market in markets:
        token_ids.extend([market.get("up_token_id"), market.get("down_token_id")])
    try:
        books = fetch_books([token for token in token_ids if token])
    except Exception as exc:
        logger.warning("Books request failed: %s", exc)
        return 0

    now = time.time()
    inserted = 0
    for market in markets:
        up = _book_summary(books.get(str(market.get("up_token_id"))))
        down = _book_summary(books.get(str(market.get("down_token_id"))))
        coin = market.get("coin")
        reference = latest.get(coin)
        start = market.get("start_timestamp")
        row = {
            "timestamp": now,
            "datetime_utc": utc_iso(now),
            "condition_id": market["condition_id"],
            "coin": coin,
            "market_second": now - start if start else None,
            "reference_price": reference[1] if reference else None,
            "reference_change_1s": _price_change(coin, 1),
            "reference_change_5s": _price_change(coin, 5),
            "reference_change_15s": _price_change(coin, 15),
            "reference_change_30s": _price_change(coin, 30),
            "up_best_bid": up["bid"], "up_best_ask": up["ask"],
            "up_mid": up["mid"], "up_spread": up["spread"],
            "up_bid_size": up["bid_size"], "up_ask_size": up["ask_size"],
            "down_best_bid": down["bid"], "down_best_ask": down["ask"],
            "down_mid": down["mid"], "down_spread": down["spread"],
            "down_bid_size": down["bid_size"], "down_ask_size": down["ask_size"],
        }
        if insert_snapshot(row):
            inserted += 1
    return inserted


def _on_message(ws, message: str) -> None:
    import json
    try:
        payload = json.loads(message)
        data = payload.get("data", payload)
        symbol = str(data.get("s") or "").upper()
        coin = "BTC" if symbol == "BTCUSDT" else "ETH" if symbol == "ETHUSDT" else None
        if not coin:
            return
        price = safe_float(data.get("p"))
        timestamp = safe_int(data.get("T") or data.get("E")) / 1000
        trade_id = str(data.get("a") or "")
        quantity = safe_float(data.get("q"))
        with _LOCK:
            _LATEST[coin] = (timestamp, price)
            _HISTORY[coin].append((timestamp, price))
        insert_reference_price({
            "symbol": symbol, "timestamp": timestamp, "datetime_utc": utc_iso(timestamp),
            "price": price, "quantity": quantity, "trade_id": trade_id,
        })
    except Exception:
        logger.exception("Binance message processing failed")


def _binance_loop() -> None:
    while not _STOP.is_set():
        try:
            websocket.WebSocketApp(
                BINANCE_WS_URL,
                on_message=_on_message,
                on_open=lambda ws: logger.info("Binance WebSocket connected"),
                on_error=lambda ws, error: logger.warning("Binance WebSocket: %s", error),
            ).run_forever(ping_interval=20, ping_timeout=10)
        except Exception:
            logger.exception("Binance WebSocket loop failed")
        _STOP.wait(5)


def start_binance_thread() -> threading.Thread:
    thread = threading.Thread(target=_binance_loop, name="binance-ws", daemon=True)
    thread.start()
    return thread


def stop() -> None:
    _STOP.set()
