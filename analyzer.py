from datetime import datetime, timezone
from typing import Any

from database import fetch_all, fetch_one, upsert_analysis
from utils import normalize_outcome, normalize_side


def analyze_market(condition_id: str) -> dict[str, Any] | None:
    trades = fetch_all(
        "SELECT * FROM trades WHERE condition_id=? ORDER BY timestamp,id",
        (condition_id,),
    )
    if not trades:
        return None

    market = fetch_one("SELECT * FROM markets WHERE condition_id=?", (condition_id,)) or {}
    holdings = {
        "UP": {"buy": 0.0, "sell": 0.0},
        "DOWN": {"buy": 0.0, "sell": 0.0},
    }
    buy_cost = 0.0
    sell_revenue = 0.0
    buys = sells = switches = max_streak = current_streak = 0
    previous = None

    for trade in trades:
        outcome = normalize_outcome(trade["outcome"])
        side = normalize_side(trade["side"])
        size = float(trade["size"])
        value = float(trade["usdc_value"])
        if outcome not in holdings:
            continue
        if side == "BUY":
            holdings[outcome]["buy"] += size
            buy_cost += value
            buys += 1
        elif side == "SELL":
            holdings[outcome]["sell"] += size
            sell_revenue += value
            sells += 1

        if previous is None or previous != outcome:
            if previous is not None:
                switches += 1
            current_streak = 1
        else:
            current_streak += 1
        previous = outcome
        max_streak = max(max_streak, current_streak)

    up_remaining = holdings["UP"]["buy"] - holdings["UP"]["sell"]
    down_remaining = holdings["DOWN"]["buy"] - holdings["DOWN"]["sell"]
    cash_flow = sell_revenue - buy_cost
    pnl_if_up = cash_flow + up_remaining
    pnl_if_down = cash_flow + down_remaining

    winner = market.get("winner")
    realized_pnl = None
    if winner == "UP":
        realized_pnl = pnl_if_up
    elif winner == "DOWN":
        realized_pnl = pnl_if_down

    if sells == 0:
        strategy_type = "BUY_AND_HOLD"
    elif up_remaining == 0 and down_remaining == 0:
        strategy_type = "ACTIVE_FULL_CLOSE"
    else:
        strategy_type = "ACTIVE_PARTIAL_CLOSE"

    if up_remaining > 0 and down_remaining > 0:
        final_position = "HEDGED"
    elif up_remaining > 0:
        final_position = "UP_ONLY"
    elif down_remaining > 0:
        final_position = "DOWN_ONLY"
    else:
        final_position = "CLOSED"

    seconds = [t.get("market_second") for t in trades if t.get("market_second") is not None]
    row = {
        "condition_id": condition_id,
        "title": trades[0].get("title"),
        "coin": trades[0].get("coin"),
        "start_timestamp": market.get("start_timestamp") or trades[0].get("market_start_timestamp"),
        "end_timestamp": market.get("end_timestamp") or trades[0].get("market_end_timestamp"),
        "closed": int(bool(market.get("closed"))),
        "winner": winner,
        "trade_count": len(trades),
        "buy_count": buys,
        "sell_count": sells,
        "up_bought": holdings["UP"]["buy"],
        "up_sold": holdings["UP"]["sell"],
        "up_remaining": up_remaining,
        "down_bought": holdings["DOWN"]["buy"],
        "down_sold": holdings["DOWN"]["sell"],
        "down_remaining": down_remaining,
        "buy_cost": buy_cost,
        "sell_revenue": sell_revenue,
        "cash_flow": cash_flow,
        "pnl_if_up": pnl_if_up,
        "pnl_if_down": pnl_if_down,
        "realized_pnl": realized_pnl,
        "first_trade_second": min(seconds) if seconds else None,
        "last_trade_second": max(seconds) if seconds else None,
        "switches": switches,
        "max_streak": max_streak,
        "strategy_type": strategy_type,
        "final_position": final_position,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    upsert_analysis(row)
    return row


def analyze_all() -> int:
    conditions = fetch_all(
        "SELECT DISTINCT condition_id FROM trades WHERE condition_id IS NOT NULL"
    )
    count = 0
    for item in conditions:
        if analyze_market(item["condition_id"]):
            count += 1
    return count


def summary(hours: int = 24) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT * FROM analyses
        WHERE updated_at >= datetime('now', ?)
        ORDER BY COALESCE(end_timestamp,start_timestamp) DESC
        """,
        (f"-{int(hours)} hours",),
    )
    resolved = [r for r in rows if r.get("realized_pnl") is not None]
    return {
        "markets": len(rows),
        "resolved": len(resolved),
        "realized_pnl": sum(float(r["realized_pnl"]) for r in resolved),
        "guaranteed_markets": sum(
            1 for r in rows
            if r.get("pnl_if_up") is not None and r.get("pnl_if_down") is not None
            and min(float(r["pnl_if_up"]), float(r["pnl_if_down"])) > 0
        ),
        "sell_markets": sum(1 for r in rows if int(r.get("sell_count") or 0) > 0),
    }
