import csv
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DB_FILE, EXPORT_DIR, WALLET


logger = logging.getLogger("EXPORTER")


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _stamp() -> str:
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d_%H-%M-%S"
    )


def _connect(
    database_path: str | Path,
) -> sqlite3.Connection:

    connection = sqlite3.connect(
        str(database_path),
        timeout=60,
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# БЕЗОПАСНАЯ КОПИЯ SQLITE
# ============================================================

def _backup_database(
    destination: Path,
) -> None:

    logger.info(
        "Создание резервной копии SQLite: %s",
        destination,
    )

    source_connection = _connect(
        DB_FILE
    )

    destination_connection = _connect(
        destination
    )

    try:
        source_connection.backup(
            destination_connection,
            pages=1000,
            sleep=0.05,
        )

        destination_connection.commit()

    finally:
        destination_connection.close()
        source_connection.close()

    logger.info(
        "Копия SQLite создана"
    )


# ============================================================
# ЭКСПОРТ ТАБЛИЦЫ В CSV
# ============================================================

def _export_table_to_csv(
    connection: sqlite3.Connection,
    table_name: str,
    destination: Path,
) -> int:

    logger.info(
        "Экспорт таблицы %s",
        table_name,
    )

    cursor = connection.execute(
        f'SELECT * FROM "{table_name}"'
    )

    column_names = [
        description[0]
        for description in cursor.description
    ]

    rows_count = 0

    with destination.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow(
            column_names
        )

        while True:
            rows = cursor.fetchmany(
                2000
            )

            if not rows:
                break

            writer.writerows(
                [
                    tuple(row)
                    for row in rows
                ]
            )

            rows_count += len(
                rows
            )

    logger.info(
        "Таблица %s экспортирована: %s строк",
        table_name,
        rows_count,
    )

    return rows_count


# ============================================================
# СТАТИСТИКА КОПИИ БАЗЫ
# ============================================================

def _database_statistics(
    connection: sqlite3.Connection,
) -> dict:

    tables = (
        "trades",
        "activities",
        "markets",
        "snapshots",
        "reference_prices",
        "analyses",
    )

    result = {}

    for table_name in tables:
        try:
            row = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()

            result[
                table_name
            ] = int(
                row[0]
                if row
                else 0
            )

        except sqlite3.Error:
            result[
                table_name
            ] = 0

    return result


# ============================================================
# JSON-ОТЧЁТ
# ============================================================

def _export_json_report(
    connection: sqlite3.Connection,
    destination: Path,
) -> None:

    cursor = connection.execute(
        """
        SELECT *
        FROM analyses
        ORDER BY COALESCE(
            end_timestamp,
            start_timestamp
        )
        """
    )

    analyses = [
        dict(row)
        for row in cursor.fetchall()
    ]

    payload = {
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "wallet": WALLET,

        "database_statistics": (
            _database_statistics(
                connection
            )
        ),

        "analyses": analyses,
    }

    destination.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    logger.info(
        "JSON-отчёт создан: %s",
        destination,
    )


# ============================================================
# ОЧИСТКА СТАРЫХ ВРЕМЕННЫХ ПАПОК
# ============================================================

def _cleanup_old_temporary_directories(
    export_root: Path,
) -> None:

    for path in export_root.glob(
        "_export_work_*"
    ):
        if not path.is_dir():
            continue

        try:
            shutil.rmtree(
                path
            )

            logger.info(
                "Удалена старая временная папка: %s",
                path,
            )

        except OSError as error:
            logger.warning(
                "Не удалось удалить %s: %s",
                path,
                error,
            )


# ============================================================
# ОСНОВНОЙ ЭКСПОРТ
# ============================================================

def export_bundle() -> list[str]:

    stamp = _stamp()

    export_root = Path(
        EXPORT_DIR
    )

    export_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    _cleanup_old_temporary_directories(
        export_root
    )

    # Все временные файлы создаются в отдельной папке.
    # Эта папка потом архивируется и удаляется.
    work_dir = (
        export_root
        / f"_export_work_{stamp}"
    )

    work_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    archive_base = (
        export_root
        / f"polymarket_research_{stamp}"
    )

    archive_path = Path(
        f"{archive_base}.zip"
    )

    database_copy = (
        work_dir
        / f"research_{stamp}.db"
    )

    try:
        logger.info(
            "Начало экспорта: %s",
            stamp,
        )

        # Создаём согласованную копию SQLite,
        # включая данные, находившиеся в WAL.
        _backup_database(
            database_copy
        )

        backup_connection = _connect(
            database_copy
        )

        try:
            tables = (
                "trades",
                "activities",
                "markets",
                "snapshots",
                "reference_prices",
                "analyses",
            )

            for table_name in tables:
                csv_path = (
                    work_dir
                    / f"{table_name}_{stamp}.csv"
                )

                _export_table_to_csv(
                    backup_connection,
                    table_name,
                    csv_path,
                )

            json_path = (
                work_dir
                / f"research_report_{stamp}.json"
            )

            _export_json_report(
                backup_connection,
                json_path,
            )

        finally:
            backup_connection.close()

        logger.info(
            "Создание ZIP: %s",
            archive_path,
        )

        # Важно: архивируем только временную папку.
        # ZIP находится снаружи и не может включить сам себя.
        created_archive = shutil.make_archive(
            base_name=str(
                archive_base
            ),
            format="zip",
            root_dir=str(
                work_dir
            ),
        )

        archive_path = Path(
            created_archive
        )

        archive_size_mb = (
            archive_path.stat().st_size
            / 1024
            / 1024
        )

        logger.info(
            "Экспорт завершён: %s | %.2f MB",
            archive_path,
            archive_size_mb,
        )

        # Telegram-код берёт последний элемент списка.
        return [
            str(
                archive_path
            )
        ]

    except Exception:
        logger.exception(
            "Ошибка создания экспорта"
        )

        try:
            if archive_path.exists():
                archive_path.unlink()
        except OSError:
            pass

        raise

    finally:
        # CSV, JSON и временную копию БД после упаковки удаляем.
        # На диске остаётся только готовый ZIP.
        try:
            if work_dir.exists():
                shutil.rmtree(
                    work_dir
                )

                logger.info(
                    "Временные файлы экспорта удалены"
                )

        except OSError as error:
            logger.warning(
                "Не удалось удалить временную папку %s: %s",
                work_dir,
                error,
    )
