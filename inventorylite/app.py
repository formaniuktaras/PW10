"""InventoryLite GUI with cash-basis accounting and moving-average inventory.

The app focuses on a lightweight workflow for a trading business:
- Cash basis only: income/expense are registered when money changes hands.
- Inventory cost uses moving-average per product and warehouse.
- Direct-costing: only variable costs (purchase price) are included into COGS; fixed
  expenses are tracked separately via cash transactions.
"""
from __future__ import annotations

import csv
import logging
import math
import traceback
import webbrowser
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
import sqlite3
from typing import Optional

from inventorylite import db
from inventorylite import labels
from inventorylite.helpers import (
    PURCHASE_FIELDS,
    SALES_FIELDS,
    _find_index_by_name,
    _format_cell_value,
    _normalize_header,
    _normalize_purchase_records,
    _normalize_sales_records,
    _parse_bool_value,
    _parse_date_value,
    _parse_float_value,
    _parse_num,
    _read_rate_two_way,
    _sanitize_barcode_prefix,
    _suggest_purchase_mapping,
    _suggest_sales_mapping,
    parse_import_file,
    parse_sales_file,
)
from inventorylite.error_handling import install_tk_exception_handler, setup_logging
from inventorylite.label_templates_ui import TemplateManagerDialog
from inventorylite.tabs.products import ProductsTab, open_products_bulk_actions_dialog
from inventorylite.tabs.reports import ReportsTab
from inventorylite.tabs.settings import SettingsTab
from inventorylite.utils import (
    APP_NAME,
    VERSION,
    SingleInstance,
    backup_all_data,
    get_data_dir,
    get_db_path,
    get_lock_path,
    Settings,
    apply_base_currency_settings,
    get_base_currency_code,
    get_base_currency_name,
    get_base_currency_decimals,
    open_data_folder,
    open_file,
    restore_all_data,
    show_error,
    backup_database,
    bind_common_shortcuts,
)
from inventorylite.ui_components import DatePicker, TableFrame, simple_prompt
from inventorylite.dialogs import (
    category_prompt,
    counterparty_prompt,
    warehouse_prompt,
    channel_prompt,
)
from inventorylite.dialogs_documents import document_prompt, ensure_rate_for_date
from inventorylite.dialogs_inventory import inventory_prompt


class InventoryApp(tk.Tk):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x720")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.settings = settings or Settings()
        apply_base_currency_settings(self.settings)
        self.status_var = tk.StringVar(value="Готово")
        self.status_bar: ttk.Label | None = None
        bind_common_shortcuts(self)
        self.create_menu()
        self.apply_settings()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.brands_frame = ttk.Frame(self.notebook)
        self.categories_frame = ttk.Frame(self.notebook)
        self.counterparties_frame = ttk.Frame(self.notebook)
        self.warehouses_frame = ttk.Frame(self.notebook)
        self.channels_frame = ttk.Frame(self.notebook)
        self.currencies_frame = ttk.Frame(self.notebook)
        self.purchases_frame = ttk.Frame(self.notebook)
        self.extra_costs_frame = ttk.Frame(self.notebook)
        self.sales_frame = ttk.Frame(self.notebook)
        self.inventory_frame = ttk.Frame(self.notebook)
        self.cash_frame = ttk.Frame(self.notebook)
        self.stock_frame = ttk.Frame(self.notebook)
        self.export_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.brands_frame, text="Бренди")
        self.notebook.add(self.categories_frame, text="Категорії")
        self.products_tab = ProductsTab(
            parent=self.notebook,
            settings=self.settings,
            flatten_categories_provider=self.flatten_categories,
        )
        self.notebook.add(self.products_tab.frame, text="Товари")
        self.notebook.add(self.counterparties_frame, text="Контрагенти")
        self.notebook.add(self.warehouses_frame, text="Склади")
        self.notebook.add(self.channels_frame, text="Канали продажу")
        self.notebook.add(self.currencies_frame, text="Валюти")
        self.notebook.add(self.purchases_frame, text="Закупівлі")
        self.notebook.add(self.extra_costs_frame, text="Супутні витрати")
        self.notebook.add(self.sales_frame, text="Продажі")
        self.notebook.add(self.inventory_frame, text="Інвентаризація")
        self.notebook.add(self.cash_frame, text="Каса")
        self.notebook.add(self.stock_frame, text="Залишки")
        self.notebook.add(self.export_frame, text="Експорт")
        self.settings_tab = SettingsTab(
            parent=self.notebook,
            settings=self.settings,
            on_settings_saved=self._on_settings_saved,
        )
        self.notebook.add(self.settings_tab.frame, text="Налаштування")
        self.reports_tab = ReportsTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.reports_tab.frame, text="Звіти")

        self.create_brands_tab()
        self.create_categories_tab()
        self.create_counterparties_tab()
        self.create_warehouses_tab()
        self.create_channels_tab()
        self.create_currencies_tab()
        self.create_purchases_tab()
        self.create_extra_costs_tab()
        self.create_sales_tab()
        self.create_inventory_tab()
        self.create_cash_tab()
        self.create_stock_tab()
        self.create_export_tab()
        # "Про програму" is opened from the File menu

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
        file_menu.add_command(label="Налаштування", command=self.open_settings_dialog)
        file_menu.add_command(label="Скинути профіль гарячих клавіш", command=self.reset_hotkeys_profile)
        file_menu.add_separator()
        file_menu.add_command(label="Документація/FAQ", command=self.open_docs)
        file_menu.add_separator()
        file_menu.add_command(label="Про програму", command=self.show_about)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.config(menu=menubar)

    def default_workdir(self) -> Path:
        path = self.settings.get("files", "working_dir") or str(get_data_dir())
        try:
            return Path(path)
        except Exception:
            return get_data_dir()

    def open_settings_dialog(self, section: str = "general") -> None:
        self.settings_tab.refresh()
        self.notebook.select(self.settings_tab.frame)
        self.settings_tab.select_section(section)

    def reset_hotkeys_profile(self) -> None:
        self.settings.set("Типовий", "hotkeys", "profile")
        self.settings.save()
        messagebox.showinfo("Гарячі клавіші", "Профіль клавіш скинуто до типового.")

    def open_docs(self) -> None:
        url = self.settings.get("support", "docs_url") or "https://example.com/docs"
        webbrowser.open(url)

    def apply_settings(self) -> None:
        self.apply_theme()
        self.apply_status_bar()
        self.apply_window_modes()
        self.apply_editor_font()

    def _on_settings_saved(self) -> None:
        apply_base_currency_settings(self.settings)
        self.refresh_currencies()
        self.apply_settings()

    def apply_theme(self) -> None:
        theme = (self.settings.get("general", "theme") or "system").lower()
        style = ttk.Style()
        try:
            if theme == "dark":
                palette = self._apply_dark_theme(style)
            elif theme == "light":
                palette = self._apply_light_theme(style)
            else:
                palette = self._apply_system_theme(style)
            self._apply_palette(palette)
        except tk.TclError:
            logging.warning("Не вдалося застосувати тему %s", theme)

    def _preferred_base_theme(self, style: ttk.Style) -> str:
        for candidate in ("vista", "xpnative", "clam", "default"):
            if candidate in style.theme_names():
                return candidate
        return style.theme_use()

    def _apply_system_theme(self, style: ttk.Style) -> dict[str, str]:
        base_theme = self._preferred_base_theme(style)
        style.theme_use(base_theme)
        return {
            "bg": style.lookup("TFrame", "background") or style.lookup(".", "background") or "#f0f0f0",
            "surface": style.lookup("TNotebook", "background") or "#e6e6e6",
            "surface_alt": style.lookup("TButton", "background") or "#d9d9d9",
            "text": style.lookup("TLabel", "foreground") or "#000000",
            "muted": "#555555",
            "accent": "#4a90e2",
        }

    def _apply_light_theme(self, style: ttk.Style) -> dict[str, str]:
        base_theme = self._preferred_base_theme(style)
        palette = {
            "bg": "#f7f7f7",
            "surface": "#ffffff",
            "surface_alt": "#ededed",
            "text": "#202020",
            "muted": "#5b5b5b",
            "accent": "#4a90e2",
        }

        if "inventorylite-light" not in style.theme_names():
            style.theme_create(
                "inventorylite-light",
                parent=base_theme,
                settings={
                    ".": {
                        "configure": {
                            "background": palette["bg"],
                            "foreground": palette["text"],
                            "fieldbackground": palette["surface"],
                            "troughcolor": palette["surface_alt"],
                            "bordercolor": palette["surface_alt"],
                            "focuscolor": palette["accent"],
                        }
                    },
                    "TFrame": {"configure": {"background": palette["bg"]}},
                    "TLabel": {
                        "configure": {
                            "background": palette["bg"],
                            "foreground": palette["text"],
                        }
                    },
                    "TButton": {
                        "configure": {
                            "background": palette["surface_alt"],
                            "foreground": palette["text"],
                            "padding": (10, 6),
                        },
                        "map": {
                            "background": [
                                ("pressed", palette["accent"]),
                                ("active", palette["surface"]),
                            ]
                        },
                    },
                    "TEntry": {
                        "configure": {
                            "fieldbackground": palette["surface"],
                            "foreground": palette["text"],
                            "insertcolor": palette["text"],
                        }
                    },
                    "TCombobox": {
                        "configure": {
                            "fieldbackground": palette["surface"],
                            "foreground": palette["text"],
                            "background": palette["surface_alt"],
                            "arrowsize": 14,
                        },
                        "map": {
                            "fieldbackground": [("readonly", palette["surface"])],
                            "background": [
                                ("active", palette["surface_alt"]),
                                ("readonly", palette["surface_alt"]),
                            ],
                        },
                    },
                    "TNotebook": {
                        "configure": {
                            "background": palette["bg"],
                            "tabmargins": (6, 3, 6, 0),
                        }
                    },
                    "TNotebook.Tab": {
                        "configure": {
                            "background": palette["surface_alt"],
                            "foreground": palette["muted"],
                            "padding": (12, 6),
                        },
                        "map": {
                            "background": [("selected", palette["surface"])],
                            "foreground": [("selected", palette["text"])],
                        },
                    },
                    "Treeview": {
                        "configure": {
                            "background": palette["surface"],
                            "fieldbackground": palette["surface"],
                            "foreground": palette["text"],
                            "bordercolor": palette["surface_alt"],
                            "lightcolor": palette["surface"],
                            "darkcolor": palette["surface_alt"],
                        },
                        "map": {
                            "background": [("selected", palette["accent"])],
                            "foreground": [("selected", palette["surface"]), ("!selected", palette["text"])],
                        },
                    },
                    "Treeview.Heading": {
                        "configure": {
                            "background": palette["surface_alt"],
                            "foreground": palette["text"],
                            "relief": "flat",
                        },
                        "map": {"background": [("active", palette["surface_alt"])]},
                    },
                },
            )

        style.theme_use("inventorylite-light")
        return palette

    def _apply_dark_theme(self, style: ttk.Style) -> dict[str, str]:
        base_theme = "clam" if "clam" in style.theme_names() else style.theme_use()
        palette = {
            "bg": "#2b2b2b",
            "surface": "#333333",
            "surface_alt": "#3a3a3a",
            "text": "#e6e6e6",
            "muted": "#c0c0c0",
            "accent": "#5a5a5a",
        }

        if "inventorylite-dark" not in style.theme_names():
            style.theme_create(
                "inventorylite-dark",
                parent=base_theme,
                settings={
                    ".": {
                        "configure": {
                            "background": palette["bg"],
                            "foreground": palette["text"],
                            "fieldbackground": palette["surface_alt"],
                            "troughcolor": palette["surface_alt"],
                            "bordercolor": palette["surface"],
                            "focuscolor": palette["accent"],
                        }
                    },
                    "TFrame": {"configure": {"background": palette["bg"]}},
                    "TLabel": {
                        "configure": {
                            "background": palette["bg"],
                            "foreground": palette["text"],
                        }
                    },
                    "TButton": {
                        "configure": {
                            "background": palette["surface_alt"],
                            "foreground": palette["text"],
                            "padding": (10, 6),
                        },
                        "map": {
                            "background": [
                                ("pressed", palette["accent"]),
                                ("active", palette["surface"]),
                            ]
                        },
                    },
                    "TEntry": {
                        "configure": {
                            "fieldbackground": palette["surface_alt"],
                            "foreground": palette["text"],
                            "insertcolor": palette["text"],
                        }
                    },
                    "TCombobox": {
                        "configure": {
                            "fieldbackground": palette["surface_alt"],
                            "foreground": palette["text"],
                            "background": palette["surface_alt"],
                            "arrowsize": 14,
                        },
                        "map": {
                            "fieldbackground": [("readonly", palette["surface_alt"])],
                            "background": [
                                ("active", palette["surface"]),
                                ("readonly", palette["surface_alt"]),
                            ],
                        },
                    },
                    "TNotebook": {
                        "configure": {
                            "background": palette["bg"],
                            "tabmargins": (6, 3, 6, 0),
                        }
                    },
                    "TNotebook.Tab": {
                        "configure": {
                            "background": palette["surface"],
                            "foreground": palette["muted"],
                            "padding": (12, 6),
                        },
                        "map": {
                            "background": [("selected", palette["surface_alt"])],
                            "foreground": [("selected", palette["text"])],
                        },
                    },
                    "Treeview": {
                        "configure": {
                            "background": palette["surface"],
                            "fieldbackground": palette["surface"],
                            "foreground": palette["text"],
                            "bordercolor": palette["surface_alt"],
                            "lightcolor": palette["surface"],
                            "darkcolor": palette["surface_alt"],
                        },
                        "map": {
                            "background": [("selected", palette["accent"])],
                            "foreground": [("selected", palette["text"])],
                        },
                    },
                    "Treeview.Heading": {
                        "configure": {
                            "background": palette["surface_alt"],
                            "foreground": palette["text"],
                            "relief": "flat",
                        },
                        "map": {"background": [("active", palette["surface_alt"])]},
                    },
                },
            )

        style.theme_use("inventorylite-dark")
        return palette

    def _apply_palette(self, palette: dict[str, str]) -> None:
        try:
            self.configure(background=palette.get("bg"))
        except tk.TclError:
            logging.debug("Tk configure not available for background")
        try:
            self.tk_setPalette(
                background=palette.get("bg"),
                foreground=palette.get("text"),
                activeBackground=palette.get("surface"),
                activeForeground=palette.get("text"),
                highlightColor=palette.get("accent"),
                highlightBackground=palette.get("surface"),
                insertBackground=palette.get("text"),
                troughColor=palette.get("surface"),
            )
        except tk.TclError:
            logging.debug("Tk palette is not available")

    def apply_status_bar(self) -> None:
        show_status = bool(self.settings.get("ui", "status_bar"))
        if show_status and not self.status_bar:
            self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
            self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        elif not show_status and self.status_bar:
            self.status_bar.destroy()
            self.status_bar = None

    def apply_window_modes(self) -> None:
        self.attributes("-fullscreen", bool(self.settings.get("ui", "fullscreen")))
        compact = bool(self.settings.get("ui", "compact_mode"))
        try:
            self.tk.call("tk", "scaling", 0.9 if compact else 1.0)
        except tk.TclError:
            logging.debug("Tk scaling is not available")

    def apply_editor_font(self) -> None:
        family = self.settings.get("editor", "font_family") or "TkDefaultFont"
        size = int(self.settings.get("editor", "font_size") or 10)
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            text_font = tkfont.nametofont("TkTextFont")
            default_font.configure(family=family, size=size)
            text_font.configure(family=family, size=size)
        except tk.TclError:
            logging.warning("Не вдалося застосувати шрифт %s", family)

    def on_backup_all(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{APP_NAME}_backup_{timestamp}.zip"
        initialdir = str(self.default_workdir())
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
            initialdir=str(self.default_workdir()),
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
        self.brand_table.on_double_click(self.edit_brand)
        self.brand_table.register_context_menu(self.edit_brand, self.delete_brand)

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
        top = ttk.Frame(self.categories_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук").pack(side=tk.LEFT)
        self.category_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.category_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Знайти", command=self.refresh_categories).pack(side=tk.LEFT)

        btns = ttk.Frame(self.categories_frame)
        btns.pack(fill=tk.X, padx=8)
        ttk.Button(btns, text="Коренева", command=lambda: self.add_category(parent_id=None)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Підкатегорія", command=lambda: self.add_category(parent_id=self.selected_category_id())).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Перейменувати", command=self.edit_category).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Перемістити", command=self.move_category_ui).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Вище", command=lambda: self.bump_category(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Нижче", command=lambda: self.bump_category(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Службова/Прихована", command=self.toggle_category_flags).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити/Злити", command=self.delete_category).pack(side=tk.LEFT, padx=4)

        columns = ("products", "quantity", "flags")
        self.category_tree = ttk.Treeview(
            self.categories_frame,
            columns=columns,
            show="tree headings",
            selectmode="browse",
        )
        self.category_tree.heading("#0", text="Категорія")
        self.category_tree.heading("products", text="Найменувань")
        self.category_tree.column("products", width=110, anchor="center")
        self.category_tree.heading("quantity", text="Одиниць на складі")
        self.category_tree.column("quantity", width=140, anchor="center")
        self.category_tree.heading("flags", text="Статус")
        self.category_tree.column("flags", width=160, anchor="w")
        self.category_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.category_tree.bind("<Double-1>", lambda e: self.edit_category())
        self.category_tree.bind(
            "<Button-3>",
            lambda e: self.category_tree.event_generate("<<TreeviewSelect>>") or self.category_tree.tk.call(
                self.category_tree, "identify", "row", e.y
            ),
        )

    def selected_category_id(self) -> Optional[int]:
        sel = self.category_tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def add_category(self, parent_id: Optional[int]) -> None:
        values = category_prompt("Нова категорія", None)
        if not values:
            return
        try:
            name, color, icon, attrs, is_service, is_hidden = values
            db.add_category(name, parent_id, color, icon, attrs, is_service, is_hidden)
            self.refresh_categories()
        except sqlite3.IntegrityError:
            show_error("Категорії", "Категорія з такою назвою вже існує.")
        except Exception:
            logging.exception("Add category error")
            show_error("Категорії", "Не вдалося додати категорію.")

    def edit_category(self) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для редагування.")
            return
        current = self.categories_index.get(category_id)
        values = category_prompt(
            "Редагувати категорію",
            (
                current.get("name", "") if current else "",
                current.get("color") if current else "",
                current.get("icon") if current else "",
                current.get("typical_attributes") if current else "",
                bool(current.get("is_service")) if current else False,
                bool(current.get("is_hidden")) if current else False,
            ),
        )
        if not values:
            return
        try:
            name, color, icon, attrs, is_service, is_hidden = values
            db.update_category(
                category_id,
                name,
                parent_id=current.get("parent_id") if current else None,
                color=color,
                icon=icon,
                typical_attributes=attrs,
                is_service=is_service,
                is_hidden=is_hidden,
                sort_order=current.get("sort_order") if current else None,
            )
            self.refresh_categories()
            self.refresh_products()
        except sqlite3.IntegrityError:
            show_error("Категорії", "Категорія з такою назвою вже існує.")
        except Exception as exc:
            logging.exception("Edit category error")
            show_error("Категорії", f"Не вдалося змінити категорію: {exc}")

    def bump_category(self, direction: str) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для переміщення.")
            return
        db.bump_category_order(category_id, direction)
        self.refresh_categories()

    def move_category_ui(self) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для переміщення.")
            return
        exclude = {category_id}
        exclude.update(db.get_category_descendants(category_id))
        options = [(None, "(Корінь)")]
        for cat in self.flatten_categories():
            if cat["id"] in exclude:
                continue
            options.append((cat["id"], cat["label"]))
        choice = select_category_dialog("Новий батько", options)
        if choice is None:
            return
        try:
            db.move_category(category_id, choice)
            self.refresh_categories()
            self.refresh_products()
        except Exception:
            logging.exception("Move category error")
            show_error("Категорії", "Не вдалося перемістити категорію.")

    def bump_category(self, delta: int) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для зміни порядку.")
            return
        db.bump_category_order(category_id, delta)
        self.refresh_categories()

    def toggle_category_flags(self) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію.")
            return
        current = self.categories_index.get(category_id)
        if not current:
            return
        try:
            db.update_category(
                category_id,
                current["name"],
                parent_id=current.get("parent_id"),
                color=current.get("color"),
                icon=current.get("icon"),
                typical_attributes=current.get("typical_attributes"),
                is_service=not bool(current.get("is_service")) if messagebox.askyesno(
                    "Статус", "Позначити/зняти позначку 'службова'?"
                )
                else bool(current.get("is_service")),
                is_hidden=not bool(current.get("is_hidden")) if messagebox.askyesno(
                    "Статус", "Приховати/показати категорію?"
                )
                else bool(current.get("is_hidden")),
                sort_order=current.get("sort_order"),
            )
            self.refresh_categories()
        except Exception:
            logging.exception("Toggle flags error")
            show_error("Категорії", "Не вдалося змінити статус.")

    def delete_category(self) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для видалення.")
            return
        target = None
        if messagebox.askyesno("Злиття", "Злити категорію з іншою (рекомендовано для категорій з товарами)?"):
            options = [(None, "(видалити, якщо порожня)")]
            for cat in self.flatten_categories():
                if cat["id"] == category_id:
                    continue
                options.append((cat["id"], cat["label"]))
            target = select_category_dialog("Цільова категорія", options)
        try:
            db.delete_category(category_id, target)
            self.refresh_categories()
            self.refresh_products()
        except ValueError as exc:
            show_error("Категорії", str(exc))
        except Exception:
            logging.exception("Delete category error")
            show_error("Категорії", f"Не вдалося видалити категорію: {exc}")

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

        def make_table(parent: tk.Widget) -> TableFrame:
            table = TableFrame(parent, columns)
            table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            table.on_double_click(self.edit_counterparty)
            table.register_context_menu(self.edit_counterparty, self.delete_counterparty)
            return table

        self.counterparty_notebook = ttk.Notebook(self.counterparties_frame)
        self.counterparty_notebook.pack(fill=tk.BOTH, expand=True)

        supplier_tab = ttk.Frame(self.counterparty_notebook)
        customer_tab = ttk.Frame(self.counterparty_notebook)
        all_tab = ttk.Frame(self.counterparty_notebook)

        self.counterparty_notebook.add(supplier_tab, text="Постачальники")
        self.counterparty_notebook.add(customer_tab, text="Покупці")
        self.counterparty_notebook.add(all_tab, text="Всі/Інші")

        self.counterparty_tables = {
            "suppliers": make_table(supplier_tab),
            "customers": make_table(customer_tab),
            "all": make_table(all_tab),
        }
        self.counterparty_tab_frames = {
            "suppliers": supplier_tab,
            "customers": customer_tab,
            "all": all_tab,
        }

        btns = ttk.Frame(self.counterparties_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_counterparty).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_counterparty).pack(side=tk.LEFT, padx=4)

    def get_active_counterparty_selection(self) -> tuple[str, TableFrame | None, int | None]:
        if not hasattr(self, "counterparty_notebook"):
            return "suppliers", None, None
        current_tab = self.counterparty_notebook.select()
        active_key = "suppliers"
        for key, frame in self.counterparty_tab_frames.items():
            if str(frame) == current_tab:
                active_key = key
                break
        table = self.counterparty_tables.get(active_key)
        selected_id = table.selected_id() if table else None
        return active_key, table, selected_id

    def add_counterparty(self) -> None:
        active_key, _, _ = self.get_active_counterparty_selection()
        default_types = {"suppliers": "supplier", "customers": "customer", "all": "other"}
        try:
            values = counterparty_prompt(default_type=default_types.get(active_key))
        except Exception as exc:
            logging.exception("Counterparty prompt error")
            messagebox.showerror("Контрагенти", str(exc))
            return
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
        _, _, counterparty_id = self.get_active_counterparty_selection()
        if not counterparty_id:
            show_error("Контрагенти", "Оберіть контрагента.")
            return
        rows = [c for c in db.list_counterparties() if c["id"] == counterparty_id]
        if not rows:
            return
        c = rows[0]
        values = counterparty_prompt(
            (c["name"], c["type"], c["phone"], c["email"], c["address"], c["note"])
        )
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
        _, _, counterparty_id = self.get_active_counterparty_selection()
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
        self.warehouse_table.on_double_click(self.edit_warehouse)
        self.warehouse_table.register_context_menu(self.edit_warehouse, self.delete_warehouse)
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
        self.channel_table.on_double_click(self.edit_channel)
        self.channel_table.register_context_menu(self.edit_channel, self.delete_channel)
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
        self.base_currency_label = ttk.Label(top, text=self._format_base_currency_label())
        self.base_currency_label.pack(anchor="w", pady=(0, 4))
        curr_columns = [("code", "Код", 80), ("name", "Назва", 200), ("decimals", "Знаків", 60), ("is_active", "Активна", 80)]
        self.currency_table = TableFrame(top, curr_columns, height=6)
        self.currency_table.pack(fill=tk.X, pady=4)
        self.currency_table.on_double_click(self.edit_currency)
        self.currency_table.register_context_menu(self.edit_currency, self.delete_currency)

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
        ttk.Button(rate_btns, text="Змінити", command=self.edit_rate).pack(side=tk.LEFT, padx=4)
        ttk.Button(rate_btns, text="Видалити", command=self.delete_rate).pack(side=tk.LEFT, padx=4)

        self.currency_table.on_select(self.refresh_rates)
        self.rate_table.on_double_click(self.edit_rate)
        self.rate_table.register_context_menu(self.edit_rate, self.delete_rate)

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
        self.update_base_currency_label()
        self.refresh_rates()

    def _format_base_currency_label(self) -> str:
        return (
            f"Базова валюта: {get_base_currency_code()} — "
            f"{get_base_currency_name()} ({get_base_currency_decimals()} знаків)"
        )

    def update_base_currency_label(self) -> None:
        if hasattr(self, "base_currency_label"):
            self.base_currency_label.configure(text=self._format_base_currency_label())

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
        base = get_base_currency_code()
        defaults = [datetime.now().strftime("%Y-%m-%d"), "1", ""]
        values = simple_prompt(
            "Новий курс",
            ["Дата", f"1 {code} = ? {base}", f"1 {base} = ? {code}"],
            defaults,
        )
        if not values:
            return
        try:
            rate = _read_rate_two_way(code, base, values[1], values[2])
            db.add_currency_rate(code, values[0], rate)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Add rate error")
            show_error("Курси", str(exc))

    def edit_rate(self) -> None:
        rate_id = self.rate_table.selected_id()
        if not rate_id:
            show_error("Курси", "Оберіть курс")
            return
        rates = [r for r in db.list_currency_rates(self.currency_table.selected_id()) if r["id"] == rate_id]
        if not rates:
            return
        current = rates[0]
        base = get_base_currency_code()
        direct_default = f"{current['rate']:.6f}"
        inverse_default = f"{(1.0 / current['rate']):.6f}" if current["rate"] > 0 else ""
        values = simple_prompt(
            "Змінити курс",
            ["Дата", f"1 {code} = ? {base}", f"1 {base} = ? {code}"],
            [current["rate_date"], direct_default, inverse_default],
        )
        if not values:
            return
        try:
            rate = _read_rate_two_way(code, base, values[1], values[2])
            db.update_currency_rate(rate_id, values[0], rate)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Edit rate error")
            show_error("Курси", str(exc))

    def delete_rate(self) -> None:
        rate_id = self.rate_table.selected_id()
        if not rate_id:
            show_error("Курси", "Оберіть курс")
            return
        if not messagebox.askyesno("Курси", "Видалити курс?"):
            return
        try:
            db.delete_currency_rate(rate_id)
            self.refresh_rates()
        except Exception as exc:
            logging.exception("Delete rate error")
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
            ("total_extra", "Супутні (база)", 120),
            ("comment", "Коментар", 240),
        ]
        self.purchase_table = TableFrame(self.purchases_frame, columns)
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

        btns = ttk.Frame(self.purchases_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Нова закупівля", command=self.new_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_purchase).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_purchase_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_purchase_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Імпорт із файлу", command=self.import_purchases_from_file).pack(side=tk.LEFT, padx=4)

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
        open_labels_print_dialog(self, items, "Кількість з документа закупівлі")

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

    def import_purchases_from_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Файл закупівель",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Усі файли", "*.*")],
            initialdir=str(self.default_workdir()),
        )
        if not file_path:
            return

        try:
            raw_rows, headers = parse_import_file(Path(file_path), encoding=self.settings.get("files", "encoding") or "utf-8")
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

        dialog = PurchasesImportDialog(self, raw_rows, headers, warehouses, suppliers, currencies, self.settings)
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
        self.refresh_cash()
        self.refresh_stock()

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
                final_sku = sku or self._generate_unique_sku(name, set(products_by_sku.keys()))
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

    # Extra costs
    def create_extra_costs_tab(self) -> None:
        filters = ttk.Frame(self.extra_costs_frame)
        filters.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        self.extra_status_var = tk.StringVar(value="Усі")
        ttk.Combobox(filters, textvariable=self.extra_status_var, values=["Усі", "Чернетка", "Проведений"], state="readonly", width=14).pack(side=tk.LEFT, padx=4)
        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        self.extra_date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.extra_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        self.extra_date_to_var = tk.StringVar()
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
        self.extra_table = TableFrame(self.extra_costs_frame, columns)
        self.extra_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.extra_table.on_double_click(self.edit_extra_cost)
        self.extra_table.register_context_menu(self.edit_extra_cost, self.delete_extra_cost)

        btns = ttk.Frame(self.extra_costs_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Новий документ", command=self.new_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_extra_cost).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_extra_cost_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_extra_cost_action).pack(side=tk.LEFT, padx=4)

    def _selected_extra_cost(self):
        doc_id = self.extra_table.selected_id()
        if not doc_id:
            show_error("Супутні витрати", "Оберіть документ")
            return None
        return doc_id

    def refresh_extra_costs(self) -> None:
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
            self.refresh_purchases()
            self.refresh_stock()
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
            self.refresh_purchases()
            self.refresh_stock()
        except Exception as exc:
            logging.exception("Unpost extra cost error")
            show_error("Супутні витрати", str(exc))

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
        self.sales_table.on_double_click(self.edit_sale)
        self.sales_table.register_context_menu(self.edit_sale, self.delete_sale)

        btns = ttk.Frame(self.sales_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Новий продаж", command=self.new_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_sale).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_sale_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Відмінити проведення", command=self.unpost_sale_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Імпорт із файлу", command=self.import_sales_from_file).pack(side=tk.LEFT, padx=4)

    def create_inventory_tab(self) -> None:
        filters = ttk.Frame(self.inventory_frame)
        filters.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(filters, text="Статус:").pack(side=tk.LEFT)
        self.inventory_status_var = tk.StringVar(value="Усі")
        ttk.Combobox(
            filters,
            textvariable=self.inventory_status_var,
            values=["Усі", "Чернетка", "Проведений"],
            state="readonly",
            width=14,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Склад:").pack(side=tk.LEFT)
        self.inventory_warehouse_var = tk.StringVar(value="Усі")
        self.inventory_warehouse_combo = ttk.Combobox(
            filters,
            textvariable=self.inventory_warehouse_var,
            values=["Усі"],
            state="readonly",
            width=18,
        )
        self.inventory_warehouse_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(filters, text="Дата з:").pack(side=tk.LEFT)
        self.inventory_date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.inventory_date_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(filters, text="по:").pack(side=tk.LEFT)
        self.inventory_date_to_var = tk.StringVar()
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
        self.inventory_table = TableFrame(self.inventory_frame, columns)
        self.inventory_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.inventory_table.on_double_click(self.edit_inventory)
        self.inventory_table.register_context_menu_actions(
            [
                ("Редагувати/Переглянути", self.edit_inventory),
                ("Видалити", self.delete_inventory),
            ]
        )

        btns = ttk.Frame(self.inventory_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Створити…", command=self.new_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Редагувати…", command=self.edit_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Провести", command=self.post_inventory_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Розпровести", command=self.unpost_inventory_action).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_inventory).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Експорт CSV", command=self.export_inventory_csv).pack(side=tk.LEFT, padx=4)

    def _selected_inventory(self) -> Optional[int]:
        doc_id = self.inventory_table.selected_id()
        if not doc_id:
            show_error("Інвентаризація", "Оберіть документ")
            return None
        return int(doc_id)

    def _refresh_inventory_warehouse_filter(self) -> None:
        warehouses = db.list_warehouses(active_only=False)
        self.inventory_warehouse_options = warehouses
        names = ["Усі"] + [w["name"] for w in warehouses]
        self.inventory_warehouse_combo.configure(values=names)
        if self.inventory_warehouse_var.get() not in names:
            self.inventory_warehouse_var.set("Усі")

    def refresh_inventory_documents(self) -> None:
        self._refresh_inventory_warehouse_filter()
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
        doc_id = self.inventory_table.selected_id()
        default_name = "inventory_lines.csv" if doc_id else "inventory_documents.csv"
        file_path = filedialog.asksaveasfilename(
            title="Експорт CSV",
            defaultextension=".csv",
            initialfile=default_name,
            initialdir=str(self.default_workdir()),
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
                        ["date", "warehouse", "sku", "name", "expected_qty", "counted_qty", "diff", "cost_override", "note"]
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
        result = document_prompt("sale", products, counterparties, warehouses, channels, currencies, settings=self.settings)
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
                info.get("order_expense_doc", 0.0),
            )
            db.replace_sale_lines(doc_id, lines, info["rate"], info.get("order_expense_doc", 0.0))
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
        result = document_prompt(
            "sale",
            products,
            counterparties,
            warehouses,
            channels,
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
                db.update_sale(
                    doc_id,
                    info["doc_date"],
                    info["counterparty_id"],
                    info["warehouse_id"],
                    info["channel"],
                    info["comment"],
                    info["currency"],
                    info["rate"],
                    info.get("order_expense_doc", 0.0),
                )
                db.replace_sale_lines(doc_id, new_lines, info["rate"], info.get("order_expense_doc", 0.0))
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
                    doc.get("order_expense_doc", 0.0),
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
                status_row = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (doc_id,)).fetchone()
            if not status_row:
                raise ValueError("Документ не знайдено")

            was_posted = status_row[0] == "posted"
            if was_posted:
                if not messagebox.askyesno(
                    "Підтвердження", "Документ проведено. Скасувати проведення та видалити?"
                ):
                    return
                db.unpost_sale(doc_id)

            with db.get_connection() as conn:
                with db.safe_transaction(conn):
                    conn.execute("DELETE FROM SalesDocuments WHERE id=?", (doc_id,))

            self.refresh_sales()
            if was_posted:
                self.refresh_stock()
                self.refresh_cash()
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

    def import_sales_from_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Файл замовлень",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Усі файли", "*.*")],
            initialdir=str(self.default_workdir()),
        )
        if not file_path:
            return

        try:
            raw_rows, headers = parse_sales_file(Path(file_path), encoding=self.settings.get("files", "encoding") or "utf-8")
        except Exception as exc:
            logging.exception("Не вдалося прочитати файл імпорту")
            show_error(
                "Імпорт продажів",
                "Не вдалося прочитати файл. Перевірте формат, кодування та структуру даних.\n" + str(exc),
            )
            return

        if not raw_rows:
            messagebox.showinfo("Імпорт продажів", "У файлі не знайдено рядків із товарами.")
            return

        warehouses = db.list_warehouses(active_only=True)
        if not warehouses:
            show_error("Імпорт продажів", "Спочатку створіть хоча б один склад.")
            return
        channels = db.list_channels(active_only=False)

        dialog = SalesImportDialog(self, raw_rows, headers, warehouses, channels, self.settings)
        result = dialog.result
        if not result:
            return

        try:
            summary = self._process_sales_import(result["orders"], result["options"])
        except Exception:
            logging.exception("Помилка під час імпорту продажів")
            show_error("Імпорт продажів", "Імпорт перервано помилкою. Деталі у логах.")
            return

        messagebox.showinfo("Імпорт продажів", summary)
        self.refresh_sales()
        self.refresh_cash()
        self.refresh_stock()

    def _process_sales_import(self, orders: list[dict], options: dict) -> str:
        warehouse_id = options["warehouse_id"]
        channel_override = options.get("channel", "")
        mode = options.get("mode", "draft")
        allow_negative = bool(options.get("allow_negative"))
        create_products = bool(options.get("create_products", True))
        create_customers = bool(options.get("create_customers"))
        use_file_channel = bool(options.get("use_file_channel"))

        product_rows = db.list_products()
        products_by_sku = {p["sku"].lower(): dict(p) for p in product_rows if p["sku"]}
        products_by_name = {p["name"].lower(): dict(p) for p in product_rows if p["name"]}
        products_by_supplier_sku = {p["supplier_sku"].lower(): dict(p) for p in product_rows if p.get("supplier_sku")}
        counterparties = db.list_counterparties()
        allowed_customer_types = {"customer", "both", "other"}
        customers_by_name = {
            c["name"].lower(): c for c in counterparties if c["type"] in allowed_customer_types and c["name"]
        }

        default_brand = self.settings.get("defaults", "product", "brand") or "Імпорт"
        default_category = self.settings.get("defaults", "product", "category") or "Імпорт"
        default_unit = (self.settings.get("defaults", "product", "unit") or "pcs").strip() or "pcs"
        brand_id, category_id = db.ensure_import_defaults(default_brand, default_category)
        stock_map = db.stock_on_hand(warehouse_id)

        created_products = 0
        created_customers = 0
        skipped_lines = 0
        posted_docs = 0
        draft_docs = 0
        total_docs = 0

        grouped: dict[str, list[dict]] = defaultdict(list)
        for idx, row in enumerate(orders):
            key = row.get("order_no") or f"#{idx+1}"
            grouped[key].append(row)

        for order_no, lines in grouped.items():
            doc_date = lines[0].get("doc_date") or datetime.now().strftime("%Y-%m-%d")
            customer_name = lines[0].get("customer", "").strip()
            phone = lines[0].get("phone", "").strip()
            email = lines[0].get("email", "").strip()
            customer_id = None

            if customer_name:
                existing = customers_by_name.get(customer_name.lower()) or db.find_counterparty_by_name(
                    customer_name, allowed_customer_types
                )
                if existing:
                    customer_id = existing["id"]
                    customers_by_name[customer_name.lower()] = dict(existing)
                elif create_customers:
                    customer_id = db.add_counterparty(customer_name, "customer", phone, email, "", "Імпортований клієнт")
                    new_cp = {
                        "id": customer_id,
                        "name": customer_name,
                        "type": "customer",
                        "phone": phone,
                        "email": email,
                        "address": "",
                        "note": "Імпортований клієнт",
                    }
                    counterparties.append(new_cp)
                    customers_by_name[customer_name.lower()] = new_cp
                    created_customers += 1

            sale_lines: list[tuple[int, float, float]] = []
            comment = lines[0].get("comment", "").strip()
            line_channel = lines[0].get("channel", "").strip()
            channel_value = line_channel if (use_file_channel and line_channel) else channel_override

            for row in lines:
                sku = (row.get("sku") or "").strip()
                supplier_sku = (row.get("supplier_sku") or "").strip()
                name = (row.get("product_name") or sku or "Без назви").strip()
                qty = float(row.get("quantity") or 0)
                price = float(row.get("price") or 0)
                amount = float(row.get("amount") or 0)
                if not price and qty and amount:
                    price = amount / qty

                product_row = products_by_supplier_sku.get(supplier_sku.lower()) if supplier_sku else None
                if not product_row:
                    product_row = products_by_sku.get(sku.lower()) if sku else None
                if not product_row and name:
                    product_row = products_by_name.get(name.lower())
                if not product_row and create_products:
                    final_sku = sku or self._generate_unique_sku(name, set(products_by_sku.keys()))
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
                    }
                    products_by_sku[final_sku.lower()] = product_row
                    if supplier_sku:
                        products_by_supplier_sku[supplier_sku.lower()] = product_row
                    products_by_name[name.lower()] = product_row
                    created_products += 1

                if not product_row or qty <= 0:
                    skipped_lines += 1
                    continue

                sale_lines.append((int(product_row["id"]), qty, price, 0.0))

            if not sale_lines:
                skipped_lines += len(lines)
                continue

            total_docs += 1
            try:
                sale_id = db.create_sale(doc_date, customer_id, warehouse_id, channel_value, comment, "UAH", 1.0)
                db.replace_sale_lines(sale_id, sale_lines, 1.0, 0.0)
            except Exception as exc:
                logging.warning("Не вдалося створити продаж %s: %s", order_no, exc)
                skipped_lines += len(sale_lines)
                continue

            should_post = mode == "post"
            if mode == "in_stock":
                enough = True
                for pid, qty, _, _ in sale_lines:
                    current_qty = stock_map.get(pid, db.get_stock_quantity(pid, warehouse_id))
                    if qty > current_qty:
                        enough = False
                        break
                should_post = enough

            if should_post:
                try:
                    db.post_sale(sale_id, allow_negative=allow_negative)
                    posted_docs += 1
                    for pid, qty, _, _ in sale_lines:
                        stock_map[pid] = stock_map.get(pid, db.get_stock_quantity(pid, warehouse_id)) - qty
                except Exception as exc:
                    logging.warning("Проведення продажу #%s завершилось помилкою: %s", sale_id, exc)
                    try:
                        db.unpost_sale(sale_id)
                    except Exception:
                        logging.exception("Не вдалося скасувати проведення після помилки імпорту")
                    draft_docs += 1
            else:
                draft_docs += 1

        lines_msg = f"Пропущено рядків: {skipped_lines}" if skipped_lines else "Без пропусків"
        created_parts = []
        if created_products:
            created_parts.append(f"створено товарів: {created_products}")
        if created_customers:
            created_parts.append(f"створено клієнтів: {created_customers}")
        created_msg = ", ".join(created_parts) if created_parts else "без нових довідників"
        return (
            f"Опрацьовано документів: {total_docs}. Проведено: {posted_docs}, чернеток: {draft_docs}. "
            f"{lines_msg}; {created_msg}."
        )

    def _generate_unique_sku(self, base: str, existing: set[str]) -> str:
        clean = (base or "AUTO").upper().replace(" ", "")
        if len(clean) < 3:
            clean = f"AUTO{clean}"
        candidate = clean[:20] or "AUTO"
        idx = 1
        while candidate.lower() in existing:
            idx += 1
            candidate = f"{clean[:15]}-{idx}"
        return candidate

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
        self.stock_table = TableFrame(self.stock_frame, columns, selectmode="extended")
        self.stock_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._stock_row_meta: dict[str, dict[str, object]] = {}
        self.stock_table.register_context_menu_actions(
            [
                ("Друк етикеток…", self.print_stock_labels),
                ("Масові дії з товарами…", self.bulk_actions_from_stock),
            ]
        )

    def on_search_stock(self) -> None:
        self.refresh_stock(self.stock_search_var.get())

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
        open_products_bulk_actions_dialog(self, db.get_connection(), None, product_ids)

    def print_stock_labels(self) -> None:
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
        open_labels_print_dialog(self, items, "Кількість із залишків")

    # Export
    def create_export_tab(self) -> None:
        ttk.Label(self.export_frame, text="Експорт таблиць у CSV", font=("Segoe UI", 10, "bold")).pack(pady=10)
        tables = [
            ("Brands", "Бренди"),
            ("Categories", "Категорії"),
            ("Products", "Товари"),
            ("AdditionalProductCategories", "Додаткові категорії"),
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
    def show_about(self) -> None:
        about_window = tk.Toplevel(self)
        about_window.title("Про програму")
        about_window.resizable(False, False)
        about_window.transient(self)
        about_window.grab_set()

        frame = ttk.Frame(about_window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"{APP_NAME} v{VERSION}", font=("Segoe UI", 12, "bold")).pack(pady=(0, 8))
        ttk.Label(
            frame,
            text=(
                "Мінімалістичний офлайн-облік товарів і каси. "
                "Касовий метод, середньозважена собівартість, мультивалюта."
            ),
            wraplength=420,
            justify=tk.CENTER,
        ).pack(pady=4)

        info_frame = ttk.Frame(frame)
        info_frame.pack(pady=6, fill=tk.X)
        ttk.Label(info_frame, text="Шлях до БД:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        ttk.Label(info_frame, text=str(get_db_path()), wraplength=340, justify=tk.LEFT).grid(
            row=0, column=1, sticky=tk.W
        )
        ttk.Label(info_frame, text="Тека даних:").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=(4, 0))
        ttk.Label(info_frame, text=str(get_data_dir()), wraplength=340, justify=tk.LEFT).grid(
            row=1, column=1, sticky=tk.W, pady=(4, 0)
        )

        actions = ttk.Frame(frame)
        actions.pack(pady=(10, 0))
        ttk.Button(actions, text="Документація/FAQ", command=self.open_docs).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Відкрити папку даних", command=lambda: open_data_folder(get_data_dir())).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(actions, text="Закрити", command=about_window.destroy).pack(side=tk.LEFT, padx=4)

    # Refresh helpers
    def refresh_brands(self) -> None:
        rows = db.list_brands()
        self.brand_table.set_rows([{"id": r["id"], "name": r["name"]} for r in rows])

    def refresh_categories(self) -> None:
        rows = db.list_categories(include_hidden=True)
        self.categories_index = {int(r["id"]): dict(r) for r in rows}
        search = getattr(self, "category_search_var", tk.StringVar(value="")).get().lower().strip()
        category_products, product_quantities = db.category_inventory_data()

        children_map: dict[Optional[int], list[dict]] = {}
        for row in rows:
            children_map.setdefault(row["parent_id"], []).append(dict(row))

        for lst in children_map.values():
            lst.sort(key=lambda c: (c.get("sort_order", 0), c.get("name", "")))

        subtree_counts: dict[int, int] = {}
        subtree_quantities: dict[int, float] = {}

        def calc_total(cid: int) -> set[int]:
            products = set(category_products.get(cid, set()))
            for child in children_map.get(cid, []):
                products |= calc_total(child["id"])
            subtree_counts[cid] = len(products)
            subtree_quantities[cid] = sum(product_quantities.get(pid, 0.0) for pid in products)
            return products

        for root in children_map.get(None, []):
            calc_total(root["id"])

        match_cache: dict[int, bool] = {}

        def has_match(cid: int) -> bool:
            if cid in match_cache:
                return match_cache[cid]
            cat = self.categories_index.get(cid, {})
            own_match = not search or search in cat.get("name", "").lower()
            child_match = any(has_match(child["id"]) for child in children_map.get(cid, []))
            match_cache[cid] = bool(own_match or child_match)
            return match_cache[cid]

        self.category_tree.delete(*self.category_tree.get_children())

        def render(parent_id: Optional[int], tree_parent: str) -> None:
            for cat in children_map.get(parent_id, []):
                if not has_match(cat["id"]):
                    continue
                flags = []
                if cat.get("is_service"):
                    flags.append("службова")
                if cat.get("is_hidden"):
                    flags.append("прихована")
                node_id = self.category_tree.insert(
                    tree_parent,
                    "end",
                    iid=str(cat["id"]),
                    text=cat["name"],
                    values=(
                        subtree_counts.get(cat["id"], len(category_products.get(cat["id"], set()))),
                        f"{subtree_quantities.get(cat['id'], 0.0):.2f}",
                        ", ".join(flags),
                    ),
                )
                render(cat["id"], node_id)

        render(None, "")
        self.update_category_filters()

    def flatten_categories(self) -> list[dict]:
        rows = db.list_categories(include_hidden=False)
        children_map: dict[Optional[int], list[dict]] = {}
        for row in rows:
            children_map.setdefault(row["parent_id"], []).append(dict(row))
        for lst in children_map.values():
            lst.sort(key=lambda c: (c.get("sort_order", 0), c.get("name", "")))

        result: list[dict] = []

        def walk(parent_id: Optional[int], depth: int) -> None:
            for cat in children_map.get(parent_id, []):
                label = "  " * depth + ("• " if depth else "") + cat.get("name", "")
                result.append({"id": cat["id"], "label": label, "name": cat.get("name", "")})
                walk(cat["id"], depth + 1)

        walk(None, 0)
        return result

    def update_category_filters(self) -> None:
        options = self.flatten_categories()
        if hasattr(self, "products_tab"):
            self.products_tab.set_category_filter_options(options)

    def refresh_products(self, search: str | None = None) -> None:
        if hasattr(self, "products_tab"):
            self.products_tab.refresh_products(search)

    def refresh_counterparties(self) -> None:
        rows = db.list_counterparties()
        type_labels = {
            "supplier": "Постачальник",
            "customer": "Покупець",
            "both": "Постачальник/Покупець",
            "other": "Інший",
        }

        suppliers: list[dict] = []
        customers: list[dict] = []
        all_rows: list[dict] = []

        for r in rows:
            mapped = {
                "id": r["id"],
                "name": r["name"],
                "type": type_labels.get(r["type"], r["type"]),
                "phone": r["phone"] or "",
                "email": r["email"] or "",
                "address": r["address"] or "",
                "note": r["note"] or "",
            }
            all_rows.append(mapped)
            if r["type"] in ("supplier", "both"):
                suppliers.append(mapped)
            if r["type"] in ("customer", "both"):
                customers.append(mapped)

        self.counterparty_tables["suppliers"].set_rows(suppliers)
        self.counterparty_tables["customers"].set_rows(customers)
        self.counterparty_tables["all"].set_rows(all_rows)

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
        self.refresh_extra_costs()
        self.refresh_sales()
        self.refresh_inventory_documents()
        self.refresh_cash()
        self.refresh_stock()
        self.reports_tab.refresh_all()


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
        wh_combo = ttk.Combobox(parent, textvariable=self.wh_var, values=[w["name"] for w in self.warehouses], state="readonly")
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
        ttk.Label(parent, text="Попередній перегляд (перші 30 рядків):").grid(row=12, column=0, columnspan=3, sticky="w", pady=6)
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


class SalesImportDialog(tk.Toplevel):
    def __init__(self, app: tk.Tk, raw_rows: list[dict[str, object]], headers: list[str], warehouses, channels, settings) -> None:
        super().__init__(app)
        self.title("Імпорт продажів")
        self.resizable(True, True)
        self.grab_set()
        self.result: Optional[dict] = None
        self.raw_rows = raw_rows
        self.headers = headers
        self.warehouses = warehouses
        self.channels = channels
        self.settings = settings
        self.templates: dict[str, dict[str, str]] = settings.get("sales_import", "templates") or {}
        self.current_mapping = _suggest_sales_mapping(headers)

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
        btns.grid(row=12, column=0, columnspan=3, pady=8, sticky="e")
        ttk.Button(btns, text="Скасувати", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="Імпортувати", command=self._on_ok).pack(side=tk.RIGHT, padx=4)

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_window(self)

    def _on_ok(self) -> None:
        warehouse = next((w for w in self.warehouses if w["name"] == self.wh_var.get()), None)
        if not warehouse:
            show_error("Імпорт", "Оберіть склад")
            return

        normalized_orders = _normalize_sales_records(self.raw_rows, self.current_mapping)
        self.result = {
            "options": {
                "warehouse_id": warehouse["id"],
                "channel": self.channel_var.get().strip(),
                "mode": self.mode_var.get(),
                "allow_negative": bool(self.allow_negative_var.get()),
                "create_products": bool(self.create_products_var.get()),
                "create_customers": bool(self.create_customers_var.get()),
                "use_file_channel": bool(self.use_file_channel_var.get()),
            },
            "orders": normalized_orders,
        }
        self.settings.set(self.current_template_name.get(), "sales_import", "last_template")
        self.settings.save()
        self.destroy()

    def _build_template_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Шаблон співставлення:").grid(row=1, column=0, sticky="w", pady=4)
        self.current_template_name = tk.StringVar(value=self.settings.get("sales_import", "last_template") or "")
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
        for idx, (field_key, field_label, _aliases) in enumerate(SALES_FIELDS):
            ttk.Label(mapping_frame, text=field_label).grid(row=idx, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=self.current_mapping.get(field_key, ""))
            combo = ttk.Combobox(mapping_frame, textvariable=var, values=options, state="readonly")
            combo.grid(row=idx, column=1, sticky="ew", pady=2)
            combo.bind("<<ComboboxSelected>>", lambda _e, key=field_key, v=var: self._update_mapping(key, v.get()))
            self.mapping_vars[field_key] = var

    def _build_options(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Склад для імпорту:").grid(row=3, column=0, sticky="w", pady=4)
        self.wh_var = tk.StringVar(value=self.warehouses[0]["name"] if self.warehouses else "")
        wh_combo = ttk.Combobox(parent, textvariable=self.wh_var, values=[w["name"] for w in self.warehouses], state="readonly")
        wh_combo.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Канал (якщо не вказано у файлі):").grid(row=4, column=0, sticky="w", pady=4)
        self.channel_var = tk.StringVar()
        channel_values = [c["name"] for c in self.channels]
        ttk.Combobox(parent, textvariable=self.channel_var, values=channel_values).grid(row=4, column=1, sticky="ew", pady=4)

        self.use_file_channel_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Брати канал із файлу, якщо він є", variable=self.use_file_channel_var).grid(
            row=5, column=1, sticky="w"
        )

        ttk.Label(parent, text="Режим проведення:").grid(row=6, column=0, sticky="nw", pady=4)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=6, column=1, sticky="w", pady=4)
        self.mode_var = tk.StringVar(value="post")
        ttk.Radiobutton(mode_frame, text="Провести всі", variable=self.mode_var, value="post").pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Тільки чернетки", variable=self.mode_var, value="draft").pack(anchor="w")
        ttk.Radiobutton(
            mode_frame, text="Проводити, лише якщо є залишок", variable=self.mode_var, value="in_stock"
        ).pack(anchor="w")

        self.allow_negative_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent,
            text="Дозволити від'ємний залишок під час проведення",
            variable=self.allow_negative_var,
        ).grid(row=7, column=1, sticky="w")

        self.create_products_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Створювати відсутні товари", variable=self.create_products_var).grid(
            row=8, column=1, sticky="w", pady=(4, 0)
        )
        self.create_customers_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Створювати відсутніх клієнтів", variable=self.create_customers_var).grid(
            row=9, column=1, sticky="w"
        )

    def _build_preview(self, parent: ttk.Frame) -> ttk.Treeview:
        ttk.Label(parent, text="Попередній перегляд (перші 30 рядків):").grid(row=10, column=0, columnspan=3, sticky="w", pady=6)
        preview = ttk.Treeview(
            parent,
            columns=("order", "date", "customer", "sku", "name", "qty", "price"),
            show="headings",
            height=10,
        )
        headings = {
            "order": ("Замовлення", 120),
            "date": ("Дата", 90),
            "customer": ("Клієнт", 160),
            "sku": ("SKU", 90),
            "name": ("Товар", 200),
            "qty": ("К-сть", 70),
            "price": ("Ціна", 90),
        }
        for col, (title, width) in headings.items():
            preview.heading(col, text=title)
            preview.column(col, width=width, anchor="w")
        preview.grid(row=11, column=0, columnspan=3, sticky="nsew")
        parent.grid_rowconfigure(11, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=preview.yview)
        preview.configure(yscrollcommand=scroll.set)
        scroll.grid(row=11, column=3, sticky="ns")
        return preview

    def _refresh_preview(self) -> None:
        self.preview.delete(*self.preview.get_children())
        normalized = _normalize_sales_records(self.raw_rows, self.current_mapping)
        for row in normalized[:30]:
            self.preview.insert(
                "",
                "end",
                values=(
                    row.get("order_no") or "-",
                    row.get("doc_date"),
                    row.get("customer"),
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
        self.settings.set(self.templates, "sales_import", "templates")
        self.settings.set(name, "sales_import", "last_template")
        self.settings.save()
        self.current_template_name.set(name)
        self.template_combo.configure(values=list(self.templates.keys()))


def open_labels_print_dialog(parent, items: list[dict], mode_title: str) -> None:
    if not items:
        messagebox.showwarning("Етикетки", "Немає позицій для друку.")
        return

    dlg = tk.Toplevel(parent)
    dlg.title("Друк етикеток")
    dlg.grab_set()
    dlg.resizable(False, False)

    ttk.Label(dlg, text=mode_title, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, padx=8, pady=(8, 4), sticky="w")

    template_frame = ttk.LabelFrame(dlg, text="Шаблон")
    template_frame.grid(row=1, column=0, columnspan=3, padx=8, pady=4, sticky="ew")
    ttk.Label(template_frame, text="Шаблон:").pack(side=tk.LEFT, padx=4, pady=4)
    template_display_var = tk.StringVar()
    template_combo = ttk.Combobox(template_frame, textvariable=template_display_var, state="readonly", width=26)
    template_combo.pack(side=tk.LEFT, padx=4, pady=4)
    template_map: dict[str, int] = {}
    templates_cache: dict[int, dict] = {}

    start_row_var = tk.StringVar(value="1")
    start_col_var = tk.StringVar(value="1")
    start_frame = ttk.Frame(template_frame)
    start_row_label = ttk.Label(start_frame, text="Ряд:")
    start_row_spin = ttk.Spinbox(start_frame, from_=1, to=1, textvariable=start_row_var, width=4)
    start_col_label = ttk.Label(start_frame, text="Кол:")
    start_col_spin = ttk.Spinbox(start_frame, from_=1, to=1, textvariable=start_col_var, width=4)

    def refresh_template_choices(selected_id: int | None = None) -> None:
        nonlocal templates_cache
        template_map.clear()
        templates_cache = {}
        try:
            templates = db.list_label_templates(active_only=True)
        except Exception:
            logging.exception("Failed to load label templates")
            show_error("Етикетки", "Не вдалося завантажити шаблони")
            return
        display_values: list[str] = []
        default_display: str | None = None
        last_selected_id = None
        try:
            last_selected_id = int(parent.settings.get("print", "last_template_id") or 0)
        except Exception:
            last_selected_id = None
        for row in templates:
            tpl = dict(row)
            display = f"{tpl['title']} [{tpl['code']}]"
            display_values.append(display)
            tid = int(tpl["id"])
            template_map[display] = tid
            templates_cache[tid] = tpl
            if int(tpl.get("is_default") or 0) == 1:
                default_display = display
        template_combo.configure(values=display_values)
        target_id = selected_id or last_selected_id
        if target_id and target_id in template_map.values():
            for disp, tid in template_map.items():
                if tid == target_id:
                    template_display_var.set(disp)
                    break
        elif default_display:
            template_display_var.set(default_display)
        elif display_values:
            template_display_var.set(display_values[0])
        update_start_controls()

    def update_start_controls(*_args) -> None:
        display = template_display_var.get()
        tpl_id = template_map.get(display)
        tpl_row = templates_cache.get(tpl_id or -1)
        is_sheet = tpl_row and (tpl_row.get("kind") == "sheet")
        for widget in [start_row_label, start_row_spin, start_col_label, start_col_spin, start_frame]:
            widget.pack_forget()
        if is_sheet:
            rows = max(int(tpl_row.get("rows", 1)), 1)
            cols = max(int(tpl_row.get("cols", 1)), 1)
            start_row_spin.configure(to=rows)
            start_col_spin.configure(to=cols)
            start_row_label.pack(side=tk.LEFT, padx=2)
            start_row_spin.pack(side=tk.LEFT, padx=2)
            start_col_label.pack(side=tk.LEFT, padx=2)
            start_col_spin.pack(side=tk.LEFT, padx=2)
            start_frame.pack(side=tk.LEFT, padx=4, pady=4)
        else:
            start_row_var.set("1")
            start_col_var.set("1")

    template_combo.bind("<<ComboboxSelected>>", update_start_controls)

    def open_template_manager() -> None:
        dlg_manager = TemplateManagerDialog(parent, settings=getattr(parent, "settings", None))
        parent.wait_window(dlg_manager.root)
        refresh_template_choices()

    ttk.Button(template_frame, text="Шаблони…", command=open_template_manager).pack(side=tk.LEFT, padx=4, pady=4)

    qty_frame = ttk.LabelFrame(dlg, text="Кількість етикеток")
    qty_frame.grid(row=2, column=0, columnspan=3, padx=8, pady=4, sticky="ew")
    ttk.Label(qty_frame, text="Округлення:").pack(side=tk.LEFT, padx=4, pady=4)
    rounding_var = tk.StringVar(value="round")
    rounding_combo = ttk.Combobox(qty_frame, textvariable=rounding_var, state="readonly", values=["round", "floor", "ceil", "skip"], width=8)
    rounding_combo.pack(side=tk.LEFT, padx=4, pady=4)

    ttk.Label(qty_frame, text="Множник:").pack(side=tk.LEFT, padx=4, pady=4)
    multiplier_var = tk.StringVar(value="1")
    ttk.Spinbox(qty_frame, from_=1, to=999, textvariable=multiplier_var, width=5).pack(side=tk.LEFT, padx=4, pady=4)

    include_aliases_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        qty_frame,
        text="Друкувати також додаткові штрихкоди (аліаси)",
        variable=include_aliases_var,
    ).pack(side=tk.LEFT, padx=4, pady=4)

    info_var = tk.StringVar(value="")
    info_label = ttk.Label(dlg, textvariable=info_var)
    info_label.grid(row=3, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="w")

    def _apply_rounding(qty_value: float, mode: str) -> int | None:
        if mode == "floor":
            return math.floor(qty_value)
        if mode == "ceil":
            return math.ceil(qty_value)
        if mode == "skip":
            if math.isclose(qty_value, round(qty_value)):
                return int(round(qty_value))
            return None
        return int(round(qty_value))

    def compute_summary() -> tuple[int, int, int]:
        try:
            multiplier = max(1, min(999, int(multiplier_var.get())))
        except ValueError:
            multiplier = 1
        rounding_mode = rounding_var.get()
        positions = 0
        labels_count = 0
        skipped = 0
        for item in items:
            qty_value = float(item.get("qty", 0) or 0)
            qty_int = _apply_rounding(qty_value, rounding_mode)
            if qty_int is None:
                skipped += 1
                continue
            if qty_int <= 0:
                continue
            positions += 1
            labels_count += qty_int * multiplier
        return positions, labels_count, skipped

    def update_summary(*_args) -> None:
        positions, labels_count, skipped = compute_summary()
        text = f"Позицій: {positions} | Етикеток (SKU): {labels_count}"
        if include_aliases_var.get():
            text += " + аліаси"
        if rounding_var.get() == "skip" and skipped:
            text += f" | Пропущено дробових: {skipped}"
        info_var.set(text)

    rounding_combo.bind("<<ComboboxSelected>>", update_summary)
    multiplier_var.trace_add("write", update_summary)
    include_aliases_var.trace_add("write", update_summary)

    refresh_template_choices()
    update_summary()

    def generate_labels() -> None:
        try:
            multiplier = int(multiplier_var.get())
        except ValueError:
            show_error("Етикетки", "Множник має бути числом")
            return
        if multiplier < 1:
            show_error("Етикетки", "Множник має бути не менше 1")
            return
        rounding_mode = rounding_var.get()

        tpl_display = template_display_var.get()
        tpl_id = template_map.get(tpl_display)
        if not tpl_id:
            show_error("Етикетки", "Оберіть шаблон")
            return
        template_full = db.get_label_template_full(tpl_id)
        if not template_full:
            show_error("Етикетки", "Шаблон не знайдено")
            return

        positions, labels_count, skipped = compute_summary()
        if labels_count <= 0:
            messagebox.showwarning("Етикетки", "Немає позицій з кількістю > 0.")
            return
        if rounding_mode == "skip" and skipped:
            messagebox.showinfo("Етикетки", f"Пропущено позицій через дробову кількість: {skipped}")

        file_path = filedialog.asksaveasfilename(
            title="Файл PDF з етикетками",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("Усі файли", "*.*")],
            initialdir=str(parent.default_workdir()),
        )
        if not file_path:
            return

        try:
            start_row = max(1, int(start_row_var.get() or 1))
            start_col = max(1, int(start_col_var.get() or 1))
        except ValueError:
            start_row = start_col = 1
        include_aliases = bool(include_aliases_var.get())
        product_ids = []
        for item in items:
            try:
                pid = int(item.get("product_id"))
            except (TypeError, ValueError):
                continue
            if pid not in product_ids:
                product_ids.append(pid)

        alias_map: dict[int, list[str]] = defaultdict(list)
        if include_aliases and product_ids:
            try:
                placeholders = ",".join("?" * len(product_ids))
                with db.get_connection() as conn:
                    for alias_row in conn.execute(
                        f"SELECT product_id, code FROM ProductBarcodes WHERE product_id IN ({placeholders})",
                        tuple(product_ids),
                    ).fetchall():
                        alias_map[int(alias_row["product_id"])].append(alias_row["code"])
            except Exception:
                logging.exception("Failed to load aliases for labels")

        def build_expanded_items() -> list[dict]:
            expanded: list[dict] = []
            for item in items:
                try:
                    pid = int(item.get("product_id"))
                except (TypeError, ValueError):
                    continue
                qty_value = float(item.get("qty", 0) or 0)
                qty_int = _apply_rounding(qty_value, rounding_mode)
                if qty_int is None or qty_int <= 0:
                    continue
                total_qty = qty_int * multiplier
                if total_qty <= 0:
                    continue
                entry = {
                    "product_id": pid,
                    "sku": item.get("sku") or "",
                    "name": item.get("name") or "",
                    "aliases": alias_map.get(pid, []),
                }
                expanded.extend([entry] * total_qty)
            return expanded

        expanded_items = build_expanded_items()
        if not expanded_items:
            messagebox.showwarning("Етикетки", "Немає позицій для друку після округлення.")
            return

        try:
            prefix = _sanitize_barcode_prefix(parent.settings.get("defaults", "product", "barcode_prefix") or "")
        except Exception:
            prefix = ""

        try:
            labels.generate_product_labels_pdf_v2(
                Path(file_path),
                expanded_items,
                barcode_prefix=prefix,
                qty_each=1,
                template_full=template_full,
                include_aliases=include_aliases,
                start_row=start_row,
                start_col=start_col,
            )
            try:
                parent.settings.set(tpl_id, "print", "last_template_id")
                parent.settings.save()
            except Exception:
                logging.exception("Failed to save template selection")
            open_file(Path(file_path))
        except Exception:
            logging.exception("Labels generation error (doc/stock)")
            show_error("Етикетки", "Не вдалося згенерувати етикетки")

    ttk.Button(dlg, text="Згенерувати PDF...", command=generate_labels).grid(row=4, column=0, padx=8, pady=8, sticky="w")
    ttk.Button(dlg, text="Закрити", command=dlg.destroy).grid(row=4, column=2, padx=8, pady=8, sticky="e")
    dlg.columnconfigure(1, weight=1)
    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

def select_category_dialog(title: str, options: list[tuple[Optional[int], str]]):
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.grab_set()

    ttk.Label(dlg, text="Категорія").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    values = [opt[1] for opt in options]
    combo_var = tk.StringVar()
    combo = ttk.Combobox(dlg, textvariable=combo_var, state="readonly", values=values)
    combo.grid(row=0, column=1, padx=6, pady=4)
    combo.current(0 if values else -1)

    result: Optional[int] = None

    def on_ok():
        nonlocal result
        if not values:
            result = None
        else:
            idx = combo.current()
            result = options[idx][0]
        dlg.destroy()

    ttk.Button(dlg, text="OK", command=on_ok).grid(row=1, column=0, padx=6, pady=8)
    ttk.Button(dlg, text="Скасувати", command=dlg.destroy).grid(row=1, column=1, padx=6, pady=8)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.wait_window()
    return result


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








def main() -> None:
    log_path = setup_logging(APP_NAME)

    def _sys_hook(exc, val, tb):
        logging.critical("Unhandled exception", exc_info=(exc, val, tb))

    sys.excepthook = _sys_hook
    logging.info("Starting %s", APP_NAME)
    try:
        with SingleInstance(get_lock_path()):
            settings = Settings()
            apply_base_currency_settings(settings)
            db.init_db()
            app = InventoryApp(settings)
            install_tk_exception_handler(app, log_path)
            app.mainloop()
    except RuntimeError:
        messagebox.showwarning(APP_NAME, "Програма вже запущена.")
    except ValueError as exc:
        messagebox.showerror(APP_NAME, str(exc))
    except Exception:
        logging.exception("Fatal error")
        try:
            messagebox.showerror(APP_NAME, f"Критична помилка. Деталі у логах: {log_path}")
        except tk.TclError:
            print("Критична помилка. Деталі у логах:", log_path, file=sys.stderr)
        traceback.print_exc()


if __name__ == "__main__":
    main()
