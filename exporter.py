import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import DB_FILE, EXPORT_DIR, WALLET
from database import fetch_all, statistics


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


def export_bundle() -> list[str]:
    stamp = _stamp()
    export_dir = Path(EXPORT_DIR)
    files: list[str] = []

    tables = ("trades", "activities", "markets", "snapshots", "reference_prices", "analyses")
    for table in tables:
        rows = fetch_all(f"SELECT * FROM {table}")
        path = export_dir / f"{table}_{stamp}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            else:
                handle.write("")
        files.append(str(path))

    analysis_rows = fetch_all(
        "SELECT * FROM analyses ORDER BY COALESCE(end_timestamp,start_timestamp)"
    )
    json_path = export_dir / f"research_report_{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "wallet": WALLET,
                "database_statistics": statistics(),
                "analyses": analysis_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    files.append(str(json_path))

    db_copy = export_dir / f"research_{stamp}.db"
    shutil.copy2(DB_FILE, db_copy)
    files.append(str(db_copy))

    zip_path = export_dir / f"polymarket_research_{stamp}"
    archive = shutil.make_archive(str(zip_path), "zip", export_dir)
    # make_archive includes previous exports too; return only the useful zip as last.
    files.append(archive)
    return files
