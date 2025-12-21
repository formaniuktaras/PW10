from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.dialogs import counterparty_prompt
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings, show_error


class CounterpartiesTab:
    def __init__(self, parent: ttk.Notebook, settings: Settings) -> None:
        self.parent = parent
        self.settings = settings
        self.frame = ttk.Frame(parent)

        self.counterparty_notebook: ttk.Notebook | None = None
        self.counterparty_tables: dict[str, TableFrame] = {}
        self.counterparty_tab_frames: dict[str, ttk.Frame] = {}

        self._build()

    def _build(self) -> None:
        columns = [
            ("name", "Назва", 200),
            ("type", "Тип", 120),
            ("phone", "Телефон", 120),
            ("email", "Email", 170),
            ("address", "Адреса", 200),
            ("note", "Нотатка", 200),
        ]

        def make_table(parent_widget: tk.Widget) -> TableFrame:
            table = TableFrame(parent_widget, columns)
            table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            table.on_double_click(self.edit_counterparty)
            table.register_context_menu(self.edit_counterparty, self.delete_counterparty)
            return table

        nb = ttk.Notebook(self.frame)
        nb.pack(fill=tk.BOTH, expand=True)
        self.counterparty_notebook = nb

        supplier_tab = ttk.Frame(nb)
        customer_tab = ttk.Frame(nb)
        all_tab = ttk.Frame(nb)

        nb.add(supplier_tab, text="Постачальники")
        nb.add(customer_tab, text="Покупці")
        nb.add(all_tab, text="Всі/Інші")

        self.counterparty_tables = {
            "suppliers": make_table(supplier_tab),
            "customers": make_table(customer_tab),
            "all": make_table(all_tab),
        }
        self.counterparty_tab_frames = {
            "suppliers": supplier_tab,
            "customers": customer_tab,
            "all": all_tab,
        }

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_counterparty).pack(side=tk.LEFT, padx=4)

        self.frame.after_idle(self.refresh_counterparties)

    def get_active_counterparty_selection(self) -> tuple[str, TableFrame | None, int | None]:
        if not self.counterparty_notebook:
            return "suppliers", None, None

        current_tab = self.counterparty_notebook.select()
        active_key = "suppliers"
        for key, frame in self.counterparty_tab_frames.items():
            if str(frame) == current_tab:
                active_key = key
                break
        table = self.counterparty_tables.get(active_key)
        selected_id = table.selected_id() if table else None
        return active_key, table, selected_id

    def refresh_counterparties(self) -> None:
        rows = db.list_counterparties()
        type_labels = {
            "supplier": "Постачальник",
            "customer": "Покупець",
            "both": "Постачальник/Покупець",
            "other": "Інший",
        }

        suppliers: list[dict] = []
        customers: list[dict] = []
        all_rows: list[dict] = []

        for r in rows:
            mapped = {
                "id": r["id"],
                "name": r["name"],
                "type": type_labels.get(r["type"], r["type"]),
                "phone": r["phone"] or "",
                "email": r["email"] or "",
                "address": r["address"] or "",
                "note": r["note"] or "",
            }
            all_rows.append(mapped)
            if r["type"] in ("supplier", "both"):
                suppliers.append(mapped)
            if r["type"] in ("customer", "both"):
                customers.append(mapped)

        self.counterparty_tables["suppliers"].set_rows(suppliers)
        self.counterparty_tables["customers"].set_rows(customers)
        self.counterparty_tables["all"].set_rows(all_rows)

    def add_counterparty(self) -> None:
        active_key, _, _ = self.get_active_counterparty_selection()
        default_types = {"suppliers": "supplier", "customers": "customer", "all": "other"}
        try:
            values = counterparty_prompt(default_type=default_types.get(active_key))
        except Exception as exc:
            logging.exception("Counterparty prompt error")
            messagebox.showerror("Контрагенти", str(exc))
            return
        if not values:
            return
        try:
            db.add_counterparty(*values)
            self.refresh_counterparties()
        except sqlite3.IntegrityError:
            show_error("Контрагенти", "Контрагент з такою назвою вже існує.")
        except Exception:
            logging.exception("Add counterparty error")
            show_error("Контрагенти", "Не вдалося додати контрагента.")

    def edit_counterparty(self) -> None:
        _, _, counterparty_id = self.get_active_counterparty_selection()
        if not counterparty_id:
            show_error("Контрагенти", "Оберіть контрагента для редагування.")
            return

        rows = [c for c in db.list_counterparties() if c["id"] == counterparty_id]
        if not rows:
            show_error("Контрагенти", "Контрагент не знайдений.")
            return
        c = rows[0]

        try:
            values = counterparty_prompt(
                initial=(c["name"], c["type"], c["phone"], c["email"], c["address"], c["note"])
            )
        except Exception as exc:
            logging.exception("Counterparty prompt error")
            messagebox.showerror("Контрагенти", str(exc))
            return
        if not values:
            return

        try:
            db.update_counterparty(counterparty_id, *values)
            self.refresh_counterparties()
        except sqlite3.IntegrityError:
            show_error("Контрагенти", "Контрагент з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit counterparty error")
            show_error("Контрагенти", "Не вдалося змінити контрагента.")

    def delete_counterparty(self) -> None:
        _, _, counterparty_id = self.get_active_counterparty_selection()
        if not counterparty_id:
            show_error("Контрагенти", "Оберіть контрагента для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити контрагента?"):
            return
        try:
            db.delete_counterparty(counterparty_id)
            self.refresh_counterparties()
        except ValueError as exc:
            show_error("Контрагенти", str(exc))
        except Exception:
            logging.exception("Delete counterparty error")
            show_error("Контрагенти", "Не вдалося видалити контрагента.")
