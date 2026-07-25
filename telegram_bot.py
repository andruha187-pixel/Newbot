import logging
import threading
from pathlib import Path

import requests

from analyzer import analyze_all, summary
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_POLLING_ENABLED,
)
from database import statistics
from exporter import export_bundle


logger = logging.getLogger("TELEGRAM")


# ============================================================
# СОСТОЯНИЕ
# ============================================================

_STOP = threading.Event()

_ANALYZE_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()

_POLLING_THREAD: threading.Thread | None = None


# ============================================================
# ПРОВЕРКА НАСТРОЕК
# ============================================================

def configured() -> bool:
    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


# ============================================================
# TELEGRAM API
# ============================================================

def send_message(text: str) -> bool:
    if not configured():
        logger.warning("Telegram не настроен")
        return False

    try:
        response = requests.post(
            (
                f"https://api.telegram.org/"
                f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            ),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": str(text)[:4096],
                "disable_web_page_preview": True,
            },
            timeout=30,
        )

        response.raise_for_status()
        return True

    except Exception as exc:
        logger.warning(
            "Telegram sendMessage failed: %s",
            exc,
        )
        return False


def send_file(
    path: str,
    caption: str = "",
) -> bool:
    file_path = Path(path)

    if not configured():
        logger.warning("Telegram не настроен")
        return False

    if not file_path.exists():
        logger.warning(
            "Файл не найден: %s",
            file_path,
        )
        return False

    try:
        with file_path.open("rb") as handle:
            response = requests.post(
                (
                    f"https://api.telegram.org/"
                    f"bot{TELEGRAM_BOT_TOKEN}/sendDocument"
                ),
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": str(caption)[:1024],
                },
                files={
                    "document": (
                        file_path.name,
                        handle,
                        "application/octet-stream",
                    )
                },
                timeout=300,
            )

        response.raise_for_status()

        logger.info(
            "Файл отправлен в Telegram: %s",
            file_path,
        )

        return True

    except Exception as exc:
        logger.warning(
            "Telegram sendDocument failed: %s",
            exc,
        )
        return False


# ============================================================
# СТАТУС
# ============================================================

def status_text() -> str:
    try:
        stats = statistics()
        report = summary(24)

        return (
            "📊 POLYMARKET RESEARCH STATUS\n\n"

            f"Сделок: {stats.get('trades', 0)}\n"
            f"Событий активности: "
            f"{stats.get('activities', 0)}\n"
            f"Рынков: {stats.get('markets', 0)}\n"
            f"Снимков стакана: "
            f"{stats.get('snapshots', 0)}\n"
            f"Цен Binance: "
            f"{stats.get('reference_prices', 0)}\n"
            f"Проанализировано рынков: "
            f"{stats.get('analyses', 0)}\n\n"

            f"За 24 часа: рынков "
            f"{report.get('markets', 0)}, "
            f"завершено "
            f"{report.get('resolved', 0)}\n"

            f"Реализованный PnL: "
            f"${float(report.get('realized_pnl', 0)):.2f}\n"

            f"Рынков с SELL: "
            f"{report.get('sell_markets', 0)}\n"

            f"Гарантированно прибыльных позиций: "
            f"{report.get('guaranteed_markets', 0)}"
        )

    except Exception:
        logger.exception(
            "Не удалось сформировать статус"
        )

        return (
            "⚠️ Не удалось получить статус.\n"
            "Посмотри логи Render."
        )


# ============================================================
# ФОНОВЫЙ АНАЛИЗ
# ============================================================

def _analyze_worker() -> None:
    if not _ANALYZE_LOCK.acquire(
        blocking=False,
    ):
        send_message(
            "⏳ Анализ уже выполняется."
        )
        return

    try:
        logger.info(
            "Ручной анализ запущен"
        )

        count = analyze_all()

        send_message(
            f"✅ Анализ завершён.\n"
            f"Рынков: {count}"
        )

        logger.info(
            "Ручной анализ завершён: %s рынков",
            count,
        )

    except Exception:
        logger.exception(
            "Ошибка ручного анализа"
        )

        send_message(
            "❌ Ошибка анализа.\n"
            "Подробности находятся в логах Render."
        )

    finally:
        _ANALYZE_LOCK.release()


def start_analyze_background() -> None:
    if _ANALYZE_LOCK.locked():
        send_message(
            "⏳ Анализ уже выполняется."
        )
        return

    send_message(
        "⏳ Анализ запущен в фоне.\n"
        "Telegram продолжит отвечать на команды."
    )

    thread = threading.Thread(
        target=_analyze_worker,
        name="telegram-analyze",
        daemon=True,
    )

    thread.start()


# ============================================================
# ФОНОВЫЙ ЭКСПОРТ
# ============================================================

def _export_worker() -> None:
    if not _EXPORT_LOCK.acquire(
        blocking=False,
    ):
        send_message(
            "⏳ Экспорт уже выполняется."
        )
        return

    try:
        logger.info(
            "Ручной экспорт запущен"
        )

        files = export_bundle()

        if not files:
            raise RuntimeError(
                "export_bundle() не создал файлов"
            )

        zip_file = Path(files[-1])

        if not zip_file.exists():
            raise FileNotFoundError(
                f"Архив не найден: {zip_file}"
            )

        send_message(
            "✅ Архив создан.\n"
            "Начинаю отправку в Telegram..."
        )

        sent = send_file(
            str(zip_file),
            "Полный пакет данных Polymarket Research v3",
        )

        if not sent:
            raise RuntimeError(
                "Не удалось отправить архив"
            )

        logger.info(
            "Ручной экспорт завершён: %s",
            zip_file,
        )

        # После успешной отправки удаляем ZIP,
        # чтобы старые архивы не заполняли диск.
        try:
            zip_file.unlink()
            logger.info(
                "Отправленный ZIP удалён с диска: %s",
                zip_file,
            )
        except OSError as exc:
            logger.warning(
                "Не удалось удалить ZIP %s: %s",
                zip_file,
                exc,
            )

    except Exception:
        logger.exception(
            "Ошибка ручного экспорта"
        )

        send_message(
            "❌ Ошибка при создании или отправке архива.\n"
            "Посмотри логи Render."
        )

    finally:
        _EXPORT_LOCK.release()


def start_export_background() -> None:
    if _EXPORT_LOCK.locked():
        send_message(
            "⏳ Экспорт уже выполняется.\n"
            "Дождись предыдущего архива."
        )
        return

    send_message(
        "⏳ Создаю архив в фоне.\n"
        "Можно пользоваться /status и другими командами."
    )

    thread = threading.Thread(
        target=_export_worker,
        name="telegram-export",
        daemon=True,
    )

    thread.start()


# ============================================================
# ОБРАБОТКА КОМАНД
# ============================================================

def handle_command(text: str) -> None:
    try:
        command = (
            text.strip()
            .split()[0]
            .split("@")[0]
            .lower()
        )

        logger.info(
            "Получена команда Telegram: %s",
            command,
        )

        if command in {
            "/start",
            "/help",
        }:
            send_message(
                "Команды:\n\n"
                "/status — состояние бота\n"
                "/analyze — пересчитать рынки в фоне\n"
                "/export — создать ZIP в фоне\n"
                "/report — итог за 24 часа\n"
                "/ping — проверить Telegram"
            )

        elif command == "/ping":
            send_message(
                "🏓 Pong. Telegram-обработчик работает."
            )

        elif command == "/status":
            send_message(
                status_text()
            )

        elif command == "/analyze":
            start_analyze_background()

        elif command == "/report":
            report = summary(24)

            send_message(
                "📈 ОТЧЁТ ЗА 24 ЧАСА\n\n"

                f"Рынков: "
                f"{report.get('markets', 0)}\n"

                f"Завершено: "
                f"{report.get('resolved', 0)}\n"

                f"PnL: "
                f"${float(report.get('realized_pnl', 0)):.2f}\n"

                f"Рынков с продажами: "
                f"{report.get('sell_markets', 0)}\n"

                f"Гарантированная прибыль: "
                f"{report.get('guaranteed_markets', 0)}"
            )

        elif command == "/export":
            start_export_background()

        else:
            send_message(
                "Неизвестная команда.\n"
                "Используй /help."
            )

    except Exception:
        logger.exception(
            "Ошибка обработки Telegram-команды"
        )

        send_message(
            "❌ Ошибка обработки команды."
        )


# ============================================================
# POLLING
# ============================================================

def polling_loop() -> None:
    if not configured():
        logger.warning(
            "Telegram polling не запущен: "
            "токен или Chat ID отсутствует"
        )
        return

    if not TELEGRAM_POLLING_ENABLED:
        logger.info(
            "Telegram polling отключён"
        )
        return

    offset = 0

    logger.info(
        "Telegram polling loop запущен"
    )

    while not _STOP.is_set():
        try:
            response = requests.get(
                (
                    f"https://api.telegram.org/"
                    f"bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                ),
                params={
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": ["message"],
                },
                timeout=35,
            )

            if response.status_code == 409:
                logger.error(
                    "Telegram 409 Conflict: "
                    "этот токен уже используется другим "
                    "запущенным экземпляром бота"
                )

                _STOP.wait(10)
                continue

            response.raise_for_status()

            payload = response.json()

            for update in payload.get(
                "result",
                [],
            ):
                update_id = int(
                    update.get(
                        "update_id",
                        0,
                    )
                )

                offset = max(
                    offset,
                    update_id + 1,
                )

                message = (
                    update.get("message")
                    or {}
                )

                chat = (
                    message.get("chat")
                    or {}
                )

                chat_id = str(
                    chat.get("id")
                    or ""
                )

                text = str(
                    message.get("text")
                    or ""
                )

                if chat_id != str(
                    TELEGRAM_CHAT_ID
                ):
                    continue

                if not text.startswith("/"):
                    continue

                # Каждую команду обрабатываем отдельно.
                # Даже медленный /status не остановит getUpdates.
                command_thread = threading.Thread(
                    target=handle_command,
                    args=(text,),
                    name="telegram-command",
                    daemon=True,
                )

                command_thread.start()

        except requests.Timeout:
            # Для long polling тайм-аут нормален.
            continue

        except Exception as exc:
            logger.warning(
                "Telegram polling failed: %s",
                exc,
            )

            _STOP.wait(5)

    logger.info(
        "Telegram polling loop остановлен"
    )


# ============================================================
# ЗАПУСК И ОСТАНОВКА
# ============================================================

def start_polling() -> threading.Thread | None:
    global _POLLING_THREAD

    if not configured():
        logger.warning(
            "Telegram не настроен"
        )
        return None

    if not TELEGRAM_POLLING_ENABLED:
        logger.info(
            "Telegram polling отключён"
        )
        return None

    if (
        _POLLING_THREAD is not None
        and _POLLING_THREAD.is_alive()
    ):
        logger.info(
            "Telegram polling уже работает"
        )
        return _POLLING_THREAD

    _STOP.clear()

    _POLLING_THREAD = threading.Thread(
        target=polling_loop,
        name="telegram-polling",
        daemon=True,
    )

    _POLLING_THREAD.start()

    logger.info(
        "Telegram polling thread запущен"
    )

    return _POLLING_THREAD


def stop() -> None:
    logger.info(
        "Остановка Telegram polling"
    )

    _STOP.set()
