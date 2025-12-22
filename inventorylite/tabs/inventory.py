from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from inventorylite import db
from inventorylite.dialogs_inventory import inventory_prompt
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings, show_error


class InventoryTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        default_workdir_provider: Callable[[], Path],
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.settings = settings
        self.default_workdir_provider = default_workdir_provider

        self.inventory_status_var = tk.StringVar(value="Усі")
        self.inventory_warehouse_var = tk.StringVar(value="Усі")
        self.inventory_date_from_var = tk.StringVar()
        self.inventory_date_to_var = tk.StringVar()

        self.inventory_table: TableFrame | None = None
        self.inventory_warehouse_combo: ttk.Combobox | None = None
        self.inventory_warehouse_options: list[dict] = []

        self._build()

    def _build(self) -> None:
        filters = ttk.Frame(self.frame)
        filters.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        ttk.Combobox(
            filters,
            textvariable=self.inventory_status_var,
            values=["Усі", "Чернетка", "Проведений"],
            state="readonly",
            width=14,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Склад:").pack(side=tk.LEFT)
        self.inventory_warehouse_combo = ttk.Combobox(
            filters,
            textvariable=self.inventory_warehouse_var,
            values=["Усі"],
            state="readonly",
            width=18,
        )
        self.inventory_warehouse_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.inventory_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.inventory_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(filters, text="Фільтр/Оновити", command=self.refresh_inventory_documents).pack(
            side=tk.LEFT, padx=6
        )

        columns = [
            ("id", "ID", 60),
            ("doc_date", "Дата", 90),
            ("warehouse", "Склад", 160),
            ("status", "Статус", 90),
            ("lines_count", "Рядків", 80),
            ("diff_total", "Розбіжність", 120),
            ("comment", "Коментар", 240),
        ]
        self.inventory_table = TableFrame(
            self.frame,
            columns,
            settings=self.settings,
            persist_key="inventory_table",
        )
        self.inventory_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.inventory_table.on_double_click(self.edit_inventory)
        self.inventory_table.register_context_menu_actions(
            [
                ("Редагувати/Переглянути", self.edit_inventory),
                ("Видалити", self.delete_inventory),
            ]
        )

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Створити…", command=self.new_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Редагувати…", command=self.edit_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_inventory_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Розпровести", command=self.unpost_inventory_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Експорт CSV", command=self.export_inventory_csv).pack(side=tk.LEFT, padx=4)

        self.frame.after_idle(self.refresh_inventory_documents)

    def _selected_inventory(self) -> Optional[int]:
        if not self.inventory_table:
            return None
        doc_id = self.inventory_table.selected_id()
        if not doc_id:
            show_error("Інвентаризація", "Оберіть документ")
            return None
        return int(doc_id)

    def refresh_warehouse_filter(self) -> None:
        warehouses = db.list_warehouses(active_only=False)
        self.inventory_warehouse_options = warehouses
        names = ["Усі"] + [w["name"] for w in warehouses]
        if self.inventory_warehouse_combo:
            self.inventory_warehouse_combo.configure(values=names)
        if self.inventory_warehouse_var.get() not in names:
            self.inventory_warehouse_var.set("Усі")

    def refresh_inventory_documents(self) -> None:
        if not self.inventory_table:
            return
        self.refresh_warehouse_filter()
        status_filter = self.inventory_status_var.get()
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        warehouse_name = self.inventory_warehouse_var.get()
        warehouse_id = None
        if warehouse_name and warehouse_name != "Усі":
            match = next((w["id"] for w in self.inventory_warehouse_options if w["name"] == warehouse_name), None)
            warehouse_id = match
        rows = db.list_inventory_documents(
            status_value,
            self.inventory_date_from_var.get().strip() or None,
            self.inventory_date_to_var.get().strip() or None,
            warehouse_id,
        )
        self.inventory_table.set_rows(
            [
                {
                    "id": r["id"],
                    "doc_date": r["doc_date"],
                    "warehouse": r["warehouse_name"] or "-",
                    "status": "Чернетка" if r["status"] == "draft" else "Проведений",
                    "lines_count": r["lines_count"],
                    "diff_total": f"{float(r['diff_total'] or 0.0):.2f}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def new_inventory(self) -> None:
        warehouses = db.list_warehouses(active_only=True)
        products = db.list_products()
        result = inventory_prompt(warehouses, products, self.settings)
        if not result:
            return
        info, lines, post_now = result
        try:
            doc_id = db.create_inventory_document(info["doc_date"], info["warehouse_id"], info["comment"])
            db.replace_inventory_lines(doc_id, lines)
            if post_now:
                db.post_inventory(doc_id)
            self.refresh_inventory_documents()
        except Exception as exc:
            logging.exception("Create inventory error")
            show_error("Інвентаризація", str(exc))

    def edit_inventory(self) -> None:
        doc_id = self._selected_inventory()
        if not doc_id:
            return
        doc = db.get_inventory_document(doc_id)
        if not doc:
            return
        lines = db.list_inventory_lines(doc_id)
        warehouses = db.list_warehouses(active_only=False)
        products = db.list_products()
        result = inventory_prompt(warehouses, products, self.settings, doc=doc, lines=lines)
        if not result:
            return
        info, new_lines, post_now = result
        try:
            if doc["status"] == "draft":
                db.update_inventory_document(doc_id, info["doc_date"], info["warehouse_id"], info["comment"])
                db.replace_inventory_lines(doc_id, new_lines)
                if post_now:
                    db.post_inventory(doc_id)
            else:
                db.update_inventory_document(doc_id, doc["doc_date"], doc["warehouse_id"], info["comment"])
            self.refresh_inventory_documents()
        except Exception as exc:
            logging.exception("Edit inventory error")
            show_error("Інвентаризація", str(exc))

    def delete_inventory(self) -> None:
        doc_id = self._selected_inventory()
        if not doc_id:
            return
        if not messagebox.askyesno("Підтвердження", "Видалити документ?"):
            return
        try:
            db.delete_inventory_document(doc_id)
            self.refresh_inventory_documents()
        except Exception as exc:
            logging.exception("Delete inventory error")
            show_error("Інвентаризація", str(exc))

    def post_inventory_action(self) -> None:
        doc_id = self._selected_inventory()
        if not doc_id:
            return
        try:
            doc = db.get_inventory_document(doc_id)
            if not doc:
                raise ValueError("Документ не знайдено")
            latest = db.get_latest_posted_stock_doc_date()
            if latest and doc["doc_date"] < latest:
                proceed = messagebox.askyesno(
                    "Підтвердження",
                    "Документ інвентаризації датований "
                    f"{doc['doc_date']}, але є проведені документи до {latest}.\n"
                    f"Проведення змінить історію залишків після {doc['doc_date']}. Продовжити?",
                )
                if not proceed:
                    return
            db.post_inventory(doc_id)
            self.refresh_inventory_documents()
        except Exception as exc:
            logging.exception("Post inventory error")
            show_error("Інвентаризація", str(exc))

    def unpost_inventory_action(self) -> None:
        doc_id = self._selected_inventory()
        if not doc_id:
            return
        try:
            db.unpost_inventory(doc_id)
            self.refresh_inventory_documents()
        except Exception as exc:
            logging.exception("Unpost inventory error")
            show_error("Інвентаризація", str(exc))

    def export_inventory_csv(self) -> None:
        if not self.inventory_table:
            return
        doc_id = self.inventory_table.selected_id()
        default_name = "inventory_lines.csv" if doc_id else "inventory_documents.csv"
        file_path = filedialog.asksaveasfilename(
            title="Експорт CSV",
            defaultextension=".csv",
            initialfile=default_name,
            initialdir=str(self.default_workdir_provider()),
            filetypes=[("CSV", "*.csv"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        try:
            if doc_id:
                doc = db.get_inventory_document(int(doc_id))
                if not doc:
                    raise ValueError("Документ не знайдено")
                lines = db.list_inventory_lines(int(doc_id))
                warehouse_name = next(
                    (w["name"] for w in db.list_warehouses(active_only=False) if w["id"] == doc["warehouse_id"]),
                    "",
                )
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "date",
                            "warehouse",
                            "sku",
                            "name",
                            "expected_qty",
                            "counted_qty",
                            "diff",
                            "cost_override",
                            "note",
                        ]
                    )
                    for ln in lines:
                        writer.writerow(
                            [
                                doc["doc_date"],
                                warehouse_name,
                                ln["sku"],
                                ln["name"],
                                ln["expected_qty"],
                                ln["counted_qty"],
                                ln["diff"],
                                ln["cost_override"] if ln["cost_override"] is not None else "",
                                ln["note"] or "",
                            ]
                        )
            else:
                rows = db.list_inventory_documents()
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["id", "date", "warehouse", "status", "lines_count", "diff_total", "comment"])
                    for row in rows:
                        writer.writerow(
                            [
                                row["id"],
                                row["doc_date"],
                                row["warehouse_name"] or "",
                                row["status"],
                                row["lines_count"],
                                row["diff_total"],
                                row["comment"] or "",
                            ]
                        )
            messagebox.showinfo("Експорт CSV", "Дані збережено.")
        except Exception:
            logging.exception("Inventory export error")
            show_error("Інвентаризація", "Не вдалося експортувати дані.")
