from __future__ import annotations

import datetime as _dt
import logging
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import messagebox


def setup_logging(app_name: str = "InventoryLite") -> Path:
    # Логи в домашній теці користувача: %USERPROFILE%/InventoryLite/logs або ~/.InventoryLite/logs
    base = Path.home() / app_name / "logs"
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / f"{app_name.lower()}_{_dt.datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    logging.info("Logging started: %s", log_path)
    return log_path


def install_tk_exception_handler(root: tk.Tk, log_path: Path) -> None:
    # Tkinter callback exceptions (натиснув кнопку -> exception) часто “ковтаються” в GUI без консолі.
    def _handler(exc, val, tb):
        logging.error("Tkinter callback exception", exc_info=(exc, val, tb))
        short = f"{val}" if val is not None else "Невідома помилка"
        details = "".join(traceback.format_exception(exc, val, tb))
        # Показуємо коротко, деталі — в лог
        messagebox.showerror(
            "Помилка",
            "Сталася помилка під час виконання дії.\n"
            "\n"
            f"Деталі збережені в лог:\n{log_path}\n"
            "\n"
            f"Причина: {short}",
        )
        if details:
            logging.debug("Error details:\n%s", details)

    # Підміняємо стандартний механізм Tk
    root.report_callback_exception = _handler  # type: ignore[attr-defined]
