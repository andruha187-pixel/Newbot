import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def hash_key(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_side(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper()


def normalize_outcome(value: Any) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    if text in {"YES", "UP"}:
        return "UP"
    if text in {"NO", "DOWN"}:
        return "DOWN"
    return text


def detect_coin(*values: Any) -> str | None:
    text = " ".join(str(v or "") for v in values).lower()
    if "bitcoin" in text or re.search(r"(^|[^a-z])btc([^a-z]|$)", text):
        return "BTC"
    if "ethereum" in text or "ether " in text or re.search(r"(^|[^a-z])eth([^a-z]|$)", text):
        return "ETH"
    return None


def market_window(timestamp: int, title: Any, slug: Any, event_slug: Any = None):
    text = " ".join(str(v or "") for v in (title, slug, event_slug)).lower()
    is_five_minute = (
        "up or down" in text
        or "updown" in text
        or "-5m-" in text
        or "5-minute" in text
    )
    if not is_five_minute:
        return None, None, None
    start = (timestamp // 300) * 300
    return start, start + 300, timestamp - start


def decode_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, list) else []
        except json.JSONDecodeError:
            return []
    return []
