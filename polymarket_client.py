import logging
from typing import Any

import requests

from config import ACTIVITY_PAGE_LIMIT, CLOB_API_URL, DATA_API_URL, GAMMA_API_URL
from utils import safe_int

logger = logging.getLogger("POLYMARKET_CLIENT")

_session = requests.Session()
_session.headers.update({
    "Accept": "application/json",
    "User-Agent": "polymarket-strategy-research-v3/1.0",
})


def get_list(url: str, params: dict[str, Any], timeout: int = 30) -> list[dict[str, Any]]:
    response = _session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def fetch_trades(wallet: str, limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
    return get_list(
        f"{DATA_API_URL}/trades",
        {"user": wallet, "limit": limit, "offset": offset, "takerOnly": "false"},
    )


def fetch_activity(wallet: str, max_pages: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(max_pages):
        batch = get_list(
            f"{DATA_API_URL}/activity",
            {"user": wallet, "limit": ACTIVITY_PAGE_LIMIT, "offset": page * ACTIVITY_PAGE_LIMIT},
        )
        items.extend(batch)
        if len(batch) < ACTIVITY_PAGE_LIMIT:
            break
    return items


def fetch_event_by_slug(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    response = _session.get(
        f"{GAMMA_API_URL}/events",
        params={"slug": slug, "limit": 1},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def fetch_active_events(limit: int = 200) -> list[dict[str, Any]]:
    return get_list(
        f"{GAMMA_API_URL}/events",
        {"active": "true", "closed": "false", "limit": limit, "order": "id", "ascending": "false"},
        timeout=30,
    )


def fetch_books(token_ids: list[str]) -> dict[str, dict[str, Any]]:
    clean = [str(token) for token in token_ids if token]
    if not clean:
        return {}
    response = _session.post(
        f"{CLOB_API_URL}/books",
        json=[{"token_id": token} for token in clean],
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return {}
    return {
        str(item.get("asset_id")): item
        for item in data
        if isinstance(item, dict) and item.get("asset_id")
    }


def fetch_market_by_condition(condition_id: str) -> dict[str, Any] | None:
    response = _session.get(
        f"{GAMMA_API_URL}/markets",
        params={"condition_ids": condition_id, "limit": 1},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None
