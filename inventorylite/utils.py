"""Utility helpers for InventoryLite."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import shutil
import datetime
from tkinter import messagebox
from pathlib import Path

try:
    import fcntl  # type: ignore
except ImportError:  # Windows fallback
    fcntl = None  # type: ignore

try:
    import msvcrt  # type: ignore
except ImportError:  # POSIX fallback
    msvcrt = None  # type: ignore

APP_NAME = "InventoryLite"
VERSION = "0.2.0"


def get_data_dir() -> Path:
    """Return the data directory under LOCALAPPDATA."""
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    path = Path(local_appdata) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    return get_data_dir() / "data.db"


def get_lock_path() -> Path:
    return get_data_dir() / "app.lock"


def get_log_path() -> Path:
    return get_data_dir() / "app.log"


def configure_logging() -> None:
    log_path = get_log_path()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def show_error(title: str, message: str) -> None:
    logging.error("%s: %s", title, message)
    messagebox.showerror(title, message)


class SingleInstance:
    """Simple file-based single instance lock."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.handle = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = open(self.lock_path, "a+")
        except OSError:
            return False
        try:
            if msvcrt:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            elif fcntl:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                return False
            self.handle.seek(0)
            self.handle.write(str(os.getpid()))
            self.handle.truncate()
            return True
        except OSError:
            return False

    def release(self) -> None:
        try:
            if self.handle:
                if msvcrt:
                    try:
                        msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                elif fcntl:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                self.handle.close()
                self.lock_path.unlink(missing_ok=True)
        finally:
            self.handle = None

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise RuntimeError("Application is already running.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def backup_database(db_path: Path) -> Path:
    """Create timestamped copy of the database in the same folder."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = db_path.with_name(f"data_{timestamp}.db")
    shutil.copy(db_path, target)
    logging.info("Database backup created: %s", target)
    return target


def open_data_folder(path: Path) -> None:
    """Open data folder in system file explorer."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f"open '{path}'")
        else:
            os.system(f"xdg-open '{path}' >/dev/null 2>&1 &")
    except Exception as exc:  # pragma: no cover - GUI feedback
        show_error("Open folder", str(exc))


