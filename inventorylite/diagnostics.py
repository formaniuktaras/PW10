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
    base = db.db_health_check()
    conn = db.get_connection()
    try:
        schema_version_row = conn.execute("PRAGMA user_version").fetchone()
        schema_version = int(schema_version_row[0]) if schema_version_row else 0
    finally:
        conn.close()

    return {
        "integrity": base["integrity_check"],
        "foreign_key_issues": base["foreign_key_issues"],
        "counts": base["counts"],
        "db_path": str(get_db_path()),
        "schema_version": schema_version,
    }
