"""InventoryLite GUI with cash-basis accounting and moving-average inventory.

The app focuses on a lightweight workflow for a trading business:
- Cash basis only: income/expense are registered when money changes hands.
- Inventory cost uses moving-average per product and warehouse.
- Direct-costing: only variable costs (purchase price) are included into COGS; fixed
  expenses are tracked separately via cash transactions.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3

import db
from utils import (
    APP_NAME,
    VERSION,
    SingleInstance,
    backup_all_data,
    configure_logging,
    get_data_dir,
    get_db_path,
    get_lock_path,
    get_log_path,
    open_data_folder,
    restore_all_data,
    show_error,
    backup_database,
)
from ui_components import TableFrame, simple_prompt


class InventoryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x720")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.create_menu()

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.brands_frame = ttk.Frame(notebook)
        self.categories_frame = ttk.Frame(notebook)
        self.products_frame = ttk.Frame(notebook)
        self.counterparties_frame = ttk.Frame(notebook)
        self.warehouses_frame = ttk.Frame(notebook)
        self.channels_frame = ttk.Frame(notebook)
        self.currencies_frame = ttk.Frame(notebook)
        self.purchases_frame = ttk.Frame(notebook)
        self.sales_frame = ttk.Frame(notebook)
        self.cash_frame = ttk.Frame(notebook)
        self.stock_frame = ttk.Frame(notebook)
        self.reports_frame = ttk.Frame(notebook)
        self.export_frame = ttk.Frame(notebook)
        self.about_frame = ttk.Frame(notebook)

        notebook.add(self.brands_frame, text="Бренди")
        notebook.add(self.categories_frame, text="Категорії")
        notebook.add(self.products_frame, text="Товари")
        notebook.add(self.counterparties_frame, text="Контрагенти")
        notebook.add(self.warehouses_frame, text="Склади")
        notebook.add(self.channels_frame, text="Канали продажу")
        notebook.add(self.currencies_frame, text="Валюти")
        notebook.add(self.purchases_frame, text="Закупівлі")
        notebook.add(self.sales_frame, text="Продажі")
        notebook.add(self.cash_frame, text="Каса")
        notebook.add(self.stock_frame, text="Залишки")
        notebook.add(self.reports_frame, text="Звіти")
        notebook.add(self.export_frame, text="Експорт")
        notebook.add(self.about_frame, text="Про програму")

        self.create_brands_tab()
        self.create_categories_tab()
        self.create_products_tab()
        self.create_counterparties_tab()
        self.create_warehouses_tab()
        self.create_channels_tab()
        self.create_currencies_tab()
        self.create_purchases_tab()
        self.create_sales_tab()
        self.create_cash_tab()
        self.create_stock_tab()
        self.create_reports_tab()
        self.create_export_tab()
        self.create_about_tab()

        self.refresh_all()

    # Menu
    def create_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Резервна копія всіх даних", command=self.on_backup_all)
        file_menu.add_command(label="Відновлення з резервної копії", command=self.on_restore_all)
        file_menu.add_separator()
        file_menu.add_command(label="Резервна копія БД", command=self.on_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.config(menu=menubar)

    def on_backup_all(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{APP_NAME}_backup_{timestamp}.zip"
        initialdir = get_data_dir()
        target_path = filedialog.asksaveasfilename(
            title="Зберегти резервну копію",
            defaultextension=".zip",
            initialfile=default_name,
            initialdir=initialdir,
            filetypes=(("ZIP", "*.zip"), ("Усі файли", "*.*")),
        )
        if not target_path:
            return
        try:
            target = backup_all_data(Path(target_path))
            messagebox.showinfo("Резервна копія", f"Створено: {target}")
        except Exception:
            logging.exception("Full backup failed")
            show_error("Резервна копія", "Не вдалося створити копію даних.")

    def on_restore_all(self) -> None:
        archive_path = filedialog.askopenfilename(
            title="Відновити з резервної копії",
            initialdir=get_data_dir(),
            filetypes=(("ZIP", "*.zip"), ("Усі файли", "*.*")),
        )
        if not archive_path:
            return
        if not messagebox.askyesno(
            "Відновлення даних",
            "Відновити всі дані з вибраної копії? Поточні дані буде перезаписано.",
        ):
            return
        try:
            restore_all_data(Path(archive_path))
            messagebox.showinfo(
                "Відновлення даних",
                "Дані відновлено. Перезапустіть додаток, щоб застосувати зміни.",
            )
            self.refresh_all()
        except Exception as exc:
            logging.exception("Restore failed")
            show_error("Відновлення даних", str(exc))

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
        ttk.Label(top, text="Пошук:").pack(side=tk.LEFT)
        self.product_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.product_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Оновити", command=self.on_search_products).pack(side=tk.LEFT)

        columns = [
            ("sku", "SKU", 120),
            ("name", "Назва", 230),
            ("brand", "Бренд", 140),
            ("category", "Категорія", 140),
            ("unit", "Одиниця", 90),
            ("is_active", "Активний", 90),
        ]
        self.product_table = TableFrame(self.products_frame, columns)
        self.product_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.products_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_product).pack(side=tk.LEFT, padx=4)

    def on_search_products(self) -> None:
        self.refresh_products(self.product_search_var.get())

    def add_product(self) -> None:
        brands = db.list_brands()
        categories = db.list_categories()
        values = product_prompt(brands, categories, "Новий товар")
        if not values:
            return
        sku, name, brand_id, category_id, unit, is_active = values
        try:
            db.add_product(sku, name, brand_id, category_id, unit, is_active)
            self.refresh_products()
        except sqlite3.IntegrityError:
            show_error("Товари", "SKU або назва вже існує.")
        except Exception:
            logging.exception("Add product error")
            show_error("Товари", "Не вдалося додати товар.")

    def edit_product(self) -> None:
        product_id = self.product_table.selected_id()
        if not product_id:
            show_error("Товари", "Оберіть товар для редагування.")
            return
        rows = [p for p in db.list_products() if p["id"] == product_id]
        if not rows:
            return
        p = rows[0]
        brands = db.list_brands()
        categories = db.list_categories()
        values = product_prompt(
            brands,
            categories,
            "Редагувати товар",
            (p["sku"], p["name"], p["brand_id"], p["category_id"], p["unit"], bool(p["is_active"])),
        )
        if not values:
            return
        sku, name, brand_id, category_id, unit, is_active = values
        try:
            db.update_product(product_id, sku, name, brand_id, category_id, unit, is_active)
            self.refresh_products()
        except sqlite3.IntegrityError:
            show_error("Товари", "SKU або назва вже існує.")
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
        columns = [
            ("name", "Назва", 200),
            ("type", "Тип", 120),
            ("phone", "Телефон", 120),
            ("email", "Email", 170),
            ("address", "Адреса", 200),
            ("note", "Нотатка", 200),
        ]
        self.counterparty_table = TableFrame(self.counterparties_frame, columns)
        self.counterparty_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.counterparties_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_counterparty).pack(side=tk.LEFT, padx=4)

    def add_counterparty(self) -> None:
        values = counterparty_prompt()
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
        counterparty_id = self.counterparty_table.selected_id()
        if not counterparty_id:
            show_error("Контрагенти", "Оберіть контрагента.")
            return
        rows = [c for c in db.list_counterparties() if c["id"] == counterparty_id]
        if not rows:
            return
        c = rows[0]
        values = counterparty_prompt((c["name"], c["type"], c["phone"], c["email"], c["address"], c["note"]))
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

    # Warehouses
    def create_warehouses_tab(self) -> None:
        columns = [("name", "Назва", 200), ("description", "Опис", 260), ("is_active", "Активний", 100)]
        self.warehouse_table = TableFrame(self.warehouses_frame, columns)
        self.warehouse_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        btns = ttk.Frame(self.warehouses_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_warehouse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_warehouse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_warehouse).pack(side=tk.LEFT, padx=4)

    def add_warehouse(self) -> None:
        values = warehouse_prompt()
        if not values:
            return
        name, description, is_active = values
        try:
            db.add_warehouse(name, description, is_active)
            self.refresh_warehouses()
        except sqlite3.IntegrityError:
            show_error("Склади", "Склад з такою назвою вже існує.")
        except Exception:
            logging.exception("Add warehouse error")
            show_error("Склади", "Не вдалося додати склад.")

    def edit_warehouse(self) -> None:
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
        except sqlite3.IntegrityError:
            show_error("Склади", "Склад з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit warehouse error")
            show_error("Склади", "Не вдалося змінити склад.")

    def delete_warehouse(self) -> None:
        warehouse_id = self.warehouse_table.selected_id()
        if not warehouse_id:
            show_error("Склади", "Оберіть склад для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити склад?"):
            return
        try:
            db.delete_warehouse(warehouse_id)
            self.refresh_warehouses()
        except Exception as exc:
            logging.exception("Delete warehouse error")
            show_error("Склади", str(exc))

    # Channels
    def create_channels_tab(self) -> None:
        columns = [("name", "Назва", 240), ("is_active", "Активний", 100)]
        self.channel_table = TableFrame(self.channels_frame, columns)
        self.channel_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        btns = ttk.Frame(self.channels_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_channel).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_channel).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_channel).pack(side=tk.LEFT, padx=4)

    def add_channel(self) -> None:
        values = channel_prompt()
        if not values:
            return
        name, is_active = values
        try:
            db.add_channel(name, is_active)
            self.refresh_channels()
        except sqlite3.IntegrityError:
            show_error("Канали", "Канал з такою назвою вже існує.")
        except Exception:
            logging.exception("Add channel error")
            show_error("Канали", "Не вдалося додати канал.")

    def edit_channel(self) -> None:
        channel_id = self.channel_table.selected_id()
        if not channel_id:
            show_error("Канали", "Оберіть канал.")
            return
        rows = [c for c in db.list_channels() if c["id"] == channel_id]
        if not rows:
            return
        c = rows[0]
        values = channel_prompt((c["name"], bool(c["is_active"])))
        if not values:
            return
        name, is_active = values
        try:
            db.update_channel(channel_id, name, is_active)
            self.refresh_channels()
        except sqlite3.IntegrityError:
            show_error("Канали", "Канал з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit channel error")
            show_error("Канали", "Не вдалося змінити канал.")

    def delete_channel(self) -> None:
        channel_id = self.channel_table.selected_id()
        if not channel_id:
            show_error("Канали", "Оберіть канал для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити канал?"):
            return
        try:
            db.delete_channel(channel_id)
            self.refresh_channels()
        except Exception as exc:
            logging.exception("Delete channel error")
            show_error("Канали", str(exc))

    # Currencies
    def create_currencies_tab(self) -> None:
        top = ttk.Frame(self.currencies_frame)
        top.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(top, text="Довідник валют").pack(anchor="w")
        curr_columns = [("code", "Код", 80), ("name", "Назва", 200), ("decimals", "Знаків", 60), ("is_active", "Активна", 80)]
        self.currency_table = TableFrame(top, curr_columns, height=6)
        self.currency_table.pack(fill=tk.X, pady=4)

        btns = ttk.Frame(top)
        btns.pack(pady=4, anchor="w")
        ttk.Button(btns, text="Додати валюту", command=self.add_currency).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_currency).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_currency).pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="Курси валют").pack(anchor="w", pady=(10, 0))
        rate_columns = [("rate_date", "Дата", 120), ("rate", "Курс до базової", 160)]
        self.rate_table = TableFrame(top, rate_columns, height=6)
        self.rate_table.pack(fill=tk.X, pady=4)

        rate_btns = ttk.Frame(top)
        rate_btns.pack(pady=4, anchor="w")
        ttk.Button(rate_btns, text="Додати курс", command=self.add_rate).pack(side=tk.LEFT, padx=4)

        self.currency_table.on_select(self.refresh_rates)

    def add_currency(self) -> None:
        values = simple_prompt("Нова валюта", ["Код", "Назва", "Знаків після коми"], ["USD", "Долар США", "2"])
        if not values:
            return
        try:
            decimals = int(values[2]) if len(values) > 2 else 2
            db.add_currency(values[0], values[1], decimals)
            self.refresh_currencies()
        except sqlite3.IntegrityError:
            show_error("Валюти", "Валюта з таким кодом вже існує")
        except Exception as exc:
            logging.exception("Add currency error")
            show_error("Валюти", str(exc))

    def edit_currency(self) -> None:
        code = self.currency_table.selected_id()
        if not code:
            show_error("Валюти", "Оберіть валюту")
            return
        rows = [c for c in db.list_currencies(active_only=False) if c["code"] == code]
        if not rows:
            return
        cur = rows[0]
        values = simple_prompt("Змінити валюту", ["Код", "Назва", "Знаків після коми", "Активна (1/0)"], [cur["code"], cur["name"], str(cur["decimals"]), str(cur["is_active"]),])
        if not values:
            return
        try:
            decimals = int(values[2]) if len(values) > 2 else 2
            is_active = values[3].strip() != "0" if len(values) > 3 else True
            db.update_currency(values[0], values[1], decimals, is_active)
            self.refresh_currencies()
        except Exception as exc:
            logging.exception("Edit currency error")
            show_error("Валюти", str(exc))

    def delete_currency(self) -> None:
        code = self.currency_table.selected_id()
        if not code:
            show_error("Валюти", "Оберіть валюту")
            return
        if not messagebox.askyesno("Валюти", "Видалити валюту?"):
            return
        try:
            db.delete_currency(code)
            self.refresh_currencies()
        except Exception as exc:
            logging.exception("Delete currency error")
            show_error("Валюти", str(exc))

    def refresh_currencies(self) -> None:
        rows = db.list_currencies(active_only=False)
        self.currency_table.set_rows(
            [
                {
                    "id": row["code"],
                    "code": row["code"],
                    "name": row["name"],
                    "decimals": row["decimals"],
                    "is_active": "Так" if row["is_active"] else "Ні",
                }
                for row in rows
            ]
        )
        self.refresh_rates()

    def refresh_rates(self) -> None:
        code = self.currency_table.selected_id()
        code = code or (db.list_currencies(active_only=True)[0]["code"] if db.list_currencies(active_only=True) else None)
        if not code:
            self.rate_table.set_rows([])
            return
        rates = db.list_currency_rates(code)
        self.rate_table.set_rows(
            [
                {
                    "id": r["id"],
                    "rate_date": r["rate_date"],
                    "rate": f"{r['rate']:.4f}",
                }
                for r in rates
            ]
        )

    def add_rate(self) -> None:
        code = self.currency_table.selected_id()
        if not code:
            show_error("Курси", "Оберіть валюту")
            return
        defaults = [datetime.now().strftime("%Y-%m-%d"), "1"]
        values = simple_prompt("Новий курс", ["Дата", "Курс до базової валюти"], defaults)
        if not values:
            return
        try:
            rate = float(values[1])
            db.add_currency_rate(code, values[0], rate)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Add rate error")
            show_error("Курси", str(exc))

    # Purchases
    def create_purchases_tab(self) -> None:
        filters = ttk.Frame(self.purchases_frame)
        filters.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        self.purchase_status_var = tk.StringVar(value="Усі")
        status_combo = ttk.Combobox(filters, textvariable=self.purchase_status_var, values=["Усі", "Чернетка", "Проведений"], state="readonly", width=14)
        status_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        self.purchase_date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.purchase_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        self.purchase_date_to_var = tk.StringVar()
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
            ("comment", "Коментар", 240),
        ]
        self.purchase_table = TableFrame(self.purchases_frame, columns)
        self.purchase_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.purchases_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Нова закупівля", command=self.new_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_purchase_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_purchase_action).pack(side=tk.LEFT, padx=4)

    def _selected_purchase(self):
        doc_id = self.purchase_table.selected_id()
        if not doc_id:
            show_error("Закупівлі", "Оберіть документ")
            return None
        return doc_id

    def refresh_purchases(self) -> None:
        status_filter = self.purchase_status_var.get()
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        rows = db.list_purchases(status_value, self.purchase_date_from_var.get().strip() or None, self.purchase_date_to_var.get().strip() or None)
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
        result = document_prompt("purchase", products, counterparties, warehouses, [], currencies)
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
        result = document_prompt("purchase", products, counterparties, warehouses, [], currencies, doc=doc, lines=lines)
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
                status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (doc_id,)).fetchone()
                if status and status[0] != "draft":
                    raise ValueError("Видаляти можна лише чернетки")
                conn.execute("DELETE FROM PurchaseDocuments WHERE id=?", (doc_id,))
                conn.commit()
            self.refresh_purchases()
        except Exception as exc:
            logging.exception("Delete purchase error")
            show_error("Закупівлі", str(exc))

    def post_purchase_action(self) -> None:
        doc_id = self._selected_purchase()
        if not doc_id:
            return
        try:
            db.post_purchase(doc_id)
            self.refresh_purchases()
            self.refresh_stock()
            self.refresh_cash()
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
            self.refresh_stock()
            self.refresh_cash()
        except Exception as exc:
            logging.exception("Unpost purchase error")
            show_error("Закупівлі", str(exc))

    # Sales
    def create_sales_tab(self) -> None:
        filters = ttk.Frame(self.sales_frame)
        filters.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        self.sales_status_var = tk.StringVar(value="Усі")
        status_combo = ttk.Combobox(filters, textvariable=self.sales_status_var, values=["Усі", "Чернетка", "Проведений"], state="readonly", width=14)
        status_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        self.sales_date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.sales_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        self.sales_date_to_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.sales_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(filters, text="Фільтр", command=self.refresh_sales).pack(side=tk.LEFT, padx=6)

        columns = [
            ("doc_date", "Дата", 90),
            ("customer", "Покупець", 180),
            ("warehouse", "Склад", 140),
            ("channel", "Канал", 100),
            ("status", "Статус", 90),
            ("currency", "Валюта", 80),
            ("rate", "Курс", 80),
            ("total_doc", "Сума (вал)", 110),
            ("total", "Сума (база)", 110),
            ("comment", "Коментар", 220),
        ]
        self.sales_table = TableFrame(self.sales_frame, columns)
        self.sales_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self.sales_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Новий продаж", command=self.new_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_sale_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_sale_action).pack(side=tk.LEFT, padx=4)

    def _selected_sale(self):
        doc_id = self.sales_table.selected_id()
        if not doc_id:
            show_error("Продажі", "Оберіть документ")
            return None
        return doc_id

    def refresh_sales(self) -> None:
        status_filter = self.sales_status_var.get()
        status_value = "draft" if status_filter == "Чернетка" else "posted" if status_filter == "Проведений" else None
        rows = db.list_sales(status_value, self.sales_date_from_var.get().strip() or None, self.sales_date_to_var.get().strip() or None)
        self.sales_table.set_rows(
            [
                {
                    "id": r["id"],
                    "doc_date": r["doc_date"],
                    "customer": r["customer"] or "-",
                    "warehouse": r["warehouse"] or "-",
                    "channel": r["channel"] or "-",
                    "status": "Чернетка" if r["status"] == "draft" else "Проведений",
                    "currency": r["currency_code"],
                    "rate": f"{r['exchange_rate']:.4f}",
                    "total_doc": f"{r['total_doc']:.2f}",
                    "total": f"{r['total']:.2f}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def new_sale(self) -> None:
        products = db.list_products()
        warehouses = db.list_warehouses(active_only=True)
        channels = db.list_channels(active_only=True)
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        result = document_prompt("sale", products, counterparties, warehouses, channels, currencies)
        if not result:
            return
        info, lines = result
        try:
            doc_id = db.create_sale(
                info["doc_date"],
                info["counterparty_id"],
                info["warehouse_id"],
                info["channel"],
                info["comment"],
                info["currency"],
                info["rate"],
            )
            db.replace_sale_lines(doc_id, lines, info["rate"])
            self.refresh_sales()
        except Exception:
            logging.exception("Create sale error")
            show_error("Продажі", "Не вдалося створити документ")

    def edit_sale(self) -> None:
        doc_id = self._selected_sale()
        if not doc_id:
            return
        doc = db.get_sale(doc_id)
        if not doc:
            return
        lines = db.list_sale_lines(doc_id)
        products = db.list_products()
        warehouses = db.list_warehouses(active_only=False)
        channels = db.list_channels(active_only=False)
        counterparties = db.list_counterparties()
        currencies = db.list_currencies()
        result = document_prompt("sale", products, counterparties, warehouses, channels, currencies, doc=doc, lines=lines)
        if not result:
            return
        info, new_lines = result
        try:
            if doc["status"] == "draft":
                db.update_sale(
                    doc_id,
                    info["doc_date"],
                    info["counterparty_id"],
                    info["warehouse_id"],
                    info["channel"],
                    info["comment"],
                    info["currency"],
                    info["rate"],
                )
                db.replace_sale_lines(doc_id, new_lines, info["rate"])
            else:
                db.update_sale(
                    doc_id,
                    doc["doc_date"],
                    doc["customer_id"],
                    doc["warehouse_id"],
                    doc["channel"] or "",
                    info["comment"],
                    doc["currency_code"],
                    doc["exchange_rate"],
                )
            self.refresh_sales()
        except Exception:
            logging.exception("Edit sale error")
            show_error("Продажі", "Не вдалося змінити документ")

    def delete_sale(self) -> None:
        doc_id = self._selected_sale()
        if not doc_id:
            return
        if not messagebox.askyesno("Підтвердження", "Видалити документ?"):
            return
        try:
            with db.get_connection() as conn:
                status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (doc_id,)).fetchone()
                if status and status[0] != "draft":
                    raise ValueError("Видаляти можна лише чернетки")
                conn.execute("DELETE FROM SalesDocuments WHERE id=?", (doc_id,))
                conn.commit()
            self.refresh_sales()
        except Exception as exc:
            logging.exception("Delete sale error")
            show_error("Продажі", str(exc))

    def post_sale_action(self) -> None:
        doc_id = self._selected_sale()
        if not doc_id:
            return
        try:
            db.post_sale(doc_id)
            self.refresh_sales()
            self.refresh_stock()
            self.refresh_cash()
        except Exception as exc:
            logging.exception("Post sale error")
            show_error("Продажі", str(exc))

    def unpost_sale_action(self) -> None:
        doc_id = self._selected_sale()
        if not doc_id:
            return
        try:
            db.unpost_sale(doc_id)
            self.refresh_sales()
            self.refresh_stock()
            self.refresh_cash()
        except Exception as exc:
            logging.exception("Unpost sale error")
            show_error("Продажі", str(exc))

    # Cash
    def create_cash_tab(self) -> None:
        top = ttk.Frame(self.cash_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Дата з:").pack(side=tk.LEFT)
        self.cash_date_from_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.cash_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(top, text="по:").pack(side=tk.LEFT)
        self.cash_date_to_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.cash_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Фільтр", command=self.refresh_cash).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Додати рух", command=self.add_cash).pack(side=tk.LEFT, padx=6)

        columns = [
            ("date", "Дата", 90),
            ("type", "Тип", 140),
            ("amount", "Сума", 100),
            ("counterparty", "Контрагент", 160),
            ("channel", "Канал", 120),
            ("related", "Документ", 120),
            ("comment", "Коментар", 260),
        ]
        self.cash_table = TableFrame(self.cash_frame, columns)
        self.cash_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def refresh_cash(self) -> None:
        rows = db.list_cash(self.cash_date_from_var.get().strip() or None, self.cash_date_to_var.get().strip() or None)
        type_labels = {
            "sale_payment": "Оплата від клієнта",
            "purchase_payment": "Оплата постачальнику",
            "other_income": "Інший дохід",
            "other_variable_expense": "Змінна витрата",
            "fixed_expense": "Постійна витрата",
        }
        self.cash_table.set_rows(
            [
                {
                    "id": r["id"],
                    "date": r["date"],
                    "type": type_labels.get(r["type"], r["type"]),
                    "amount": f"{r['amount']:.2f}",
                    "counterparty": r["counterparty"] or "-",
                    "channel": r["channel"] or "-",
                    "related": f"{r['related_doc_type'] or ''} #{r['related_doc_id'] or ''}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def add_cash(self) -> None:
        counterparties = db.list_counterparties()
        channels = db.list_channels(active_only=True)
        transactions = cash_prompt(counterparties, channels)
        if not transactions:
            return
        try:
            for tx in transactions:
                db.add_cash_transaction(**tx)
            self.refresh_cash()
        except Exception:
            logging.exception("Add cash error")
            show_error("Каса", "Не вдалося зберегти рух коштів")

    # Stock
    def create_stock_tab(self) -> None:
        top = ttk.Frame(self.stock_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук товару:").pack(side=tk.LEFT)
        self.stock_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.stock_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Оновити", command=self.on_search_stock).pack(side=tk.LEFT)
        ttk.Button(top, text="Перерахувати залишки", command=self.recalc_stock).pack(side=tk.LEFT, padx=6)

        columns = [("name", "Товар", 240), ("sku", "SKU", 120), ("warehouse", "Склад", 160), ("quantity", "Кількість", 100), ("average_cost", "Сер. собівартість", 140)]
        self.stock_table = TableFrame(self.stock_frame, columns)
        self.stock_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def on_search_stock(self) -> None:
        self.refresh_stock(self.stock_search_var.get())

    def refresh_stock(self, search: str | None = None) -> None:
        rows = db.list_stock(search)
        self.stock_table.set_rows(
            [
                {
                    "id": f"{r['product_id']}-{r['warehouse_id'] if r['warehouse_id'] else '0'}",
                    "name": r["name"],
                    "sku": r["sku"],
                    "warehouse": r["warehouse"] or "-",
                    "quantity": f"{r['quantity']:.2f}",
                    "average_cost": f"{r['average_cost']:.2f}",
                }
                for r in rows
            ]
        )

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

    # Reports
    def create_reports_tab(self) -> None:
        frm = ttk.Frame(self.reports_frame)
        frm.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(frm, text="Дата з:").pack(side=tk.LEFT)
        self.report_date_from_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.report_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(frm, text="по:").pack(side=tk.LEFT)
        self.report_date_to_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.report_date_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(frm, text="Прибуток по товарам", command=self.show_profit_by_product).pack(side=tk.LEFT, padx=6)
        ttk.Button(frm, text="Грошовий потік", command=self.show_cash_flow).pack(side=tk.LEFT, padx=6)

        columns = [("name", "Назва", 260), ("metric1", "Значення 1", 160), ("metric2", "Значення 2", 160), ("metric3", "Значення 3", 160)]
        self.report_table = TableFrame(self.reports_frame, columns)
        self.report_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def show_profit_by_product(self) -> None:
        rows = db.profit_by_product(self.report_date_from_var.get().strip() or None, self.report_date_to_var.get().strip() or None)
        self.report_table.set_rows(
            [
                {
                    "id": r["product_id"],
                    "name": r["product"],
                    "metric1": f"Дохід: {r['income']:.2f}",
                    "metric2": f"Собівартість: {r['cogs']:.2f}",
                    "metric3": f"Валовий прибуток: {r['gross_profit']:.2f}",
                }
                for r in rows
            ]
        )

    def show_cash_flow(self) -> None:
        rows = db.cash_flow_summary(self.report_date_from_var.get().strip() or None, self.report_date_to_var.get().strip() or None)
        self.report_table.set_rows(
            [
                {
                    "id": idx,
                    "name": r["type"],
                    "metric1": f"Сума: {r['total']:.2f}",
                    "metric2": "",
                    "metric3": "",
                }
                for idx, r in enumerate(rows, 1)
            ]
        )

    # Export
    def create_export_tab(self) -> None:
        ttk.Label(self.export_frame, text="Експорт таблиць у CSV", font=("Segoe UI", 10, "bold")).pack(pady=10)
        tables = [
            ("Brands", "Бренди"),
            ("Categories", "Категорії"),
            ("Products", "Товари"),
            ("Counterparties", "Контрагенти"),
            ("Warehouses", "Склади"),
            ("SalesChannels", "Канали"),
            ("PurchaseDocuments", "Закупівлі"),
            ("PurchaseLines", "Рядки закупівель"),
            ("SalesDocuments", "Продажі"),
            ("SalesLines", "Рядки продажів"),
            ("StockBalances", "Залишки"),
            ("StockMoves", "Рухи товарів"),
            ("CashTransactions", "Каса"),
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
        ttk.Label(self.about_frame, text="Облік лише за касовим методом. Собівартість за середньозваженим методом.").pack(pady=4)
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
                    "unit": r["unit"],
                    "is_active": "Так" if r["is_active"] else "Ні",
                }
                for r in rows
            ]
        )

    def refresh_counterparties(self) -> None:
        rows = db.list_counterparties()
        type_labels = {
            "supplier": "Постачальник",
            "customer": "Покупець",
            "both": "Постачальник/Покупець",
            "other": "Інший",
        }
        self.counterparty_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": type_labels.get(r["type"], r["type"]),
                    "phone": r["phone"] or "",
                    "email": r["email"] or "",
                    "address": r["address"] or "",
                    "note": r["note"] or "",
                }
                for r in rows
            ]
        )

    def refresh_warehouses(self) -> None:
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

    def refresh_channels(self) -> None:
        rows = db.list_channels()
        self.channel_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "is_active": "Так" if r["is_active"] else "Ні",
                }
                for r in rows
            ]
        )

    def refresh_all(self) -> None:
        self.refresh_brands()
        self.refresh_categories()
        self.refresh_products()
        self.refresh_counterparties()
        self.refresh_warehouses()
        self.refresh_channels()
        self.refresh_currencies()
        self.refresh_purchases()
        self.refresh_sales()
        self.refresh_cash()
        self.refresh_stock()


# Dialogs

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

    ttk.Label(dlg, text="Одиниця").grid(row=4, column=0, padx=6, pady=4, sticky="w")
    unit_var = tk.StringVar(value=initial[4] if initial else "pcs")
    ttk.Entry(dlg, textvariable=unit_var, width=10).grid(row=4, column=1, padx=6, pady=4, sticky="w")

    is_active_var = tk.BooleanVar(value=initial[5] if initial else True)
    ttk.Checkbutton(dlg, text="Активний", variable=is_active_var).grid(row=5, column=1, padx=6, pady=4, sticky="w")

    if initial:
        brand_combo.current(next((i for i, b in enumerate(brands) if b["id"] == initial[2]), 0))
        category_combo.current(next((i for i, c in enumerate(categories) if c["id"] == initial[3]), 0))
    else:
        if brands:
            brand_combo.current(0)
        if categories:
            category_combo.current(0)

    result = None

    def on_ok():
        nonlocal result
        sku = sku_var.get().strip()
        name = name_var.get().strip()
        if not sku or not name:
            messagebox.showerror("Валідація", "Заповніть SKU та назву")
            return
        try:
            brand_id = brands[brand_combo.current()]["id"]
            category_id = categories[category_combo.current()]["id"]
        except IndexError:
            messagebox.showerror("Валідація", "Оберіть бренд і категорію")
            return
        result = (sku, name, brand_id, category_id, unit_var.get().strip() or "pcs", bool(is_active_var.get()))
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


def counterparty_prompt(initial=None):
    dlg = tk.Toplevel()
    dlg.title("Контрагент")
    dlg.grab_set()

    labels = ["Назва", "Телефон", "Email", "Адреса", "Нотатка"]
    vars_ = [tk.StringVar(value=initial[i] if initial else "") for i in [0, 2, 3, 4, 5]]

    ttk.Label(dlg, text="Назва").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    ttk.Entry(dlg, textvariable=vars_[0], width=30).grid(row=0, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Тип").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    type_var = tk.StringVar()
    types = ["Постачальник", "Покупець", "Постачальник/Покупець", "Інший"]
    type_values = {"Постачальник": "supplier", "Покупець": "customer", "Постачальник/Покупець": "both", "Інший": "other"}
    type_combo = ttk.Combobox(dlg, textvariable=type_var, values=types, state="readonly")
    type_combo.grid(row=1, column=1, padx=6, pady=4)
    if initial:
        inv_map = {v: k for k, v in type_values.items()}
        type_combo.set(inv_map.get(initial[1], types[0]))
    else:
        type_combo.current(0)

    for i, label in enumerate(labels[1:], start=2):
        ttk.Label(dlg, text=label).grid(row=i, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(dlg, textvariable=vars_[i - 1], width=30).grid(row=i, column=1, padx=6, pady=4)

    result = None

    def on_ok():
        nonlocal result
        name = vars_[0].get().strip()
        if not name:
            messagebox.showerror("Валідація", "Заповніть назву")
            return
        ctype = type_values.get(type_var.get(), "supplier")
        phone, email, address, note = [v.get().strip() for v in vars_[1:]]
        result = (name, ctype, phone, email, address, note)
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


def warehouse_prompt(initial=None):
    dlg = tk.Toplevel()
    dlg.title("Склад")
    dlg.grab_set()

    name_var = tk.StringVar(value=initial[0] if initial else "")
    desc_var = tk.StringVar(value=initial[1] if initial else "")
    active_var = tk.BooleanVar(value=initial[2] if initial else True)

    ttk.Label(dlg, text="Назва").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    ttk.Entry(dlg, textvariable=name_var, width=30).grid(row=0, column=1, padx=6, pady=4)
    ttk.Label(dlg, text="Опис").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    ttk.Entry(dlg, textvariable=desc_var, width=40).grid(row=1, column=1, padx=6, pady=4)
    ttk.Checkbutton(dlg, text="Активний", variable=active_var).grid(row=2, column=1, padx=6, pady=4, sticky="w")

    result = None

    def on_ok():
        nonlocal result
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Валідація", "Заповніть назву")
            return
        result = (name, desc_var.get().strip(), bool(active_var.get()))
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=3, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def channel_prompt(initial=None):
    dlg = tk.Toplevel()
    dlg.title("Канал продажу")
    dlg.grab_set()
    name_var = tk.StringVar(value=initial[0] if initial else "")
    active_var = tk.BooleanVar(value=initial[1] if initial else True)

    ttk.Label(dlg, text="Назва").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    ttk.Entry(dlg, textvariable=name_var, width=30).grid(row=0, column=1, padx=6, pady=4)
    ttk.Checkbutton(dlg, text="Активний", variable=active_var).grid(row=1, column=1, padx=6, pady=4, sticky="w")

    result = None

    def on_ok():
        nonlocal result
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Валідація", "Заповніть назву")
            return
        result = (name, bool(active_var.get()))
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=2, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def document_prompt(doc_type: str, products, counterparties, warehouses, channels, currencies, doc=None, lines=None):
    dlg = tk.Toplevel()
    dlg.title("Документ")
    dlg.grab_set()
    editable = not doc or doc["status"] == "draft"

    ttk.Label(dlg, text="Тип").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    doc_type_label = "Закупівля" if doc_type == "purchase" else "Продаж"
    ttk.Label(dlg, text=doc_type_label).grid(row=0, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Дата (YYYY-MM-DD)").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    date_var = tk.StringVar(value=doc["doc_date"] if doc else datetime.now().strftime("%Y-%m-%d"))
    ttk.Entry(dlg, textvariable=date_var, width=15, state="normal" if editable else "disabled").grid(row=1, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Валюта").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    curr_var = tk.StringVar(value=doc["currency_code"] if doc else (currencies[0]["code"] if currencies else "UAH"))
    curr_codes = [c["code"] for c in currencies] if currencies else ["UAH"]
    curr_combo = ttk.Combobox(dlg, textvariable=curr_var, values=curr_codes, state="readonly")
    if not editable:
        curr_combo.state(["disabled"])
    curr_combo.grid(row=2, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Курс до базової").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    default_rate = doc["exchange_rate"] if doc else (db.latest_rate(curr_var.get()) if currencies else 1.0)
    rate_var = tk.StringVar(value=f"{default_rate:.4f}")
    rate_entry = ttk.Entry(dlg, textvariable=rate_var, width=12, state="normal" if editable else "disabled")
    rate_entry.grid(row=3, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Склад").grid(row=4, column=0, padx=6, pady=4, sticky="w")
    wh_var = tk.StringVar()
    wh_names = [w["name"] for w in warehouses]
    wh_combo = ttk.Combobox(dlg, textvariable=wh_var, values=wh_names, state="readonly")
    wh_combo.grid(row=4, column=1, padx=6, pady=4, sticky="w")

    row_idx = 5
    ch_var = tk.StringVar()
    ch_combo = None
    if doc_type == "sale":
        ttk.Label(dlg, text="Канал").grid(row=row_idx, column=0, padx=6, pady=4, sticky="w")
        ch_names = [c["name"] for c in channels]
        ch_combo = ttk.Combobox(dlg, textvariable=ch_var, values=ch_names, state="readonly")
        ch_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
        row_idx += 1

    ttk.Label(dlg, text="Контрагент").grid(row=row_idx, column=0, padx=6, pady=4, sticky="w")
    allowed_types = {"purchase": {"supplier", "both", "other"}, "sale": {"customer", "both", "other"}}[doc_type]
    filtered_counterparties = [c for c in counterparties if c["type"] in allowed_types]
    cp_names = ["-"] + [c["name"] for c in filtered_counterparties]
    cp_var = tk.StringVar()
    cp_combo = ttk.Combobox(dlg, textvariable=cp_var, values=cp_names, state="readonly", width=25)
    cp_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
    row_idx += 1

    ttk.Label(dlg, text="Коментар").grid(row=row_idx, column=0, padx=6, pady=4, sticky="w")
    comment_var = tk.StringVar(value=doc["comment"] if doc else "")
    ttk.Entry(dlg, textvariable=comment_var, width=40).grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Рядки").grid(row=row_idx + 1, column=0, padx=6, pady=4, sticky="nw")
    line_frame = ttk.Frame(dlg)
    line_frame.grid(row=row_idx + 1, column=1, padx=6, pady=4, sticky="nsew")
    line_frame.grid_columnconfigure(0, weight=1)

    columns = ["product", "quantity", "price", "amount"]
    tree = ttk.Treeview(line_frame, columns=columns, show="headings", height=8)
    headings = {
        "product": ("Товар", 200),
        "quantity": ("Кількість", 90),
        "price": ("Ціна", 90),
        "amount": ("Сума", 90),
    }
    for col, (title, width) in headings.items():
        tree.heading(col, text=title)
        tree.column(col, width=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll = ttk.Scrollbar(line_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    yscroll.grid(row=0, column=1, sticky="ns")
    line_frame.grid_rowconfigure(0, weight=1)

    def refresh_currency_ui() -> None:
        price_label.config(text=f"Ціна ({curr_var.get()})")
        tree.heading("price", text=f"Ціна ({curr_var.get()})")
        tree.heading("amount", text=f"Сума ({curr_var.get()})")

    def on_currency_change(event=None):
        if editable:
            try:
                rate_var.set(f"{db.latest_rate(curr_var.get()):.4f}")
            except Exception:
                pass
        refresh_currency_ui()

    curr_combo.bind("<<ComboboxSelected>>", on_currency_change)

    product_lookup = {f"{p['name']} ({p['sku']})": p["id"] for p in products}
    products_by_id = {p["id"]: f"{p['name']} ({p['sku']})" for p in products}

    entry_frame = ttk.Frame(dlg)
    entry_frame.grid(row=7, column=0, columnspan=2, padx=6, pady=4, sticky="w")
    ttk.Label(entry_frame, text="Товар").grid(row=0, column=0, padx=4, pady=2)
    product_var = tk.StringVar()
    product_combo = ttk.Combobox(entry_frame, textvariable=product_var, values=list(product_lookup.keys()), state="readonly", width=40)
    product_combo.grid(row=0, column=1, padx=4, pady=2)
    if product_lookup:
        product_combo.current(0)

    ttk.Label(entry_frame, text="Кількість").grid(row=0, column=2, padx=4, pady=2)
    qty_var = tk.StringVar(value="1")
    ttk.Entry(entry_frame, textvariable=qty_var, width=10).grid(row=0, column=3, padx=4, pady=2)

    price_label = ttk.Label(entry_frame, text="Ціна")
    price_label.grid(row=0, column=4, padx=4, pady=2)
    price_var = tk.StringVar(value="0")
    ttk.Entry(entry_frame, textvariable=price_var, width=10).grid(row=0, column=5, padx=4, pady=2)

    line_data = []
    if lines:
        for ln in lines:
            price_field = "purchase_price" if doc_type == "purchase" else "sale_price"
            line_data.append(
                {
                    "product_id": ln["product_id"],
                    "product_name": ln["product_name"],
                    "quantity": float(ln["quantity"]),
                    "price": float(ln[price_field]),
                    "amount": float(ln["quantity"]) * float(ln[price_field]),
                }
            )

    if doc:
        if doc["warehouse_id"]:
            try:
                wh_combo.current(next(i for i, w in enumerate(warehouses) if w["id"] == doc["warehouse_id"]))
            except StopIteration:
                wh_combo.set(warehouses[0]["name"] if warehouses else "")
        if curr_codes:
            try:
                curr_combo.current(curr_codes.index(doc.get("currency_code", curr_codes[0])))
            except ValueError:
                curr_combo.current(0)
        if doc_type == "sale" and ch_combo:
            if doc["channel"]:
                try:
                    ch_combo.current(next(i for i, c in enumerate(channels) if c["name"] == doc["channel"]))
                except StopIteration:
                    ch_combo.set(channels[0]["name"] if channels else "")
            elif channels:
                ch_combo.current(0)
        if doc.get("supplier_id"):
            target = next((c["name"] for c in filtered_counterparties if c["id"] == doc.get("supplier_id")), "-")
            cp_var.set(target)
        if doc.get("customer_id"):
            target = next((c["name"] for c in filtered_counterparties if c["id"] == doc.get("customer_id")), "-")
            cp_var.set(target)
    else:
        if warehouses:
            wh_combo.current(0)
        if ch_combo and channels:
            ch_combo.current(0)
        if curr_codes:
            curr_combo.current(0)
        cp_var.set("-")

    selected_idx: list[int] = []

    refresh_currency_ui()

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
        try:
            rate = float(rate_var.get())
        except ValueError:
            messagebox.showerror("Валідація", "Невірний курс")
            return
        if rate <= 0:
            messagebox.showerror("Валідація", "Курс має бути більшим за 0")
            return
        cp_name = cp_var.get()
        cp_id = None
        if cp_name and cp_name != "-":
            cp_id = next((c["id"] for c in filtered_counterparties if c["name"] == cp_name), None)
        try:
            warehouse_id = warehouses[wh_combo.current()]["id"]
        except Exception:
            messagebox.showerror("Валідація", "Оберіть склад")
            return
        channel_name = ""
        if doc_type == "sale":
            channel_name = ch_var.get() if ch_var.get() else (channels[0]["name"] if channels else "")
        info = {
            "doc_type": doc_type,
            "doc_date": date_var.get().strip(),
            "counterparty_id": cp_id,
            "warehouse_id": warehouse_id,
            "channel": channel_name,
            "comment": comment_var.get().strip(),
            "currency": curr_var.get(),
            "rate": rate,
        }
        lines_to_save = [(ln["product_id"], ln["quantity"], ln["price"]) for ln in line_data]
        result = (info, lines_to_save)
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=8, column=0, columnspan=2, pady=8)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def cash_prompt(counterparties, channels):
    dlg = tk.Toplevel()
    dlg.title("Рух коштів")
    dlg.grab_set()

    ttk.Label(dlg, text="Дата (YYYY-MM-DD)").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
    ttk.Entry(dlg, textvariable=date_var, width=15).grid(row=0, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Тип").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    type_var = tk.StringVar()
    types = [
        ("Оплата від клієнта", "sale_payment"),
        ("Оплата постачальнику", "purchase_payment"),
        ("Інший дохід", "other_income"),
        ("Змінна витрата", "other_variable_expense"),
        ("Постійна витрата", "fixed_expense"),
    ]
    type_combo = ttk.Combobox(dlg, textvariable=type_var, values=[t[0] for t in types], state="readonly")
    type_combo.grid(row=1, column=1, padx=6, pady=4, sticky="w")
    type_combo.current(0)

    ttk.Label(dlg, text="Сума (+ вхід, - вихід)").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    amount_var = tk.StringVar(value="0")
    ttk.Entry(dlg, textvariable=amount_var, width=15).grid(row=2, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Контрагент").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    cp_var = tk.StringVar()
    cp_names = ["-"] + [c["name"] for c in counterparties]
    cp_combo = ttk.Combobox(dlg, textvariable=cp_var, values=cp_names, state="readonly", width=30)
    cp_combo.grid(row=3, column=1, padx=6, pady=4, sticky="w")
    cp_combo.current(0)

    ttk.Label(dlg, text="Канал").grid(row=4, column=0, padx=6, pady=4, sticky="w")
    ch_var = tk.StringVar()
    ch_names = [c["name"] for c in channels]
    ch_combo = ttk.Combobox(dlg, textvariable=ch_var, values=ch_names, state="readonly", width=20)
    ch_combo.grid(row=4, column=1, padx=6, pady=4, sticky="w")
    if channels:
        ch_combo.current(0)

    ttk.Label(dlg, text="Коментар").grid(row=5, column=0, padx=6, pady=4, sticky="w")
    comment_var = tk.StringVar()
    ttk.Entry(dlg, textvariable=comment_var, width=40).grid(row=5, column=1, padx=6, pady=4, sticky="w")

    result: list[dict] | None = None

    def on_ok():
        nonlocal result
        try:
            datetime.fromisoformat(date_var.get())
            amount = float(amount_var.get())
        except ValueError:
            messagebox.showerror("Валідація", "Невірні значення дати або суми")
            return
        ctype = next((t[1] for t in types if t[0] == type_var.get()), types[0][1])
        cp_name = cp_var.get()
        cp_id = None
        if cp_name and cp_name != "-":
            cp_id = next((c["id"] for c in counterparties if c["name"] == cp_name), None)
        channel = ch_var.get() if ch_var.get() else ""
        result = [
            {
                "date": date_var.get().strip(),
                "amount": amount,
                "ctype": ctype,
                "counterparty_id": cp_id,
                "related_doc_type": None,
                "related_doc_id": None,
                "channel": channel,
                "comment": comment_var.get().strip(),
            }
        ]
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
    except Exception:
        logging.exception("Fatal error")
        try:
            messagebox.showerror(APP_NAME, f"Критична помилка. Деталі у логах: {get_log_path()}")
        except tk.TclError:
            print("Критична помилка. Деталі у логах:", get_log_path(), file=sys.stderr)
        traceback.print_exc()


if __name__ == "__main__":
    main()

