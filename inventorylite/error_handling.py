from __future__ import annotations

import logging
import traceback
from pathlib import Path

import tkinter as tk

from inventorylite import diagnostics
from inventorylite.utils import setup_logging


def install_tk_exception_handler(root: tk.Tk, log_path: Path) -> None:
    # Tkinter callback exceptions (натиснув кнопку -> exception) часто “ковтаються” в GUI без консолі.
    in_handler = {"active": False}

    def _handler(exc, val, tb):
        if in_handler["active"]:
            return
        in_handler["active"] = True
        try:
            logging.error("Tkinter callback exception", exc_info=(exc, val, tb))
            short = f"{val}" if val is not None else "Невідома помилка"
            details = "".join(traceback.format_exception(exc, val, tb))
            _show_exception_dialog(root, log_path, short, details)
            if details:
                logging.debug("Error details:\n%s", details)
        finally:
            in_handler["active"] = False

    # Підміняємо стандартний механізм Tk
    root.report_callback_exception = _handler  # type: ignore[attr-defined]


def _show_exception_dialog(root: tk.Tk, log_path: Path, short: str, details: str) -> None:
    dialog = tk.Toplevel(root)
    dialog.title("Помилка")
    dialog.transient(root)
    dialog.grab_set()
    dialog.geometry("720x420")

    header = (
        "Сталася помилка під час виконання дії.\n"
        f"Причина: {short}\n"
        f"Лог: {log_path}"
    )
    label = tk.Label(dialog, text=header, justify="left", anchor="w")
    label.pack(fill="x", padx=12, pady=(12, 6))

    text = tk.Text(dialog, wrap="word")
    text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    text.insert("1.0", details or "Немає деталей")
    text.configure(state="disabled")

    buttons = tk.Frame(dialog)
    buttons.pack(fill="x", padx=12, pady=(0, 12))

    open_log_button = tk.Button(
        buttons,
        text="Відкрити лог",
        command=lambda: diagnostics.open_in_os(log_path),
    )
    copy_button = tk.Button(
        buttons,
        text="Копіювати деталі",
        command=lambda: _copy_details_to_clipboard(root, details),
    )
    close_button = tk.Button(buttons, text="Закрити", command=dialog.destroy)

    open_log_button.pack(side="left")
    copy_button.pack(side="left", padx=(8, 0))
    close_button.pack(side="right")


def _copy_details_to_clipboard(root: tk.Tk, details: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(details or "Немає деталей")
    root.update_idletasks()
