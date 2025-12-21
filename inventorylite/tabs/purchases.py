from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from inventorylite import db
from inventorylite.helpers import (
    PURCHASE_FIELDS,
    _normalize_purchase_records,
    _suggest_purchase_mapping,
    parse_import_file,
)
from inventorylite.dialogs_documents import document_prompt, ensure_rate_for_date
from inventorylite.ui_components import DatePicker, TableFrame, simple_prompt
from inventorylite.utils import Settings, show_error, get_base_currency_code


class PurchasesTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        default_workdir_provider: Callable[[], Path],
        generate_unique_sku: Callable[[str, set[str]], str],
        on_refresh_stock: Callable[[], None],
        on_refresh_cash: Callable[[], None],
        open_labels_dialog: Callable[[tk.Misc, list[dict], str], None],
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.settings = settings
        self.default_workdir_provider = default_workdir_provider
        self.generate_unique_sku = generate_unique_sku
        self.on_refresh_stock = on_refresh_stock
        self.on_refresh_cash = on_refresh_cash
        self.open_labels_dialog = open_labels_dialog

        self.purchase_status_var = tk.StringVar(value="Усі")
        self.purchase_date_from_var = tk.StringVar()
        self.purchase_date_to_var = tk.StringVar()
        self.purchase_table: TableFrame | None = None

        self._build()

    def _build(self) -> None:
        filters = ttk.Frame(self.frame)
        filters.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        status_combo = ttk.Combobox(
            filters,
            textvariable=self.purchase_status_var,
            values=["Усі", "Чернетка", "Проведений"],
            state="readonly",
            width=14,
        )
        status_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.purchase_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.purchase_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(filters, text="Фільтр", command=self.refresh_purchases).pack(side=tk.LEFT, padx=6)

        columns = [
            ("doc_date", "Дата", 90),
            ("supplier", "Постачальник", 200),
            ("warehouse", "Склад", 160),
            ("status", "Статус", 90),
            ("currency", "Валюта", 80),
            ("rate", "Курс", 80),
            ("total_doc", "Сума (вал)", 110),
            ("total", "Сума (база)", 110),
            ("total_extra", "Супутні (база)", 120),
            ("comment", "Коментар", 240),
        ]
        self.purchase_table = TableFrame(self.frame, columns)
        self.purchase_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.purchase_table.on_double_click(self.edit_purchase)
        self.purchase_table.register_context_menu_actions(
            [
                ("Редагувати", self.edit_purchase),
                ("Видалити", self.delete_purchase),
                ("---", None),
                ("Друк етикеток…", self.print_purchase_labels),
            ]
        )

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Нова закупівля", command=self.new_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_purchase_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_purchase_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Імпорт із файлу", command=self.import_purchases_from_file).pack(side=tk.LEFT, padx=4)

    def _selected_purchase(self):
        if not self.purchase_table:
            return None
        doc_id = self.purchase_table.selected_id()
        if not doc_id:
            show_error("Закупівлі", "Оберіть документ")
            return None
        return doc_id

    def refresh_purchases(self) -> None:
        if not self.purchase_table:
            return
        status_filter = self.purchase_status_var.get()
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        rows = db.list_purchases(
            status_value,
            self.purchase_date_from_var.get().strip() or None,
            self.purchase_date_to_var.get().strip() or None,
        )
        self.purchase_table.set_rows(
            [
                {
                    "id": r["id"],
                    "doc_date": r["doc_date"],
                    "supplier": r["supplier"] or "-",
                    "warehouse": r["warehouse"] or "-",
                    "status": "Чернетка" if r["status"] == "draft" else "Проведений",
                    "currency": r["currency_code"],
                    "rate": f"{r['exchange_rate']:.4f}",
                    "total_doc": f"{r['total_doc']:.2f}",
                    "total": f"{r['total']:.2f}",
                    "total_extra": f"{r['total_extra_base']:.2f}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def new_purchase(self) -> None:
        products = db.list_products()
        warehouses = db.list_warehouses(active_only=True)
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        result = document_prompt("purchase", products, counterparties, warehouses, [], currencies, settings=self.settings)
        if not result:
            return
        info, lines = result
        try:
            doc_id = db.create_purchase(
                info["doc_date"],
                info["counterparty_id"],
                info["warehouse_id"],
                "",
                info["comment"],
                info["currency"],
                info["rate"],
            )
            db.replace_purchase_lines(doc_id, lines, info["rate"])
            self.refresh_purchases()
        except Exception:
            logging.exception("Create purchase error")
            show_error("Закупівлі", "Не вдалося створити документ")

    def edit_purchase(self) -> None:
        doc_id = self._selected_purchase()
        if not doc_id:
            return
        doc = db.get_purchase(doc_id)
        if not doc:
            return
        lines = db.list_purchase_lines(doc_id)
        products = db.list_products()
        warehouses = db.list_warehouses(active_only=False)
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        result = document_prompt(
            "purchase",
            products,
            counterparties,
            warehouses,
            [],
            currencies,
            doc=doc,
            lines=lines,
            settings=self.settings,
        )
        if not result:
            return
        info, new_lines = result
        try:
            if doc["status"] == "draft":
                db.update_purchase(
                    doc_id,
                    info["doc_date"],
                    info["counterparty_id"],
                    info["warehouse_id"],
                    "",
                    info["comment"],
                    info["currency"],
                    info["rate"],
                )
                db.replace_purchase_lines(doc_id, new_lines, info["rate"])
            else:
                db.update_purchase(
                    doc_id,
                    doc["doc_date"],
                    doc["supplier_id"],
                    doc["warehouse_id"],
                    "",
                    info["comment"],
                    doc["currency_code"],
                    doc["exchange_rate"],
                )
            self.refresh_purchases()
        except Exception:
            logging.exception("Edit purchase error")
            show_error("Закупівлі", "Не вдалося змінити документ")

    def delete_purchase(self) -> None:
        doc_id = self._selected_purchase()
        if not doc_id:
            return
        if not messagebox.askyesno("Підтвердження", "Видалити документ?"):
            return
        try:
            with db.get_connection() as conn:
                with db.safe_transaction(conn):
                    status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (doc_id,)).fetchone()
                    if status and status[0] == "posted":
                        raise ValueError("Видаляти можна лише чернетки")
                    conn.execute("DELETE FROM PurchaseDocuments WHERE id=?", (doc_id,))
            self.refresh_purchases()
        except Exception as exc:
            logging.exception("Delete purchase error")
            show_error("Закупівлі", str(exc))

    def print_purchase_labels(self) -> None:
        if not self.purchase_table:
            return
        doc_id = self.purchase_table.selected_id()
        if not doc_id:
            show_error("Закупівлі", "Оберіть документ")
            return
        try:
            lines = db.list_purchase_lines(doc_id)
        except Exception:
            logging.exception("Failed to load purchase lines for labels")
            show_error("Етикетки", "Не вдалося завантажити позиції документа")
            return
        aggregated: dict[int, dict[str, object]] = {}
        for line in lines:
            try:
                pid = int(line["product_id"])
            except (TypeError, ValueError):
                continue
            qty = float(line["quantity"] or 0)
            if pid not in aggregated:
                aggregated[pid] = {
                    "product_id": pid,
                    "sku": line["sku"] or "",
                    "name": line["product_name"] or "",
                    "qty": 0.0,
                }
            aggregated[pid]["qty"] = float(aggregated[pid].get("qty", 0.0) or 0.0) + qty
        items = [item for item in aggregated.values() if float(item.get("qty", 0) or 0) > 0]
        if not items:
            messagebox.showwarning("Етикетки", "У документі немає позицій з кількістю > 0.")
            return
        self.open_labels_dialog(self.frame.winfo_toplevel(), items, "Кількість з документа закупівлі")

    def post_purchase_action(self) -> None:
        doc_id = self._selected_purchase()
        if not doc_id:
            return
        try:
            db.post_purchase(doc_id)
            self.refresh_purchases()
            self.on_refresh_stock()
            self.on_refresh_cash()
        except Exception as exc:
            logging.exception("Post purchase error")
            show_error("Закупівлі", str(exc))

    def unpost_purchase_action(self) -> None:
        doc_id = self._selected_purchase()
        if not doc_id:
            return
        try:
            db.unpost_purchase(doc_id)
            self.refresh_purchases()
            self.on_refresh_stock()
            self.on_refresh_cash()
        except Exception as exc:
            logging.exception("Unpost purchase error")
            show_error("Закупівлі", str(exc))

    def import_purchases_from_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Файл закупівель",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Усі файли", "*.*")],
            initialdir=str(self.default_workdir_provider()),
        )
        if not file_path:
            return

        try:
            raw_rows, headers = parse_import_file(
                Path(file_path),
                encoding=self.settings.get("files", "encoding") or "utf-8",
            )
        except Exception as exc:
            logging.exception("Не вдалося прочитати файл імпорту закупівель")
            show_error(
                "Імпорт закупівель",
                "Не вдалося прочитати файл. Перевірте формат, кодування та структуру даних.\n" + str(exc),
            )
            return

        if not raw_rows:
            messagebox.showinfo("Імпорт закупівель", "У файлі не знайдено рядків із товарами.")
            return

        warehouses = db.list_warehouses(active_only=True)
        if not warehouses:
            show_error("Імпорт закупівель", "Спочатку створіть хоча б один склад.")
            return

        counterparties = [dict(c) for c in db.list_counterparties()]
        suppliers = sorted(
            (c for c in counterparties if c["type"] in {"supplier", "both", "other"}),
            key=lambda c: c.get("name", ""),
        )
        if not suppliers:
            show_error("Імпорт закупівель", "Спочатку додайте постачальника у контрагенти.")
            return
        currencies = db.list_currencies()

        dialog = PurchasesImportDialog(
            self.frame.winfo_toplevel(),
            raw_rows,
            headers,
            warehouses,
            suppliers,
            currencies,
            self.settings,
        )
        result = dialog.result
        if not result:
            return

        try:
            summary = self._process_purchase_import(result["orders"], result["options"])
        except Exception:
            logging.exception("Помилка під час імпорту закупівель")
            show_error("Імпорт закупівель", "Імпорт перервано помилкою. Деталі у логах.")
            return

        messagebox.showinfo("Імпорт закупівель", summary)
        self.refresh_purchases()
        self.on_refresh_cash()
        self.on_refresh_stock()

    def _process_purchase_import(self, orders: list[dict], options: dict) -> str:
        warehouse_id = options["warehouse_id"]
        mode = options.get("mode", "draft")
        create_products = bool(options.get("create_products", True))
        selected_supplier_id = options.get("supplier_id")
        currency_code = (options.get("currency_code") or get_base_currency_code()).strip().upper()
        exchange_rate = float(options.get("exchange_rate") or 1.0)

        product_rows = db.list_products()
        products_by_sku = {p["sku"].lower(): dict(p) for p in product_rows if p["sku"]}
        products_by_name = {p["name"].lower(): dict(p) for p in product_rows if p["name"]}
        products_by_supplier_sku = {p["supplier_sku"].lower(): dict(p) for p in product_rows if p.get("supplier_sku")}

        default_brand = self.settings.get("defaults", "product", "brand") or "Імпорт"
        default_category = self.settings.get("defaults", "product", "category") or "Імпорт"
        default_unit = (self.settings.get("defaults", "product", "unit") or "pcs").strip() or "pcs"
        brand_id, category_id = db.ensure_import_defaults(default_brand, default_category)

        created_products = 0
        skipped_lines = 0
        posted_docs = 0
        draft_docs = 0
        total_docs = 0

        doc_date = next((r.get("doc_date") for r in orders if r.get("doc_date")), None) or datetime.now().strftime(
            "%Y-%m-%d"
        )
        supplier_id = selected_supplier_id
        if not supplier_id:
            raise ValueError("Не вказано постачальника для імпорту закупівель")
        with db.get_connection() as conn:
            supplier_code_rows = conn.execute(
                """
                SELECT lower(psc.supplier_sku) AS k, p.id, p.sku, p.supplier_sku, p.name, p.brand_id, p.category_id, p.unit, p.is_active
                FROM ProductSupplierCodes psc
                JOIN Products p ON p.id = psc.product_id
                WHERE psc.supplier_id = ?
                """,
                (supplier_id,),
            ).fetchall()
        products_by_supplier_code = {
            row["k"]: {key: row[key] for key in row.keys() if key != "k"} for row in supplier_code_rows
        }
        purchase_lines: list[tuple[int, float, float]] = []
        comments: list[str] = []

        for row in orders:
            comment_val = (row.get("comment") or "").strip()
            if comment_val:
                comments.append(comment_val)

            sku = (row.get("sku") or "").strip()
            supplier_sku = (row.get("supplier_sku") or "").strip()
            name = (row.get("product_name") or sku or "Без назви").strip()
            qty = float(row.get("quantity") or 0)
            price = float(row.get("price") or 0)
            amount = float(row.get("amount") or 0)
            if not price and qty and amount:
                price = amount / qty

            product_row = products_by_supplier_code.get(supplier_sku.lower()) if supplier_sku else None
            if not product_row:
                product_row = products_by_supplier_sku.get(supplier_sku.lower()) if supplier_sku else None
            if not product_row:
                product_row = products_by_sku.get(sku.lower()) if sku else None
            if not product_row and name:
                product_row = products_by_name.get(name.lower())
            if not product_row and create_products:
                final_sku = sku or self.generate_unique_sku(name, set(products_by_sku.keys()))
                product_id = db.add_product(
                    final_sku,
                    name,
                    brand_id,
                    category_id,
                    unit=default_unit,
                    supplier_sku=supplier_sku,
                )
                product_row = {
                    "id": product_id,
                    "sku": final_sku,
                    "name": name,
                    "supplier_sku": supplier_sku,
                    "brand_id": brand_id,
                    "category_id": category_id,
                    "unit": default_unit,
                    "is_active": True,
                }
                if supplier_sku:
                    try:
                        db.replace_product_supplier_codes(
                            product_id,
                            [
                                {
                                    "supplier_id": supplier_id,
                                    "supplier_sku": supplier_sku,
                                    "is_primary": True,
                                }
                            ],
                        )
                        products_by_supplier_code[supplier_sku.lower()] = product_row
                    except sqlite3.IntegrityError as exc:
                        logging.warning("Не вдалося зберегти артикул постачальника для імпорту: %s", exc)
                products_by_sku[final_sku.lower()] = product_row
                if supplier_sku:
                    products_by_supplier_sku[supplier_sku.lower()] = product_row
                products_by_name[name.lower()] = product_row
                created_products += 1

            if not product_row or qty <= 0:
                skipped_lines += 1
                continue

            purchase_lines.append((int(product_row["id"]), qty, price))

        if not purchase_lines:
            return "Не знайдено жодного рядка з товарами для створення закупівлі."

        total_docs = 1
        try:
            if currency_code != get_base_currency_code():
                try:
                    db.add_currency_rate(currency_code, doc_date, exchange_rate)
                except Exception as exc:
                    logging.warning("Не вдалося зберегти курс %s на %s: %s", currency_code, doc_date, exc)

            purchase_id = db.create_purchase(
                doc_date, supplier_id, warehouse_id, "", "; ".join(dict.fromkeys(comments)), currency_code, exchange_rate
            )
            db.replace_purchase_lines(purchase_id, purchase_lines, exchange_rate)
        except Exception as exc:
            logging.warning("Не вдалося створити закупівлю: %s", exc)
            skipped_lines += len(purchase_lines)
            total_docs = 0
            posted_docs = 0
            draft_docs = 0
        else:
            if mode == "post":
                try:
                    db.post_purchase(purchase_id)
                    posted_docs = 1
                    draft_docs = 0
                except Exception as exc:
                    logging.warning("Проведення закупівлі #%s завершилось помилкою: %s", purchase_id, exc)
                    posted_docs = 0
                    draft_docs = 1
            else:
                posted_docs = 0
                draft_docs = 1

        lines_msg = f"Пропущено рядків: {skipped_lines}" if skipped_lines else "Без пропусків"
        created_parts = []
        if created_products:
            created_parts.append(f"створено товарів: {created_products}")
        created_msg = ", ".join(created_parts) if created_parts else "без нових довідників"
        return (
            f"Опрацьовано документів: {total_docs}. Проведено: {posted_docs}, чернеток: {draft_docs}. "
            f"{lines_msg}; {created_msg}."
        )


class PurchasesImportDialog(tk.Toplevel):
    def __init__(
        self,
        app: tk.Tk,
        raw_rows: list[dict[str, object]],
        headers: list[str],
        warehouses,
        suppliers,
        currencies,
        settings,
    ) -> None:
        super().__init__(app)
        self.title("Імпорт закупівель")
        self.resizable(True, True)
        self.grab_set()
        self.result: Optional[dict] = None
        self.raw_rows = raw_rows
        self.headers = headers
        self.warehouses = warehouses
        self.suppliers = suppliers
        self.supplier_names = list(dict.fromkeys([s["name"] for s in suppliers if s.get("name")]))
        self.currencies = currencies
        self.currency_codes = [c["code"] for c in currencies] if currencies else [get_base_currency_code()]
        self.settings = settings
        self.templates: dict[str, dict[str, str]] = settings.get("purchase_import", "templates") or {}
        self.current_mapping = _suggest_purchase_mapping(headers)

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        info = ttk.Label(main, text=f"Рядків у файлі: {len(raw_rows)}")
        info.grid(row=0, column=0, columnspan=3, sticky="w")

        self._build_template_controls(main)
        self._build_mapping_controls(main)
        self._build_options(main)
        self.preview = self._build_preview(main)
        self._refresh_preview()

        btns = ttk.Frame(main)
        btns.grid(row=14, column=0, columnspan=3, pady=8, sticky="e")
        ttk.Button(btns, text="Скасувати", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="Імпортувати", command=self._on_ok).pack(side=tk.RIGHT, padx=4)

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_window(self)

    def _on_ok(self) -> None:
        warehouse = next((w for w in self.warehouses if w["name"] == self.wh_var.get()), None)
        supplier = next((s for s in self.suppliers if s["name"] == self.supplier_var.get()), None)
        if not warehouse:
            show_error("Імпорт", "Оберіть склад")
            return
        if not supplier:
            show_error("Імпорт", "Оберіть постачальника")
            return

        try:
            exchange_rate = float(self.rate_var.get())
        except ValueError:
            show_error("Імпорт", "Курс має бути числом")
            return
        if exchange_rate <= 0:
            show_error("Імпорт", "Курс має бути більшим за 0")
            return

        normalized_orders = _normalize_purchase_records(
            self.raw_rows,
            self.current_mapping,
            default_supplier=self.supplier_var.get().strip(),
            default_doc_date=self.date_picker.get(),
            default_order_no=self.order_no_var.get(),
            default_comment=self.comment_var.get(),
        )
        self.result = {
            "options": {
                "warehouse_id": warehouse["id"],
                "supplier_id": supplier["id"],
                "mode": self.mode_var.get(),
                "create_products": bool(self.create_products_var.get()),
                "currency_code": self.currency_var.get(),
                "exchange_rate": exchange_rate,
            },
            "orders": normalized_orders,
        }
        self.settings.set(self.current_template_name.get(), "purchase_import", "last_template")
        self.settings.save()
        self.destroy()

    def _build_template_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Шаблон співставлення:").grid(row=1, column=0, sticky="w", pady=4)
        self.current_template_name = tk.StringVar(value=self.settings.get("purchase_import", "last_template") or "")
        self.template_combo = ttk.Combobox(
            parent, textvariable=self.current_template_name, values=list(self.templates.keys()), state="readonly"
        )
        self.template_combo.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Застосувати", command=self._apply_template).grid(row=1, column=2, padx=4, sticky="w")
        ttk.Button(parent, text="Зберегти як…", command=self._save_template).grid(row=1, column=3, padx=4, sticky="w")

    def _build_mapping_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Співставлення колонок:").grid(row=2, column=0, sticky="nw", pady=4)
        mapping_frame = ttk.Frame(parent)
        mapping_frame.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
        mapping_frame.columnconfigure(1, weight=1)

        options = ["(не використовувати)"] + self.headers
        self.mapping_vars: dict[str, tk.StringVar] = {}
        for idx, (field_key, field_label, _aliases) in enumerate(PURCHASE_FIELDS):
            ttk.Label(mapping_frame, text=field_label).grid(row=idx, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=self.current_mapping.get(field_key, ""))
            combo = ttk.Combobox(mapping_frame, textvariable=var, values=options, state="readonly")
            combo.grid(row=idx, column=1, sticky="ew", pady=2)
            combo.bind("<<ComboboxSelected>>", lambda _e, key=field_key, v=var: self._update_mapping(key, v.get()))
            self.mapping_vars[field_key] = var

    def _build_options(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Склад для імпорту:").grid(row=3, column=0, sticky="w", pady=4)
        self.wh_var = tk.StringVar(value=self.warehouses[0]["name"] if self.warehouses else "")
        wh_combo = ttk.Combobox(
            parent,
            textvariable=self.wh_var,
            values=[w["name"] for w in self.warehouses],
            state="readonly",
        )
        wh_combo.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Постачальник:").grid(row=4, column=0, sticky="w", pady=4)
        self.supplier_var = tk.StringVar(value=self.supplier_names[0] if self.supplier_names else "")
        supplier_combo = ttk.Combobox(parent, textvariable=self.supplier_var, values=self.supplier_names, state="readonly")
        supplier_combo.grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Дата документа:").grid(row=5, column=0, sticky="w", pady=4)
        self.date_picker = DatePicker(parent)
        self.date_picker.grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Валюта:").grid(row=6, column=0, sticky="w", pady=4)
        default_currency = self.currency_codes[0] if self.currency_codes else get_base_currency_code()
        self.currency_var = tk.StringVar(value=default_currency)
        currency_combo = ttk.Combobox(parent, textvariable=self.currency_var, values=self.currency_codes, state="readonly")
        currency_combo.grid(row=6, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Курс:").grid(row=7, column=0, sticky="w", pady=4)
        try:
            default_rate = ensure_rate_for_date(self.currency_var.get(), self.date_picker.get())
        except Exception:
            default_rate = 1.0
        self.rate_var = tk.StringVar(value=f"{default_rate:.4f}")
        ttk.Entry(parent, textvariable=self.rate_var, width=14).grid(row=7, column=1, sticky="w", pady=4)

        def on_currency_change(_event=None):
            try:
                rate_val = ensure_rate_for_date(self.currency_var.get(), self.date_picker.get())
            except ValueError as exc:
                messagebox.showerror("Курс", str(exc))
                self.currency_var.set(default_currency)
                return
            self.rate_var.set(f"{rate_val:.4f}")

        currency_combo.bind("<<ComboboxSelected>>", on_currency_change)

        ttk.Label(parent, text="Замовлення/рахунок:").grid(row=8, column=0, sticky="w", pady=4)
        self.order_no_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.order_no_var).grid(row=8, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Коментар:").grid(row=9, column=0, sticky="w", pady=4)
        self.comment_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.comment_var).grid(row=9, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Режим проведення:").grid(row=10, column=0, sticky="nw", pady=4)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=10, column=1, sticky="w", pady=4)
        self.mode_var = tk.StringVar(value="post")
        ttk.Radiobutton(mode_frame, text="Провести всі", variable=self.mode_var, value="post").pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Тільки чернетки", variable=self.mode_var, value="draft").pack(anchor="w")

        self.create_products_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Створювати відсутні товари", variable=self.create_products_var).grid(
            row=11, column=1, sticky="w", pady=(4, 0)
        )

    def _build_preview(self, parent: ttk.Frame) -> ttk.Treeview:
        ttk.Label(parent, text="Попередній перегляд (перші 30 рядків):").grid(
            row=12, column=0, columnspan=3, sticky="w", pady=6
        )
        preview = ttk.Treeview(
            parent,
            columns=("order", "date", "supplier", "sku", "name", "qty", "price"),
            show="headings",
            height=10,
        )
        headings = {
            "order": ("Замовлення", 120),
            "date": ("Дата", 90),
            "supplier": ("Постачальник", 180),
            "sku": ("SKU", 90),
            "name": ("Товар", 200),
            "qty": ("К-сть", 70),
            "price": ("Ціна", 90),
        }
        for col, (title, width) in headings.items():
            preview.heading(col, text=title)
            preview.column(col, width=width, anchor="w")
        preview.grid(row=13, column=0, columnspan=3, sticky="nsew")
        parent.grid_rowconfigure(13, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=preview.yview)
        preview.configure(yscrollcommand=scroll.set)
        scroll.grid(row=13, column=3, sticky="ns")
        return preview

    def _refresh_preview(self) -> None:
        self.preview.delete(*self.preview.get_children())
        normalized = _normalize_purchase_records(
            self.raw_rows,
            self.current_mapping,
            default_supplier=self.supplier_var.get().strip(),
            default_doc_date=self.date_picker.get(),
            default_order_no=self.order_no_var.get(),
            default_comment=self.comment_var.get(),
        )
        for row in normalized[:30]:
            self.preview.insert(
                "",
                "end",
                values=(
                    row.get("order_no") or "-",
                    row.get("doc_date"),
                    row.get("supplier"),
                    row.get("sku"),
                    row.get("product_name"),
                    f"{float(row.get('quantity') or 0):.2f}",
                    f"{float(row.get('price') or 0):.2f}",
                ),
            )

    def _update_mapping(self, key: str, value: str) -> None:
        clean_value = "" if value == "(не використовувати)" else value
        self.current_mapping[key] = clean_value
        self._refresh_preview()

    def _apply_template(self) -> None:
        name = self.current_template_name.get().strip()
        if not name or name not in self.templates:
            return
        template = self.templates[name]
        for key, var in self.mapping_vars.items():
            var.set(template.get(key, ""))
            self.current_mapping[key] = template.get(key, "")
        self._refresh_preview()

    def _save_template(self) -> None:
        values = simple_prompt(
            "Назва шаблону",
            ["Вкажіть назву шаблону"],
            [self.current_template_name.get().strip()],
        )
        if not values:
            return

        name = values[0].strip()
        if not name:
            return

        self.templates[name] = dict(self.current_mapping)
        self.settings.set(self.templates, "purchase_import", "templates")
        self.settings.set(name, "purchase_import", "last_template")
        self.settings.save()
        self.current_template_name.set(name)
        self.template_combo.configure(values=list(self.templates.keys()))
