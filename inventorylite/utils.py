"""Utility helpers for InventoryLite."""
from __future__ import annotations

import datetime
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import TclError, messagebox

try:
    import fcntl  # type: ignore
except ImportError:  # Windows fallback
    fcntl = None  # type: ignore

try:
    import msvcrt  # type: ignore
except ImportError:  # POSIX fallback
    msvcrt = None  # type: ignore

APP_NAME = "InventoryLite"
# v0.3 adds cash-basis accounting, moving-average inventory costing and direct-costing reports.
VERSION = "0.3.0"
BASE_CURRENCY = "UAH"
BASE_CURRENCY_NAME = "Українська гривня"
BASE_CURRENCY_DECIMALS = 2


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
    try:
        messagebox.showerror(title, message)
    except TclError:
        # Fallback for headless environments where Tk dialogs cannot be shown
        logging.error("Could not show error dialog (headless environment): %s - %s", title, message)
        print(f"{title}: {message}", file=sys.stderr)


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


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def backup_all_data(target: Path | None = None) -> Path:
    """Archive the entire data directory into a single zip file."""

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if target is None:
        target = data_dir / f"{APP_NAME}_backup_{timestamp}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in data_dir.rglob("*"):
            if path.is_dir():
                continue
            if target.resolve() == path.resolve():
                # Skip the archive file itself if it lives in the data directory.
                continue
            archive.write(path, path.relative_to(data_dir))

    logging.info("Full data backup created: %s", target)
    return target


def restore_all_data(archive_path: Path) -> None:
    """Restore data directory contents from a backup zip archive."""

    archive_path = archive_path.expanduser().resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(temp_dir)

        # Remove existing data files except for the archive itself if it is stored under data_dir.
        skip_path = archive_path if _is_relative_to(archive_path, data_dir) else None
        for item in list(data_dir.iterdir()):
            if skip_path and item.resolve() == skip_path:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)

        for source in temp_dir.rglob("*"):
            target = data_dir / source.relative_to(temp_dir)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    logging.info("Data directory restored from: %s", archive_path)


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


