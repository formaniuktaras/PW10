"""Utility helpers for InventoryLite."""
from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
from logging.handlers import RotatingFileHandler
from pathlib import Path

HEADLESS = os.environ.get("INVENTORYLITE_HEADLESS", "").strip().lower() in ("1", "true", "yes")

tk = None
TclError = Exception
messagebox = None
ttk = None

if not HEADLESS:
    try:
        import tkinter as tk
        from tkinter import TclError, messagebox, ttk
    except Exception:
        pass

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
BASE_CURRENCY = "USD"
BASE_CURRENCY_NAME = "Долар США"
BASE_CURRENCY_DECIMALS = 2


DEFAULT_SETTINGS = {
    "general": {"language": "uk", "theme": "system"},
    "files": {
        "working_dir": str(Path.home()),
        "recent_limit": 10,
        "recent_items": [],
        "encoding": "utf-8",
    },
    "ui": {
        "panel_layout": "Авто",
        "status_bar": True,
        "compact_mode": False,
        "fullscreen": False,
        "notifications_volume": 70,
        "notifications_duration": 3,
    },
    "editor": {
        "font_family": "TkDefaultFont",
        "font_size": 10,
        "syntax_highlighting": True,
        "indent_with_tabs": False,
        "tab_width": 4,
        "line_numbers": True,
        "minimap": False,
        "auto_format": False,
        "autocomplete": True,
        "line_length_limit": 120,
    },
    "hotkeys": {"profile": "Типовий", "allow_custom": True},
    "support": {
        "log_level": "INFO",
        "collect_system_info": True,
        "auto_error_reports": False,
        "docs_url": "https://example.com/docs",
    },
    "sales_import": {"templates": {}, "last_template": ""},
    "purchase_import": {"templates": {}, "last_template": ""},
    "print": {"last_template_id": None},
    "ui_state": {
        "window_geometry": "",
        "last_tab": "",
        "table_columns": {},
    },
    "defaults": {
        "product": {
            "unit": "pcs",
            "brand": "",
            "category": "",
            "barcode_prefix": "",
        },
        "currency": {
            "base_code": BASE_CURRENCY,
            "base_name": BASE_CURRENCY_NAME,
            "base_decimals": BASE_CURRENCY_DECIMALS,
        },
    },
}


def get_data_dir() -> Path:
    """Return the data directory under LOCALAPPDATA."""
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    path = Path(local_appdata) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_backups_dir() -> Path:
    d = get_data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    return get_data_dir() / "data.db"


def get_lock_path() -> Path:
    return get_data_dir() / "app.lock"


def get_log_path() -> Path:
    return get_data_dir() / "app.log"


def get_settings_path() -> Path:
    return get_data_dir() / "settings.json"


class Settings:
    """Simple JSON-based settings storage."""

    def __init__(self) -> None:
        self.path = get_settings_path()
        self.data = deepcopy(DEFAULT_SETTINGS)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self._merge(self.data, loaded)
        except Exception:
            logging.exception("Failed to load settings; using defaults")

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logging.exception("Failed to save settings")

    def _merge(self, dest: dict, src: dict) -> None:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dest.get(key), dict):
                self._merge(dest[key], value)
            else:
                dest[key] = value

    def get(self, *keys: str, default=None):
        cursor = self.data
        for key in keys:
            if not isinstance(cursor, dict):
                return default
            cursor = cursor.get(key)
        return cursor if cursor is not None else default

    def set(self, value, *keys: str) -> None:
        if not keys:
            raise ValueError("At least one key is required")
        cursor = self.data
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = value


def apply_base_currency_settings(settings: Settings) -> None:
    """Update global base currency values using the given settings."""

    code = (settings.get("defaults", "currency", "base_code") or BASE_CURRENCY).strip().upper()
    name = settings.get("defaults", "currency", "base_name") or BASE_CURRENCY_NAME
    try:
        decimals = int(settings.get("defaults", "currency", "base_decimals") or BASE_CURRENCY_DECIMALS)
    except (TypeError, ValueError):
        decimals = BASE_CURRENCY_DECIMALS
    set_base_currency(code, name, decimals)


def get_base_currency_code() -> str:
    return BASE_CURRENCY


def get_base_currency_name() -> str:
    return BASE_CURRENCY_NAME


def get_base_currency_decimals() -> int:
    return BASE_CURRENCY_DECIMALS


def set_base_currency(code: str, name: str, decimals: int) -> None:
    global BASE_CURRENCY, BASE_CURRENCY_NAME, BASE_CURRENCY_DECIMALS
    BASE_CURRENCY = code.strip().upper()
    BASE_CURRENCY_NAME = name.strip() or BASE_CURRENCY
    BASE_CURRENCY_DECIMALS = max(int(decimals), 0)

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
    if messagebox is None:
        logging.error("Could not show error dialog (headless environment): %s - %s", title, message)
        print(f"{title}: {message}", file=sys.stderr)
        return
    try:
        messagebox.showerror(title, message)
    except TclError:
        # Fallback for headless environments where Tk dialogs cannot be shown
        logging.error("Could not show error dialog (headless environment): %s - %s", title, message)
        print(f"{title}: {message}", file=sys.stderr)


def _is_text_input(widget: tk.Widget) -> bool:
    """Return True if widget supports text selection/copy/paste shortcuts."""

    if tk is None or ttk is None:
        return False
    return isinstance(
        widget,
        (
            tk.Entry,
            ttk.Entry,
            tk.Text,
            tk.Spinbox,
            ttk.Spinbox,
            ttk.Combobox,
        ),
    )


def _enable_undo(widget: tk.Widget) -> None:
    """Enable undo stack for widgets that support it."""

    if tk is None:
        return
    try:
        if str(widget.cget("undo")) == "0":
            widget.configure(undo=True)
    except (tk.TclError, AttributeError):
        # Widget does not expose undo configuration; skip silently.
        return


def _tune_text_input_caret(widget: tk.Widget) -> None:
    """Make text input caret thicker and more visible."""

    if tk is None:
        return
    try:
        widget.configure(insertwidth=4)
    except Exception:
        pass
    try:
        widget.configure(insertbackground="#ffffff")
    except Exception:
        pass
    try:
        widget.configure(insertcolor="#ffffff")
    except Exception:
        pass
    try:
        widget.configure(insertontime=600, insertofftime=350)
    except Exception:
        pass


def _select_all_text(widget: tk.Widget) -> bool:
    """Select all content for entry-like and text widgets."""

    if tk is None:
        return False
    try:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            widget.see("insert")
            return True
        if hasattr(widget, "selection_range"):
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
            return True
    except tk.TclError:
        return False
    return False


def bind_common_shortcuts(root: tk.Tk) -> None:
    """Bind copy/paste/select-all/undo shortcuts application-wide."""

    if tk is None:
        return

    def _find_tableframe_from_widget(widget: tk.Widget | None):
        current = widget
        while current is not None:
            if hasattr(current, "copy_selection_to_clipboard") and hasattr(current, "tree"):
                return current
            current = getattr(current, "master", None)
        return None

    def on_focus_in(event: tk.Event) -> None:
        w = event.widget
        if _is_text_input(w):
            _enable_undo(w)
            _tune_text_input_caret(w)

    def handle_copy(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        tableframe = _find_tableframe_from_widget(widget)
        if tableframe:
            tableframe.copy_selection_to_clipboard(include_headers=False)
            return "break"
        return None

    def handle_cut(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        return None

    def handle_paste(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        return None

    def handle_select_all(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget) and _select_all_text(widget):
            return "break"
        return None

    def handle_undo(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        return None

    def handle_redo(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        return None

    def handle_copy_with_headers(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            widget.event_generate("<<Copy>>")
            return "break"
        tableframe = _find_tableframe_from_widget(widget)
        if tableframe:
            tableframe.copy_selection_to_clipboard(include_headers=True)
            return "break"
        return None

    def handle_find(event: tk.Event) -> str | None:
        widget = event.widget
        if _is_text_input(widget):
            return None
        tableframe = _find_tableframe_from_widget(widget)
        if tableframe is None:
            tableframe = _find_tableframe_from_widget(root.focus_get())
        if tableframe:
            from inventorylite.dialogs_table_find import open_table_find_dialog

            open_table_find_dialog(root)
            return "break"
        return None

    def show_context_menu(event: tk.Event) -> str | None:
        widget = event.widget
        if not _is_text_input(widget):
            return None

        def popup(x: int, y: int) -> None:
            menu.tk_popup(x, y)
            menu.grab_release()

        popup(event.x_root, event.y_root)
        return "break"

    def show_context_menu_keyboard(event: tk.Event) -> str | None:
        widget = root.focus_get()
        if not widget or not _is_text_input(widget):
            return None

        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() // 2
        menu.tk_popup(x, y)
        menu.grab_release()
        return "break"

    menu = tk.Menu(root, tearoff=0)

    def focused_widget() -> tk.Widget | None:
        widget = root.focus_get()
        return widget if widget and _is_text_input(widget) else None

    def menu_cut() -> None:
        widget = focused_widget()
        if widget:
            widget.event_generate("<<Cut>>")

    def menu_copy() -> None:
        widget = focused_widget()
        if widget:
            widget.event_generate("<<Copy>>")

    def menu_paste() -> None:
        widget = focused_widget()
        if widget:
            widget.event_generate("<<Paste>>")

    def menu_undo() -> None:
        widget = focused_widget()
        if widget:
            _enable_undo(widget)
            widget.event_generate("<<Undo>>")

    def menu_redo() -> None:
        widget = focused_widget()
        if widget:
            _enable_undo(widget)
            widget.event_generate("<<Redo>>")

    def menu_select_all() -> None:
        widget = focused_widget()
        if widget:
            _select_all_text(widget)

    menu.add_command(label="Вирізати", command=menu_cut, accelerator="Ctrl+X")
    menu.add_command(label="Копіювати", command=menu_copy, accelerator="Ctrl+C")
    menu.add_command(label="Вставити", command=menu_paste, accelerator="Ctrl+V")
    menu.add_separator()
    menu.add_command(label="Скасувати", command=menu_undo, accelerator="Ctrl+Z")
    menu.add_command(label="Повернути", command=menu_redo, accelerator="Ctrl+Y")
    menu.add_separator()
    menu.add_command(label="Виділити все", command=menu_select_all, accelerator="Ctrl+A")

    for sequence, handler in (
        ("<Control-c>", handle_copy),
        ("<Control-C>", handle_copy),
        ("<Control-Insert>", handle_copy),
        ("<Control-v>", handle_paste),
        ("<Control-V>", handle_paste),
        ("<Shift-Insert>", handle_paste),
        ("<Control-x>", handle_cut),
        ("<Control-X>", handle_cut),
        ("<Shift-Delete>", handle_cut),
        ("<Control-a>", handle_select_all),
        ("<Control-A>", handle_select_all),
        ("<Control-z>", handle_undo),
        ("<Control-Z>", handle_undo),
        ("<Control-y>", handle_redo),
        ("<Control-Y>", handle_redo),
        ("<Button-3>", show_context_menu),
        ("<Shift-F10>", show_context_menu_keyboard),
    ):
        root.bind_all(sequence, handler, add="+")

    root.bind_all("<FocusIn>", on_focus_in, add="+")
    root.bind_all("<Control-Shift-C>", handle_copy_with_headers, add=True)
    root.bind_all("<Control-f>", handle_find, add=True)


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
                try:
                    if msvcrt:
                        try:
                            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
                    elif fcntl:
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                finally:
                    try:
                        self.handle.close()
                    except Exception:
                        pass
                try:
                    self.lock_path.unlink(missing_ok=True)
                except Exception:
                    logging.warning("Failed to remove lock file: %s", self.lock_path, exc_info=True)
        finally:
            self.handle = None

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise RuntimeError("Application is already running.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.release()
        except Exception:
            pass


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def is_wal_file(path: Path) -> bool:
    return (
        path.name.endswith("-wal")
        or path.name.endswith("-shm")
        or path.name.endswith(".db-wal")
        or path.name.endswith(".db-shm")
    )


def prune_old_files(folder: Path, *, prefix: str, suffix: str, keep_last: int) -> None:
    if keep_last < 0:
        return
    try:
        candidates = [
            path
            for path in folder.iterdir()
            if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix)
        ]
    except FileNotFoundError:
        return

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in candidates[keep_last:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            logging.warning("Failed to delete old backup: %s", old, exc_info=True)


def backup_database_consistent(db_path: Path, target: Path, *, timeout: float = 5.0) -> None:
    """
    Create a consistent database snapshot using SQLite backup API.
    Works even when the database is open under normal circumstances.
    """
    from inventorylite import db as db_module

    src = sqlite3.connect(db_path, timeout=timeout)
    db_module.apply_connection_pragmas(src)
    try:
        dst = sqlite3.connect(target, timeout=timeout)
        try:
            db_module.apply_connection_pragmas(dst)
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def backup_database(
    db_path: Path, *, keep_last: int = 30, conn: sqlite3.Connection | None = None
) -> Path:
    """Create timestamped copy of the database in the backups folder."""
    backups_dir = get_backups_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backups_dir / f"data_{timestamp}.db"
    backups_dir.mkdir(parents=True, exist_ok=True)
    if conn is not None:
        dst_conn = sqlite3.connect(target, timeout=5.0)
        try:
            from inventorylite import db as db_module

            db_module.apply_connection_pragmas(dst_conn)
            conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    else:
        backup_database_consistent(db_path, target)
    prune_old_files(backups_dir, prefix="data_", suffix=".db", keep_last=keep_last)
    logging.info("Database backup created: %s", target)
    return target


def backup_all_data(target: Path | None = None) -> Path:
    """Archive the entire data directory into a single zip file."""

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = get_backups_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if target is None:
        target = backups_dir / f"{APP_NAME}_backup_{timestamp}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_path = Path(tmp) / "data.db"
        backup_database_consistent(get_db_path(), snapshot_path)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_path, "data.db")
            for path in data_dir.rglob("*"):
                if path.is_dir():
                    continue
                if target.resolve() == path.resolve():
                    # Skip the archive file itself if it lives in the data directory.
                    continue
                if path == data_dir / "data.db":
                    continue
                if _is_relative_to(path, backups_dir):
                    continue
                if is_wal_file(path):
                    continue
                if path.name == "app.lock":
                    continue
                if path.suffix == ".log":
                    continue
                if path.name.endswith(".tmp") or path.name.endswith(".journal"):
                    continue
                archive.write(path, path.relative_to(data_dir))

    prune_old_files(backups_dir, prefix=f"{APP_NAME}_backup_", suffix=".zip", keep_last=30)
    logging.info("Full data backup created: %s", target)
    return target


def _remove_wal_shm_files(base: Path) -> None:
    for pattern in ("*.db-wal", "*.db-shm", "*-wal", "*-shm"):
        for path in base.glob(pattern):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                logging.warning("Failed to delete WAL/SHM file: %s", path, exc_info=True)


def restore_all_data(archive_path: Path) -> None:
    """Restore data directory contents from a backup zip archive."""

    archive_path = archive_path.expanduser().resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = get_backups_dir()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore_path = backups_dir / f"{APP_NAME}_pre_restore_{timestamp}.zip"
    try:
        pre_restore_backup = backup_all_data(pre_restore_path)
    except Exception as exc:
        raise RuntimeError(
            "Не вдалося створити резервну копію перед відновленням. Restore скасовано."
        ) from exc

    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(temp_dir)

        # Remove existing data files except for the archive itself if it is stored under data_dir.
        skip_path = archive_path if _is_relative_to(archive_path, data_dir) else None
        for item in list(data_dir.iterdir()):
            # Skip the archive file and its parent directories to avoid deleting the source during restore.
            if skip_path and (item.resolve() == skip_path or _is_relative_to(skip_path, item)):
                continue
            if item.resolve() == backups_dir.resolve():
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)

        _remove_wal_shm_files(data_dir)

        for source in temp_dir.rglob("*"):
            target = data_dir / source.relative_to(temp_dir)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    _remove_wal_shm_files(data_dir)

    logging.info("Pre-restore backup: %s", pre_restore_backup)
    prune_old_files(backups_dir, prefix=f"{APP_NAME}_pre_restore_", suffix=".zip", keep_last=10)
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


def open_file(path: Path) -> None:
    """Open a file with the default system handler."""

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f"open '{path}'")
        else:
            os.system(f"xdg-open '{path}' >/dev/null 2>&1 &")
    except Exception as exc:  # pragma: no cover - GUI feedback
        show_error("Відкриття файлу", str(exc))
