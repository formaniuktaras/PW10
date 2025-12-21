from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings, show_error, get_base_currency_code
from inventorylite.dialogs_documents import ensure_rate_for_date


class ExtraCostsTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        on_refresh_purchases: Callable[[], None],
        on_refresh_stock: Callable[[], None],
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.settings = settings
        self.on_refresh_purchases = on_refresh_purchases
        self.on_refresh_stock = on_refresh_stock

        self.extra_status_var = tk.StringVar(value="Усі")
        self.extra_date_from_var = tk.StringVar()
        self.extra_date_to_var = tk.StringVar()

        self.extra_table: TableFrame | None = None

        self._build()

    def _build(self) -> None:
        filters = ttk.Frame(self.frame)
        filters.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        ttk.Combobox(filters, textvariable=self.extra_status_var, values=["Усі", "Чернетка", "Проведений"], state="readonly", width=14).pack(side=tk.LEFT, padx=4)
        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.extra_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.extra_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(filters, text="Фільтр", command=self.refresh_extra_costs).pack(side=tk.LEFT, padx=6)

        columns = [
            ("doc_date", "Дата", 90),
            ("partner", "Контрагент", 180),
            ("currency", "Валюта", 80),
            ("rate", "Курс", 80),
            ("total_doc", "Сума (вал)", 110),
            ("total_base", "Сума (база)", 110),
            ("status", "Статус", 100),
            ("comment", "Коментар", 220),
        ]
        self.extra_table = TableFrame(self.frame, columns)
        self.extra_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.extra_table.on_double_click(self.edit_extra_cost)
        self.extra_table.register_context_menu(self.edit_extra_cost, self.delete_extra_cost)

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Новий документ", command=self.new_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_extra_cost_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_extra_cost_action).pack(side=tk.LEFT, padx=4)

        self.frame.after_idle(self.refresh_extra_costs)

    def _selected_extra_cost(self) -> Optional[int]:
        if not self.extra_table:
            return None
        doc_id = self.extra_table.selected_id()
        if not doc_id:
            show_error("Супутні витрати", "Оберіть документ")
            return None
        return doc_id

    def refresh_extra_costs(self) -> None:
        if not self.extra_table:
            return
        status_filter = self.extra_status_var.get()
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        rows = db.list_extra_cost_documents(status_value, self.extra_date_from_var.get().strip() or None, self.extra_date_to_var.get().strip() or None)
        self.extra_table.set_rows(
            [
                {
                    "id": r["id"],
                    "doc_date": r["doc_date"],
                    "partner": r["partner"] or "-",
                    "currency": r["currency_code"],
                    "rate": f"{r['exchange_rate']:.4f}",
                    "total_doc": f"{r['total_amount_doc']:.2f}",
                    "total_base": f"{r['total_amount_base']:.2f}",
                    "status": "Чернетка" if (r["status"] or "draft").strip() == "draft" else "Проведений",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def new_extra_cost(self) -> None:
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        purchases = db.list_purchases(status="posted")
        result = extra_cost_prompt(counterparties, currencies, purchases)
        if not result:
            return
        info, lines, purchase_ids, post_now = result
        try:
            doc_id = db.create_extra_cost_document(
                info["doc_date"],
                info["currency"],
                info["rate"],
                info["partner_id"],
                info["comment"],
            )
            db.replace_extra_cost_lines(doc_id, lines, info["rate"])
            if post_now:
                db.post_extra_cost(doc_id, purchase_ids)
            self.refresh_extra_costs()
        except Exception as exc:
            logging.exception("Create extra cost error")
            show_error("Супутні витрати", str(exc))

    def edit_extra_cost(self) -> None:
        doc_id = self._selected_extra_cost()
        if not doc_id:
            return
        doc = db.get_extra_cost_document(doc_id)
        if not doc:
            return
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        purchases = db.list_purchases(status="posted")
        lines = db.list_extra_cost_lines(doc_id)
        selected_ids = [row["purchase_id"] for row in db.list_extra_cost_allocations(doc_id)]
        allow_edit = doc["status"] == "draft"
        result = extra_cost_prompt(counterparties, currencies, purchases, doc=doc, lines=lines, selected_purchase_ids=selected_ids, allow_edit=allow_edit)
        if not result or not allow_edit:
            return
        info, new_lines, purchase_ids, post_now = result
        try:
            db.update_extra_cost_document(
                doc_id,
                info["doc_date"],
                info["currency"],
                info["rate"],
                info["partner_id"],
                info["comment"],
            )
            db.replace_extra_cost_lines(doc_id, new_lines, info["rate"])
            if post_now:
                db.post_extra_cost(doc_id, purchase_ids)
            self.refresh_extra_costs()
        except Exception as exc:
            logging.exception("Edit extra cost error")
            show_error("Супутні витрати", str(exc))

    def delete_extra_cost(self) -> None:
        doc_id = self._selected_extra_cost()
        if not doc_id:
            return
        if not messagebox.askyesno("Підтвердження", "Видалити документ?"):
            return
        try:
            db.delete_extra_cost_document(doc_id)
            self.refresh_extra_costs()
        except Exception as exc:
            logging.exception("Delete extra cost error")
            show_error("Супутні витрати", str(exc))

    def post_extra_cost_action(self) -> None:
        doc_id = self._selected_extra_cost()
        if not doc_id:
            return
        doc = db.get_extra_cost_document(doc_id)
        status = (doc["status"] or "draft").strip() if doc else None
        if not doc:
            show_error("Супутні витрати", "Документ не знайдено")
            return
        if status != "draft":
            show_error("Супутні витрати", "Проводити можна лише чернетку")
            return
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        purchases = db.list_purchases(status="posted")
        lines = db.list_extra_cost_lines(doc_id)
        selected_ids = [row["purchase_id"] for row in db.list_extra_cost_allocations(doc_id)]
        result = extra_cost_prompt(
            counterparties,
            currencies,
            purchases,
            doc=doc,
            lines=lines,
            selected_purchase_ids=selected_ids,
        )
        if not result:
            return
        info, new_lines, purchase_ids, _ = result
        try:
            db.update_extra_cost_document(
                doc_id,
                info["doc_date"],
                info["currency"],
                info["rate"],
                info["partner_id"],
                info["comment"],
            )
            db.replace_extra_cost_lines(doc_id, new_lines, info["rate"])
            db.post_extra_cost(doc_id, purchase_ids)
            self.refresh_extra_costs()
            self.on_refresh_purchases()
            self.on_refresh_stock()
        except Exception as exc:
            logging.exception("Post extra cost error")
            show_error("Супутні витрати", str(exc))

    def unpost_extra_cost_action(self) -> None:
        doc_id = self._selected_extra_cost()
        if not doc_id:
            return
        try:
            db.unpost_extra_cost(doc_id)
            self.refresh_extra_costs()
            self.on_refresh_purchases()
            self.on_refresh_stock()
        except Exception as exc:
            logging.exception("Unpost extra cost error")
            show_error("Супутні витрати", str(exc))


def extra_cost_prompt(counterparties, currencies, purchases, doc=None, lines=None, selected_purchase_ids=None, allow_edit: bool = True):
    dlg = tk.Toplevel()
    dlg.title("Супутні витрати")
    dlg.grab_set()
    if doc and isinstance(doc, sqlite3.Row):
        doc = dict(doc)
    selected_purchase_ids = list(selected_purchase_ids or [])

    frame = ttk.Frame(dlg, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    dlg.columnconfigure(0, weight=1)
    dlg.rowconfigure(0, weight=1)

    row_idx = 0
    ttk.Label(frame, text="Дата (YYYY-MM-DD)").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    date_var = tk.StringVar(value=doc["doc_date"] if doc else datetime.now().strftime("%Y-%m-%d"))
    ttk.Entry(frame, textvariable=date_var, width=14, state="normal" if allow_edit else "disabled").grid(row=row_idx, column=1, sticky="w")

    row_idx += 1
    ttk.Label(frame, text="Валюта").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    curr_codes = [c["code"] for c in currencies]
    curr_var = tk.StringVar(value=doc["currency_code"] if doc else (curr_codes[0] if curr_codes else get_base_currency_code()))
    curr_combo = ttk.Combobox(frame, textvariable=curr_var, values=curr_codes, state="readonly")
    if not allow_edit:
        curr_combo.state(["disabled"])
    curr_combo.grid(row=row_idx, column=1, sticky="w")

    last_currency = curr_var.get()

    row_idx += 1
    ttk.Label(frame, text="Курс").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    try:
        default_rate = doc["exchange_rate"] if doc else ensure_rate_for_date(curr_var.get(), date_var.get())
    except Exception:
        default_rate = doc["exchange_rate"] if doc else 1.0
    rate_var = tk.StringVar(value=f"{default_rate:.4f}")
    ttk.Entry(frame, textvariable=rate_var, width=12, state="normal" if allow_edit else "disabled").grid(row=row_idx, column=1, sticky="w")

    def on_currency_change(event=None):
        nonlocal last_currency
        if not allow_edit:
            return
        try:
            rate_val = ensure_rate_for_date(curr_var.get(), date_var.get())
        except ValueError as exc:
            messagebox.showerror("Курс", str(exc))
            curr_var.set(last_currency)
            return
        rate_var.set(f"{rate_val:.4f}")
        last_currency = curr_var.get()

    curr_combo.bind("<<ComboboxSelected>>", on_currency_change)

    row_idx += 1
    ttk.Label(frame, text="Контрагент").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    filtered_counterparties = [c for c in counterparties if c["type"] in {"supplier", "both", "other"}]
    cp_names = ["-"] + [c["name"] for c in filtered_counterparties]
    cp_var = tk.StringVar()
    cp_combo = ttk.Combobox(frame, textvariable=cp_var, values=cp_names, state="readonly")
    if not allow_edit:
        cp_combo.state(["disabled"])
    cp_combo.grid(row=row_idx, column=1, sticky="w")

    row_idx += 1
    ttk.Label(frame, text="Коментар").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    comment_var = tk.StringVar(value=doc["comment"] if doc else "")
    ttk.Entry(frame, textvariable=comment_var, width=40, state="normal" if allow_edit else "disabled").grid(row=row_idx, column=1, sticky="ew")

    if doc and doc.get("partner_id"):
        try:
            cp_combo.current(next(i for i, c in enumerate(filtered_counterparties, start=1) if c["id"] == doc.get("partner_id")))
        except StopIteration:
            cp_combo.current(0)
    else:
        cp_combo.current(0)

    row_idx += 1
    ttk.Label(frame, text="Рядки витрат").grid(row=row_idx, column=0, sticky="ne", padx=4, pady=4)
    line_frame = ttk.Frame(frame)
    line_frame.grid(row=row_idx, column=1, sticky="nsew")
    frame.rowconfigure(row_idx, weight=1)
    line_frame.columnconfigure(0, weight=1)

    line_columns = ("type", "amount_doc")
    line_tree = ttk.Treeview(line_frame, columns=line_columns, show="headings", height=6)
    line_tree.heading("type", text="Стаття")
    line_tree.heading("amount_doc", text="Сума (вал)")
    line_tree.column("type", width=180)
    line_tree.column("amount_doc", width=100)
    line_tree.grid(row=0, column=0, sticky="nsew")
    line_scroll = ttk.Scrollbar(line_frame, orient="vertical", command=line_tree.yview)
    line_tree.configure(yscrollcommand=line_scroll.set)
    line_scroll.grid(row=0, column=1, sticky="ns")
    line_frame.rowconfigure(0, weight=1)

    lines_data = []
    if lines:
        lines_data = [dict(cost_type=ln["cost_type"], amount_doc=float(ln["amount_doc"])) for ln in lines]

    def refresh_lines():
        line_tree.delete(*line_tree.get_children())
        for idx, ln in enumerate(lines_data):
            line_tree.insert("", "end", iid=str(idx), values=(ln["cost_type"], f"{ln['amount_doc']:.2f}"))

    if allow_edit:
        entry_row = ttk.Frame(line_frame)
        entry_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(entry_row, text="Стаття").grid(row=0, column=0, padx=2)
        cost_var = tk.StringVar(value="Доставка")
        ttk.Entry(entry_row, textvariable=cost_var, width=20).grid(row=0, column=1, padx=2)
        ttk.Label(entry_row, text="Сума").grid(row=0, column=2, padx=2)
        amount_var = tk.StringVar(value="0")
        ttk.Entry(entry_row, textvariable=amount_var, width=12).grid(row=0, column=3, padx=2)

        def add_line():
            try:
                amount_val = float(amount_var.get())
            except ValueError:
                show_error("Валідація", "Невірна сума")
                return
            if amount_val == 0:
                show_error("Валідація", "Сума повинна бути більшою за 0")
                return
            lines_data.append({"cost_type": cost_var.get().strip() or "Інше", "amount_doc": amount_val})
            refresh_lines()

        def delete_line():
            sel = line_tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if 0 <= idx < len(lines_data):
                lines_data.pop(idx)
                refresh_lines()

        ttk.Button(entry_row, text="Додати", command=add_line).grid(row=0, column=4, padx=4)
        ttk.Button(entry_row, text="Видалити", command=delete_line).grid(row=0, column=5, padx=4)

    row_idx += 1
    ttk.Label(frame, text="Закупівлі").grid(row=row_idx, column=0, sticky="ne", padx=4, pady=4)
    purchase_frame = ttk.Frame(frame)
    purchase_frame.grid(row=row_idx, column=1, sticky="nsew")
    frame.rowconfigure(row_idx, weight=1)
    purchase_frame.columnconfigure(1, weight=1)

    available_tree = ttk.Treeview(purchase_frame, columns=("date", "supplier", "total"), show="headings", height=6)
    for col, title, width in [("date", "Дата", 90), ("supplier", "Постачальник", 200), ("total", "Сума (база)", 120)]:
        available_tree.heading(col, text=title)
        available_tree.column(col, width=width)
    available_tree.grid(row=0, column=0, sticky="nsew")
    avail_scroll = ttk.Scrollbar(purchase_frame, orient="vertical", command=available_tree.yview)
    available_tree.configure(yscrollcommand=avail_scroll.set)
    avail_scroll.grid(row=0, column=1, sticky="ns")

    selected_list = tk.Listbox(purchase_frame, height=6)
    selected_list.grid(row=0, column=2, padx=6, sticky="nsew")
    purchase_frame.columnconfigure(2, weight=1)

    purchase_lookup = {p["id"]: p for p in purchases}
    for p in purchases:
        available_tree.insert("", "end", iid=str(p["id"]), values=(p["doc_date"], p["supplier"] or "-", f"{p['total']:.2f}"))

    def refresh_selected():
        selected_list.delete(0, tk.END)
        for pid in selected_purchase_ids:
            p = purchase_lookup.get(pid)
            if p:
                selected_list.insert(tk.END, f"{p['id']} | {p['doc_date']} | {p['supplier'] or '-'} | {p['total']:.2f}")

    def add_purchase():
        if not allow_edit:
            return
        sel = available_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        if pid not in selected_purchase_ids:
            selected_purchase_ids.append(pid)
            refresh_selected()

    def remove_purchase():
        if not allow_edit:
            return
        idx = selected_list.curselection()
        if not idx:
            return
        pid = selected_purchase_ids[idx[0]]
        selected_purchase_ids.remove(pid)
        refresh_selected()

    purchase_btns = ttk.Frame(purchase_frame)
    purchase_btns.grid(row=1, column=0, columnspan=3, pady=4)
    ttk.Button(purchase_btns, text="Додати закупівлю", command=add_purchase).pack(side=tk.LEFT, padx=4)
    ttk.Button(purchase_btns, text="Видалити", command=remove_purchase).pack(side=tk.LEFT, padx=4)

    if selected_purchase_ids:
        refresh_selected()

    row_idx += 1
    post_var = tk.IntVar(value=0)
    if allow_edit:
        ttk.Checkbutton(frame, text="Провести після збереження", variable=post_var).grid(row=row_idx, column=1, sticky="w", pady=6)

    row_idx += 1
    btns = ttk.Frame(frame)
    btns.grid(row=row_idx, column=0, columnspan=2, pady=6)

    result: list = []

    def on_ok():
        try:
            rate_val = float(rate_var.get())
        except ValueError:
            show_error("Валідація", "Невірний курс")
            return
        if rate_val <= 0:
            show_error("Валідація", "Курс має бути більшим за 0")
            return
        partner_name = cp_var.get()
        partner_id = None
        if partner_name and partner_name != "-":
            found = next((c for c in filtered_counterparties if c["name"] == partner_name), None)
            partner_id = found["id"] if found else None
        if curr_var.get().strip().upper() != get_base_currency_code() and not db.rate_on_date(curr_var.get(), date_var.get()):
            db.add_currency_rate(curr_var.get(), date_var.get(), rate_val)
        result.append(
            (
                {
                    "doc_date": date_var.get(),
                    "currency": curr_var.get(),
                    "rate": rate_val,
                    "partner_id": partner_id,
                    "comment": comment_var.get(),
                },
                [(ln["cost_type"], ln["amount_doc"]) for ln in lines_data],
                list(selected_purchase_ids),
                bool(post_var.get()),
            )
        )
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btns, text="OK", command=on_ok, state="normal" if allow_edit else "disabled").pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)

    refresh_lines()
    dlg.wait_window()
    return result[0] if result else None
