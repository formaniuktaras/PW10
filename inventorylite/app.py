"""InventoryLite minimal Tkinter app."""
from __future__ import annotations

import logging
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
        self.geometry("820x520")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.create_menu()

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.brands_frame = ttk.Frame(notebook)
        self.categories_frame = ttk.Frame(notebook)
        self.products_frame = ttk.Frame(notebook)
        self.export_frame = ttk.Frame(notebook)
        self.about_frame = ttk.Frame(notebook)

        notebook.add(self.brands_frame, text="Бренди")
        notebook.add(self.categories_frame, text="Категорії")
        notebook.add(self.products_frame, text="Товари")
        notebook.add(self.export_frame, text="Експорт")
        notebook.add(self.about_frame, text="Про програму")

        self.create_brands_tab()
        self.create_categories_tab()
        self.create_products_tab()
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

    # Export
    def create_export_tab(self) -> None:
        ttk.Label(self.export_frame, text="Експорт таблиць у CSV", font=("Segoe UI", 10, "bold")).pack(pady=10)
        for table, label in [("Brands", "Бренди"), ("Categories", "Категорії"), ("Products", "Товари")]:
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

