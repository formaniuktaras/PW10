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
from datetime import date, datetime
from pathlib import Path
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
from typing import Optional

from inventorylite import db
from inventorylite import diagnostics
from inventorylite.helpers import (
    _find_index_by_name,
    _format_cell_value,
    _normalize_header,
    _parse_bool_value,
    _parse_date_value,
    _parse_float_value,
    _parse_num,
)
from inventorylite.error_handling import install_tk_exception_handler, setup_logging
from inventorylite.dialogs_labels import open_labels_print_dialog
from inventorylite.tabs.categories import CategoriesTab
from inventorylite.tabs.brands import BrandsTab
from inventorylite.tabs.counterparties import CounterpartiesTab
from inventorylite.tabs.products import ProductsTab, open_products_bulk_actions_dialog
from inventorylite.tabs.reports import ReportsTab
from inventorylite.tabs.settings import SettingsTab
from inventorylite.tabs.warehouses import WarehousesTab
from inventorylite.tabs.channels import ChannelsTab
from inventorylite.tabs.currencies import CurrenciesTab
from inventorylite.tabs.inventory import InventoryTab
from inventorylite.tabs.purchases import PurchasesTab
from inventorylite.tabs.sales import SalesTab
from inventorylite.tabs.cash import CashTab
from inventorylite.tabs.stock import StockTab
from inventorylite.tabs.extra_costs import ExtraCostsTab
from inventorylite.tabs.export import ExportTab
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
    open_data_folder,
    restore_all_data,
    show_error,
    backup_database,
    bind_common_shortcuts,
)


class InventoryApp(tk.Tk):
    def __init__(self, settings: Settings | None = None, log_path: Path | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x720")
        self.iconbitmap(default="icons/app.ico") if Path("icons/app.ico").exists() else None
        self.settings = settings or Settings()
        self.log_path = log_path
        apply_base_currency_settings(self.settings)
        self.status_var = tk.StringVar(value="Готово")
        self.status_bar: ttk.Label | None = None
        bind_common_shortcuts(self)
        self.create_menu()
        self.apply_settings()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.brands_tab = BrandsTab(
            parent=self.notebook,
            settings=self.settings,
            on_products_refresh=lambda: self.refresh_products(),
        )
        self.notebook.add(self.brands_tab.frame, text="Бренди")
        self.categories_tab = CategoriesTab(
            parent=self.notebook,
            settings=self.settings,
            flatten_categories_provider=self.flatten_categories,
            on_categories_changed=self.update_category_filters,
            on_products_refresh=lambda: self.refresh_products(),
        )
        self.notebook.add(self.categories_tab.frame, text="Категорії")
        self.products_tab = ProductsTab(
            parent=self.notebook,
            settings=self.settings,
            flatten_categories_provider=self.flatten_categories,
        )
        self.notebook.add(self.products_tab.frame, text="Товари")
        self.counterparties_tab = CounterpartiesTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.counterparties_tab.frame, text="Контрагенти")
        self.warehouses_tab = WarehousesTab(
            parent=self.notebook,
            settings=self.settings,
            on_warehouses_changed=self._on_warehouses_changed,
        )
        self.notebook.add(self.warehouses_tab.frame, text="Склади")

        self.channels_tab = ChannelsTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.channels_tab.frame, text="Канали продажу")
        self.currencies_tab = CurrenciesTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.currencies_tab.frame, text="Валюти")
        self.extra_costs_tab = ExtraCostsTab(
            parent=self.notebook,
            settings=self.settings,
            on_refresh_purchases=self.refresh_purchases,
            on_refresh_stock=self.refresh_stock,
        )
        self.notebook.add(self.extra_costs_tab.frame, text="Супутні витрати")
        self.inventory_tab = InventoryTab(
            parent=self.notebook,
            settings=self.settings,
            default_workdir_provider=self.default_workdir,
        )
        self.notebook.add(self.inventory_tab.frame, text="Інвентаризація")
        self.cash_tab = CashTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.cash_tab.frame, text="Каса")
        self.stock_tab = StockTab(
            parent=self.notebook,
            settings=self.settings,
            open_labels_dialog=open_labels_print_dialog,
            open_bulk_actions_dialog=open_products_bulk_actions_dialog,
        )
        self.notebook.add(self.stock_tab.frame, text="Залишки")
        self.export_tab = ExportTab(parent=self.notebook)
        self.notebook.add(self.export_tab.frame, text="Експорт")
        self.settings_tab = SettingsTab(
            parent=self.notebook,
            settings=self.settings,
            on_settings_saved=self._on_settings_saved,
        )
        self.notebook.add(self.settings_tab.frame, text="Налаштування")
        self.reports_tab = ReportsTab(parent=self.notebook, settings=self.settings)
        self.notebook.add(self.reports_tab.frame, text="Звіти")

        self.purchases_tab = PurchasesTab(
            parent=self.notebook,
            settings=self.settings,
            default_workdir_provider=self.default_workdir,
            generate_unique_sku=self._generate_unique_sku,
            on_refresh_stock=self.refresh_stock,
            on_refresh_cash=self.refresh_cash,
            open_labels_dialog=open_labels_print_dialog,
        )
        self.notebook.add(self.purchases_tab.frame, text="Закупівлі")
        self.sales_tab = SalesTab(
            parent=self.notebook,
            settings=self.settings,
            default_workdir_provider=self.default_workdir,
            generate_unique_sku=self._generate_unique_sku,
            on_refresh_stock=self.refresh_stock,
            on_refresh_cash=self.refresh_cash,
        )
        self.notebook.add(self.sales_tab.frame, text="Продажі")
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
        diagnostics_menu = tk.Menu(menubar, tearoff=0)
        diagnostics_menu.add_command(
            label="Відкрити теку даних", command=lambda: open_data_folder(get_data_dir())
        )
        diagnostics_menu.add_command(label="Відкрити папку логів", command=self.open_log_folder)
        diagnostics_menu.add_command(label="Відкрити поточний лог", command=self.open_log_file)
        diagnostics_menu.add_separator()
        diagnostics_menu.add_command(label="Швидка перевірка БД", command=self.show_db_healthcheck)
        menubar.add_cascade(label="Діагностика", menu=diagnostics_menu)
        self.config(menu=menubar)

    def open_log_folder(self) -> None:
        if not self.log_path:
            show_error(APP_NAME, "Шлях до логу невідомий.")
            return
        diagnostics.open_in_os(self.log_path.parent)

    def open_log_file(self) -> None:
        if not self.log_path:
            show_error(APP_NAME, "Шлях до логу невідомий.")
            return
        diagnostics.open_in_os(self.log_path)

    def show_db_healthcheck(self) -> None:
        results = diagnostics.run_db_healthcheck()
        lines = [
            f"DB: {results['db_path']}",
            f"integrity_check: {results['integrity']}",
            f"foreign_key_check: {results['foreign_key_issues']} issues",
            "counts:",
        ]
        for table, count in results["counts"].items():
            lines.append(f"  {table}: {count}")
        content = "\n".join(lines)

        window = tk.Toplevel(self)
        window.title("Швидка перевірка БД")
        window.transient(self)
        window.grab_set()
        window.geometry("520x360")

        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        text = tk.Text(frame, wrap="word", height=12)
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill=tk.BOTH, expand=True)

        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            actions,
            text="Копіювати",
            command=lambda: self._copy_healthcheck_result(content),
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(actions, text="Закрити", command=window.destroy).pack(side=tk.RIGHT)

    def _copy_healthcheck_result(self, content: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update_idletasks()

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

    def _on_warehouses_changed(self) -> None:
        if hasattr(self, "_refresh_inventory_warehouse_filter"):
            try:
                self._refresh_inventory_warehouse_filter()
            except Exception:
                logging.exception("Failed to refresh inventory warehouse filter")

    def refresh_inventory_documents(self) -> None:
        if hasattr(self, "inventory_tab"):
            self.inventory_tab.refresh_inventory_documents()

    def _refresh_inventory_warehouse_filter(self) -> None:
        if hasattr(self, "inventory_tab"):
            self.inventory_tab.refresh_warehouse_filter()

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

    # Currencies
    def refresh_currencies(self) -> None:
        if hasattr(self, "currencies_tab"):
            self.currencies_tab.refresh_currencies()

    # Purchases
    def refresh_purchases(self) -> None:
        if hasattr(self, "purchases_tab"):
            self.purchases_tab.refresh_purchases()

    def refresh_sales(self) -> None:
        if hasattr(self, "sales_tab"):
            self.sales_tab.refresh_sales()

    def refresh_extra_costs(self) -> None:
        if hasattr(self, "extra_costs_tab"):
            self.extra_costs_tab.refresh_extra_costs()

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
    def refresh_cash(self) -> None:
        if hasattr(self, "cash_tab"):
            self.cash_tab.refresh_cash()

    # Stock
    def refresh_stock(self, search: str | None = None) -> None:
        if hasattr(self, "stock_tab"):
            self.stock_tab.refresh_stock(search)

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
        if hasattr(self, "brands_tab"):
            self.brands_tab.refresh_brands()

    def refresh_categories(self) -> None:
        if hasattr(self, "categories_tab"):
            self.categories_tab.refresh_categories()

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
        if hasattr(self, "counterparties_tab"):
            self.counterparties_tab.refresh_counterparties()

    def refresh_warehouses(self) -> None:
        if hasattr(self, "warehouses_tab"):
            self.warehouses_tab.refresh_warehouses()

    def refresh_channels(self) -> None:
        if hasattr(self, "channels_tab"):
            self.channels_tab.refresh_channels()

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
            app = InventoryApp(settings, log_path=log_path)
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
