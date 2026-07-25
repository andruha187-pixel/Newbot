import os
from pathlib import Path


# ============================================================
# ХРАНЕНИЕ ДАННЫХ
# ============================================================

# На Render подключён Persistent Disk с Mount Path:
# /var/data
#
# Все важные файлы хранятся здесь и не пропадают
# после перезапуска или нового деплоя.

DATA_DIR = Path(
    os.getenv(
        "DATA_DIR",
        "/var/data",
    )
)

EXPORT_DIR = DATA_DIR / "exports"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

EXPORT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# КОШЕЛЁК
# ============================================================

WALLET = os.getenv(
    "TARGET_WALLET",
    "0xf3531b23b504cf0aed4ff21325232b2a2d496685",
).strip().lower()


# ============================================================
# POLYMARKET API
# ============================================================

DATA_API_URL = "https://data-api.polymarket.com"

GAMMA_API_URL = "https://gamma-api.polymarket.com"

CLOB_API_URL = "https://clob.polymarket.com"


# ============================================================
# ФАЙЛЫ
# ============================================================

DB_FILE = str(
    DATA_DIR / "research.db"
)

LOG_FILE = str(
    DATA_DIR / "research.log"
)


# ============================================================
# ИНТЕРВАЛЫ
# ============================================================

POLL_INTERVAL = int(
    os.getenv(
        "POLL_INTERVAL",
        "10",
    )
)

ACTIVITY_INTERVAL = int(
    os.getenv(
        "ACTIVITY_INTERVAL",
        "30",
    )
)

MARKET_REFRESH_INTERVAL = int(
    os.getenv(
        "MARKET_REFRESH_INTERVAL",
        "15",
    )
)

SNAPSHOT_INTERVAL = float(
    os.getenv(
        "SNAPSHOT_INTERVAL",
        "2",
    )
)

ANALYSIS_INTERVAL = int(
    os.getenv(
        "ANALYSIS_INTERVAL",
        "30",
    )
)

AUTO_EXPORT_INTERVAL = int(
    os.getenv(
        "AUTO_EXPORT_INTERVAL",
        "3600",
    )
)

ERROR_RETRY_INTERVAL = int(
    os.getenv(
        "ERROR_RETRY_INTERVAL",
        "20",
    )
)


# ============================================================
# ЛИМИТЫ API
# ============================================================

TRADES_LIMIT = min(
    int(
        os.getenv(
            "TRADES_LIMIT",
            "1000",
        )
    ),
    10000,
)

ACTIVITY_PAGE_LIMIT = min(
    int(
        os.getenv(
            "ACTIVITY_PAGE_LIMIT",
            "500",
        )
    ),
    500,
)

ACTIVITY_MAX_PAGES = min(
    int(
        os.getenv(
            "ACTIVITY_MAX_PAGES",
            "10",
        )
    ),
    20,
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()

TELEGRAM_POLLING_ENABLED = (
    os.getenv(
        "TELEGRAM_POLLING_ENABLED",
        "true",
    ).strip().lower()
    == "true"
)


# ============================================================
# ПОДДЕРЖИВАЕМЫЕ МОНЕТЫ
# ============================================================

SUPPORTED_COINS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


# ============================================================
# BINANCE WEBSOCKET
# ============================================================

BINANCE_WS_URL = (
    "wss://stream.binance.com:9443/stream"
    "?streams=btcusdt@aggTrade/ethusdt@aggTrade"
)


# ============================================================
# ДИАГНОСТИКА
# ============================================================

DEBUG = (
    os.getenv(
        "DEBUG",
        "false",
    ).strip().lower()
    == "true"
)

HEARTBEAT_INTERVAL = int(
    os.getenv(
        "HEARTBEAT_INTERVAL",
        "30",
    )
)
