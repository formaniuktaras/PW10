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
from openpyxl import load_workbook

import db
from utils import (
    APP_NAME,
    VERSION,
    SingleInstance,
    backup_all_data,
    BASE_CURRENCY,
    configure_logging,
    get_data_dir,
    get_db_path,
    get_lock_path,
    get_log_path,
    Settings,
    open_data_folder,
    restore_all_data,
    show_error,
    backup_database,
    bind_common_shortcuts,
)
from ui_components import TableFrame, simple_prompt


class InventoryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x720")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.settings = Settings()
        self.status_var = tk.StringVar(value="Готово")
        self.status_bar: ttk.Label | None = None
        bind_common_shortcuts(self)
        self.create_menu()
        self.apply_settings()

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
        self.extra_costs_frame = ttk.Frame(notebook)
        self.sales_frame = ttk.Frame(notebook)
        self.cash_frame = ttk.Frame(notebook)
        self.stock_frame = ttk.Frame(notebook)
        self.reports_frame = ttk.Frame(notebook)
        self.export_frame = ttk.Frame(notebook)

        notebook.add(self.brands_frame, text="Бренди")
        notebook.add(self.categories_frame, text="Категорії")
        notebook.add(self.products_frame, text="Товари")
        notebook.add(self.counterparties_frame, text="Контрагенти")
        notebook.add(self.warehouses_frame, text="Склади")
        notebook.add(self.channels_frame, text="Канали продажу")
        notebook.add(self.currencies_frame, text="Валюти")
        notebook.add(self.purchases_frame, text="Закупівлі")
        notebook.add(self.extra_costs_frame, text="Супутні витрати")
        notebook.add(self.sales_frame, text="Продажі")
        notebook.add(self.cash_frame, text="Каса")
        notebook.add(self.stock_frame, text="Залишки")
        notebook.add(self.reports_frame, text="Звіти")
        notebook.add(self.export_frame, text="Експорт")

        self.create_brands_tab()
        self.create_categories_tab()
        self.create_products_tab()
        self.create_counterparties_tab()
        self.create_warehouses_tab()
        self.create_channels_tab()
        self.create_currencies_tab()
        self.create_purchases_tab()
        self.create_extra_costs_tab()
        self.create_sales_tab()
        self.create_cash_tab()
        self.create_stock_tab()
        self.create_reports_tab()
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
        SettingsDialog(self, section)

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
        initialdir = self.default_workdir()
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
            initialdir=self.default_workdir(),
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

    # Products
    def create_products_tab(self) -> None:
        top = ttk.Frame(self.products_frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук:").pack(side=tk.LEFT)
        self.product_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.product_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Категорія:").pack(side=tk.LEFT, padx=6)
        self.product_category_filter_var = tk.StringVar()
        self.product_category_filter_combo = ttk.Combobox(
            top, textvariable=self.product_category_filter_var, state="readonly", width=30
        )
        self.product_category_filter_combo.pack(side=tk.LEFT)
        self.include_subcategories_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Включно з підкатегоріями", variable=self.include_subcategories_var).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(top, text="Оновити", command=self.on_search_products).pack(side=tk.LEFT, padx=6)

        columns = [
            ("sku", "SKU", 120),
            ("name", "Назва", 230),
            ("brand", "Бренд", 140),
            ("category", "Категорія", 140),
            ("extra_categories", "Додаткові категорії", 200),
            ("unit", "Одиниця", 90),
            ("is_active", "Активний", 90),
        ]
        self.product_table = TableFrame(self.products_frame, columns)
        self.product_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.product_table.on_double_click(self.edit_product)
        self.product_table.register_context_menu(self.edit_product, self.delete_product)

        btns = ttk.Frame(self.products_frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_product).pack(side=tk.LEFT, padx=4)

    def on_search_products(self) -> None:
        category_id = None
        try:
            selection = self.product_category_combo.current()
            if selection is not None and selection > 0:
                category_id = self.category_choices[selection]["id"]
        except (AttributeError, IndexError):
            category_id = None
        self.refresh_products(
            self.product_search_var.get(),
            category_id=category_id,
            include_subtree=bool(self.include_subcategories_var.get()),
        )

    def add_product(self) -> None:
        brands = db.list_brands()
        categories = self.flatten_categories()
        values = product_prompt(brands, categories, "Новий товар")
        if not values:
            return
        sku, name, brand_id, category_id, unit, is_active, extras = values
        try:
            product_id = db.add_product(sku, name, brand_id, category_id, unit, is_active)
            db.set_product_categories(product_id, category_id, extras)
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
        product = db.get_product(product_id)
        if not product:
            return
        brands = db.list_brands()
        categories = self.flatten_categories()
        values = product_prompt(
            brands,
            categories,
            "Редагувати товар",
            (
                product["sku"],
                product["name"],
                product["brand_id"],
                product["category_id"],
                product["unit"],
                bool(product["is_active"]),
                db.get_product_additional_categories(product_id),
            ),
        )
        if not values:
            return
        sku, name, brand_id, category_id, unit, is_active, extras = values
        try:
            db.update_product(product_id, sku, name, brand_id, category_id, unit, is_active)
            db.set_product_categories(product_id, category_id, extras)
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
        self.counterparty_table.on_double_click(self.edit_counterparty)
        self.counterparty_table.register_context_menu(self.edit_counterparty, self.delete_counterparty)

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
            ("total_extra", "Супутні (база)", 120),
            ("comment", "Коментар", 240),
        ]
        self.purchase_table = TableFrame(self.purchases_frame, columns)
        self.purchase_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.purchase_table.on_double_click(self.edit_purchase)
        self.purchase_table.register_context_menu(self.edit_purchase, self.delete_purchase)

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
                if status and status[0] == "posted":
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
                status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (doc_id,)).fetchone()
                if status and status[0] == "posted":
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

    def import_sales_from_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Файл замовлень",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Усі файли", "*.*")],
            initialdir=self.default_workdir(),
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
        create_products = bool(options.get("create_products"))
        create_customers = bool(options.get("create_customers"))
        use_file_channel = bool(options.get("use_file_channel"))

        product_rows = db.list_products()
        products_by_sku = {p["sku"].lower(): dict(p) for p in product_rows if p["sku"]}
        products_by_name = {p["name"].lower(): dict(p) for p in product_rows if p["name"]}
        counterparties = db.list_counterparties()
        allowed_customer_types = {"customer", "both", "other"}
        customers_by_name = {
            c["name"].lower(): c for c in counterparties if c["type"] in allowed_customer_types and c["name"]
        }

        brand_id, category_id = db.ensure_import_defaults()
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
                name = (row.get("product_name") or sku or "Без назви").strip()
                qty = float(row.get("quantity") or 0)
                price = float(row.get("price") or 0)
                amount = float(row.get("amount") or 0)
                if not price and qty and amount:
                    price = amount / qty

                product_row = products_by_sku.get(sku.lower()) if sku else None
                if not product_row and name:
                    product_row = products_by_name.get(name.lower())
                if not product_row and create_products:
                    final_sku = sku or self._generate_unique_sku(name, set(products_by_sku.keys()))
                    product_id = db.add_product(final_sku, name, brand_id, category_id)
                    product_row = {
                        "id": product_id,
                        "sku": final_sku,
                        "name": name,
                    }
                    products_by_sku[final_sku.lower()] = product_row
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
        notebook = ttk.Notebook(self.reports_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Dashboard
        dashboard_tab = ttk.Frame(notebook)
        notebook.add(dashboard_tab, text="Дашборд")
        dash_filters = ttk.Frame(dashboard_tab)
        dash_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(dash_filters, text="Дата з:").pack(side=tk.LEFT)
        self.dashboard_from_var = tk.StringVar()
        ttk.Entry(dash_filters, textvariable=self.dashboard_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(dash_filters, text="по:").pack(side=tk.LEFT)
        self.dashboard_to_var = tk.StringVar()
        ttk.Entry(dash_filters, textvariable=self.dashboard_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(dash_filters, text="Оновити", command=self.refresh_dashboard).pack(side=tk.LEFT, padx=6)
        dash_columns = [("name", "Показник", 260), ("value", "Значення", 200), ("extra", "Примітка", 200)]
        self.dashboard_table = TableFrame(dashboard_tab, dash_columns)
        self.dashboard_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Sales analysis
        sales_tab = ttk.Frame(notebook)
        notebook.add(sales_tab, text="Продажі")
        sales_filters = ttk.Frame(sales_tab)
        sales_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(sales_filters, text="Дата з:").pack(side=tk.LEFT)
        self.sales_from_var = tk.StringVar()
        ttk.Entry(sales_filters, textvariable=self.sales_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(sales_filters, text="по:").pack(side=tk.LEFT)
        self.sales_to_var = tk.StringVar()
        ttk.Entry(sales_filters, textvariable=self.sales_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(sales_filters, text="Оновити", command=self.refresh_sales_analysis).pack(side=tk.LEFT, padx=6)
        sales_tables = ttk.Frame(sales_tab)
        sales_tables.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        channel_columns = [
            ("name", "Канал", 180),
            ("revenue", "Дохід", 140),
            ("gross_profit", "Валовий прибуток", 160),
            ("qty", "К-сть", 100),
        ]
        category_columns = [
            ("name", "Категорія", 200),
            ("revenue", "Дохід", 140),
            ("gross_profit", "Валовий прибуток", 160),
            ("qty", "К-сть", 100),
        ]
        ttk.Label(sales_tables, text="По каналах", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.sales_channels_table = TableFrame(sales_tables, channel_columns)
        self.sales_channels_table.pack(fill=tk.BOTH, expand=True, pady=4)
        ttk.Label(sales_tables, text="По категоріях", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.sales_categories_table = TableFrame(sales_tables, category_columns)
        self.sales_categories_table.pack(fill=tk.BOTH, expand=True, pady=4)

        # ABC/XYZ
        abc_tab = ttk.Frame(notebook)
        notebook.add(abc_tab, text="ABC/XYZ")
        abc_filters = ttk.Frame(abc_tab)
        abc_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(abc_filters, text="Дата з:").pack(side=tk.LEFT)
        self.abc_from_var = tk.StringVar()
        ttk.Entry(abc_filters, textvariable=self.abc_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(abc_filters, text="по:").pack(side=tk.LEFT)
        self.abc_to_var = tk.StringVar()
        ttk.Entry(abc_filters, textvariable=self.abc_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(abc_filters, text="Оновити", command=self.refresh_abc_xyz).pack(side=tk.LEFT, padx=6)
        abc_columns = [
            ("name", "Товар", 220),
            ("sku", "SKU", 100),
            ("category", "Категорія", 160),
            ("revenue", "Дохід", 120),
            ("abc", "ABC", 60),
            ("xyz", "XYZ", 60),
        ]
        self.abc_table = TableFrame(abc_tab, abc_columns)
        self.abc_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Cash flow
        cash_tab = ttk.Frame(notebook)
        notebook.add(cash_tab, text="Каса")
        cash_filters = ttk.Frame(cash_tab)
        cash_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(cash_filters, text="Дата з:").pack(side=tk.LEFT)
        self.cash_from_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="по:").pack(side=tk.LEFT)
        self.cash_to_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="Тип:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_type_var = tk.StringVar()
        self.cash_type_combo = ttk.Combobox(
            cash_filters,
            textvariable=self.cash_type_var,
            values=["", "sale_payment", "purchase_payment", "income", "expense", "transfer"],
            width=15,
        )
        self.cash_type_combo.pack(side=tk.LEFT)
        ttk.Label(cash_filters, text="Канал:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_channel_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_channel_var, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="Контрагент:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_counterparty_var = tk.StringVar()
        self.cash_counterparty_combo = ttk.Combobox(cash_filters, textvariable=self.cash_counterparty_var, width=25)
        self.cash_counterparty_combo.pack(side=tk.LEFT)
        ttk.Button(cash_filters, text="Показати", command=self.refresh_cash_flow_report).pack(side=tk.LEFT, padx=6)
        cash_columns = [
            ("date", "Дата", 90),
            ("type", "Тип", 140),
            ("amount", "Сума", 100),
            ("counterparty", "Контрагент", 180),
            ("channel", "Канал", 120),
            ("comment", "Коментар", 200),
        ]
        self.cash_report_table = TableFrame(cash_tab, cash_columns)
        self.cash_report_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.refresh_dashboard()
        self.refresh_sales_analysis()
        self.refresh_abc_xyz()
        self.refresh_cash_counterparties()
        self.refresh_cash_flow_report()

    def refresh_dashboard(self) -> None:
        metrics = db.dashboard_metrics(
            self.dashboard_from_var.get().strip() or None, self.dashboard_to_var.get().strip() or None
        )
        self.dashboard_table.set_rows(
            [
                {"id": 1, "name": "Оборот", "value": f"{metrics['turnover']:.2f}", "extra": "оплачені продажі"},
                {
                    "id": 2,
                    "name": "Валовий прибуток",
                    "value": f"{metrics['gross_profit']:.2f}",
                    "extra": "дохід мінус собівартість та витрати продажів",
                },
                {"id": 3, "name": "Маржа", "value": f"{metrics['margin_pct']:.2f}%", "extra": ""},
                {"id": 4, "name": "Вартість залишків", "value": f"{metrics['stock_value']:.2f}", "extra": "на зараз"},
            ]
        )

    def refresh_sales_analysis(self) -> None:
        analysis = db.sales_analysis(self.sales_from_var.get().strip() or None, self.sales_to_var.get().strip() or None)
        self.sales_channels_table.set_rows(
            [
                {
                    "id": idx,
                    "name": r["name"],
                    "revenue": f"{r['revenue']:.2f}",
                    "gross_profit": f"{r['gross_profit']:.2f}",
                    "qty": f"{r['qty']:.2f}",
                }
                for idx, r in enumerate(analysis["channels"], 1)
            ]
        )
        self.sales_categories_table.set_rows(
            [
                {
                    "id": idx,
                    "name": r["name"],
                    "revenue": f"{r['revenue']:.2f}",
                    "gross_profit": f"{r['gross_profit']:.2f}",
                    "qty": f"{r['qty']:.2f}",
                }
                for idx, r in enumerate(analysis["categories"], 1)
            ]
        )

    def refresh_abc_xyz(self) -> None:
        rows = db.abc_xyz_report(self.abc_from_var.get().strip() or None, self.abc_to_var.get().strip() or None)
        self.abc_table.set_rows(
            [
                {
                    "id": r["product_id"],
                    "name": r["name"],
                    "sku": r["sku"],
                    "category": r["category"],
                    "revenue": f"{r['revenue']:.2f}",
                    "abc": r["abc"],
                    "xyz": r["xyz"],
                }
                for r in rows
            ]
        )

    def refresh_cash_counterparties(self) -> None:
        counterparts = db.list_counterparties()
        names = ["Усі"] + [c["name"] for c in counterparts]
        self.cash_counterparty_combo["values"] = names
        if not self.cash_counterparty_var.get():
            self.cash_counterparty_combo.current(0) if names else None

    def refresh_cash_flow_report(self) -> None:
        cp_name = self.cash_counterparty_var.get().strip()
        cp_id = None
        if cp_name and cp_name != "Усі":
            for c in db.list_counterparties():
                if c["name"] == cp_name:
                    cp_id = c["id"]
                    break
        rows = db.cash_flow_detailed(
            self.cash_from_var.get().strip() or None,
            self.cash_to_var.get().strip() or None,
            self.cash_type_var.get().strip() or None,
            self.cash_channel_var.get().strip() or None,
            cp_id,
        )
        self.cash_report_table.set_rows(
            [
                {
                    "id": r["id"],
                    "date": r["date"],
                    "type": r["type"],
                    "amount": f"{r['amount']:.2f}",
                    "counterparty": r["counterparty"],
                    "channel": r["channel"],
                    "comment": r["comment"],
                }
                for r in rows
            ]
        )

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
            text="Облік лише за касовим методом. Собівартість за середньозваженим методом.",
            wraplength=360,
            justify=tk.CENTER,
        ).pack(pady=4)
        ttk.Label(frame, text=f"База даних: {get_db_path()}").pack(pady=4)

        actions = ttk.Frame(frame)
        actions.pack(pady=(8, 0))
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
        self.category_filter_options = self.flatten_categories()
        values = ["Усі категорії"] + [c["label"] for c in self.category_filter_options]
        if hasattr(self, "product_category_filter_combo"):
            self.product_category_filter_combo.configure(values=values)
            current = self.product_category_filter_var.get()
            if current not in values:
                self.product_category_filter_combo.current(0)

    def refresh_products(self, search: str | None = None) -> None:
        category_id = None
        selected_label = self.product_category_filter_var.get()
        for option in getattr(self, "category_filter_options", []):
            if option["label"] == selected_label:
                category_id = option["id"]
                break

        rows = db.list_products(search, category_id, self.include_subcategories_var.get())
        self.product_table.set_rows(
            [
                {
                    "id": r["id"],
                    "sku": r["sku"],
                    "name": r["name"],
                    "brand": r["brand"],
                    "category": r["category"],
                    "extra_categories": r["extra_categories"] or "",
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
        self.refresh_extra_costs()
        self.refresh_sales()
        self.refresh_cash()
        self.refresh_stock()
        self.refresh_cash_counterparties()
        self.refresh_dashboard()
        self.refresh_sales_analysis()
        self.refresh_abc_xyz()
        self.refresh_cash_flow_report()


# Dialogs

def _parse_date_value(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


def _parse_float_value(raw: str) -> float:
    if raw is None:
        return 0.0
    text = str(raw).replace(" ", "").replace(",", ".").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).strftime("%Y-%m-%d")
    return str(value)


SalesField = tuple[str, str, tuple[str, ...]]


SALES_FIELDS: list[SalesField] = [
    ("order_no", "Замовлення", ("номер", "замовлення", "order", "order_id", "order_no", "id")),
    ("doc_date", "Дата", ("дата", "date", "order_date", "дата оформлення")),
    ("customer", "Клієнт", ("клієнт", "покупець", "customer", "контрагент")),
    ("phone", "Телефон", ("телефон", "phone")),
    ("email", "Email", ("email", "e-mail")),
    ("sku", "SKU", ("sku", "артикул", "код")),
    ("product_name", "Товар", ("товар", "product", "назва", "item")),
    ("quantity", "Кількість", ("кількість", "к-сть", "qty", "quantity", "шт")),
    ("price", "Ціна", ("ціна", "price", "amount")),
    ("amount", "Сума", ("сума", "amount", "total")),
    ("discount", "Знижка", ("знижка", "discount")),
    ("comment", "Коментар", ("коментар", "примітка", "comment", "note")),
    ("channel", "Канал", ("канал", "channel", "майданчик", "площадка", "platform")),
]


def _suggest_sales_mapping(headers: list[str]) -> dict[str, str]:
    normalized_headers = {h.lower(): h for h in headers}
    mapping: dict[str, str] = {}
    for key, _label, aliases in SALES_FIELDS:
        for alias in aliases:
            if alias.lower() in normalized_headers:
                mapping[key] = normalized_headers[alias.lower()]
                break
        else:
            mapping[key] = ""
    return mapping


def _normalize_sales_records(rows: list[dict[str, object]], mapping: dict[str, str]) -> list[dict]:
    records: list[dict] = []
    for row in rows:
        normalized = {(k or "").strip(): _format_cell_value(v).strip() for k, v in row.items()}

        def pick(field: str, parser=None):
            header = mapping.get(field, "")
            value = normalized.get(header, "") if header else ""
            return parser(value) if parser else value

        records.append(
            {
                "order_no": pick("order_no"),
                "doc_date": pick("doc_date", _parse_date_value),
                "customer": pick("customer"),
                "phone": pick("phone"),
                "email": pick("email"),
                "sku": pick("sku"),
                "product_name": pick("product_name"),
                "quantity": pick("quantity", _parse_float_value),
                "price": pick("price", _parse_float_value),
                "amount": pick("amount", _parse_float_value),
                "discount": pick("discount", _parse_float_value),
                "comment": pick("comment"),
                "channel": pick("channel"),
            }
        )
    return records


def _read_sales_csv(path: Path, encoding: str) -> tuple[list[dict[str, object]], list[str]]:
    with path.open("r", encoding=encoding, newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        rows = [{k or "": v for k, v in row.items()} for row in reader]
        headers = list(reader.fieldnames or [])
        return rows, [h or "" for h in headers]


def _read_sales_xlsx(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return [], []

    headers = [_format_cell_value(cell).strip() for cell in rows[0]]
    records: list[dict[str, object]] = []
    for row in rows[1:]:
        record: dict[str, object] = {}
        for idx, value in enumerate(row):
            header = headers[idx] if idx < len(headers) else ""
            record[header] = value
        records.append(record)
    return records, headers


def _read_sales_xls(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    try:
        # Деякі сервіси експортують XLSX-файли з розширенням .xls, тому
        # спершу пробуємо прочитати їх через openpyxl.
        return _read_sales_xlsx(path)
    except Exception:
        # Якщо це справді старий XLS, повертаємося до xlrd.
        try:
            import xlrd
        except ImportError as exc:
            raise ImportError(
                "Для імпорту XLS-файлів потрібно встановити залежність 'xlrd'."
            ) from exc

    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return [], []

    headers = [_format_cell_value(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    records: list[dict[str, object]] = []
    for row_idx in range(1, sheet.nrows):
        record: dict[str, object] = {}
        for col_idx in range(sheet.ncols):
            header = headers[col_idx] if col_idx < len(headers) else ""
            cell = sheet.cell(row_idx, col_idx)
            value: object = cell.value
            if cell.ctype == xlrd.XL_CELL_DATE:
                try:
                    value = xlrd.xldate_as_datetime(value, workbook.datemode)
                except Exception:
                    pass
            record[header] = value
        records.append(record)
    return records, headers


def parse_sales_file(path: Path, encoding: str = "utf-8") -> tuple[list[dict[str, object]], list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        raw_rows, headers = _read_sales_xlsx(path)
    elif suffix == ".xls":
        raw_rows, headers = _read_sales_xls(path)
    else:
        raw_rows, headers = _read_sales_csv(path, encoding)

    return raw_rows, headers


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


def product_prompt(brands, categories, title: str, initial=None):
    base_initial = {
        "sku": "",
        "name": "",
        "brand_id": None,
        "category_id": None,
        "unit": "pcs",
        "is_active": True,
        "extras": [],
    }

    if isinstance(initial, dict):
        normalized_initial = {**base_initial, **initial}
    elif initial:
        # Support tuples/lists passed by the callers
        normalized_initial = base_initial.copy()
        normalized_initial.update(
            {
                "sku": initial[0] if len(initial) > 0 else "",
                "name": initial[1] if len(initial) > 1 else "",
                "brand_id": initial[2] if len(initial) > 2 else None,
                "category_id": initial[3] if len(initial) > 3 else None,
                "unit": initial[4] if len(initial) > 4 else "pcs",
                "is_active": bool(initial[5]) if len(initial) > 5 else True,
                "extras": initial[6] if len(initial) > 6 else [],
            }
        )
    else:
        normalized_initial = base_initial

    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.grab_set()
    dlg.columnconfigure(1, weight=1)

    ttk.Label(dlg, text="SKU").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    sku_var = tk.StringVar(value=normalized_initial.get("sku", ""))
    ttk.Entry(dlg, textvariable=sku_var, width=30).grid(row=0, column=1, padx=6, pady=4, sticky="ew")

    ttk.Label(dlg, text="Назва").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    name_var = tk.StringVar(value=normalized_initial.get("name", ""))
    ttk.Entry(dlg, textvariable=name_var, width=30).grid(row=1, column=1, padx=6, pady=4, sticky="ew")

    ttk.Label(dlg, text="Бренд").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    brand_var = tk.StringVar()
    brand_combo = ttk.Combobox(dlg, textvariable=brand_var, state="readonly", values=[b["name"] for b in brands])
    brand_combo.grid(row=2, column=1, padx=6, pady=4, sticky="ew")

    ttk.Label(dlg, text="Головна категорія").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    category_var = tk.StringVar()
    category_combo = ttk.Combobox(dlg, textvariable=category_var, values=[c["label"] for c in categories])
    category_combo.grid(row=3, column=1, padx=6, pady=4, sticky="ew")

    def refresh_category_options(*_args):
        search = category_var.get().strip().lower()
        filtered = [c["label"] for c in categories if search in c["label"].lower()]
        category_combo["values"] = filtered or [c["label"] for c in categories]

    category_combo.bind("<KeyRelease>", refresh_category_options)

    ttk.Label(dlg, text="Додаткові категорії").grid(row=4, column=0, padx=6, pady=4, sticky="nw")
    extras_frame = ttk.Frame(dlg)
    extras_frame.grid(row=4, column=1, padx=6, pady=4, sticky="nsew")
    extras_frame.columnconfigure(0, weight=1)
    extras_frame.rowconfigure(1, weight=1)
    extras_search_var = tk.StringVar()
    ttk.Entry(extras_frame, textvariable=extras_search_var).grid(
        row=0, column=0, columnspan=2, padx=(0, 8), pady=(0, 4), sticky="ew"
    )
    extras_box = tk.Listbox(
        extras_frame, selectmode=tk.MULTIPLE, height=min(10, max(6, len(categories))), exportselection=False
    )
    extras_scroll = ttk.Scrollbar(extras_frame, orient="vertical", command=extras_box.yview)
    extras_box.configure(yscrollcommand=extras_scroll.set)
    extras_box.grid(row=1, column=0, sticky="nsew")
    extras_scroll.grid(row=1, column=1, sticky="ns")

    filtered_extra_categories = list(categories)
    initial_extra_ids = set(normalized_initial.get("extras") or [])

    def refresh_extra_list(*_args):
        selected_labels = {extras_box.get(i) for i in extras_box.curselection()}
        search = extras_search_var.get().strip().lower()
        extras_box.delete(0, tk.END)
        filtered_extra_categories.clear()
        filtered_extra_categories.extend([c for c in categories if search in c["label"].lower()])
        for idx, cat in enumerate(filtered_extra_categories):
            extras_box.insert(tk.END, cat["label"])
            if cat["label"] in selected_labels or cat["id"] in initial_extra_ids:
                extras_box.selection_set(idx)
        initial_extra_ids.difference_update({c["id"] for c in filtered_extra_categories})

    extras_search_var.trace_add("write", refresh_extra_list)
    refresh_extra_list()

    dlg.rowconfigure(4, weight=1)

    ttk.Label(dlg, text="Одиниця").grid(row=5, column=0, padx=6, pady=4, sticky="w")
    unit_var = tk.StringVar(value=normalized_initial.get("unit", "pcs"))
    ttk.Entry(dlg, textvariable=unit_var, width=12).grid(row=5, column=1, padx=6, pady=4, sticky="w")

    is_active_var = tk.BooleanVar(value=normalized_initial.get("is_active", True))
    ttk.Checkbutton(dlg, text="Активний", variable=is_active_var).grid(row=6, column=1, padx=6, pady=4, sticky="w")

    if initial:
        brand_combo.current(next((i for i, b in enumerate(brands) if b["id"] == normalized_initial["brand_id"]), 0))
        category_var.set(next((c["label"] for c in categories if c["id"] == normalized_initial["category_id"]), ""))
        refresh_category_options()
        extras = set(normalized_initial.get("extras") or [])
        for idx, cat in enumerate(filtered_extra_categories):
            if cat["id"] in extras:
                extras_box.selection_set(idx)
    else:
        if brands:
            brand_combo.current(0)
        if categories:
            category_var.set(categories[0]["label"])
            refresh_category_options()

    result = None

    def on_ok():
        nonlocal result
        sku = sku_var.get().strip()
        name = name_var.get().strip()
        if not sku or not name:
            messagebox.showerror("Валідація", "Заповніть SKU та назву")
            return
        if not categories:
            messagebox.showerror("Валідація", "Створіть принаймні одну категорію")
            return
        try:
            brand_id = brands[brand_combo.current()]["id"]
        except IndexError:
            messagebox.showerror("Валідація", "Оберіть бренд і категорію")
            return
        selected_label = category_var.get().strip()
        matched_category = next((c for c in categories if c["label"].lower() == selected_label.lower()), None)
        if not matched_category:
            matched_category = next((c for c in categories if selected_label.lower() in c["label"].lower()), None)
        if not matched_category:
            messagebox.showerror("Валідація", "Оберіть бренд і категорію")
            return
        selected = [filtered_extra_categories[i]["id"] for i in extras_box.curselection() if i < len(filtered_extra_categories)]
        result = (
            sku,
            name,
            brand_id,
            matched_category["id"],
            unit_var.get().strip() or "pcs",
            bool(is_active_var.get()),
            selected,
        )
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.grid(row=7, column=0, columnspan=2, pady=8, sticky="e")
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: on_cancel())
    dlg.wait_window()
    return result


def category_prompt(title: str, initial=None):
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.grab_set()

    ttk.Label(dlg, text="Назва").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    name_var = tk.StringVar(value=initial[0] if initial else "")
    ttk.Entry(dlg, textvariable=name_var, width=30).grid(row=0, column=1, padx=6, pady=4)

    ttk.Label(dlg, text="Колір (hex)").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    color_var = tk.StringVar(value=initial[1] if initial else "")
    ttk.Entry(dlg, textvariable=color_var, width=20).grid(row=1, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Іконка/emoji").grid(row=2, column=0, padx=6, pady=4, sticky="w")
    icon_var = tk.StringVar(value=initial[2] if initial else "")
    ttk.Entry(dlg, textvariable=icon_var, width=20).grid(row=2, column=1, padx=6, pady=4, sticky="w")

    ttk.Label(dlg, text="Типові атрибути (через кому)").grid(row=3, column=0, padx=6, pady=4, sticky="w")
    attrs_var = tk.StringVar(value=initial[3] if initial else "")
    ttk.Entry(dlg, textvariable=attrs_var, width=40).grid(row=3, column=1, padx=6, pady=4, sticky="w")

    service_var = tk.BooleanVar(value=initial[4] if initial else False)
    hidden_var = tk.BooleanVar(value=initial[5] if initial else False)
    ttk.Checkbutton(dlg, text="Службова", variable=service_var).grid(row=4, column=1, padx=6, pady=4, sticky="w")
    ttk.Checkbutton(dlg, text="Прихована", variable=hidden_var).grid(row=5, column=1, padx=6, pady=4, sticky="w")

    result = None

    def on_ok():
        nonlocal result
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Валідація", "Назва обов'язкова")
            return
        result = (name, color_var.get().strip(), icon_var.get().strip(), attrs_var.get().strip(), service_var.get(), hidden_var.get())
        dlg.destroy()

    ttk.Button(dlg, text="OK", command=on_ok).grid(row=6, column=0, padx=6, pady=8)
    ttk.Button(dlg, text="Скасувати", command=dlg.destroy).grid(row=6, column=1, padx=6, pady=8)
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.wait_window()
    return result


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
    curr_var = tk.StringVar(value=doc["currency_code"] if doc else (curr_codes[0] if curr_codes else BASE_CURRENCY))
    curr_combo = ttk.Combobox(frame, textvariable=curr_var, values=curr_codes, state="readonly")
    if not allow_edit:
        curr_combo.state(["disabled"])
    curr_combo.grid(row=row_idx, column=1, sticky="w")

    row_idx += 1
    ttk.Label(frame, text="Курс").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
    default_rate = doc["exchange_rate"] if doc else db.latest_rate(curr_var.get())
    rate_var = tk.StringVar(value=f"{default_rate:.4f}")
    ttk.Entry(frame, textvariable=rate_var, width=12, state="normal" if allow_edit else "disabled").grid(row=row_idx, column=1, sticky="w")

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
        partner_name = cp_var.get()
        partner_id = None
        if partner_name and partner_name != "-":
            found = next((c for c in filtered_counterparties if c["name"] == partner_name), None)
            partner_id = found["id"] if found else None
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


def document_prompt(doc_type: str, products, counterparties, warehouses, channels, currencies, doc=None, lines=None):
    dlg = tk.Toplevel()
    dlg.title("Документ")
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
    ttk.Label(content, text="Тип").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    doc_type_label = "Закупівля" if doc_type == "purchase" else "Продаж"
    ttk.Label(content, text=doc_type_label).grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ttk.Label(content, text="Дата (YYYY-MM-DD)").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    date_var = tk.StringVar(value=doc["doc_date"] if doc else datetime.now().strftime("%Y-%m-%d"))
    ttk.Entry(content, textvariable=date_var, width=15, state="normal" if editable else "disabled").grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ttk.Label(content, text="Валюта").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    curr_var = tk.StringVar(value=doc["currency_code"] if doc else (currencies[0]["code"] if currencies else "UAH"))
    curr_codes = [c["code"] for c in currencies] if currencies else ["UAH"]
    curr_combo = ttk.Combobox(content, textvariable=curr_var, values=curr_codes, state="readonly")
    if not editable:
        curr_combo.state(["disabled"])
    curr_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ttk.Label(content, text="Курс до базової").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    default_rate = doc["exchange_rate"] if doc else (db.latest_rate(curr_var.get()) if currencies else 1.0)
    rate_var = tk.StringVar(value=f"{default_rate:.4f}")
    rate_entry = ttk.Entry(content, textvariable=rate_var, width=12, state="normal" if editable else "disabled")
    rate_entry.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ttk.Label(content, text="Склад").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    wh_var = tk.StringVar()
    wh_names = [w["name"] for w in warehouses]
    wh_combo = ttk.Combobox(content, textvariable=wh_var, values=wh_names, state="readonly")
    wh_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")

    row_idx += 1
    ch_var = tk.StringVar()
    ch_combo = None
    if doc_type == "sale":
        ttk.Label(content, text="Канал").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
        ch_names = [c["name"] for c in channels]
        ch_combo = ttk.Combobox(content, textvariable=ch_var, values=ch_names, state="readonly")
        ch_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
        row_idx += 1

    ttk.Label(content, text="Контрагент").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    allowed_types = {"purchase": {"supplier", "both", "other"}, "sale": {"customer", "both", "other"}}[doc_type]
    filtered_counterparties = [c for c in counterparties if c["type"] in allowed_types]
    cp_names = ["-"] + [c["name"] for c in filtered_counterparties]
    cp_var = tk.StringVar()
    cp_combo = ttk.Combobox(content, textvariable=cp_var, values=cp_names, state="readonly", width=25)
    cp_combo.grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
    row_idx += 1

    ttk.Label(content, text="Коментар").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
    comment_var = tk.StringVar(value=doc["comment"] if doc else "")
    ttk.Entry(content, textvariable=comment_var, width=40).grid(row=row_idx, column=1, padx=6, pady=4, sticky="ew")

    row_idx += 1
    order_expense_var = tk.StringVar(value=f"{float(doc.get('order_expense_doc', 0.0)):.2f}" if doc else "0")
    if doc_type == "sale":
        ttk.Label(content, text="Витрати замовлення").grid(row=row_idx, column=0, padx=6, pady=4, sticky="e")
        ttk.Entry(content, textvariable=order_expense_var, width=20).grid(row=row_idx, column=1, padx=6, pady=4, sticky="w")
        row_idx += 1

    ttk.Label(content, text="Рядки").grid(row=row_idx, column=0, padx=6, pady=4, sticky="ne")
    line_frame = ttk.Frame(content)
    line_frame.grid(row=row_idx, column=1, padx=6, pady=4, sticky="nsew")
    line_frame.grid_columnconfigure(0, weight=1)
    content.rowconfigure(row_idx, weight=1)

    columns = ["product", "quantity", "price", "expense", "amount"]
    tree = ttk.Treeview(line_frame, columns=columns, show="headings", height=8)
    headings = {
        "product": ("Товар", 200),
        "quantity": ("Кількість", 90),
        "price": ("Ціна", 90),
        "expense": ("Витрата/од.", 110),
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
        expense_label.config(text=f"Витрата/од. ({curr_var.get()})")
        tree.heading("expense", text=f"Витрата/од. ({curr_var.get()})")
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
    product_names = list(product_lookup.keys())

    row_idx += 1
    entry_frame = ttk.Frame(content)
    entry_frame.grid(row=row_idx, column=0, columnspan=2, padx=6, pady=4, sticky="ew")
    entry_frame.columnconfigure(1, weight=1)
    ttk.Label(entry_frame, text="Товар").grid(row=0, column=0, padx=4, pady=2, sticky="e")
    product_var = tk.StringVar()
    product_combo_state = "normal" if editable else "readonly"
    product_combo = ttk.Combobox(entry_frame, textvariable=product_var, values=product_names, state=product_combo_state, width=40)
    product_combo.grid(row=0, column=1, padx=4, pady=2, sticky="ew")
    if product_lookup:
        product_combo.current(0)

    def filter_products(event=None):
        if not editable:
            return
        text = product_var.get().lower()
        matches = [name for name in product_names if text in name.lower()]
        product_combo["values"] = matches if matches else product_names

    product_combo.bind("<KeyRelease>", filter_products)

    ttk.Label(entry_frame, text="Кількість").grid(row=0, column=2, padx=4, pady=2, sticky="e")
    qty_var = tk.StringVar(value="1")
    ttk.Entry(entry_frame, textvariable=qty_var, width=10).grid(row=0, column=3, padx=4, pady=2, sticky="w")

    price_label = ttk.Label(entry_frame, text="Ціна")
    price_label.grid(row=0, column=4, padx=4, pady=2, sticky="e")
    price_var = tk.StringVar(value="0")
    ttk.Entry(entry_frame, textvariable=price_var, width=10).grid(row=0, column=5, padx=4, pady=2, sticky="w")

    expense_label = ttk.Label(entry_frame, text="Витрата/од.")
    expense_label.grid(row=0, column=6, padx=4, pady=2, sticky="e")
    expense_var = tk.StringVar(value="0")
    ttk.Entry(entry_frame, textvariable=expense_var, width=10).grid(row=0, column=7, padx=4, pady=2, sticky="w")

    line_data = []
    if lines:
        for ln in lines:
            price_field = "purchase_price" if doc_type == "purchase" else "sale_price"
            expense_value = 0.0
            if doc_type == "sale" and "unit_expense_doc" in ln.keys():
                try:
                    expense_value = float(ln["unit_expense_doc"])
                except Exception:
                    expense_value = 0.0
            line_data.append(
                {
                    "product_id": ln["product_id"],
                    "product_name": ln["product_name"],
                    "quantity": float(ln["quantity"]),
                    "price": float(ln[price_field]),
                    "expense": expense_value,
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
                values=(
                    ln["product_name"],
                    f"{ln['quantity']:.2f}",
                    f"{ln['price']:.2f}",
                    f"{ln.get('expense', 0.0):.2f}",
                    f"{ln['amount']:.2f}",
                ),
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
            expense_var.set(str(ln.get("expense", 0.0)))

    tree.bind("<<TreeviewSelect>>", on_select)

    def add_or_update_line():
        if not editable:
            return
        try:
            qty = float(qty_var.get())
            price = float(price_var.get())
            expense_value = float(expense_var.get() or 0)
        except ValueError:
            messagebox.showerror("Валідація", "Невірні числові значення")
            return
        if qty <= 0:
            messagebox.showerror("Валідація", "Кількість повинна бути більшою за 0")
            return
        if expense_value < 0:
            messagebox.showerror("Валідація", "Витрати не можуть бути від'ємними")
            return
        product_name = product_var.get().strip()
        product_id = product_lookup.get(product_name)
        if not product_id:
            if not editable:
                return
            if not product_name:
                messagebox.showerror("Валідація", "Введіть назву товару")
                return
            created = add_new_product(product_name)
            if not created:
                return
            product_id, product_name = created
        data = {
            "product_id": product_id,
            "product_name": product_name,
            "quantity": qty,
            "price": price,
            "expense": expense_value,
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

    def add_new_product(default_name: str = ""):
        if not editable:
            return None
        brands = db.list_brands()
        categories = [
            {
                **c,
                "label": c.get("label") or ("    " * c.get("depth", 0) + c.get("name", "")),
            }
            for c in db.list_categories_tree()
        ]
        if not brands or not categories:
            messagebox.showerror(
                "Товари",
                "Додайте принаймні один бренд і категорію у вкладці \"Товари\", щоб створювати нові позиції.",
            )
            return None

        dlg_product = tk.Toplevel(dlg)
        dlg_product.title("Новий товар")
        dlg_product.grab_set()

        ttk.Label(dlg_product, text="Артикул").grid(row=0, column=0, padx=6, pady=4, sticky="e")
        sku_var = tk.StringVar(value=default_name)
        ttk.Entry(dlg_product, textvariable=sku_var, width=30).grid(row=0, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(dlg_product, text="Назва").grid(row=1, column=0, padx=6, pady=4, sticky="e")
        name_var = tk.StringVar(value=default_name)
        ttk.Entry(dlg_product, textvariable=name_var, width=30).grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(dlg_product, text="Бренд").grid(row=2, column=0, padx=6, pady=4, sticky="e")
        brand_var = tk.StringVar()
        brand_combo = ttk.Combobox(
            dlg_product,
            textvariable=brand_var,
            values=[b["name"] for b in brands],
            state="readonly",
            width=28,
        )
        brand_combo.grid(row=2, column=1, padx=6, pady=4, sticky="w")
        brand_combo.current(0)

        ttk.Label(dlg_product, text="Категорія").grid(row=3, column=0, padx=6, pady=4, sticky="e")
        category_var = tk.StringVar()
        category_combo = ttk.Combobox(
            dlg_product,
            textvariable=category_var,
            values=[c["label"] for c in categories],
            state="readonly",
            width=28,
        )
        category_combo.grid(row=3, column=1, padx=6, pady=4, sticky="w")
        category_combo.current(0)

        ttk.Label(dlg_product, text="Одиниця").grid(row=4, column=0, padx=6, pady=4, sticky="e")
        unit_var = tk.StringVar(value="pcs")
        ttk.Entry(dlg_product, textvariable=unit_var, width=30).grid(row=4, column=1, padx=6, pady=4, sticky="w")

        result_new: tuple[int, str] | None = None

        def on_save():
            nonlocal result_new
            sku = sku_var.get().strip()
            name = name_var.get().strip()
            unit = unit_var.get().strip() or "pcs"
            if not sku or not name:
                messagebox.showerror("Товари", "Введіть артикул і назву товару")
                return
            brand_idx = brand_combo.current()
            cat_idx = category_combo.current()
            try:
                brand_id = brands[brand_idx]["id"]
                category_id = categories[cat_idx]["id"]
            except Exception:
                messagebox.showerror("Товари", "Оберіть бренд та категорію")
                return
            try:
                new_id = db.add_product(sku, name, brand_id, category_id, unit, True)
            except Exception as exc:
                messagebox.showerror("Товари", f"Не вдалося створити товар: {exc}")
                return
            product_full_name = f"{name} ({sku})"
            product_lookup[product_full_name] = new_id
            products_by_id[new_id] = product_full_name
            product_names.append(product_full_name)
            product_names.sort(key=str.lower)
            product_combo["values"] = product_names
            product_var.set(product_full_name)
            result_new = (new_id, product_full_name)
            dlg_product.destroy()

        def on_cancel():
            dlg_product.destroy()

        btns_new = ttk.Frame(dlg_product)
        btns_new.grid(row=5, column=0, columnspan=2, pady=8)
        ttk.Button(btns_new, text="Зберегти", command=on_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns_new, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
        dlg_product.bind("<Return>", lambda e: on_save())
        dlg_product.bind("<Escape>", lambda e: on_cancel())
        dlg_product.wait_window()
        return result_new

    btn_line = ttk.Frame(entry_frame)
    btn_line.grid(row=0, column=8, padx=6)
    ttk.Button(btn_line, text="Новий товар", command=lambda: add_new_product(product_var.get()), state="normal" if editable else "disabled").pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_line, text="Додати/Оновити", command=add_or_update_line, state="normal" if editable else "disabled").pack(side=tk.LEFT)
    ttk.Button(btn_line, text="Видалити", command=delete_line, state="normal" if editable else "disabled").pack(side=tk.LEFT, padx=4)

    refresh_lines()

    row_idx += 1

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
        order_expense = 0.0
        if doc_type == "sale":
            try:
                order_expense = float(order_expense_var.get() or 0)
            except ValueError:
                messagebox.showerror("Валідація", "Невірна сума витрат замовлення")
                return
            if order_expense < 0:
                messagebox.showerror("Валідація", "Витрати замовлення не можуть бути від'ємними")
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
            "order_expense_doc": order_expense if doc_type == "sale" else 0.0,
        }
        if doc_type == "sale":
            lines_to_save = [
                (ln["product_id"], ln["quantity"], ln["price"], ln.get("expense", 0.0)) for ln in line_data
            ]
        else:
            lines_to_save = [(ln["product_id"], ln["quantity"], ln["price"]) for ln in line_data]
        result = (info, lines_to_save)
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btns = ttk.Frame(content)
    btns.grid(row=row_idx, column=0, columnspan=2, pady=8, sticky="e")
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


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: InventoryApp, section: str):
        super().__init__(app)
        self.app = app
        self.section = section
        self.title("Налаштування")
        self.resizable(False, False)
        self.grab_set()
        self.vars: dict[str, tk.Variable] = {}
        self.recent_cleared = False

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.general_tab = ttk.Frame(notebook)
        self.files_tab = ttk.Frame(notebook)
        self.ui_tab = ttk.Frame(notebook)
        self.editor_tab = ttk.Frame(notebook)
        self.hotkeys_tab = ttk.Frame(notebook)
        self.support_tab = ttk.Frame(notebook)

        notebook.add(self.general_tab, text="Загальні")
        notebook.add(self.files_tab, text="Файли й шляхи")
        notebook.add(self.ui_tab, text="Інтерфейс і вікна")
        notebook.add(self.editor_tab, text="Редактор")
        notebook.add(self.hotkeys_tab, text="Гарячі клавіші")
        notebook.add(self.support_tab, text="Допомога й підтримка")

        self.build_general_tab()
        self.build_files_tab()
        self.build_ui_tab()
        self.build_editor_tab()
        self.build_hotkeys_tab()
        self.build_support_tab()

        tab_index = {
            "general": 0,
            "files": 1,
            "ui": 2,
            "editor": 3,
            "hotkeys": 4,
            "support": 5,
        }.get(section, 0)
        notebook.select(tab_index)

        buttons = ttk.Frame(self)
        buttons.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="Скасувати", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Зберегти", command=self.save).pack(side=tk.RIGHT, padx=4)

    def build_general_tab(self) -> None:
        language_var = self._add_var("general.language", tk.StringVar(value=self.app.settings.get("general", "language")))
        ttk.Label(self.general_tab, text="Мова інтерфейсу:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.general_tab, textvariable=language_var, values=["uk", "en", "pl", "de"], width=10).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        theme_var = self._add_var("general.theme", tk.StringVar(value=self.app.settings.get("general", "theme")))
        ttk.Label(self.general_tab, text="Тема:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.general_tab, textvariable=theme_var, values=["system", "light", "dark"], width=10
        ).grid(row=1, column=1, sticky="w", padx=6, pady=4)

    def build_files_tab(self) -> None:
        workdir_var = self._add_var("files.working_dir", tk.StringVar(value=str(self.app.default_workdir())))
        ttk.Label(self.files_tab, text="Робоча директорія:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(self.files_tab, textvariable=workdir_var, width=40).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(self.files_tab, text="Огляд", command=lambda: self.choose_workdir(workdir_var)).grid(
            row=0, column=2, padx=4, pady=4
        )

        recent_limit_var = self._add_var(
            "files.recent_limit", tk.IntVar(value=int(self.app.settings.get("files", "recent_limit") or 10))
        )
        ttk.Label(self.files_tab, text="Кількість недавніх:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.files_tab, from_=0, to=50, textvariable=recent_limit_var, width=8).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        self.recent_label = ttk.Label(
            self.files_tab,
            text=f"Збережено недавніх: {len(self.app.settings.get('files', 'recent_items', default=[]))}",
        )
        self.recent_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Button(self.files_tab, text="Очистити", command=self.clear_recent).grid(row=2, column=2, padx=4, pady=4)

        encoding_var = self._add_var("files.encoding", tk.StringVar(value=self.app.settings.get("files", "encoding")))
        ttk.Label(self.files_tab, text="Кодування тексту:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.files_tab, textvariable=encoding_var, values=["utf-8", "cp1251", "latin-1", "utf-16"], width=12
        ).grid(row=3, column=1, sticky="w", padx=6, pady=4)

    def build_ui_tab(self) -> None:
        layout_var = self._add_var("ui.panel_layout", tk.StringVar(value=self.app.settings.get("ui", "panel_layout")))
        ttk.Label(self.ui_tab, text="Розташування панелей:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.ui_tab,
            textvariable=layout_var,
            values=["Авто", "Вертикально", "Горизонтально"],
            width=16,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        status_var = self._add_var("ui.status_bar", tk.BooleanVar(value=bool(self.app.settings.get("ui", "status_bar"))))
        ttk.Checkbutton(self.ui_tab, text="Показувати рядок стану", variable=status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        compact_var = self._add_var("ui.compact_mode", tk.BooleanVar(value=bool(self.app.settings.get("ui", "compact_mode"))))
        ttk.Checkbutton(self.ui_tab, text="Компактний режим", variable=compact_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        fullscreen_var = self._add_var(
            "ui.fullscreen", tk.BooleanVar(value=bool(self.app.settings.get("ui", "fullscreen")))
        )
        ttk.Checkbutton(self.ui_tab, text="Повноекранний режим", variable=fullscreen_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        volume_var = self._add_var(
            "ui.notifications_volume",
            tk.IntVar(value=int(self.app.settings.get("ui", "notifications_volume") or 70)),
        )
        ttk.Label(self.ui_tab, text="Гучність сповіщень:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        ttk.Scale(self.ui_tab, from_=0, to=100, variable=volume_var, orient=tk.HORIZONTAL, length=160).grid(
            row=4, column=1, sticky="w", padx=6, pady=4
        )

        duration_var = self._add_var(
            "ui.notifications_duration",
            tk.IntVar(value=int(self.app.settings.get("ui", "notifications_duration") or 3)),
        )
        ttk.Label(self.ui_tab, text="Тривалість сповіщень (сек):").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.ui_tab, from_=1, to=30, textvariable=duration_var, width=8).grid(
            row=5, column=1, sticky="w", padx=6, pady=4
        )

    def build_editor_tab(self) -> None:
        family_var = self._add_var("editor.font_family", tk.StringVar(value=self.app.settings.get("editor", "font_family")))
        ttk.Label(self.editor_tab, text="Шрифт редактора:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        font_box = ttk.Combobox(self.editor_tab, textvariable=family_var, values=sorted(tkfont.families()), width=24)
        font_box.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        size_var = self._add_var("editor.font_size", tk.IntVar(value=int(self.app.settings.get("editor", "font_size") or 10)))
        ttk.Label(self.editor_tab, text="Розмір шрифту:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=8, to=28, textvariable=size_var, width=6).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        syntax_var = self._add_var(
            "editor.syntax_highlighting", tk.BooleanVar(value=bool(self.app.settings.get("editor", "syntax_highlighting")))
        )
        ttk.Checkbutton(self.editor_tab, text="Підсвічування синтаксису", variable=syntax_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        indent_tabs_var = self._add_var(
            "editor.indent_with_tabs", tk.BooleanVar(value=bool(self.app.settings.get("editor", "indent_with_tabs")))
        )
        ttk.Checkbutton(self.editor_tab, text="Використовувати табуляцію для відступів", variable=indent_tabs_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        tab_width_var = self._add_var("editor.tab_width", tk.IntVar(value=int(self.app.settings.get("editor", "tab_width") or 4)))
        ttk.Label(self.editor_tab, text="Ширина табуляції:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=2, to=12, textvariable=tab_width_var, width=6).grid(
            row=4, column=1, sticky="w", padx=6, pady=4
        )

        line_numbers_var = self._add_var(
            "editor.line_numbers", tk.BooleanVar(value=bool(self.app.settings.get("editor", "line_numbers")))
        )
        ttk.Checkbutton(self.editor_tab, text="Показувати номери рядків", variable=line_numbers_var).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        minimap_var = self._add_var("editor.minimap", tk.BooleanVar(value=bool(self.app.settings.get("editor", "minimap"))))
        ttk.Checkbutton(self.editor_tab, text="Вмикати мінімеп", variable=minimap_var).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        auto_format_var = self._add_var(
            "editor.auto_format", tk.BooleanVar(value=bool(self.app.settings.get("editor", "auto_format")))
        )
        ttk.Checkbutton(self.editor_tab, text="Автоматичне форматування", variable=auto_format_var).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        autocomplete_var = self._add_var(
            "editor.autocomplete", tk.BooleanVar(value=bool(self.app.settings.get("editor", "autocomplete")))
        )
        ttk.Checkbutton(self.editor_tab, text="Автодоповнення", variable=autocomplete_var).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        length_limit_var = self._add_var(
            "editor.line_length_limit",
            tk.IntVar(value=int(self.app.settings.get("editor", "line_length_limit") or 120)),
        )
        ttk.Label(self.editor_tab, text="Фільтр по довжині рядка:").grid(row=9, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=40, to=240, textvariable=length_limit_var, width=6).grid(
            row=9, column=1, sticky="w", padx=6, pady=4
        )

    def build_hotkeys_tab(self) -> None:
        profile_var = self._add_var("hotkeys.profile", tk.StringVar(value=self.app.settings.get("hotkeys", "profile")))
        ttk.Label(self.hotkeys_tab, text="Профіль клавіш:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.hotkeys_tab, textvariable=profile_var, values=["Типовий", "Emacs", "Vim"], width=12
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        allow_custom_var = self._add_var(
            "hotkeys.allow_custom", tk.BooleanVar(value=bool(self.app.settings.get("hotkeys", "allow_custom")))
        )
        ttk.Checkbutton(self.hotkeys_tab, text="Дозволити переназначення", variable=allow_custom_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

    def build_support_tab(self) -> None:
        log_var = self._add_var("support.log_level", tk.StringVar(value=self.app.settings.get("support", "log_level")))
        ttk.Label(self.support_tab, text="Рівень логування:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.support_tab, textvariable=log_var, values=["DEBUG", "INFO", "WARNING", "ERROR"], width=12).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        sysinfo_var = self._add_var(
            "support.collect_system_info", tk.BooleanVar(value=bool(self.app.settings.get("support", "collect_system_info")))
        )
        ttk.Checkbutton(self.support_tab, text="Збирати системну інформацію", variable=sysinfo_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        autoreport_var = self._add_var(
            "support.auto_error_reports", tk.BooleanVar(value=bool(self.app.settings.get("support", "auto_error_reports")))
        )
        ttk.Checkbutton(self.support_tab, text="Надсилати звіти про помилки автоматично", variable=autoreport_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        docs_var = self._add_var("support.docs_url", tk.StringVar(value=self.app.settings.get("support", "docs_url")))
        ttk.Label(self.support_tab, text="Документація/FAQ:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(self.support_tab, textvariable=docs_var, width=40).grid(row=3, column=1, sticky="w", padx=6, pady=4)

    def choose_workdir(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(initialdir=var.get() or str(self.app.default_workdir()))
        if path:
            var.set(path)

    def clear_recent(self) -> None:
        self.recent_cleared = True
        self.recent_label.configure(text="Збережено недавніх: 0")

    def _add_var(self, path: str, var: tk.Variable) -> tk.Variable:
        self.vars[path] = var
        return var

    def save(self) -> None:
        for path, var in self.vars.items():
            value = var.get()
            keys = path.split(".")
            self.app.settings.set(value, *keys)
        if self.recent_cleared:
            self.app.settings.set([], "files", "recent_items")
        self.app.settings.save()
        self.app.apply_settings()
        self.destroy()


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

