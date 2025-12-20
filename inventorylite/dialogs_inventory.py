from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from datetime import date, datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional

import db
from helpers import _parse_date_value, _sanitize_barcode_prefix
from ui_components import DatePicker
from utils import Settings, show_error


def inventory_prompt(warehouses, products, settings: Settings, doc=None, lines=None):
    dlg = tk.Toplevel()
    dlg.title("Інвентаризація")
    dlg.grab_set()
    editable = not doc or doc["status"] == "draft"

    if doc and isinstance(doc, sqlite3.Row):
        doc = dict(doc)

    dlg.columnconfigure(0, weight=1)
    dlg.rowconfigure(0, weight=1)
    content = ttk.Frame(dlg, padding=10)
    content.grid(row=0, column=0, sticky="nsew")
    content.columnconfigure(1, weight=1)

    row_idx = 0
    ttk.Label(content, text="Дата (YYYY-MM-DD)").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    if editable:
        date_picker = DatePicker(
            content,
            initial=datetime.strptime(doc["doc_date"], "%Y-%m-%d").date() if doc else date.today(),
        )
        date_picker.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
        date_entry = None
    else:
        date_var = tk.StringVar(value=doc["doc_date"] if doc else datetime.now().strftime("%Y-%m-%d"))
        date_entry = ttk.Entry(content, textvariable=date_var, width=15, state="disabled")
        date_entry.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
        date_picker = None

    row_idx += 1
    ttk.Label(content, text="Склад").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    wh_var = tk.StringVar()
    wh_names = [w["name"] for w in warehouses]
    wh_combo = ttk.Combobox(content, textvariable=wh_var, values=wh_names, state="readonly")
    if not editable:
        wh_combo.state(["disabled"])
    wh_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ttk.Label(content, text="Коментар").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    comment_var = tk.StringVar(value=doc["comment"] if doc else "")
    comment_entry = ttk.Entry(content, textvariable=comment_var, width=40, state="normal" if editable else "disabled")
    comment_entry.grid(row=row_idx, column=1, padx=6, pady=4, sticky="ew")

    categories = db.list_categories(include_hidden=False)
    category_children: dict[int | None, list[dict]] = defaultdict(list)
    for cat in categories:
        category_children[cat["parent_id"]].append(cat)
    for items in category_children.values():
        items.sort(key=lambda item: item["name"].lower())

    category_display_names: list[str] = []
    cat_display_to_id: dict[str, int] = {}

    def _build_category_tree(parent_id: int | None, level: int = 0) -> None:
        for cat in category_children.get(parent_id, []):
            display = f"{'  ' * level}{cat['name']}"
            category_display_names.append(display)
            cat_display_to_id[display] = cat["id"]
            _build_category_tree(cat["id"], level + 1)

    _build_category_tree(None)
    category_values = ["Усі", *category_display_names]

    row_idx += 1
    ttk.Label(content, text="Категорія").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    cat_var = tk.StringVar(value="Усі")
    include_children_var = tk.BooleanVar(value=True)
    cat_frame = ttk.Frame(content)
    cat_frame.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
    cat_combo = ttk.Combobox(cat_frame, textvariable=cat_var, values=category_values, state="readonly")
    cat_combo.pack(side=tk.LEFT)
    include_children_check = ttk.Checkbutton(
        cat_frame,
        text="Включати підкатегорії",
        variable=include_children_var,
    )
    include_children_check.pack(side=tk.LEFT, padx=6)

    post_now_var = tk.BooleanVar(value=False)
    if editable:
        row_idx += 1
        ttk.Checkbutton(content, text="Провести одразу", variable=post_now_var).grid(
            row=row_idx, column=1, padx=6, pady=2, sticky="w"
        )

    row_idx += 1
    scan_frame = ttk.LabelFrame(content, text="Сканування")
    scan_frame.grid(row=row_idx, column=0, columnspan=2, padx=6, pady=6, sticky="ew")
    scan_frame.columnconfigure(1, weight=1)

    ttk.Label(scan_frame, text="Скан-код").grid(row=0, column=0, padx=6, pady=4, sticky="e")
    scan_var = tk.StringVar()
    scan_entry = ttk.Entry(scan_frame, textvariable=scan_var, width=30, state="normal" if editable else "disabled")
    scan_entry.grid(row=0, column=1, padx=6, pady=4, sticky="w")
    ttk.Label(scan_frame, text="К-сть при скані").grid(row=0, column=2, padx=6, pady=4, sticky="e")
    scan_qty_var = tk.IntVar(value=1)
    scan_qty = ttk.Spinbox(
        scan_frame,
        from_=1,
        to=999,
        textvariable=scan_qty_var,
        width=6,
        state="normal" if editable else "disabled",
    )
    scan_qty.grid(row=0, column=3, padx=6, pady=4, sticky="w")
    scan_status = ttk.Label(scan_frame, text="")
    scan_status.grid(row=1, column=0, columnspan=4, padx=6, pady=(0, 4), sticky="w")

    row_idx += 1
    ttk.Label(content, text="Рядки").grid(row=row_idx, column=0, padx=6, pady=4, sticky="ne")
    line_frame = ttk.Frame(content)
    line_frame.grid(row=row_idx, column=1, padx=6, pady=4, sticky="nsew")
    line_frame.grid_columnconfigure(0, weight=1)
    content.rowconfigure(row_idx, weight=1)

    columns = ["sku", "name", "expected", "counted", "diff", "cost_override", "note"]
    tree = ttk.Treeview(line_frame, columns=columns, show="headings", height=10, selectmode="browse")
    headings = {
        "sku": ("SKU", 100),
        "name": ("Назва", 220),
        "expected": ("Очікувано", 90),
        "counted": ("Факт", 90),
        "diff": ("Різниця", 90),
        "cost_override": ("Собівартість надлишку", 150),
        "note": ("Примітка", 160),
    }
    for col, (title, width) in headings.items():
        tree.heading(col, text=title)
        tree.column(col, width=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll = ttk.Scrollbar(line_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    yscroll.grid(row=0, column=1, sticky="ns")
    tree.tag_configure("missing_cost", background="#ffe3e3")

    product_lookup = {f"{p['sku']} — {p['name']}": p for p in products}
    products_by_id = {p["id"]: p for p in products}
    product_names = list(product_lookup.keys())
    allowed_product_ids: set[int] = set()

    line_data: list[dict] = []
    if lines:
        for ln in lines:
            line_data.append(
                {
                    "product_id": ln["product_id"],
                    "sku": ln["sku"],
                    "name": ln["name"],
                    "expected_qty": float(ln["expected_qty"] or 0.0),
                    "counted_qty": float(ln["counted_qty"] or 0.0),
                    "cost_override": float(ln["cost_override"]) if ln["cost_override"] is not None else None,
                    "note": ln["note"] or "",
                }
            )

    if doc:
        if doc["warehouse_id"]:
            try:
                wh_combo.current(next(i for i, w in enumerate(warehouses) if w["id"] == doc["warehouse_id"]))
            except StopIteration:
                wh_combo.set(warehouses[0]["name"] if warehouses else "")
    elif warehouses:
        wh_combo.current(0)

    selected_idx: list[int] = []
    balance_cache: dict[int, tuple[float, float]] = {}

    def _current_date() -> str:
        if date_picker:
            return date_picker.get()
        if date_entry:
            return date_entry.get().strip()
        return datetime.now().strftime("%Y-%m-%d")

    def _current_warehouse_id() -> Optional[int]:
        name = wh_var.get()
        if not name:
            return None
        match = next((w for w in warehouses if w["name"] == name), None)
        return match["id"] if match else None

    def _rebuild_allowed_products() -> None:
        allowed_product_ids.clear()
        display = (cat_var.get() or "Усі").strip()
        if display == "Усі":
            return
        cat_id = cat_display_to_id.get(display)
        if not cat_id:
            return
        rows = db.list_products(
            category_id=cat_id,
            include_subcategories=include_children_var.get(),
        )
        allowed_product_ids.update(int(row["id"]) for row in rows)

    def _is_allowed_product(product_id: int) -> bool:
        return (not allowed_product_ids) or (product_id in allowed_product_ids)

    def _get_balance_cached(product_id: int) -> tuple[float, float]:
        if product_id not in balance_cache:
            wh_id = _current_warehouse_id()
            if not wh_id:
                balance_cache[product_id] = (0.0, 0.0)
            else:
                balance_cache[product_id] = db.get_stock_balance(product_id, wh_id)
        return balance_cache[product_id]

    def _needs_cost(line: dict) -> bool:
        eps = 1e-9
        if line["counted_qty"] <= line["expected_qty"] + eps:
            return False
        if line.get("cost_override") and line["cost_override"] > eps:
            return False
        current_qty, avg_cost = _get_balance_cached(line["product_id"])
        if current_qty > eps and avg_cost > eps:
            return False
        wh_id = _current_warehouse_id()
        if not wh_id:
            return True
        last_price = db.get_last_purchase_price(line["product_id"], wh_id, _current_date())
        return last_price <= eps

    summary_var = tk.StringVar()
    summary_label = ttk.Label(line_frame, textvariable=summary_var)
    summary_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def refresh_lines() -> None:
        tree.delete(*tree.get_children())
        diff_total_negative = 0.0
        diff_total_positive = 0.0
        diff_count = 0
        eps = 1e-9
        for idx, ln in enumerate(line_data):
            diff = ln["counted_qty"] - ln["expected_qty"]
            if diff < -eps:
                diff_total_negative += -diff
                diff_count += 1
            elif diff > eps:
                diff_total_positive += diff
                diff_count += 1
            tags = ("missing_cost",) if _needs_cost(ln) else ()
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    ln["sku"],
                    ln["name"],
                    f"{ln['expected_qty']:.2f}",
                    f"{ln['counted_qty']:.2f}",
                    f"{diff:.2f}",
                    f"{ln['cost_override']:.2f}" if ln.get("cost_override") is not None else "",
                    ln.get("note", ""),
                ),
                tags=tags,
            )
        summary_var.set(
            "Рядків: {lines} | Розбіжності: {diffs} | Недостача (шт): {missing:.2f} | Надлишок (шт): {extra:.2f}".format(
                lines=len(line_data),
                diffs=diff_count,
                missing=diff_total_negative,
                extra=diff_total_positive,
            )
        )

    def _select_line(event=None) -> None:
        selected_idx.clear()
        sel = tree.selection()
        if not sel:
            return
        selected_idx.append(int(sel[0]))

    tree.bind("<<TreeviewSelect>>", _select_line)

    def _pick_product() -> Optional[dict]:
        def _filtered_product_names() -> list[str]:
            if not allowed_product_ids:
                return product_names
            return [
                name
                for name, product in product_lookup.items()
                if _is_allowed_product(int(product["id"]))
            ]

        filtered_names = _filtered_product_names()
        if not filtered_names:
            messagebox.showinfo("Товари", "Список товарів порожній.")
            return None
        picker = tk.Toplevel(dlg)
        picker.title("Оберіть товар")
        picker.grab_set()
        picker.columnconfigure(0, weight=1)
        picker.rowconfigure(1, weight=1)
        search_var = tk.StringVar()
        ttk.Entry(picker, textvariable=search_var).grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        listbox = tk.Listbox(picker, height=12)
        listbox.grid(row=1, column=0, padx=8, pady=6, sticky="nsew")
        for name in filtered_names:
            listbox.insert(tk.END, name)

        result: dict[str, object] = {}

        def _filter(*_args) -> None:
            text = search_var.get().lower().strip()
            allowed_names = _filtered_product_names()
            listbox.delete(0, tk.END)
            for name in allowed_names:
                if text in name.lower():
                    listbox.insert(tk.END, name)

        def _confirm(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            chosen = listbox.get(selection[0])
            result["product"] = product_lookup.get(chosen)
            picker.destroy()

        search_var.trace_add("write", _filter)
        listbox.bind("<Double-1>", _confirm)
        ttk.Button(picker, text="OK", command=_confirm).grid(row=2, column=0, padx=8, pady=(0, 8))
        picker.wait_window()
        return result.get("product")

    def _add_line(product: dict, counted_delta: float = 0.0) -> None:
        for ln in line_data:
            if ln["product_id"] == product["id"]:
                ln["counted_qty"] += counted_delta
                refresh_lines()
                return
        wh_id = _current_warehouse_id()
        expected_qty = db.get_stock_quantity(product["id"], wh_id) if wh_id else 0.0
        line_data.append(
            {
                "product_id": product["id"],
                "sku": product["sku"],
                "name": product["name"],
                "expected_qty": expected_qty,
                "counted_qty": max(0.0, counted_delta),
                "cost_override": None,
                "note": "",
            }
        )
        refresh_lines()

    def _add_product() -> None:
        if not editable:
            return
        product = _pick_product()
        if not product:
            return
        _add_line(product, counted_delta=0.0)

    def _edit_line() -> None:
        if not selected_idx:
            show_error("Інвентаризація", "Оберіть рядок")
            return
        idx = selected_idx[0]
        ln = line_data[idx]
        editor = tk.Toplevel(dlg)
        editor.title("Рядок інвентаризації")
        editor.grab_set()
        ttk.Label(editor, text=f"{ln['sku']} — {ln['name']}").grid(
            row=0, column=0, columnspan=2, padx=8, pady=(8, 4), sticky="w"
        )
        ttk.Label(editor, text="Очікувано").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        ttk.Label(editor, text=f"{ln['expected_qty']:.2f}").grid(row=1, column=1, padx=8, pady=4, sticky="w")
        ttk.Label(editor, text="Факт").grid(row=2, column=0, padx=8, pady=4, sticky="e")
        counted_var = tk.StringVar(value=f"{ln['counted_qty']:.2f}")
        ttk.Entry(editor, textvariable=counted_var, width=12, state="normal" if editable else "disabled").grid(
            row=2, column=1, padx=8, pady=4, sticky="w"
        )
        ttk.Label(editor, text="Собівартість надлишку").grid(row=3, column=0, padx=8, pady=4, sticky="e")
        cost_var = tk.StringVar(value=f"{ln['cost_override']:.2f}" if ln.get("cost_override") is not None else "")
        ttk.Entry(editor, textvariable=cost_var, width=12, state="normal" if editable else "disabled").grid(
            row=3, column=1, padx=8, pady=4, sticky="w"
        )
        ttk.Label(editor, text="Примітка").grid(row=4, column=0, padx=8, pady=4, sticky="e")
        note_var = tk.StringVar(value=ln.get("note", ""))
        ttk.Entry(editor, textvariable=note_var, width=30, state="normal" if editable else "disabled").grid(
            row=4, column=1, padx=8, pady=4, sticky="w"
        )

        def _save_line() -> None:
            if not editable:
                editor.destroy()
                return
            try:
                counted_val = float(counted_var.get() or 0)
                cost_val = cost_var.get().strip()
                cost_val_num = float(cost_val) if cost_val else None
            except ValueError:
                messagebox.showerror("Валідація", "Невірні числові значення")
                return
            if counted_val < 0:
                messagebox.showerror("Валідація", "Фактична кількість не може бути від'ємною")
                return
            if cost_val_num is not None and cost_val_num < 0:
                messagebox.showerror("Валідація", "Собівартість не може бути від'ємною")
                return
            ln["counted_qty"] = counted_val
            ln["cost_override"] = cost_val_num
            ln["note"] = note_var.get().strip()
            refresh_lines()
            editor.destroy()

        btn_frame = ttk.Frame(editor)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=8)
        if editable:
            ttk.Button(btn_frame, text="Зберегти", command=_save_line).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Закрити", command=editor.destroy).pack(side=tk.LEFT, padx=4)

    def _delete_line() -> None:
        if not editable:
            return
        if not selected_idx:
            show_error("Інвентаризація", "Оберіть рядок")
            return
        idx = selected_idx[0]
        del line_data[idx]
        selected_idx.clear()
        refresh_lines()

    def _fill_counted() -> None:
        if not editable:
            return
        for ln in line_data:
            ln["counted_qty"] = ln["expected_qty"]
        refresh_lines()

    def _clear_counted() -> None:
        if not editable:
            return
        for ln in line_data:
            ln["counted_qty"] = 0.0
        refresh_lines()

    def _add_all_stock() -> None:
        if not editable:
            return
        wh_id = _current_warehouse_id()
        if not wh_id:
            show_error("Інвентаризація", "Оберіть склад.")
            return
        stock = db.stock_on_hand(wh_id)
        if not stock:
            messagebox.showinfo("Інвентаризація", "На складі немає залишків (qty>0).")
            refresh_lines()
            return
        added_any = False
        for product_id, qty in stock.items():
            if qty <= 0:
                continue
            if not _is_allowed_product(product_id):
                continue
            added_any = True
            existing = next((ln for ln in line_data if ln["product_id"] == product_id), None)
            if existing:
                existing["expected_qty"] = qty
                continue
            product = products_by_id.get(product_id)
            if not product:
                continue
            line_data.append(
                {
                    "product_id": product_id,
                    "sku": product["sku"],
                    "name": product["name"],
                    "expected_qty": float(qty),
                    "counted_qty": 0.0,
                    "cost_override": None,
                    "note": "",
                }
            )
        if (cat_var.get() or "Усі").strip() != "Усі" and not added_any:
            messagebox.showinfo("Інвентаризація", "У вибраній категорії немає залишків (qty>0).")
        refresh_lines()

    def _add_all_category_products() -> None:
        if not editable:
            return
        wh_id = _current_warehouse_id()
        if not wh_id:
            show_error("Інвентаризація", "Оберіть склад.")
            return
        display = (cat_var.get() or "Усі").strip()
        if display == "Усі":
            products_in_scope = products or db.list_products()
        else:
            cat_id = cat_display_to_id.get(display)
            if not cat_id:
                products_in_scope = []
            else:
                products_in_scope = db.list_products(
                    category_id=cat_id,
                    include_subcategories=include_children_var.get(),
                )
        stock = db.stock_on_hand(wh_id)
        added_any = False
        for product in products_in_scope:
            pid = int(product["id"])
            if not _is_allowed_product(pid):
                continue
            added_any = True
            expected = float(stock.get(pid, 0.0))
            existing = next((ln for ln in line_data if ln["product_id"] == pid), None)
            if existing:
                existing["expected_qty"] = expected
                continue
            line_data.append(
                {
                    "product_id": pid,
                    "sku": product["sku"],
                    "name": product["name"],
                    "expected_qty": expected,
                    "counted_qty": 0.0,
                    "cost_override": None,
                    "note": "",
                }
            )
        refresh_lines()
        if not added_any:
            messagebox.showinfo("Інвентаризація", "У вибраній категорії немає товарів.")

    def _import_lines_csv() -> None:
        if not editable:
            return
        wh_id = _current_warehouse_id()
        if not wh_id:
            show_error("Інвентаризація", "Оберіть склад.")
            return
        file_path = filedialog.askopenfilename(
            title="Імпорт CSV",
            defaultextension=".csv",
            initialdir=str(get_data_dir()),
            filetypes=[("CSV", "*.csv"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        not_found_codes: list[str] = []
        not_allowed_codes: list[str] = []
        bad_rows: list[str] = []
        updated_products: set[int] = set()
        new_products: set[int] = set()
        existing_product_ids = {ln["product_id"] for ln in line_data}
        prefix = _sanitize_barcode_prefix(settings.get("defaults", "product", "barcode_prefix") or "")
        try:
            def _read_csv_content(path: str) -> str:
                last_error = None
                for encoding in ("utf-8-sig", "cp1251"):
                    try:
                        with open(path, newline="", encoding=encoding) as f:
                            return f.read()
                    except UnicodeDecodeError as exc:
                        last_error = exc
                if last_error:
                    raise last_error
                raise OSError("CSV read failed")

            content = _read_csv_content(file_path)
            sample = content[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
                reader = csv.DictReader(io.StringIO(content), dialect=dialect)
            except csv.Error:
                reader = csv.DictReader(io.StringIO(content), delimiter=",")
            if not reader.fieldnames:
                messagebox.showerror("Імпорт CSV", "Файл не містить заголовків.")
                return
            field_map = {name.strip().lower(): name for name in reader.fieldnames if name}
            code_field = field_map.get("code") or field_map.get("sku")
            qty_field = field_map.get("qty") or field_map.get("counted_qty")
            if not code_field or not qty_field:
                messagebox.showerror("Імпорт CSV", "Потрібні колонки code/sku та qty/counted_qty.")
                return
            for row in reader:
                code = (row.get(code_field) or "").strip()
                if not code:
                    bad_rows.append("порожній код")
                    continue
                qty_raw = (row.get(qty_field) or "").strip()
                if "," in qty_raw and "." not in qty_raw:
                    qty_raw = qty_raw.replace(",", ".")
                try:
                    qty = float(qty_raw)
                except (TypeError, ValueError):
                    bad_rows.append(code)
                    continue
                if qty < 0:
                    bad_rows.append(code)
                    continue
                product = db.find_product_by_scan_code(code, barcode_prefix=prefix)
                if not product:
                    not_found_codes.append(code)
                    continue
                if not _is_allowed_product(int(product["id"])):
                    not_allowed_codes.append(code)
                    continue
                existing = next((ln for ln in line_data if ln["product_id"] == product["id"]), None)
                if existing:
                    existing["counted_qty"] += qty
                    if product["id"] in existing_product_ids:
                        updated_products.add(product["id"])
                    else:
                        new_products.add(product["id"])
                else:
                    expected_qty = db.get_stock_quantity(product["id"], wh_id)
                    line_data.append(
                        {
                            "product_id": product["id"],
                            "sku": product["sku"],
                            "name": product["name"],
                            "expected_qty": expected_qty,
                            "counted_qty": qty,
                            "cost_override": None,
                            "note": "",
                        }
                    )
                    new_products.add(product["id"])
        except Exception:
            logging.exception("Inventory CSV import error")
            show_error("Імпорт CSV", "Не вдалося імпортувати дані.")
            return
        refresh_lines()
        preview = ", ".join(not_found_codes[:20])
        summary = (
            "Імпорт завершено: "
            f"нових позицій: {len(new_products)}; "
            f"оновлено позицій: {len(updated_products)}; "
            f"рядків з помилками: {len(bad_rows)}; "
            f"не знайдено кодів: {len(not_found_codes)}."
        )
        if preview:
            summary += f"\nПроблемні коди: {preview}"
        messagebox.showinfo("Імпорт CSV", summary)
        if not_allowed_codes:
            skipped_preview = ", ".join(not_allowed_codes[:20])
            messagebox.showinfo(
                "Імпорт CSV",
                f"Пропущено (поза категорією): {skipped_preview}",
            )

    def _export_lines_csv() -> None:
        if not line_data:
            messagebox.showinfo("Експорт CSV", "Немає рядків для експорту.")
            return
        file_path = filedialog.asksaveasfilename(
            title="Експорт CSV",
            defaultextension=".csv",
            initialfile="inventory_lines.csv",
            initialdir=str(get_data_dir()),
            filetypes=[("CSV", "*.csv"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["sku", "name", "expected_qty", "counted_qty", "diff", "cost_override", "note"])
            for ln in line_data:
                diff = ln["counted_qty"] - ln["expected_qty"]
                writer.writerow(
                    [
                        ln["sku"],
                        ln["name"],
                        ln["expected_qty"],
                        ln["counted_qty"],
                        diff,
                        ln["cost_override"] if ln.get("cost_override") is not None else "",
                        ln.get("note", ""),
                    ]
                )
        messagebox.showinfo("Експорт CSV", "Дані збережено.")

    btn_row = ttk.Frame(line_frame)
    btn_row.grid(row=2, column=0, columnspan=2, pady=(4, 0), sticky="w")
    ttk.Button(btn_row, text="Додати товар…", command=_add_product, state="normal" if editable else "disabled").pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(
        btn_row,
        text="Редагувати рядок…",
        command=_edit_line,
        state="normal" if editable else "disabled",
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_row, text="Видалити рядок", command=_delete_line, state="normal" if editable else "disabled").pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(
        btn_row,
        text="Додати всі залишки (qty>0)",
        command=_add_all_stock,
        state="normal" if editable else "disabled",
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        btn_row,
        text="Додати всі товари категорії (вкл. qty=0)",
        command=_add_all_category_products,
        state="normal" if editable else "disabled",
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_row, text="Імпорт CSV…", command=_import_lines_csv, state="normal" if editable else "disabled").pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(
        btn_row,
        text="Заповнити факт = очікувано",
        command=_fill_counted,
        state="normal" if editable else "disabled",
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_row, text="Очистити факт", command=_clear_counted, state="normal" if editable else "disabled").pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(btn_row, text="Експорт CSV…", command=_export_lines_csv).pack(side=tk.LEFT, padx=4)

    def _on_scan(event=None) -> None:
        if not editable:
            return
        code = scan_var.get().strip()
        if not code:
            return
        prefix = _sanitize_barcode_prefix(settings.get("defaults", "product", "barcode_prefix") or "")
        product = db.find_product_by_scan_code(code, barcode_prefix=prefix)
        if not product:
            scan_status.config(text="Товар не знайдено", foreground="#b91c1c")
            scan_entry.bell()
            return
        if not _is_allowed_product(int(product["id"])):
            scan_status.config(text="Товар поза вибраною категорією", foreground="#b91c1c")
            scan_entry.bell()
            scan_var.set("")
            scan_entry.focus_set()
            return
        qty = float(scan_qty_var.get() or 1)
        _add_line(product, counted_delta=qty)
        scan_var.set("")
        scan_status.config(text=f"OK: {product['sku']} — {product['name']}", foreground="#15803d")
        scan_entry.focus_set()

    scan_entry.bind("<Return>", _on_scan)

    def _on_warehouse_change(event=None) -> None:
        balance_cache.clear()
        if not editable:
            return
        wh_id = _current_warehouse_id()
        if wh_id is None:
            return
        for ln in line_data:
            ln["expected_qty"] = db.get_stock_quantity(ln["product_id"], wh_id)
        refresh_lines()

    wh_combo.bind("<<ComboboxSelected>>", _on_warehouse_change)
    cat_combo.bind("<<ComboboxSelected>>", lambda _event: _rebuild_allowed_products())
    include_children_check.configure(command=_rebuild_allowed_products)
    _rebuild_allowed_products()

    refresh_lines()
    if editable:
        scan_entry.focus_set()

    result: dict[str, object] = {}

    def _validate_lines() -> bool:
        missing = [ln for ln in line_data if _needs_cost(ln)]
        if missing:
            messagebox.showerror("Валідація", "Для надлишку потрібна собівартість.")
            return False
        for ln in line_data:
            if ln["counted_qty"] < 0:
                messagebox.showerror("Валідація", "Фактична кількість не може бути від'ємною.")
                return False
            if ln.get("cost_override") is not None and ln["cost_override"] < 0:
                messagebox.showerror("Валідація", "Собівартість не може бути від'ємною.")
                return False
        return True

    def _on_ok() -> None:
        if not editable:
            dlg.destroy()
            return
        wh_id = _current_warehouse_id()
        if not wh_id:
            messagebox.showerror("Валідація", "Оберіть склад.")
            return
        if not _validate_lines():
            return
        info = {
            "doc_date": _parse_date_value(_current_date()),
            "warehouse_id": wh_id,
            "comment": comment_var.get().strip(),
        }
        result["info"] = info
        result["lines"] = [
            {
                "product_id": ln["product_id"],
                "expected_qty": ln["expected_qty"],
                "counted_qty": ln["counted_qty"],
                "cost_override": ln.get("cost_override"),
                "note": ln.get("note", ""),
            }
            for ln in line_data
        ]
        result["post_now"] = bool(post_now_var.get())
        dlg.destroy()

    def _on_cancel() -> None:
        dlg.destroy()

    btns = ttk.Frame(content)
    btns.grid(row=row_idx + 1, column=0, columnspan=2, pady=8)
    if editable:
        ttk.Button(btns, text="OK", command=_on_ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Скасувати", command=_on_cancel).pack(side=tk.LEFT, padx=6)
    else:
        ttk.Button(btns, text="Закрити", command=_on_cancel).pack(side=tk.LEFT, padx=6)

    dlg.wait_window()
    if "info" not in result:
        return None
    return result["info"], result["lines"], result["post_now"]
