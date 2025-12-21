from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.helpers import _read_rate_two_way
from inventorylite.ui_components import TableFrame, simple_prompt
from inventorylite.utils import (
    Settings,
    get_base_currency_code,
    get_base_currency_decimals,
    get_base_currency_name,
    show_error,
)


class CurrenciesTab:
    def __init__(self, parent: ttk.Notebook, settings: Settings) -> None:
        self.parent = parent
        self.settings = settings

        self.frame = ttk.Frame(parent)
        self.base_currency_label: ttk.Label | None = None
        self.currency_table: TableFrame | None = None
        self.rate_table: TableFrame | None = None

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self.frame)
        top.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(top, text="Довідник валют").pack(anchor="w")
        self.base_currency_label = ttk.Label(top, text=self._format_base_currency_label())
        self.base_currency_label.pack(anchor="w", pady=(0, 4))

        curr_columns = [
            ("code", "Код", 80),
            ("name", "Назва", 200),
            ("decimals", "Знаків", 60),
            ("is_active", "Активна", 80),
        ]
        self.currency_table = TableFrame(top, curr_columns, height=6)
        self.currency_table.pack(fill=tk.X, pady=4)
        self.currency_table.on_double_click(self.edit_currency)
        self.currency_table.register_context_menu(self.edit_currency, self.delete_currency)

        btns = ttk.Frame(top)
        btns.pack(pady=4, anchor="w")
        ttk.Button(btns, text="Додати валюту", command=self.add_currency).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_currency).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_currency).pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="Курси валют").pack(anchor="w", pady=(10, 0))
        rate_columns = [("rate_date", "Дата", 120), ("rate", "Курс до базової", 160)]
        self.rate_table = TableFrame(top, rate_columns, height=6)
        self.rate_table.pack(fill=tk.X, pady=4)

        rate_btns = ttk.Frame(top)
        rate_btns.pack(pady=4, anchor="w")
        ttk.Button(rate_btns, text="Додати курс", command=self.add_rate).pack(side=tk.LEFT, padx=4)
        ttk.Button(rate_btns, text="Змінити", command=self.edit_rate).pack(side=tk.LEFT, padx=4)
        ttk.Button(rate_btns, text="Видалити", command=self.delete_rate).pack(side=tk.LEFT, padx=4)

        self.currency_table.on_select(self.refresh_rates)
        self.rate_table.on_double_click(self.edit_rate)
        self.rate_table.register_context_menu(self.edit_rate, self.delete_rate)

    def refresh_currencies(self) -> None:
        if not self.currency_table:
            return
        rows = db.list_currencies(active_only=False)
        self.currency_table.set_rows(
            [
                {
                    "id": row["code"],
                    "code": row["code"],
                    "name": row["name"],
                    "decimals": row["decimals"],
                    "is_active": "Так" if row["is_active"] else "Ні",
                }
                for row in rows
            ]
        )
        self.update_base_currency_label()
        self.refresh_rates()

    def refresh_rates(self) -> None:
        if not self.rate_table or not self.currency_table:
            return
        code = self.currency_table.selected_id()
        if not code:
            active = db.list_currencies(active_only=True)
            code = active[0]["code"] if active else None
        if not code:
            self.rate_table.set_rows([])
            return
        rates = db.list_currency_rates(code)
        self.rate_table.set_rows(
            [
                {
                    "id": r["id"],
                    "rate_date": r["rate_date"],
                    "rate": f"{r['rate']:.4f}",
                }
                for r in rates
            ]
        )

    def update_base_currency_label(self) -> None:
        if self.base_currency_label:
            self.base_currency_label.configure(text=self._format_base_currency_label())

    def add_currency(self) -> None:
        values = simple_prompt("Нова валюта", ["Код", "Назва", "Знаків після коми"], ["USD", "Долар США", "2"])
        if not values:
            return
        try:
            decimals = int(values[2]) if len(values) > 2 else 2
            db.add_currency(values[0], values[1], decimals)
            self.refresh_currencies()
        except sqlite3.IntegrityError:
            show_error("Валюти", "Валюта з таким кодом вже існує")
        except Exception as exc:
            logging.exception("Add currency error")
            show_error("Валюти", str(exc))

    def edit_currency(self) -> None:
        if not self.currency_table:
            return
        code = self.currency_table.selected_id()
        if not code:
            show_error("Валюти", "Оберіть валюту")
            return
        rows = [c for c in db.list_currencies(active_only=False) if c["code"] == code]
        if not rows:
            return
        cur = rows[0]
        values = simple_prompt(
            "Змінити валюту",
            ["Назва", "Знаків після коми", "Активна (1/0)"],
            [cur["name"], str(cur["decimals"]), str(cur["is_active"])],
        )
        if not values:
            return
        try:
            decimals = int(values[1]) if len(values) > 1 else 2
            is_active = values[2].strip() != "0" if len(values) > 2 else True
            db.update_currency(code, values[0], decimals, is_active)
            self.refresh_currencies()
        except Exception as exc:
            logging.exception("Edit currency error")
            show_error("Валюти", str(exc))

    def delete_currency(self) -> None:
        if not self.currency_table:
            return
        code = self.currency_table.selected_id()
        if not code:
            show_error("Валюти", "Оберіть валюту")
            return
        if not messagebox.askyesno("Валюти", "Видалити валюту?"):
            return
        try:
            db.delete_currency(code)
            self.refresh_currencies()
        except Exception as exc:
            logging.exception("Delete currency error")
            show_error("Валюти", str(exc))

    def add_rate(self) -> None:
        if not self.currency_table:
            return
        code = self.currency_table.selected_id()
        if not code:
            show_error("Курси", "Оберіть валюту")
            return
        base = get_base_currency_code()
        defaults = [datetime.now().strftime("%Y-%m-%d"), "1", ""]
        values = simple_prompt(
            "Новий курс",
            ["Дата", f"1 {code} = ? {base}", f"1 {base} = ? {code}"],
            defaults,
        )
        if not values:
            return
        try:
            rate = _read_rate_two_way(code, base, values[1], values[2])
            db.add_currency_rate(code, values[0], rate)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Add rate error")
            show_error("Курси", str(exc))

    def edit_rate(self) -> None:
        if not self.rate_table or not self.currency_table:
            return
        rate_id = self.rate_table.selected_id()
        if not rate_id:
            show_error("Курси", "Оберіть курс")
            return
        code = self.currency_table.selected_id()
        if not code:
            show_error("Курси", "Оберіть валюту")
            return
        rates = [r for r in db.list_currency_rates(code) if r["id"] == rate_id]
        if not rates:
            return
        current = rates[0]
        base = get_base_currency_code()
        direct_default = f"{current['rate']:.6f}"
        inverse_default = f"{(1.0 / current['rate']):.6f}" if current["rate"] > 0 else ""
        values = simple_prompt(
            "Змінити курс",
            ["Дата", f"1 {code} = ? {base}", f"1 {base} = ? {code}"],
            [current["rate_date"], direct_default, inverse_default],
        )
        if not values:
            return
        try:
            rate = _read_rate_two_way(code, base, values[1], values[2])
            db.update_currency_rate(rate_id, values[0], rate)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Edit rate error")
            show_error("Курси", str(exc))

    def delete_rate(self) -> None:
        if not self.rate_table:
            return
        rate_id = self.rate_table.selected_id()
        if not rate_id:
            show_error("Курси", "Оберіть курс")
            return
        if not messagebox.askyesno("Курси", "Видалити курс?"):
            return
        try:
            db.delete_currency_rate(rate_id)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Delete rate error")
            show_error("Курси", str(exc))

    def _format_base_currency_label(self) -> str:
        return (
            f"Базова валюта: {get_base_currency_code()} — "
            f"{get_base_currency_name()} ({get_base_currency_decimals()} знаків)"
        )
