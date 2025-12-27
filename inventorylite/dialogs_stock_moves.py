from __future__ import annotations

import csv
from typing import Any
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from inventorylite import db, dates
from inventorylite.ui_components import TableFrame, DatePicker
from inventorylite.utils import Settings
from inventorylite.text_norm import norm_text


def open_stock_moves_dialog(
    root: tk.Misc,
    settings: Settings,
    product_id: int,
    warehouse_id: int | None = None,
) -> None:
    product = db.get_product(product_id)
    if not product:
        messagebox.showerror("Рух товару", "Товар не знайдено.")
        return

    warehouses = db.list_warehouses(active_only=False)
    window = tk.Toplevel(root)
    window.title("Рух товару")
    window.transient(root)
    window.resizable(True, True)
    window.grab_set()

    header = ttk.Frame(window)
    header.pack(fill=tk.X, padx=10, pady=(10, 4))
    ttk.Label(header, text=f"{product['name']} (SKU: {product['sku']})", font=("", 11, "bold")).pack(
        side=tk.LEFT
    )

    filters = ttk.Frame(window)
    filters.pack(fill=tk.X, padx=10, pady=4)

    warehouse_var = tk.StringVar()
    ttk.Label(filters, text="Склад:").grid(row=0, column=0, sticky="w")
    warehouse_combo = ttk.Combobox(filters, state="readonly", width=28, textvariable=warehouse_var)
    warehouse_options = [(0, "Усі склади")] + [(int(w["id"]), w["name"]) for w in warehouses]
    warehouse_labels = [opt[1] for opt in warehouse_options]
    warehouse_combo.configure(values=warehouse_labels)
    try:
        initial_idx = next(i for i, opt in enumerate(warehouse_options) if opt[0] == (warehouse_id or 0))
    except StopIteration:
        initial_idx = 0
    warehouse_var.set(warehouse_labels[initial_idx])
    warehouse_combo.current(initial_idx)
    warehouse_combo.grid(row=0, column=1, sticky="w", padx=(4, 12))

    search_var = tk.StringVar()
    ttk.Label(filters, text="Пошук:").grid(row=0, column=2, sticky="e")
    ttk.Entry(filters, textvariable=search_var, width=24).grid(row=0, column=3, sticky="w", padx=(4, 12))

    date_from_enabled = tk.BooleanVar(value=False)
    date_to_enabled = tk.BooleanVar(value=False)

    ttk.Checkbutton(filters, text="Дата з", variable=date_from_enabled).grid(row=1, column=0, sticky="w", pady=4)
    date_from_picker = DatePicker(filters, state="normal")
    date_from_picker.grid(row=1, column=1, sticky="w", padx=(4, 12))

    ttk.Checkbutton(filters, text="по", variable=date_to_enabled).grid(row=1, column=2, sticky="e", pady=4)
    date_to_picker = DatePicker(filters, state="normal")
    date_to_picker.grid(row=1, column=3, sticky="w", padx=(4, 12))

    ttk.Button(filters, text="Фільтр", command=lambda: refresh()).grid(row=0, column=4, rowspan=2, padx=4)

    columns = [
        ("move_date", "Дата", 90),
        ("warehouse_name", "Склад", 140),
        ("qty_in", "+К-ть", 70),
        ("qty_out", "-К-ть", 70),
        ("cost_per_unit", "Собівартість", 100),
        ("amount", "Сума", 90),
        ("reference_type", "Тип", 100),
        ("reference_id", "Док#", 80),
        ("channel", "Канал", 120),
        ("counterparty_name", "Контрагент", 180),
    ]
    table = TableFrame(window, columns, settings=settings, persist_key="stock_moves_table")
    table.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

    buttons = ttk.Frame(window)
    buttons.pack(fill=tk.X, padx=10, pady=(0, 10))
    ttk.Button(buttons, text="Експорт CSV…", command=lambda: export_csv()).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Копіювати виділене", command=lambda: copy_selected()).pack(side=tk.LEFT, padx=6)
    ttk.Button(buttons, text="Закрити", command=window.destroy).pack(side=tk.RIGHT)

    state: dict[str, list[dict[str, Any]]] = {"rows": []}

    def current_filters() -> tuple[int | None, str | None, str | None, str]:
        selected_label = warehouse_var.get()
        active_warehouse = None
        for wid, label in warehouse_options:
            if label == selected_label:
                active_warehouse = wid or None
                break
        date_from = date_from_picker.get() if date_from_enabled.get() else None
        date_to = date_to_picker.get() if date_to_enabled.get() else None
        search_key = norm_text(search_var.get())
        return active_warehouse, date_from, date_to, search_key

    def refresh() -> None:
        active_warehouse, date_from, date_to, search_key = current_filters()
        try:
            rows = db.list_stock_moves(product_id, active_warehouse, date_from=date_from, date_to=date_to)
        except ValueError as exc:
            messagebox.showerror("Рух товару", str(exc))
            return
        state["rows"] = []
        table_rows: list[dict[str, Any]] = []
        for r in rows:
            haystack = norm_text(
                f"{r['warehouse_name'] or ''} {r['reference_type']} {r['reference_id']} {r['channel'] or ''} {r['counterparty_name'] or ''}"
            )
            if search_key and search_key not in haystack:
                continue
            state["rows"].append(dict(r))
            table_rows.append(
                {
                    "id": r["id"],
                    "move_date": dates.format_iso_to_dmy(r["move_date"]),
                    "warehouse_name": r["warehouse_name"] or "-",
                    "qty_in": f"{(r['qty_in'] or 0):.2f}",
                    "qty_out": f"{(r['qty_out'] or 0):.2f}",
                    "cost_per_unit": f"{(r['cost_per_unit'] or 0):.2f}",
                    "amount": f"{(r['amount'] or 0):.2f}",
                    "reference_type": r["reference_type"],
                    "reference_id": r["reference_id"],
                    "channel": r["channel"] or "",
                    "counterparty_name": r["counterparty_name"] or "",
                }
            )
        table.set_rows(table_rows)

    def export_csv() -> None:
        if not state["rows"]:
            messagebox.showinfo("Рух товару", "Немає рядків для експорту.")
            return
        path = filedialog.asksaveasfilename(
            title="Експорт руху",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                ["Дата", "Склад", "+К-ть", "-К-ть", "Собівартість", "Сума", "Тип", "Док#", "Канал", "Контрагент"]
            )
            for r in state["rows"]:
                writer.writerow(
                    [
                        dates.format_iso_to_dmy(r["move_date"]),
                        r["warehouse_name"] or "",
                        f"{(r['qty_in'] or 0):.2f}",
                        f"{(r['qty_out'] or 0):.2f}",
                        f"{(r['cost_per_unit'] or 0):.2f}",
                        f"{(r['amount'] or 0):.2f}",
                        r["reference_type"],
                        r["reference_id"],
                        r["channel"] or "",
                        r["counterparty_name"] or "",
                    ]
                )
        messagebox.showinfo("Рух товару", "Експорт виконано.")

    def copy_selected() -> None:
        if not table.copy_selection_to_clipboard(include_headers=True):
            messagebox.showinfo("Рух товару", "Немає вибраних рядків.")

    def open_row_details() -> None:
        row_id = table.selected_id()
        if row_id is None:
            return
        row = next((r for r in state["rows"] if int(r["id"]) == int(row_id)), None)
        if not row:
            return
        info = f"{row['reference_type']} #{row['reference_id']}"
        window.clipboard_clear()
        window.clipboard_append(info)
        messagebox.showinfo("Рух товару", f"{info}\nСкопійовано в буфер обміну.")

    table.on_double_click(open_row_details)
    search_var.trace_add("write", lambda *_: refresh())
    warehouse_combo.bind("<<ComboboxSelected>>", lambda _e: refresh())
    date_from_enabled.trace_add("write", lambda *_: refresh())
    date_to_enabled.trace_add("write", lambda *_: refresh())

    refresh()
    window.wait_window(window)
