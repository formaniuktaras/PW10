"""InventoryLite minimal Tkinter app."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import traceback

import db
from utils import (
    APP_NAME,
    VERSION,
    SingleInstance,
    configure_logging,
    get_data_dir,
    get_db_path,
    get_lock_path,
    backup_database,
    open_data_folder,
    show_error,
)
from ui_components import TableFrame, simple_prompt


class InventoryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1020x680")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.create_menu()

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.brands_frame = ttk.Frame(notebook)
        self.categories_frame = ttk.Frame(notebook)
        self.products_frame = ttk.Frame(notebook)
        self.counterparties_frame = ttk.Frame(notebook)
        self.documents_frame = ttk.Frame(notebook)
        self.stock_frame = ttk.Frame(notebook)
        self.export_frame = ttk.Frame(notebook)
        self.about_frame = ttk.Frame(notebook)

        notebook.add(self.brands_frame, text="Бренди")
        notebook.add(self.categories_frame, text="Категорії")
        notebook.add(self.products_frame, text="Товари")
        notebook.add(self.counterparties_frame, text="Контрагенти")
        notebook.add(self.documents_frame, text="Документи")
        notebook.add(self.stock_frame, text="Залишки")
        notebook.add(self.export_frame, text="Експорт")
        notebook.add(self.about_frame, text="Про програму")

        self.create_brands_tab()
        self.create_categories_tab()
        self.create_products_tab()
        self.create_counterparties_tab()
        self.create_documents_tab()
        self.create_stock_tab()
        self.create_export_tab()
        self.create_about_tab()

        self.refresh_all()

    # Menu
    def create_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Резервна копія БД", command=self.on_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.config(menu=menubar)

    def on_backup(self) -> None:
        try:
            target = backup_database(get_db_path())
            messagebox.showinfo("Резервна копія", f"Створено: {target}")
        except Exception as exc:
            logging.exception("Backup failed")
            show_error("Резервна копія", str(exc))

    # Brands
    def create_brands_tab(self) -> None:
        columns = [("name", "Назва", 300)]
        self.brand_table = TableFrame(self.brands_frame, columns)
        self.brand_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.brands_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_brand).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_brand).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_brand).pack(side=tk.LEFT, padx=4)

    def add_brand(self) -> None:
        values = simple_prompt("Новий бренд", ["Назва бренду"])
        if not values:
            return
        try:
            db.add_brand(values[0])
            self.refresh_brands()
        except sqlite3.IntegrityError:
            show_error("Бренди", "Бренд з такою назвою вже існує.")
        except Exception:
            logging.exception("Add brand error")
            show_error("Бренди", "Не вдалося додати бренд.")

    def edit_brand(self) -> None:
        brand_id = self.brand_table.selected_id()
        if not brand_id:
            show_error("Бренди", "Оберіть бренд для редагування.")
            return
        rows = [b for b in db.list_brands() if b["id"] == brand_id]
        values = simple_prompt("Редагувати бренд", ["Назва бренду"], [rows[0]["name"]] if rows else None)
        if not values:
            return
        try:
            db.update_brand(brand_id, values[0])
            self.refresh_brands()
            self.refresh_products()
        except sqlite3.IntegrityError:
            show_error("Бренди", "Бренд з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit brand error")
            show_error("Бренди", "Не вдалося змінити бренд.")

    def delete_brand(self) -> None:
        brand_id = self.brand_table.selected_id()
        if not brand_id:
            show_error("Бренди", "Оберіть бренд для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити бренд та пов'язані товари?"):
            return
        try:
            db.delete_brand(brand_id)
            self.refresh_brands()
            self.refresh_products()
        except Exception:
            logging.exception("Delete brand error")
            show_error("Бренди", "Не вдалося видалити бренд.")

    # Categories
    def create_categories_tab(self) -> None:
        columns = [("name", "Назва", 300)]
        self.category_table = TableFrame(self.categories_frame, columns)
        self.category_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.categories_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_category).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_category).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_category).pack(side=tk.LEFT, padx=4)

    def add_category(self) -> None:
        values = simple_prompt("Нова категорія", ["Назва категорії"])
        if not values:
            return
        try:
            db.add_category(values[0])
            self.refresh_categories()
        except sqlite3.IntegrityError:
            show_error("Категорії", "Категорія з такою назвою вже існує.")
        except Exception:
            logging.exception("Add category error")
            show_error("Категорії", "Не вдалося додати категорію.")

    def edit_category(self) -> None:
        category_id = self.category_table.selected_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для редагування.")
            return
        rows = [c for c in db.list_categories() if c["id"] == category_id]
        values = simple_prompt("Редагувати категорію", ["Назва категорії"], [rows[0]["name"]] if rows else None)
        if not values:
            return
        try:
            db.update_category(category_id, values[0])
            self.refresh_categories()
            self.refresh_products()
        except sqlite3.IntegrityError:
            show_error("Категорії", "Категорія з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit category error")
            show_error("Категорії", "Не вдалося змінити категорію.")

    def delete_category(self) -> None:
        category_id = self.category_table.selected_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити категорію та пов'язані товари?"):
            return
        try:
            db.delete_category(category_id)
            self.refresh_categories()
            self.refresh_products()
        except Exception:
            logging.exception("Delete category error")
            show_error("Категорії", "Не вдалося видалити категорію.")

    # Products
    def create_products_tab(self) -> None:
        top = ttk.Frame(self.products_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук (SKU/назва):").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Знайти", command=self.on_search).pack(side=tk.LEFT)

        columns = [
            ("sku", "SKU", 140),
            ("name", "Назва", 220),
            ("brand", "Бренд", 140),
            ("category", "Категорія", 140),
        ]
        self.product_table = TableFrame(self.products_frame, columns)
        self.product_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.products_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_product).pack(side=tk.LEFT, padx=4)

    def on_search(self) -> None:
        self.refresh_products(self.search_var.get())

    def add_product(self) -> None:
        brands = db.list_brands()
        categories = db.list_categories()
        if not brands or not categories:
            show_error("Товари", "Спочатку додайте бренд і категорію.")
            return
        values = product_prompt(brands, categories, title="Новий товар")
        if not values:
            return
        sku, name, brand_id, category_id = values
        try:
            db.add_product(sku, name, brand_id, category_id)
            self.refresh_products()
        except sqlite3.IntegrityError as exc:
            if "sku" in str(exc).lower():
                show_error("Товари", "SKU має бути унікальним.")
            else:
                show_error("Товари", "Назва повинна бути унікальною.")
        except Exception:
            logging.exception("Add product error")
            show_error("Товари", "Не вдалося додати товар.")

    def edit_product(self) -> None:
        product_id = self.product_table.selected_id()
        if not product_id:
            show_error("Товари", "Оберіть товар для редагування.")
            return
        brands = db.list_brands()
        categories = db.list_categories()
        rows = [p for p in db.list_products() if p["id"] == product_id]
        if not rows:
            return
        row = rows[0]
        initial = [row["sku"], row["name"], row["brand_id"], row["category_id"]]
        values = product_prompt(brands, categories, title="Редагувати товар", initial=initial)
        if not values:
            return
        sku, name, brand_id, category_id = values
        try:
            db.update_product(product_id, sku, name, brand_id, category_id)
            self.refresh_products()
        except sqlite3.IntegrityError as exc:
            if "sku" in str(exc).lower():
                show_error("Товари", "SKU має бути унікальним.")
            else:
                show_error("Товари", "Назва повинна бути унікальною.")
        except Exception:
            logging.exception("Edit product error")
            show_error("Товари", "Не вдалося змінити товар.")

    def delete_product(self) -> None:
        product_id = self.product_table.selected_id()
        if not product_id:
            show_error("Товари", "Оберіть товар для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити товар?"):
            return
        try:
            db.delete_product(product_id)
            self.refresh_products()
        except Exception:
            logging.exception("Delete product error")
            show_error("Товари", "Не вдалося видалити товар.")

    # Counterparties
    def create_counterparties_tab(self) -> None:
        top = ttk.Frame(self.counterparties_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Тип:").pack(side=tk.LEFT)
        self.counterparty_filter = tk.StringVar(value="")
        type_combo = ttk.Combobox(
            top,
            textvariable=self.counterparty_filter,
            values=["Усі", "Постачальник", "Покупець", "Інший"],
            state="readonly",
            width=15,
        )
        type_combo.pack(side=tk.LEFT, padx=4)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_counterparties())

        columns = [
            ("name", "Назва", 200),
            ("type", "Тип", 120),
            ("phone", "Телефон", 140),
            ("email", "Email", 200),
        ]
        self.counterparty_table = TableFrame(self.counterparties_frame, columns)
        self.counterparty_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.counterparties_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_counterparty).pack(side=tk.LEFT, padx=4)

    def _counterparty_type_label(self, value: str) -> str:
        return {"supplier": "Постачальник", "customer": "Покупець", "other": "Інший"}.get(value, value)

    def _counterparty_type_value(self, label: str) -> str:
        mapping = {
            "Постачальник": "supplier",
            "Покупець": "customer",
            "Інший": "other",
        }
        return mapping.get(label, "")

    def refresh_counterparties(self) -> None:
        type_value = self.counterparty_filter.get()
        db_value = self._counterparty_type_value(type_value)
        rows = db.list_counterparties(db_value if db_value else None)
        self.counterparty_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": self._counterparty_type_label(r["type"]),
                    "phone": r["phone"],
                    "email": r["email"],
                }
                for r in rows
            ]
        )
        # Update filters in documents tab
        if hasattr(self, "doc_counterparty_var"):
            current = self.doc_counterparty_var.get()
            values = ["Усі"] + [r["name"] for r in rows]
            self.doc_counterparty_combo["values"] = values
            if current not in values:
                self.doc_counterparty_var.set("Усі")

    def add_counterparty(self) -> None:
        values = counterparty_prompt()
        if not values:
            return
        try:
            db.add_counterparty(*values)
            self.refresh_counterparties()
        except sqlite3.IntegrityError:
            show_error("Контрагенти", "Контрагент з такою назвою вже існує для цього типу.")
        except Exception:
            logging.exception("Add counterparty error")
            show_error("Контрагенти", "Не вдалося додати контрагента.")

    def edit_counterparty(self) -> None:
        counterparty_id = self.counterparty_table.selected_id()
        if not counterparty_id:
            show_error("Контрагенти", "Оберіть контрагента для редагування.")
            return
        rows = [c for c in db.list_counterparties() if c["id"] == counterparty_id]
        if not rows:
            return
        row = rows[0]
        initial = [row["name"], row["type"], row["phone"], row["email"], row["address"], row["note"]]
        values = counterparty_prompt(initial=initial)
        if not values:
            return
        try:
            db.update_counterparty(counterparty_id, *values)
            self.refresh_counterparties()
        except sqlite3.IntegrityError:
            show_error("Контрагенти", "Контрагент з такою назвою вже існує для цього типу.")
        except Exception:
            logging.exception("Edit counterparty error")
            show_error("Контрагенти", "Не вдалося змінити контрагента.")

    def delete_counterparty(self) -> None:
        counterparty_id = self.counterparty_table.selected_id()
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

    # Documents
    def create_documents_tab(self) -> None:
        filters = ttk.Frame(self.documents_frame)
        filters.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(filters, text="Тип:").pack(side=tk.LEFT)
        self.doc_type_var = tk.StringVar(value="Усі")
        type_combo = ttk.Combobox(
            filters, textvariable=self.doc_type_var, values=["Усі", "Прихід", "Розхід"], state="readonly", width=12
        )
        type_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        self.doc_status_var = tk.StringVar(value="Усі")
        status_combo = ttk.Combobox(
            filters,
            textvariable=self.doc_status_var,
            values=["Усі", "Чернетка", "Проведений"],
            state="readonly",
            width=12,
        )
        status_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Контрагент:").pack(side=tk.LEFT)
        self.doc_counterparty_var = tk.StringVar(value="Усі")
        self.doc_counterparty_combo = ttk.Combobox(filters, textvariable=self.doc_counterparty_var, state="readonly", width=20)
        self.doc_counterparty_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        self.date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_to_var, width=10).pack(side=tk.LEFT, padx=2)

        ttk.Button(filters, text="Фільтр", command=self.refresh_documents).pack(side=tk.LEFT, padx=6)

        columns = [
            ("doc_date", "Дата", 90),
            ("doc_type", "Тип", 70),
            ("number", "Номер", 90),
            ("counterparty", "Контрагент", 180),
            ("status", "Статус", 90),
            ("total", "Сума", 90),
            ("comment", "Коментар", 220),
        ]
        self.documents_table = TableFrame(self.documents_frame, columns)
        self.documents_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.documents_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Новий прихід", command=lambda: self.new_document("IN")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Новий розхід", command=lambda: self.new_document("OUT")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_document).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_document).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_document_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_document_action).pack(side=tk.LEFT, padx=4)

    def _doc_type_label(self, value: str) -> str:
        return "Прихід" if value == "IN" else "Розхід"

    def _doc_status_label(self, value: str) -> str:
        return "Чернетка" if value == "draft" else "Проведений"

    def refresh_documents(self) -> None:
        type_filter = self.doc_type_var.get()
        status_filter = self.doc_status_var.get()
        cparty_name = self.doc_counterparty_var.get()
        rows_counterparties = db.list_counterparties()
        counterparties_by_name = {r["name"]: r["id"] for r in rows_counterparties}
        counterparty_id = counterparties_by_name.get(cparty_name) if cparty_name and cparty_name != "Усі" else None
        type_value = "IN" if type_filter == "Прихід" else "OUT" if type_filter == "Розхід" else None
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        date_from = self.date_from_var.get().strip() or None
        date_to = self.date_to_var.get().strip() or None
        rows = db.list_documents(type_value, status_value, counterparty_id, date_from, date_to)
        self.documents_table.set_rows(
            [
                {
                    "id": r["id"],
                    "doc_date": r["doc_date"],
                    "doc_type": self._doc_type_label(r["doc_type"]),
                    "number": r["number"],
                    "counterparty": r["counterparty"] or "-",
                    "status": self._doc_status_label(r["status"]),
                    "total": f"{r['total']:.2f}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )
        # refresh counterparty list options
        values = ["Усі"] + [r["name"] for r in rows_counterparties]
        self.doc_counterparty_combo["values"] = values
        if self.doc_counterparty_var.get() not in values:
            self.doc_counterparty_var.set("Усі")

    def _selected_document(self):
        doc_id = self.documents_table.selected_id()
        if not doc_id:
            show_error("Документи", "Оберіть документ у списку.")
            return None
        return doc_id

    def new_document(self, doc_type: str) -> None:
        products = db.list_products()
        if not products:
            show_error("Документи", "Спочатку додайте товари.")
            return
        counterparties = db.list_counterparties()
        result = document_prompt(doc_type, products, counterparties)
        if not result:
            return
        info, lines = result
        try:
            doc_id = db.create_document(info["doc_type"], info["doc_date"], info["number"], info["counterparty_id"], info["comment"])
            db.replace_document_lines(doc_id, lines)
            self.refresh_documents()
        except Exception:
            logging.exception("Create document error")
            show_error("Документи", "Не вдалося створити документ.")

    def edit_document(self) -> None:
        doc_id = self._selected_document()
        if not doc_id:
            return
        doc = db.get_document(doc_id)
        lines = db.list_document_lines(doc_id)
        products = db.list_products()
        counterparties = db.list_counterparties()
        result = document_prompt(doc["doc_type"], products, counterparties, doc=doc, lines=lines)
        if not result:
            return
        info, new_lines = result
        try:
            if doc["status"] == "draft":
                db.update_document(doc_id, info["doc_type"], info["doc_date"], info["number"], info["counterparty_id"], info["comment"])
                db.replace_document_lines(doc_id, new_lines)
            else:
                db.update_document_comment(doc_id, info["comment"])
            self.refresh_documents()
        except Exception:
            logging.exception("Edit document error")
            show_error("Документи", "Не вдалося змінити документ.")

    def delete_document(self) -> None:
        doc_id = self._selected_document()
        if not doc_id:
            return
        if not messagebox.askyesno("Підтвердження", "Видалити документ?"):
            return
        try:
            db.delete_document(doc_id)
            self.refresh_documents()
        except Exception as exc:
            logging.exception("Delete document error")
            show_error("Документи", str(exc))

    def post_document_action(self) -> None:
        doc_id = self._selected_document()
        if not doc_id:
            return
        try:
            db.post_document(doc_id)
            self.refresh_documents()
            self.refresh_stock()
        except Exception as exc:
            logging.exception("Post document error")
            show_error("Документи", str(exc))

    def unpost_document_action(self) -> None:
        doc_id = self._selected_document()
        if not doc_id:
            return
        try:
            db.unpost_document(doc_id)
            self.refresh_documents()
            self.refresh_stock()
        except Exception as exc:
            logging.exception("Unpost document error")
            show_error("Документи", str(exc))

    # Stock
    def create_stock_tab(self) -> None:
        top = ttk.Frame(self.stock_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук товару:").pack(side=tk.LEFT)
        self.stock_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.stock_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Оновити", command=self.on_search_stock).pack(side=tk.LEFT)
        ttk.Button(top, text="Перерахувати залишки", command=self.recalc_stock).pack(side=tk.LEFT, padx=6)

        columns = [("name", "Товар", 260), ("sku", "SKU", 120), ("quantity", "Кількість", 120)]
        self.stock_table = TableFrame(self.stock_frame, columns)
        self.stock_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def on_search_stock(self) -> None:
        self.refresh_stock(self.stock_search_var.get())

    def refresh_stock(self, search: str | None = None) -> None:
        rows = db.list_stock(search)
        self.stock_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "sku": r["sku"],
                    "quantity": f"{r['quantity']:.2f}",
                }
                for r in rows
            ]
        )

    def recalc_stock(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Перерахувати усі залишки?"):
            return
        try:
            db.recalc_balances()
            self.refresh_stock()
            messagebox.showinfo("Залишки", "Перерахунок виконано")
        except Exception as exc:
            logging.exception("Recalc stock error")
            show_error("Залишки", str(exc))

    # Export
    def create_export_tab(self) -> None:
        ttk.Label(self.export_frame, text="Експорт таблиць у CSV", font=("Segoe UI", 10, "bold")).pack(pady=10)
        tables = [
            ("Brands", "Бренди"),
            ("Categories", "Категорії"),
            ("Products", "Товари"),
            ("Counterparties", "Контрагенти"),
            ("Documents", "Документи"),
            ("DocumentLines", "Рядки документів"),
            ("StockBalances", "Залишки"),
        ]
        for table, label in tables:
            ttk.Button(self.export_frame, text=f"Експорт {label}", command=lambda t=table: self.export_csv(t)).pack(pady=4)

    def export_csv(self, table: str) -> None:
        file_path = get_data_dir() / f"{table.lower()}_export.csv"
        try:
            db.export_table_to_csv(table, file_path)
            messagebox.showinfo("Експорт", f"Файл збережено: {file_path}")
        except Exception:
            logging.exception("Export error")
            show_error("Експорт", "Не вдалося експортувати таблицю.")

    # About
    def create_about_tab(self) -> None:
        ttk.Label(self.about_frame, text=f"{APP_NAME} v{VERSION}", font=("Segoe UI", 12, "bold")).pack(pady=10)
        ttk.Label(self.about_frame, text=f"База даних: {get_db_path()}").pack(pady=4)
        ttk.Button(self.about_frame, text="Відкрити папку даних", command=lambda: open_data_folder(get_data_dir())).pack(pady=4)

    # Refresh helpers
    def refresh_brands(self) -> None:
        rows = db.list_brands()
        self.brand_table.set_rows([{"id": r["id"], "name": r["name"]} for r in rows])

    def refresh_categories(self) -> None:
        rows = db.list_categories()
        self.category_table.set_rows([{"id": r["id"], "name": r["name"]} for r in rows])

    def refresh_products(self, search: str | None = None) -> None:
        rows = db.list_products(search)
        self.product_table.set_rows(
            [
                {
                    "id": r["id"],
                    "sku": r["sku"],
                    "name": r["name"],
                    "brand": r["brand"],
                    "category": r["category"],
                }
                for r in rows
            ]
        )

    def refresh_all(self) -> None:
        self.refresh_brands()
        self.refresh_categories()
        self.refresh_products()
        self.refresh_counterparties()
        self.refresh_documents()
        self.refresh_stock()


def product_prompt(brands, categories, title: str, initial=None):
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.grab_set()

    ttk.Label(dlg, text="SKU").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    sku_var = tk.StringVar(value=initial[0] if initial else "")
    ttk.Entry(dlg, textvariable=sku_var, width=30).grid(row=0, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Назва").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    name_var = tk.StringVar(value=initial[1] if initial else "")
    ttk.Entry(dlg, textvariable=name_var, width=30).grid(row=1, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Бренд").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    brand_var = tk.StringVar()
    brand_combo = ttk.Combobox(dlg, textvariable=brand_var, state="readonly", values=[b["name"] for b in brands])
    brand_combo.grid(row=2, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Категорія").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    category_var = tk.StringVar()
    category_combo = ttk.Combobox(dlg, textvariable=category_var, state="readonly", values=[c["name"] for c in categories])
    category_combo.grid(row=3, column=1, padx=6, pady=4)

    if initial:
        brand_combo.current(next((i for i, b in enumerate(brands) if b["id"] == initial[2]), 0))
        category_combo.current(next((i for i, c in enumerate(categories) if c["id"] == initial[3]), 0))
    else:
        brand_combo.current(0)
        category_combo.current(0)

    result = None

    def on_ok():
        nonlocal result
        sku = sku_var.get().strip()
        name = name_var.get().strip()
        if not sku or not name:
            messagebox.showerror("Валідація", "Заповніть усі поля.")
            return
        try:
            brand_id = brands[brand_combo.current()]["id"]
            category_id = categories[category_combo.current()]["id"]
        except IndexError:
            messagebox.showerror("Валідація", "Оберіть бренд і категорію.")
            return
        result = (sku, name, brand_id, category_id)
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=4, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def counterparty_prompt(initial=None):
    dlg = tk.Toplevel()
    dlg.title("Контрагент")
    dlg.grab_set()

    ttk.Label(dlg, text="Назва").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    name_var = tk.StringVar(value=initial[0] if initial else "")
    ttk.Entry(dlg, textvariable=name_var, width=35).grid(row=0, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Тип").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    type_var = tk.StringVar()
    type_values = ["Постачальник", "Покупець", "Інший"]
    type_combo = ttk.Combobox(dlg, textvariable=type_var, values=type_values, state="readonly", width=20)
    type_combo.grid(row=1, column=1, padx=6, pady=4)
    if initial:
        type_map = {"supplier": "Постачальник", "customer": "Покупець", "other": "Інший"}
        try:
            type_combo.current(type_values.index(type_map.get(initial[1], "Постачальник")))
        except ValueError:
            type_combo.current(0)
    else:
        type_combo.current(0)

    ttk.Label(dlg, text="Телефон").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    phone_var = tk.StringVar(value=initial[2] if initial else "")
    ttk.Entry(dlg, textvariable=phone_var, width=35).grid(row=2, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Email").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    email_var = tk.StringVar(value=initial[3] if initial else "")
    ttk.Entry(dlg, textvariable=email_var, width=35).grid(row=3, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Адреса").grid(row=4, column=0, padx=6, pady=4, sticky="w")
    address_var = tk.StringVar(value=initial[4] if initial else "")
    ttk.Entry(dlg, textvariable=address_var, width=35).grid(row=4, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Коментар").grid(row=5, column=0, padx=6, pady=4, sticky="w")
    note_var = tk.StringVar(value=initial[5] if initial else "")
    ttk.Entry(dlg, textvariable=note_var, width=35).grid(row=5, column=1, padx=6, pady=4)

    result = None

    def on_ok():
        nonlocal result
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Валідація", "Назва обов'язкова")
            return
        ctype_label = type_var.get()
        type_code = {"Постачальник": "supplier", "Покупець": "customer", "Інший": "other"}.get(ctype_label, "supplier")
        result = (name, type_code, phone_var.get().strip(), email_var.get().strip(), address_var.get().strip(), note_var.get().strip())
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=6, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def document_prompt(doc_type: str, products, counterparties, doc=None, lines=None):
    dlg = tk.Toplevel()
    dlg.title("Документ")
    dlg.grab_set()
    editable = not doc or doc["status"] == "draft"

    ttk.Label(dlg, text="Тип").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    doc_type_label = "Прихід" if doc_type == "IN" else "Розхід"
    ttk.Label(dlg, text=doc_type_label).grid(row=0, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Дата (YYYY-MM-DD)").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    date_var = tk.StringVar(value=doc["doc_date"] if doc else datetime.now().strftime("%Y-%m-%d"))
    date_entry = ttk.Entry(dlg, textvariable=date_var, width=15, state="normal" if editable else "disabled")
    date_entry.grid(row=1, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Номер").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    number_var = tk.StringVar(value=doc["number"] if doc else "")
    ttk.Entry(dlg, textvariable=number_var, width=20, state="normal" if editable else "disabled").grid(row=2, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Контрагент").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    allowed_types = {"IN": {"supplier", "other"}, "OUT": {"customer", "other"}}[doc_type]
    filtered_counterparties = [c for c in counterparties if c["type"] in allowed_types]
    cp_names = ["-"] + [c["name"] for c in filtered_counterparties]
    cp_var = tk.StringVar()
    cp_combo = ttk.Combobox(dlg, textvariable=cp_var, values=cp_names, state="readonly", width=25)
    cp_combo.grid(row=3, column=1, padx=6, pady=4, sticky="w")
    if doc and doc["counterparty_id"]:
        target = next((c["name"] for c in filtered_counterparties if c["id"] == doc["counterparty_id"]), "-")
        cp_var.set(target)
    else:
        cp_var.set("-")
    if not editable:
        cp_combo.state(["disabled"])

    ttk.Label(dlg, text="Коментар").grid(row=4, column=0, padx=6, pady=4, sticky="w")
    comment_var = tk.StringVar(value=doc["comment"] if doc else "")
    ttk.Entry(dlg, textvariable=comment_var, width=40).grid(row=4, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Рядки").grid(row=5, column=0, padx=6, pady=4, sticky="nw")
    line_frame = ttk.Frame(dlg)
    line_frame.grid(row=5, column=1, padx=6, pady=4, sticky="nsew")
    line_frame.grid_columnconfigure(0, weight=1)

    columns = ["product", "quantity", "price", "amount"]
    tree = ttk.Treeview(line_frame, columns=columns, show="headings", height=8)
    headings = [("product", "Товар", 200), ("quantity", "Кількість", 90), ("price", "Ціна", 90), ("amount", "Сума", 90)]
    for col, title, width in headings:
        tree.heading(col, text=title)
        tree.column(col, width=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll = ttk.Scrollbar(line_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    yscroll.grid(row=0, column=1, sticky="ns")
    line_frame.grid_rowconfigure(0, weight=1)

    product_lookup = {f"{p['name']} ({p['sku']})": p["id"] for p in products}
    products_by_id = {p["id"]: f"{p['name']} ({p['sku']})" for p in products}

    entry_frame = ttk.Frame(dlg)
    entry_frame.grid(row=6, column=0, columnspan=2, padx=6, pady=4, sticky="w")
    ttk.Label(entry_frame, text="Товар").grid(row=0, column=0, padx=4, pady=2)
    product_var = tk.StringVar()
    product_combo = ttk.Combobox(entry_frame, textvariable=product_var, values=list(product_lookup.keys()), state="readonly", width=40)
    product_combo.grid(row=0, column=1, padx=4, pady=2)
    if product_lookup:
        product_combo.current(0)

    ttk.Label(entry_frame, text="Кількість").grid(row=0, column=2, padx=4, pady=2)
    qty_var = tk.StringVar(value="1")
    qty_entry = ttk.Entry(entry_frame, textvariable=qty_var, width=10)
    qty_entry.grid(row=0, column=3, padx=4, pady=2)

    ttk.Label(entry_frame, text="Ціна").grid(row=0, column=4, padx=4, pady=2)
    price_var = tk.StringVar(value="0")
    price_entry = ttk.Entry(entry_frame, textvariable=price_var, width=10)
    price_entry.grid(row=0, column=5, padx=4, pady=2)

    line_data = []
    if lines:
        for ln in lines:
            line_data.append(
                {
                    "product_id": ln["product_id"],
                    "product_name": ln["product_name"],
                    "quantity": float(ln["quantity"]),
                    "price": float(ln["price"]),
                    "amount": float(ln["quantity"]) * float(ln["price"]),
                }
            )

    selected_idx: list[int] = []

    def refresh_lines():
        tree.delete(*tree.get_children())
        for idx, ln in enumerate(line_data):
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(ln["product_name"], f"{ln['quantity']:.2f}", f"{ln['price']:.2f}", f"{ln['amount']:.2f}"),
            )

    def on_select(event=None):
        selected_idx.clear()
        sel = tree.selection()
        if sel:
            idx = int(sel[0])
            selected_idx.append(idx)
            ln = line_data[idx]
            product_name = products_by_id.get(ln["product_id"], ln["product_name"])
            product_var.set(product_name)
            qty_var.set(str(ln["quantity"]))
            price_var.set(str(ln["price"]))

    tree.bind("<<TreeviewSelect>>", on_select)

    def add_or_update_line():
        if not editable:
            return
        try:
            qty = float(qty_var.get())
            price = float(price_var.get())
        except ValueError:
            messagebox.showerror("Валідація", "Невірні числові значення")
            return
        if qty <= 0:
            messagebox.showerror("Валідація", "Кількість повинна бути більшою за 0")
            return
        product_name = product_var.get()
        product_id = product_lookup.get(product_name)
        if not product_id:
            messagebox.showerror("Валідація", "Оберіть товар")
            return
        data = {
            "product_id": product_id,
            "product_name": product_name,
            "quantity": qty,
            "price": price,
            "amount": qty * price,
        }
        if selected_idx:
            line_data[selected_idx[0]] = data
        else:
            line_data.append(data)
        refresh_lines()
        selected_idx.clear()

    def delete_line():
        if not editable:
            return
        if not selected_idx:
            return
        line_data.pop(selected_idx[0])
        selected_idx.clear()
        refresh_lines()

    btn_line = ttk.Frame(entry_frame)
    btn_line.grid(row=0, column=6, padx=6)
    ttk.Button(btn_line, text="Додати/Оновити", command=add_or_update_line, state="normal" if editable else "disabled").pack(side=tk.LEFT)
    ttk.Button(btn_line, text="Видалити", command=delete_line, state="normal" if editable else "disabled").pack(side=tk.LEFT, padx=4)

    refresh_lines()

    result = None

    def on_ok():
        nonlocal result
        try:
            datetime.fromisoformat(date_var.get())
        except ValueError:
            messagebox.showerror("Валідація", "Невірний формат дати (YYYY-MM-DD)")
            return
        if editable and not line_data:
            messagebox.showerror("Валідація", "Додайте хоча б один рядок")
            return
        cp_name = cp_var.get()
        cp_id = None
        if cp_name and cp_name != "-":
            cp_id = next((c["id"] for c in filtered_counterparties if c["name"] == cp_name), None)
        info = {
            "doc_type": doc_type,
            "doc_date": date_var.get().strip(),
            "number": number_var.get().strip(),
            "counterparty_id": cp_id,
            "comment": comment_var.get().strip(),
        }
        lines_to_save = [(ln["product_id"], ln["quantity"], ln["price"]) for ln in line_data]
        result = (info, lines_to_save)
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=7, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def main() -> None:
    configure_logging()
    logging.info("Starting %s", APP_NAME)
    try:
        with SingleInstance(get_lock_path()):
            db.init_db()
            app = InventoryApp()
            app.mainloop()
    except RuntimeError:
        messagebox.showwarning(APP_NAME, "Програма вже запущена.")
    except Exception:  # pragma: no cover - GUI bootstrap
        logging.exception("Fatal error")
        messagebox.showerror(APP_NAME, "Критична помилка. Деталі у логах.")
        traceback.print_exc()


if __name__ == "__main__":
    main()

