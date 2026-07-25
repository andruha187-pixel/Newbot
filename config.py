import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = DATA_DIR / "exports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

WALLET = os.getenv(
    "TARGET_WALLET",
    "0xf3531b23b504cf0aed4ff21325232b2a2d496685",
).strip().lower()

DATA_API_URL = "https://data-api.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

DB_FILE = str(DATA_DIR / "research.db")
LOG_FILE = str(DATA_DIR / "research.log")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
ACTIVITY_INTERVAL = int(os.getenv("ACTIVITY_INTERVAL", "30"))
MARKET_REFRESH_INTERVAL = int(os.getenv("MARKET_REFRESH_INTERVAL", "15"))
SNAPSHOT_INTERVAL = float(os.getenv("SNAPSHOT_INTERVAL", "2"))
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", "30"))
AUTO_EXPORT_INTERVAL = int(os.getenv("AUTO_EXPORT_INTERVAL", "3600"))
ERROR_RETRY_INTERVAL = int(os.getenv("ERROR_RETRY_INTERVAL", "20"))

TRADES_LIMIT = min(int(os.getenv("TRADES_LIMIT", "1000")), 10000)
ACTIVITY_PAGE_LIMIT = min(int(os.getenv("ACTIVITY_PAGE_LIMIT", "500")), 500)
ACTIVITY_MAX_PAGES = min(int(os.getenv("ACTIVITY_MAX_PAGES", "10")), 20)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_POLLING_ENABLED = os.getenv("TELEGRAM_POLLING_ENABLED", "true").lower() == "true"

SUPPORTED_COINS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}

BINANCE_WS_URL = (
    "wss://stream.binance.com:9443/stream"
    "?streams=btcusdt@aggTrade/ethusdt@aggTrade"
)
