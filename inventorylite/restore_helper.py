from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from inventorylite.utils import APP_NAME, SingleInstance, get_data_dir, get_lock_path, restore_all_data, setup_logging


def helper_restore_main(zip_path: str, *, relaunch: bool = True, timeout: int = 60) -> int:
    log_path = setup_logging(APP_NAME + "_restore")
    archive = Path(zip_path).expanduser().resolve()
    if not archive.exists():
        _show_error("Відновлення", f"Файл не знайдено: {archive}")
        return 2

    deadline = time.time() + max(5, int(timeout))
    lock = SingleInstance(get_lock_path())

    while True:
        if lock.acquire():
            break
        if time.time() > deadline:
            _show_error("Відновлення", "Не вдалося дочекатися закриття програми. Закрийте InventoryLite і повторіть.")
            return 3
        time.sleep(0.2)

    ok = False
    err = ""
    try:
        logging.info("Restore archive: %s", archive)
        logging.info("Target data_dir: %s", get_data_dir())
        restore_all_data(archive)
        ok = True
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logging.exception("Helper restore failed")
    finally:
        try:
            lock.release()
        except Exception:
            pass

    try:
        _write_restore_marker(ok=ok, archive=str(archive), error=err, log_path=str(log_path))
    except Exception:
        logging.exception("Failed to write restore marker")

    if not ok:
        _show_error("Відновлення", f"Помилка відновлення.\nПричина: {err}\nЛоги: {log_path}")
        return 4

    if relaunch:
        _relaunch_app()
    return 0


def _relaunch_app() -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, "-m", "inventorylite.app"]
    subprocess.Popen(cmd, close_fds=True)


def _show_error(title: str, msg: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(title, msg)
    root.destroy()


def _write_restore_marker(*, ok: bool, archive: str, error: str, log_path: str) -> None:
    marker = get_data_dir() / "restore_last.json"
    marker_data = {
        "ok": bool(ok),
        "archive": archive,
        "error": error,
        "ts": time.time(),
        "log_path": log_path,
    }
    marker.write_text(json.dumps(marker_data, ensure_ascii=False, indent=2), encoding="utf-8")
