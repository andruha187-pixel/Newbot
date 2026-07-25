import logging
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from analyzer import analyze_all, summary
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_POLLING_ENABLED
from database import statistics
from exporter import export_bundle

logger = logging.getLogger("TELEGRAM")

_STOP = threading.Event()


def configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
    if not configured():
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4096], "disable_web_page_preview": True},
            timeout=30,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Telegram sendMessage failed: %s", exc)
        return False


def send_file(path: str, caption: str = "") -> bool:
    if not configured() or not Path(path).exists():
        return False
    try:
        with open(path, "rb") as handle:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1024]},
                files={"document": handle},
                timeout=180,
            )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Telegram sendDocument failed: %s", exc)
        return False


def status_text() -> str:
    stats = statistics()
    report = summary(24)
    return (
        "📊 POLYMARKET RESEARCH STATUS\n\n"
        f"Сделок: {stats['trades']}\n"
        f"Событий активности: {stats['activities']}\n"
        f"Рынков: {stats['markets']}\n"
        f"Снимков стакана: {stats['snapshots']}\n"
        f"Цен Binance: {stats['reference_prices']}\n"
        f"Проанализировано рынков: {stats['analyses']}\n\n"
        f"За 24 часа: рынков {report['markets']}, завершено {report['resolved']}\n"
        f"Реализованный PnL: ${report['realized_pnl']:.2f}\n"
        f"Рынков с SELL: {report['sell_markets']}\n"
        f"Гарантированно прибыльных позиций: {report['guaranteed_markets']}"
    )


def handle_command(text: str) -> None:
    command = text.strip().split()[0].lower()
    if command in {"/start", "/help"}:
        send_message(
            "Команды:\n/status — состояние\n/analyze — пересчитать рынки\n"
            "/export — отправить ZIP с базой, CSV и JSON\n/report — итог за 24 часа"
        )
    elif command == "/status":
        send_message(status_text())
    elif command == "/analyze":
        count = analyze_all()
        send_message(f"✅ Анализ завершён. Рынков: {count}")
    elif command == "/report":
        report = summary(24)
        send_message(
            "📈 ОТЧЁТ ЗА 24 ЧАСА\n\n"
            f"Рынков: {report['markets']}\n"
            f"Завершено: {report['resolved']}\n"
            f"PnL: ${report['realized_pnl']:.2f}\n"
            f"Рынков с продажами: {report['sell_markets']}\n"
            f"Гарантированная прибыль: {report['guaranteed_markets']}"
        )
    elif command == "/export":
        send_message("⏳ Создаю архив...")
        files = export_bundle()
        zip_file = files[-1]
        send_file(zip_file, "Полный пакет данных Polymarket Research v3")


def polling_loop() -> None:
    if not configured() or not TELEGRAM_POLLING_ENABLED:
        return
    offset = 0
    while not _STOP.is_set():
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 25},
                timeout=35,
            )
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                message = update.get("message") or {}
                chat_id = str((message.get("chat") or {}).get("id") or "")
                text = str(message.get("text") or "")
                if chat_id == str(TELEGRAM_CHAT_ID) and text.startswith("/"):
                    handle_command(text)
        except Exception as exc:
            logger.warning("Telegram polling failed: %s", exc)
            _STOP.wait(5)


def start_polling() -> threading.Thread | None:
    if not configured() or not TELEGRAM_POLLING_ENABLED:
        return None
    thread = threading.Thread(target=polling_loop, name="telegram-polling", daemon=True)
    thread.start()
    return thread


def stop() -> None:
    _STOP.set()
