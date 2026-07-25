import logging
import time
from typing import Any

from config import ACTIVITY_MAX_PAGES, TRADES_LIMIT, WALLET
from database import insert_activity, insert_trade
from polymarket_client import fetch_activity, fetch_trades
from utils import (
    detect_coin, hash_key, json_text, market_window, normalize_outcome,
    normalize_side, safe_float, safe_int, utc_iso,
)

logger = logging.getLogger("WALLET_COLLECTOR")


def normalize_trade(raw: dict[str, Any], detected: float) -> dict[str, Any] | None:
    timestamp = safe_int(raw.get("timestamp"))
    if timestamp <= 0:
        return None

    price = safe_float(raw.get("price"))
    size = safe_float(raw.get("size"))
    title = raw.get("title")
    slug = raw.get("slug")
    event_slug = raw.get("eventSlug")
    start, end, second = market_window(timestamp, title, slug, event_slug)

    return {
        "trade_key": hash_key(
            raw.get("transactionHash"), timestamp, raw.get("asset"),
            raw.get("side"), raw.get("outcome"), price, size,
        ),
        "wallet": str(raw.get("proxyWallet") or WALLET).lower(),
        "transaction_hash": raw.get("transactionHash"),
        "timestamp": timestamp,
        "detected_timestamp": detected,
        "api_delay_seconds": max(0.0, detected - timestamp),
        "datetime_utc": utc_iso(timestamp),
        "side": normalize_side(raw.get("side")),
        "outcome": normalize_outcome(raw.get("outcome")),
        "price": price,
        "size": size,
        "usdc_value": price * size,
        "title": title,
        "slug": slug,
        "event_slug": event_slug,
        "condition_id": raw.get("conditionId"),
        "asset_id": raw.get("asset"),
        "outcome_index": safe_int(raw.get("outcomeIndex"), -1),
        "coin": detect_coin(title, slug, event_slug),
        "market_start_timestamp": start,
        "market_end_timestamp": end,
        "market_second": second,
        "raw_json": json_text(raw),
    }


def normalize_activity(raw: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = safe_int(raw.get("timestamp"))
    if timestamp <= 0:
        return None
    price = safe_float(raw.get("price"))
    size = safe_float(raw.get("size"))
    usdc = safe_float(raw.get("usdcSize"), price * size)
    return {
        "activity_key": hash_key(
            raw.get("transactionHash"), timestamp, raw.get("type"), raw.get("asset"),
            raw.get("side"), raw.get("outcome"), price, size, usdc,
        ),
        "wallet": str(raw.get("proxyWallet") or WALLET).lower(),
        "timestamp": timestamp,
        "datetime_utc": utc_iso(timestamp),
        "activity_type": str(raw.get("type") or "UNKNOWN").upper(),
        "transaction_hash": raw.get("transactionHash"),
        "condition_id": raw.get("conditionId"),
        "asset_id": raw.get("asset"),
        "side": normalize_side(raw.get("side")),
        "outcome": normalize_outcome(raw.get("outcome")),
        "price": price,
        "size": size,
        "usdc_value": usdc,
        "title": raw.get("title"),
        "slug": raw.get("slug"),
        "event_slug": raw.get("eventSlug"),
        "raw_json": json_text(raw),
    }


def collect_trades(initial: bool = False) -> dict[str, int]:
    detected = time.time()
    raw_items = fetch_trades(WALLET, TRADES_LIMIT)
    raw_items.sort(key=lambda item: safe_int(item.get("timestamp")))
    inserted = 0
    for raw in raw_items:
        row = normalize_trade(raw, detected)
        if row and insert_trade(row):
            inserted += 1
            if not initial:
                logger.info(
                    "%s %s %s @ %.4f x %.2f | second=%s | delay=%.1fs",
                    row.get("coin") or "?", row["side"], row["outcome"],
                    row["price"], row["size"], row["market_second"],
                    row["api_delay_seconds"],
                )
    return {"received": len(raw_items), "inserted": inserted}


def collect_activity(initial: bool = False) -> dict[str, int]:
    raw_items = fetch_activity(WALLET, ACTIVITY_MAX_PAGES)
    raw_items.sort(key=lambda item: safe_int(item.get("timestamp")))
    inserted = 0
    for raw in raw_items:
        row = normalize_activity(raw)
        if row and insert_activity(row):
            inserted += 1
            if not initial and row["activity_type"] != "TRADE":
                logger.info(
                    "Activity %s | %s | %.2f USDC",
                    row["activity_type"], row.get("title") or "?", row["usdc_value"],
                )
    return {"received": len(raw_items), "inserted": inserted}
