from __future__ import annotations

import logging
from typing import Callable, Optional
import tkinter as tk
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings, show_error


class StockTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        open_labels_dialog: Callable[[tk.Misc, list[dict], str], None],
        open_bulk_actions_dialog: Callable[[tk.Misc, object, object, list[int]], None],
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.settings = settings
        self.open_labels_dialog = open_labels_dialog
        self.open_bulk_actions_dialog = open_bulk_actions_dialog

        self.stock_search_var = tk.StringVar()
        self.stock_table: TableFrame | None = None
        self._stock_row_meta: dict[str, dict[str, object]] = {}

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self.frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук товару:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.stock_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Оновити", command=self.on_search_stock).pack(side=tk.LEFT)
        ttk.Button(top, text="Перерахувати залишки", command=self.recalc_stock).pack(side=tk.LEFT, padx=6)

        columns = [
            ("name", "Товар", 240),
            ("sku", "SKU", 120),
            ("warehouse", "Склад", 160),
            ("quantity", "Кількість", 100),
            ("average_cost", "Сер. собівартість", 140),
        ]
        self.stock_table = TableFrame(self.frame, columns, selectmode="extended")
        self.stock_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.stock_table.register_context_menu_actions(
            [
                ("Друк етикеток…", self.print_stock_labels),
                ("Масові дії з товарами…", self.bulk_actions_from_stock),
            ]
        )
        self.frame.after_idle(self.refresh_stock)

    def on_search_stock(self) -> None:
        search = self.stock_search_var.get().strip() or None
        self.refresh_stock(search)

    def refresh_stock(self, search: str | None = None) -> None:
        rows = db.list_stock(search)
        meta: dict[str, dict[str, object]] = {}
        table_rows = []
        for r in rows:
            iid = f"{r['product_id']}-{r['warehouse_id'] if r['warehouse_id'] else '0'}"
            qty = float(r["quantity"] or 0)
            meta[iid] = {
                "product_id": int(r["product_id"]),
                "warehouse_id": int(r["warehouse_id"]) if r["warehouse_id"] is not None else 0,
                "qty": qty,
                "sku": r["sku"],
                "name": r["name"],
            }
            table_rows.append(
                {
                    "id": iid,
                    "name": r["name"],
                    "sku": r["sku"],
                    "warehouse": r["warehouse"] or "-",
                    "quantity": f"{qty:.2f}",
                    "average_cost": f"{r['average_cost']:.2f}",
                }
            )
        self._stock_row_meta = meta
        if self.stock_table:
            self.stock_table.set_rows(table_rows)

    def recalc_stock(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Перерахувати усі залишки? Це використовує рухи товарів"):
            return
        try:
            db.recalc_stock()
            self.refresh_stock()
            messagebox.showinfo("Залишки", "Перерахунок виконано")
        except Exception as exc:
            logging.exception("Recalc stock error")
            show_error("Залишки", str(exc))

    def bulk_actions_from_stock(self) -> None:
        if not self.stock_table:
            return
        selections = self.stock_table.tree.selection()
        if not selections:
            messagebox.showwarning("Залишки", "Оберіть хоча б одну позицію.")
            return
        product_ids: list[int] = []
        seen: set[int] = set()
        for iid in selections:
            meta = self._stock_row_meta.get(iid) if hasattr(self, "_stock_row_meta") else None
            if not meta:
                continue
            try:
                pid = int(meta.get("product_id"))
            except (TypeError, ValueError):
                continue
            if pid in seen:
                continue
            seen.add(pid)
            product_ids.append(pid)
        if not product_ids:
            messagebox.showwarning("Залишки", "Не вдалося визначити товари у виборі.")
            return
        self.open_bulk_actions_dialog(self.frame.winfo_toplevel(), db.get_connection(), None, product_ids)

    def print_stock_labels(self) -> None:
        if not self.stock_table:
            return
        selections = self.stock_table.tree.selection()
        if not selections:
            messagebox.showwarning("Залишки", "Оберіть позиції для друку етикеток.")
            return
        aggregated: dict[int, dict[str, object]] = {}
        for iid in selections:
            meta = self._stock_row_meta.get(iid) if hasattr(self, "_stock_row_meta") else None
            if not meta:
                continue
            try:
                pid = int(meta.get("product_id"))
            except (TypeError, ValueError):
                continue
            qty = float(meta.get("qty", 0) or 0)
            if pid not in aggregated:
                aggregated[pid] = {
                    "product_id": pid,
                    "sku": str(meta.get("sku") or ""),
                    "name": str(meta.get("name") or ""),
                    "qty": 0.0,
                }
            aggregated[pid]["qty"] = float(aggregated[pid].get("qty", 0.0) or 0.0) + qty
        items = [item for item in aggregated.values() if float(item.get("qty", 0) or 0) > 0]
        if not items:
            messagebox.showwarning("Етикетки", "Немає позицій з кількістю > 0 для друку.")
            return
        self.open_labels_dialog(self.frame.winfo_toplevel(), items, "Кількість із залишків")
