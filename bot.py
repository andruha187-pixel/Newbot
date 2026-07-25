import logging
import signal
import threading
import time

from analyzer import analyze_all
from config import (
    ACTIVITY_INTERVAL, ANALYSIS_INTERVAL, AUTO_EXPORT_INTERVAL,
    ERROR_RETRY_INTERVAL, LOG_FILE, MARKET_REFRESH_INTERVAL,
    POLL_INTERVAL, SNAPSHOT_INTERVAL,
)
from database import init_database
from exporter import export_bundle
from market_recorder import record_snapshots, refresh_markets, start_binance_thread, stop as stop_market
from telegram_bot import send_file, send_message, start_polling, stop as stop_telegram
from wallet_collector import collect_activity, collect_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("BOT")
STOP = threading.Event()


def shutdown(*_args) -> None:
    STOP.set()
    stop_market()
    stop_telegram()


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    init_database()
    start_binance_thread()
    start_polling()

    logger.info("Первичный импорт...")
    try:
        collect_trades(initial=True)
        collect_activity(initial=True)
        analyze_all()
        refresh_markets()
    except Exception:
        logger.exception("Ошибка первичного импорта")

    send_message("🚀 Polymarket Strategy Research v3 запущен")

    last_trade = last_activity = last_market = last_snapshot = last_analysis = last_export = 0.0

    while not STOP.is_set():
        now = time.time()
        try:
            if now - last_trade >= POLL_INTERVAL:
                result = collect_trades()
                if result["inserted"]:
                    logger.info("Новых сделок: %s", result["inserted"])
                last_trade = now

            if now - last_activity >= ACTIVITY_INTERVAL:
                collect_activity()
                last_activity = now

            if now - last_market >= MARKET_REFRESH_INTERVAL:
                refresh_markets()
                last_market = now

            if now - last_snapshot >= SNAPSHOT_INTERVAL:
                record_snapshots()
                last_snapshot = now

            if now - last_analysis >= ANALYSIS_INTERVAL:
                analyze_all()
                last_analysis = now

            if AUTO_EXPORT_INTERVAL > 0 and now - last_export >= AUTO_EXPORT_INTERVAL:
                # Первый автоматический экспорт только после полного интервала.
                if last_export > 0:
                    files = export_bundle()
                    send_file(files[-1], "Автоматический полный отчёт")
                last_export = now

            STOP.wait(0.25)

        except Exception:
            logger.exception("Ошибка главного цикла")
            STOP.wait(ERROR_RETRY_INTERVAL)

    logger.info("Бот остановлен")


if __name__ == "__main__":
    main()
