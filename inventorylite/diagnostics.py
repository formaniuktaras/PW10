"""Diagnostics helpers for InventoryLite."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

from inventorylite import db
from inventorylite.utils import get_db_path


def open_in_os(path: Path) -> None:
    if not path.exists():
        messagebox.showerror("Діагностика", f"Шлях не знайдено: {path}")
        return

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def run_db_healthcheck() -> dict:
    conn = db.get_connection()
    try:
        integrity_row = conn.execute("PRAGMA integrity_check;").fetchone()
        integrity = integrity_row[0] if integrity_row else "unknown"

        foreign_key_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()
        foreign_key_count = len(foreign_key_issues)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_names = {row[0] for row in tables}

        key_tables = [
            "Products",
            "PurchaseDocuments",
            "SalesDocuments",
            "StockBalances",
            "CashTransactions",
        ]
        counts: dict[str, int] = {}
        for table in key_tables:
            if table in table_names:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            else:
                count = 0
            counts[table] = count
    finally:
        conn.close()

    return {
        "integrity": "ok" if integrity == "ok" else str(integrity),
        "foreign_key_issues": foreign_key_count,
        "counts": counts,
        "db_path": str(get_db_path()),
    }
