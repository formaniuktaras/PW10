from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from inventorylite import db
from inventorylite.ui_components import TableFrame
from inventorylite.utils import show_error, Settings
from inventorylite.dialogs import warehouse_prompt


class WarehousesTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        on_warehouses_changed: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.settings = settings
        self.on_warehouses_changed = on_warehouses_changed

        self.frame = ttk.Frame(parent)
        self.warehouse_table: TableFrame | None = None
        self._build()

    def _build(self) -> None:
        columns = [("name", "Назва", 200), ("description", "Опис", 260), ("is_active", "Активний", 100)]
        self.warehouse_table = TableFrame(self.frame, columns)
        self.warehouse_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.warehouse_table.on_double_click(self.edit_warehouse)
        self.warehouse_table.register_context_menu(self.edit_warehouse, self.delete_warehouse)

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_warehouse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_warehouse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_warehouse).pack(side=tk.LEFT, padx=4)

        self.frame.after_idle(self.refresh_warehouses)

    def refresh_warehouses(self) -> None:
        if not self.warehouse_table:
            return
        rows = db.list_warehouses()
        self.warehouse_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"] or "",
                    "is_active": "Так" if r["is_active"] else "Ні",
                }
                for r in rows
            ]
        )

    def add_warehouse(self) -> None:
        values = warehouse_prompt()
        if not values:
            return
        name, description, is_active = values
        try:
            db.add_warehouse(name, description, is_active)
            self.refresh_warehouses()
            self.on_warehouses_changed()
        except sqlite3.IntegrityError:
            show_error("Склади", "Склад з такою назвою вже існує.")
        except Exception:
            logging.exception("Add warehouse error")
            show_error("Склади", "Не вдалося додати склад.")

    def edit_warehouse(self) -> None:
        if not self.warehouse_table:
            return
        warehouse_id = self.warehouse_table.selected_id()
        if not warehouse_id:
            show_error("Склади", "Оберіть склад.")
            return
        rows = [w for w in db.list_warehouses() if w["id"] == warehouse_id]
        if not rows:
            return
        w = rows[0]
        values = warehouse_prompt((w["name"], w["description"] or "", bool(w["is_active"])))
        if not values:
            return
        name, description, is_active = values
        try:
            db.update_warehouse(warehouse_id, name, description, is_active)
            self.refresh_warehouses()
            self.on_warehouses_changed()
        except sqlite3.IntegrityError:
            show_error("Склади", "Склад з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit warehouse error")
            show_error("Склади", "Не вдалося змінити склад.")

    def delete_warehouse(self) -> None:
        if not self.warehouse_table:
            return
        warehouse_id = self.warehouse_table.selected_id()
        if not warehouse_id:
            show_error("Склади", "Оберіть склад для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити склад?"):
            return
        try:
            db.delete_warehouse(warehouse_id)
            self.refresh_warehouses()
            self.on_warehouses_changed()
        except Exception as exc:
            logging.exception("Delete warehouse error")
            show_error("Склади", str(exc))
