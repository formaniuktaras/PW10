from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from inventorylite import db
from inventorylite.ui_components import TableFrame, simple_prompt
from inventorylite.utils import show_error, Settings


class BrandsTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        on_products_refresh: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.settings = settings
        self.on_products_refresh = on_products_refresh

        self.frame = ttk.Frame(parent)
        self.brand_table: TableFrame | None = None

        self._build()

    def _build(self) -> None:
        columns = [("name", "Назва", 300)]
        self.brand_table = TableFrame(self.frame, columns)
        self.brand_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.brand_table.on_double_click(self.edit_brand)
        self.brand_table.register_context_menu(self.edit_brand, self.delete_brand)

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_brand).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_brand).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_brand).pack(side=tk.LEFT, padx=4)

    def refresh_brands(self) -> None:
        if not self.brand_table:
            return
        rows = db.list_brands()
        self.brand_table.set_rows([{"id": r["id"], "name": r["name"]} for r in rows])

    def add_brand(self) -> None:
        values = simple_prompt("Новий бренд", ["Назва бренду"])
        if not values:
            return
        try:
            db.add_brand(values[0])
            self.refresh_brands()
            self.on_products_refresh()
        except sqlite3.IntegrityError:
            show_error("Бренди", "Бренд з такою назвою вже існує.")
        except Exception:
            logging.exception("Add brand error")
            show_error("Бренди", "Не вдалося додати бренд.")

    def edit_brand(self) -> None:
        if not self.brand_table:
            return
        brand_id = self.brand_table.selected_id()
        if not brand_id:
            show_error("Бренди", "Оберіть бренд для редагування.")
            return
        rows = [b for b in db.list_brands() if b["id"] == brand_id]
        values = simple_prompt(
            "Редагувати бренд",
            ["Назва бренду"],
            [rows[0]["name"]] if rows else None,
        )
        if not values:
            return
        try:
            db.update_brand(brand_id, values[0])
            self.refresh_brands()
            self.on_products_refresh()
        except sqlite3.IntegrityError:
            show_error("Бренди", "Бренд з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit brand error")
            show_error("Бренди", "Не вдалося змінити бренд.")

    def delete_brand(self) -> None:
        if not self.brand_table:
            return
        brand_id = self.brand_table.selected_id()
        if not brand_id:
            show_error("Бренди", "Оберіть бренд для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити бренд та пов'язані товари?"):
            return
        try:
            db.delete_brand(brand_id)
            self.refresh_brands()
            self.on_products_refresh()
        except Exception:
            logging.exception("Delete brand error")
            show_error("Бренди", "Не вдалося видалити бренд.")
