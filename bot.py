import logging
import signal
import threading
import time

from analyzer import analyze_all
from config import (
    ACTIVITY_INTERVAL,
    ANALYSIS_INTERVAL,
    AUTO_EXPORT_INTERVAL,
    ERROR_RETRY_INTERVAL,
    LOG_FILE,
    MARKET_REFRESH_INTERVAL,
    POLL_INTERVAL,
    SNAPSHOT_INTERVAL,
)
from database import init_database
from exporter import export_bundle
from market_recorder import (
    record_snapshots,
    refresh_markets,
    start_binance_thread,
    stop as stop_market,
)
from telegram_bot import (
    send_file,
    send_message,
    start_polling,
    stop as stop_telegram,
)
from wallet_collector import collect_activity, collect_trades


# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOG_FILE,
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("BOT")


# ============================================================
# СОСТОЯНИЕ
# ============================================================

STOP = threading.Event()

INITIAL_IMPORT_FINISHED = threading.Event()

EXPORT_LOCK = threading.Lock()


# ============================================================
# ОСТАНОВКА
# ============================================================

def shutdown(*_args) -> None:
    logger.info("Получен сигнал остановки")

    STOP.set()

    try:
        stop_market()
    except Exception:
        logger.exception("Ошибка остановки market recorder")

    try:
        stop_telegram()
    except Exception:
        logger.exception("Ошибка остановки Telegram")


# ============================================================
# ПЕРВИЧНЫЙ ИМПОРТ
# ============================================================

def run_initial_import() -> None:
    logger.info("Первичный импорт запущен в фоне")

    try:
        trades_result = collect_trades(
            initial=True,
        )

        logger.info(
            "Первичный импорт сделок завершён: %s",
            trades_result,
        )

        activity_result = collect_activity(
            initial=True,
        )

        logger.info(
            "Первичный импорт активности завершён: %s",
            activity_result,
        )

        refresh_markets()

        logger.info(
            "Первичное обновление рынков завершено"
        )

        analyze_all()

        logger.info(
            "Первичный анализ завершён"
        )

        INITIAL_IMPORT_FINISHED.set()

        send_message(
            "✅ Первичный импорт завершён.\n"
            "Бот полностью готов к работе."
        )

    except Exception:
        logger.exception(
            "Ошибка первичного импорта"
        )

        send_message(
            "⚠️ При первичном импорте произошла ошибка. "
            "Основной сбор данных продолжает работать."
        )


# ============================================================
# БЕЗОПАСНЫЙ ЭКСПОРТ
# ============================================================

def run_export(
    caption: str = "Автоматический полный отчёт",
) -> None:

    if not EXPORT_LOCK.acquire(
        blocking=False,
    ):
        logger.warning(
            "Экспорт уже выполняется"
        )
        return

    try:
        logger.info(
            "Экспорт запущен"
        )

        files = export_bundle()

        if not files:
            logger.warning(
                "Экспорт не создал файлов"
            )
            return

        archive_path = files[-1]

        send_file(
            archive_path,
            caption,
        )

        logger.info(
            "Экспорт завершён: %s",
            archive_path,
        )

    except Exception:
        logger.exception(
            "Ошибка экспорта"
        )

    finally:
        EXPORT_LOCK.release()


# ============================================================
# ЗАПУСК TELEGRAM POLLING
# ============================================================

def run_telegram_polling() -> None:
    try:
        logger.info(
            "Запуск Telegram polling"
        )

        start_polling()

        logger.info(
            "Telegram polling запущен"
        )

    except Exception:
        logger.exception(
            "Ошибка запуска Telegram polling"
        )


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def main() -> None:

    signal.signal(
        signal.SIGTERM,
        shutdown,
    )

    signal.signal(
        signal.SIGINT,
        shutdown,
    )

    logger.info(
        "Инициализация базы данных"
    )

    init_database()

    logger.info(
        "Запуск Binance WebSocket"
    )

    start_binance_thread()

    # Telegram запускаем в отдельном потоке.
    # Даже если start_polling() блокирующий,
    # основной бот продолжит работу.
    telegram_thread = threading.Thread(
        target=run_telegram_polling,
        name="telegram-polling",
        daemon=True,
    )

    telegram_thread.start()

    # Первичный импорт тоже выполняется отдельно.
    import_thread = threading.Thread(
        target=run_initial_import,
        name="initial-import",
        daemon=True,
    )

    import_thread.start()

    send_message(
        "🚀 Polymarket Strategy Research v3 запущен.\n"
        "Первичный импорт выполняется в фоне."
    )

    last_trade = 0.0
    last_activity = 0.0
    last_market = 0.0
    last_snapshot = 0.0
    last_analysis = 0.0
    last_export = time.time()

    last_heartbeat = 0.0

    while not STOP.is_set():

        now = time.time()

        try:

            # =================================================
            # НОВЫЕ СДЕЛКИ
            # =================================================

            if now - last_trade >= POLL_INTERVAL:

                result = collect_trades()

                inserted = int(
                    result.get(
                        "inserted",
                        0,
                    )
                )

                if inserted > 0:

                    logger.info(
                        "Новых сделок: %s",
                        inserted,
                    )

                last_trade = now


            # =================================================
            # АКТИВНОСТЬ
            # =================================================

            if now - last_activity >= ACTIVITY_INTERVAL:

                collect_activity()

                last_activity = now


            # =================================================
            # РЫНКИ
            # =================================================

            if now - last_market >= MARKET_REFRESH_INTERVAL:

                refresh_markets()

                last_market = now


            # =================================================
            # СТАКАНЫ
            # =================================================

            if now - last_snapshot >= SNAPSHOT_INTERVAL:

                record_snapshots()

                last_snapshot = now


            # =================================================
            # АНАЛИЗ
            # =================================================

            if now - last_analysis >= ANALYSIS_INTERVAL:

                # Не запускаем одновременно два тяжёлых анализа.
                threading.Thread(
                    target=analyze_all,
                    name="market-analysis",
                    daemon=True,
                ).start()

                last_analysis = now


            # =================================================
            # АВТОМАТИЧЕСКИЙ ЭКСПОРТ
            # =================================================

            if (
                AUTO_EXPORT_INTERVAL > 0
                and now - last_export >= AUTO_EXPORT_INTERVAL
            ):

                threading.Thread(
                    target=run_export,
                    kwargs={
                        "caption": "Автоматический полный отчёт",
                    },
                    name="auto-export",
                    daemon=True,
                ).start()

                last_export = now


            # =================================================
            # HEARTBEAT
            # =================================================

            if now - last_heartbeat >= 30:

                logger.info(
                    "HEARTBEAT | import_finished=%s | "
                    "telegram_alive=%s | "
                    "binance_started=true",
                    INITIAL_IMPORT_FINISHED.is_set(),
                    telegram_thread.is_alive(),
                )

                last_heartbeat = now


            STOP.wait(
                0.25,
            )

        except Exception:

            logger.exception(
                "Ошибка главного цикла"
            )

            STOP.wait(
                ERROR_RETRY_INTERVAL,
            )


    logger.info(
        "Бот остановлен"
    )


if __name__ == "__main__":
    main()
