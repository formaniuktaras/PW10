from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from typing import Callable, Optional

from inventorylite import db
from inventorylite import sku_gen
from inventorylite.helpers import _sanitize_barcode_prefix
from inventorylite.utils import Settings, get_base_currency_code, get_base_currency_decimals, get_data_dir


class SettingsTab:
    def __init__(self, parent: ttk.Frame, settings: Settings, on_settings_saved: Callable[[], None]):
        self.parent = parent
        self.settings = settings
        self.on_settings_saved = on_settings_saved
        self.frame = ttk.Frame(parent)
        self.vars: dict[str, tk.Variable] = {}
        self.recent_cleared = False
        self.recent_label: ttk.Label | None = None
        self.section_notebook: ttk.Notebook | None = None
        self.section_map: dict[str, int] = {}
        self.sku_rules_state: list[dict] = []
        self._build()

    def _build(self) -> None:
        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.section_notebook = notebook

        self.general_tab = ttk.Frame(notebook)
        self.defaults_tab = ttk.Frame(notebook)
        self.files_tab = ttk.Frame(notebook)
        self.ui_tab = ttk.Frame(notebook)
        self.editor_tab = ttk.Frame(notebook)
        self.hotkeys_tab = ttk.Frame(notebook)
        self.support_tab = ttk.Frame(notebook)

        notebook.add(self.general_tab, text="Загальні")
        notebook.add(self.defaults_tab, text="Типові значення")
        notebook.add(self.files_tab, text="Файли й шляхи")
        notebook.add(self.ui_tab, text="Інтерфейс і вікна")
        notebook.add(self.editor_tab, text="Редактор")
        notebook.add(self.hotkeys_tab, text="Гарячі клавіші")
        notebook.add(self.support_tab, text="Допомога й підтримка")
        self.section_map = {
            "general": 0,
            "defaults": 1,
            "files": 2,
            "ui": 3,
            "editor": 4,
            "hotkeys": 5,
            "support": 6,
        }

        self.build_general_tab()
        self.build_defaults_tab()
        self.build_files_tab()
        self.build_ui_tab()
        self.build_editor_tab()
        self.build_hotkeys_tab()
        self.build_support_tab()

        buttons = ttk.Frame(self.frame)
        buttons.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="Скасувати", command=self.refresh).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Зберегти", command=self._on_save).pack(side=tk.RIGHT, padx=4)

    def select_section(self, section: str) -> None:
        if not self.section_notebook:
            return
        self.section_notebook.select(self.section_map.get(section, 0))

    def refresh(self) -> None:
        self.recent_cleared = False
        for path, var in self.vars.items():
            value = self._value_for_path(path)
            var.set(value)
        self._load_sku_rules_state()
        brand_map = {b["id"]: b for b in db.list_brands()}
        category_map = {c["id"]: c for c in self._flatten_categories()}
        self._refresh_sku_rules_tree(brand_map, category_map)
        if self.recent_label:
            self.recent_label.configure(
                text=f"Збережено недавніх: {len(self.settings.get('files', 'recent_items', default=[]))}",
            )

    def build_general_tab(self) -> None:
        language_var = self._add_var("general.language", tk.StringVar(value=self._value_for_path("general.language")))
        ttk.Label(self.general_tab, text="Мова інтерфейсу:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.general_tab, textvariable=language_var, values=["uk", "en", "pl", "de"], width=10).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        theme_var = self._add_var("general.theme", tk.StringVar(value=self._value_for_path("general.theme")))
        ttk.Label(self.general_tab, text="Тема:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.general_tab, textvariable=theme_var, values=["system", "light", "dark"], width=10
        ).grid(row=1, column=1, sticky="w", padx=6, pady=4)

    def build_defaults_tab(self) -> None:
        product_frame = ttk.LabelFrame(self.defaults_tab, text="Товари")
        product_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        unit_var = self._add_var("defaults.product.unit", tk.StringVar(value=self._value_for_path("defaults.product.unit")))
        ttk.Label(product_frame, text="Одиниця за замовчуванням:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(product_frame, textvariable=unit_var, width=14).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        brands = db.list_brands()
        brand_names = [b["name"] for b in brands]
        brand_var = self._add_var("defaults.product.brand", tk.StringVar(value=self._value_for_path("defaults.product.brand")))
        ttk.Label(product_frame, text="Бренд за замовчуванням:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(product_frame, textvariable=brand_var, values=brand_names, width=30).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )
        ttk.Label(product_frame, text="Залиште поле порожнім, щоб вибирати бренд вручну.").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 8)
        )

        categories = self._flatten_categories()
        category_labels = [c["label"] for c in categories]
        category_var = self._add_var(
            "defaults.product.category", tk.StringVar(value=self._value_for_path("defaults.product.category"))
        )
        ttk.Label(product_frame, text="Категорія за замовчуванням:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(product_frame, textvariable=category_var, values=category_labels, width=30).grid(
            row=3, column=1, sticky="w", padx=6, pady=4
        )
        ttk.Label(product_frame, text="Залиште поле порожнім, щоб обирати категорію під час створення.").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4)
        )

        barcode_prefix_var = self._add_var(
            "defaults.product.barcode_prefix",
            tk.StringVar(value=self._value_for_path("defaults.product.barcode_prefix")),
        )
        ttk.Label(product_frame, text="Префікс штрихкоду (додається перед SKU):").grid(
            row=5, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Entry(product_frame, textvariable=barcode_prefix_var, width=30).grid(
            row=5, column=1, sticky="w", padx=6, pady=4
        )
        ttk.Label(product_frame, text="Залиште порожнім — без префікса (немає).").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 8)
        )

        sku_frame = ttk.LabelFrame(product_frame, text="SKU (генератор)")
        sku_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        sku_frame.columnconfigure(1, weight=1)

        sku_enabled_var = self._add_var(
            "defaults.product.sku_generator.enabled",
            tk.BooleanVar(value=self._value_for_path("defaults.product.sku_generator.enabled")),
        )
        ttk.Checkbutton(sku_frame, text="Увімкнути генератор SKU", variable=sku_enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        default_prefix_var = self._add_var(
            "defaults.product.sku_generator.default.prefix_template",
            tk.StringVar(value=self._value_for_path("defaults.product.sku_generator.default.prefix_template")),
        )
        ttk.Label(sku_frame, text="Prefix template (fallback):").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(sku_frame, textvariable=default_prefix_var, width=30).grid(
            row=1, column=1, sticky="ew", padx=6, pady=4
        )

        default_digits_var = self._add_var(
            "defaults.product.sku_generator.default.digits",
            tk.IntVar(value=self._value_for_path("defaults.product.sku_generator.default.digits")),
        )
        ttk.Label(sku_frame, text="Digits:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(sku_frame, from_=3, to=10, textvariable=default_digits_var, width=8).grid(
            row=2, column=1, sticky="w", padx=6, pady=4
        )

        default_start_var = self._add_var(
            "defaults.product.sku_generator.default.start_from",
            tk.IntVar(value=self._value_for_path("defaults.product.sku_generator.default.start_from")),
        )
        ttk.Label(sku_frame, text="Start from:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(sku_frame, from_=1, to=999999, textvariable=default_start_var, width=8).grid(
            row=3, column=1, sticky="w", padx=6, pady=4
        )

        rules_frame = ttk.Frame(sku_frame)
        rules_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        rules_frame.columnconfigure(0, weight=1)
        rules_frame.rowconfigure(0, weight=1)

        columns = ("priority", "enabled", "name", "brand", "category", "subcats", "contains", "template", "digits", "start")
        self.sku_rules_tree = ttk.Treeview(
            rules_frame, columns=columns, show="headings", height=6, selectmode="browse"
        )
        headings = {
            "priority": "Пріоритет",
            "enabled": "Увімкнено",
            "name": "Назва",
            "brand": "Бренд",
            "category": "Категорія",
            "subcats": "Підкат.",
            "contains": "Назва містить",
            "template": "Префікс",
            "digits": "Цифр",
            "start": "Старт",
        }
        for col, text in headings.items():
            self.sku_rules_tree.heading(col, text=text)
            self.sku_rules_tree.column(col, width=90 if col in {"priority", "digits", "start"} else 120, anchor="w")
        self.sku_rules_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(rules_frame, orient="vertical", command=self.sku_rules_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sku_rules_tree.configure(yscrollcommand=scrollbar.set)

        brand_map = {b["id"]: b for b in brands}
        category_map = {c["id"]: c for c in categories}
        self._load_sku_rules_state()
        self._refresh_sku_rules_tree(brand_map, category_map)

        def add_or_edit_rule(existing: Optional[dict] = None, idx: Optional[int] = None) -> None:
            dialog = tk.Toplevel(self.frame)
            dialog.title("Правило SKU" + (f": {existing.get('name')}" if existing else ""))
            dialog.transient(self.frame.winfo_toplevel())
            dialog.grab_set()

            initial = existing or {}
            tk.Label(dialog, text="Назва").grid(row=0, column=0, sticky="e", padx=6, pady=4)
            name_var = tk.StringVar(value=initial.get("name", ""))
            ttk.Entry(dialog, textvariable=name_var, width=30).grid(row=0, column=1, sticky="w", padx=6, pady=4)

            enabled_var = tk.BooleanVar(value=initial.get("enabled", True))
            ttk.Checkbutton(dialog, text="Увімкнено", variable=enabled_var).grid(
                row=1, column=1, sticky="w", padx=6, pady=2
            )

            priority_var = tk.IntVar(value=initial.get("priority", 0))
            ttk.Label(dialog, text="Пріоритет").grid(row=2, column=0, sticky="e", padx=6, pady=4)
            ttk.Spinbox(dialog, from_=0, to=1000, textvariable=priority_var, width=10).grid(
                row=2, column=1, sticky="w", padx=6, pady=4
            )

            ttk.Label(dialog, text="Бренд").grid(row=3, column=0, sticky="e", padx=6, pady=4)
            brand_names_ext = ["Будь-який"] + brand_names
            brand_var = tk.StringVar()
            ttk.Combobox(dialog, textvariable=brand_var, values=brand_names_ext, state="readonly", width=28).grid(
                row=3, column=1, sticky="w", padx=6, pady=2
            )
            if initial.get("match", {}).get("brand_id") in brand_map:
                brand_var.set(brand_map[initial["match"]["brand_id"]]["name"])
            else:
                brand_var.set("Будь-який")

            ttk.Label(dialog, text="Категорія").grid(row=4, column=0, sticky="e", padx=6, pady=4)
            category_labels_ext = ["Будь-яка"] + [c["label"] for c in categories]
            category_var = tk.StringVar()
            ttk.Combobox(dialog, textvariable=category_var, values=category_labels_ext, width=28, state="readonly").grid(
                row=4, column=1, sticky="w", padx=6, pady=2
            )
            if initial.get("match", {}).get("category_id") in category_map:
                category_var.set(category_map[initial["match"]["category_id"]]["label"])
            else:
                category_var.set("Будь-яка")

            include_sub_var = tk.BooleanVar(value=bool(initial.get("match", {}).get("include_subcategories")))
            ttk.Checkbutton(dialog, text="Враховувати підкатегорії", variable=include_sub_var).grid(
                row=5, column=1, sticky="w", padx=6, pady=2
            )

            ttk.Label(dialog, text="Назва містить").grid(row=6, column=0, sticky="e", padx=6, pady=4)
            contains_var = tk.StringVar(value=initial.get("match", {}).get("name_contains", ""))
            ttk.Entry(dialog, textvariable=contains_var, width=30).grid(row=6, column=1, sticky="w", padx=6, pady=4)

            ttk.Label(dialog, text="Prefix template").grid(row=7, column=0, sticky="e", padx=6, pady=4)
            template_var = tk.StringVar(value=initial.get("prefix_template", ""))
            ttk.Entry(dialog, textvariable=template_var, width=30).grid(row=7, column=1, sticky="w", padx=6, pady=4)

            digits_var = tk.IntVar(value=int(initial.get("digits", default_digits_var.get())))
            ttk.Label(dialog, text="Digits").grid(row=8, column=0, sticky="e", padx=6, pady=4)
            ttk.Spinbox(dialog, from_=1, to=10, textvariable=digits_var, width=8).grid(
                row=8, column=1, sticky="w", padx=6, pady=4
            )

            start_var = tk.IntVar(value=int(initial.get("start_from", default_start_var.get())))
            ttk.Label(dialog, text="Start from").grid(row=9, column=0, sticky="e", padx=6, pady=4)
            ttk.Spinbox(dialog, from_=1, to=999999, textvariable=start_var, width=8).grid(
                row=9, column=1, sticky="w", padx=6, pady=4
            )

            preview_label = ttk.Label(dialog, text="")
            preview_label.grid(row=10, column=0, columnspan=2, sticky="w", padx=6, pady=4)

            def do_preview() -> None:
                brand_name = brand_var.get() if brand_var.get() != "Будь-який" else ""
                category_name = category_var.get() if category_var.get() != "Будь-яка" else ""
                prefix = sku_gen.render_prefix(template_var.get(), brand_name, category_name)
                preview_label.configure(text=f"Префікс: {prefix}")

            ttk.Button(dialog, text="Preview", command=do_preview).grid(row=7, column=2, padx=4, pady=4)

            def on_ok() -> None:
                rule = {
                    "name": name_var.get().strip(),
                    "enabled": bool(enabled_var.get()),
                    "priority": int(priority_var.get() or 0),
                    "match": {
                        "brand_id": None,
                        "category_id": None,
                        "include_subcategories": bool(include_sub_var.get()),
                        "name_contains": contains_var.get().strip(),
                    },
                    "prefix_template": template_var.get(),
                    "digits": int(digits_var.get() or default_digits_var.get()),
                    "start_from": int(start_var.get() or default_start_var.get()),
                }
                brand_choice = brand_var.get()
                if brand_choice != "Будь-який":
                    match_brand = next((b["id"] for b in brands if b["name"] == brand_choice), None)
                    rule["match"]["brand_id"] = match_brand
                category_choice = category_var.get()
                if category_choice != "Будь-яка":
                    match_category = next((c["id"] for c in categories if c["label"] == category_choice), None)
                    rule["match"]["category_id"] = match_category
                if idx is not None:
                    self.sku_rules_state[idx] = rule
                else:
                    self.sku_rules_state.append(rule)
                self._refresh_sku_rules_tree(brand_map, category_map)
                dialog.destroy()

            ttk.Button(dialog, text="Зберегти", command=on_ok).grid(row=11, column=0, padx=6, pady=6, sticky="e")
            ttk.Button(dialog, text="Скасувати", command=dialog.destroy).grid(row=11, column=1, padx=6, pady=6, sticky="w")
            dialog.bind("<Return>", lambda _e: on_ok())
            dialog.bind("<Escape>", lambda _e: dialog.destroy())
            dialog.wait_window()

        def current_index() -> Optional[int]:
            selection = self.sku_rules_tree.selection()
            if not selection:
                return None
            try:
                return int(selection[0])
            except ValueError:
                return None

        def add_rule() -> None:
            add_or_edit_rule()

        def edit_rule() -> None:
            idx = current_index()
            if idx is None or idx >= len(self.sku_rules_state):
                return
            add_or_edit_rule(self.sku_rules_state[idx], idx)

        def delete_rule() -> None:
            idx = current_index()
            if idx is None or idx >= len(self.sku_rules_state):
                return
            del self.sku_rules_state[idx]
            self._refresh_sku_rules_tree(brand_map, category_map)

        def move_rule(delta: int) -> None:
            idx = current_index()
            if idx is None:
                return
            target = idx + delta
            if target < 0 or target >= len(self.sku_rules_state):
                return
            self.sku_rules_state[idx], self.sku_rules_state[target] = (
                self.sku_rules_state[target],
                self.sku_rules_state[idx],
            )
            self._refresh_sku_rules_tree(brand_map, category_map)
            self.sku_rules_tree.selection_set(str(target))

        def test_rule() -> None:
            idx = current_index()
            if idx is None or idx >= len(self.sku_rules_state):
                return
            existing_products = db.list_products()
            default_brand = brands[0] if brands else None
            default_category = categories[0] if categories else None
            default_name = ""
            if existing_products:
                first = existing_products[0]
                default_brand = {"id": first["brand_id"], "name": first["brand"]}
                default_category = {"id": first["category_id"], "name": first["category"]}
                default_name = first["name"]

            test_dialog = tk.Toplevel(self.frame)
            test_dialog.title("Тест генерації SKU")
            test_dialog.transient(self.frame.winfo_toplevel())
            test_dialog.grab_set()

            ttk.Label(test_dialog, text="Назва").grid(row=0, column=0, sticky="e", padx=6, pady=4)
            name_var = tk.StringVar(value=default_name)
            ttk.Entry(test_dialog, textvariable=name_var, width=30).grid(row=0, column=1, sticky="w", padx=6, pady=4)

            ttk.Label(test_dialog, text="Бренд").grid(row=1, column=0, sticky="e", padx=6, pady=4)
            brand_var = tk.StringVar()
            ttk.Combobox(
                test_dialog, textvariable=brand_var, values=["(без)"] + brand_names, width=28, state="readonly"
            ).grid(row=1, column=1, sticky="w", padx=6, pady=4)
            if default_brand and default_brand.get("name") in brand_names:
                brand_var.set(default_brand.get("name"))
            else:
                brand_var.set("(без)")

            ttk.Label(test_dialog, text="Категорія").grid(row=2, column=0, sticky="e", padx=6, pady=4)
            category_labels = ["(без)"] + [c["label"] for c in categories]
            category_var = tk.StringVar()
            ttk.Combobox(
                test_dialog, textvariable=category_var, values=category_labels, width=28, state="readonly"
            ).grid(row=2, column=1, sticky="w", padx=6, pady=4)
            if default_category and default_category.get("label") in category_labels:
                category_var.set(default_category.get("label"))
            else:
                category_var.set("(без)")

            def on_test_ok() -> None:
                selected_brand = next((b for b in brands if b["name"] == brand_var.get()), None)
                selected_category = next((c for c in categories if c["label"] == category_var.get()), None)
                sku = sku_gen.generate_next_sku(self.settings, selected_brand, selected_category, name_var.get())
                messagebox.showinfo("Тест SKU", f"Згенерований SKU: {sku}")
                test_dialog.destroy()

            ttk.Button(test_dialog, text="Згенерувати", command=on_test_ok).grid(row=3, column=0, padx=6, pady=6)
            ttk.Button(test_dialog, text="Скасувати", command=test_dialog.destroy).grid(row=3, column=1, padx=6, pady=6)
            test_dialog.bind("<Return>", lambda _e: on_test_ok())
            test_dialog.bind("<Escape>", lambda _e: test_dialog.destroy())
            test_dialog.wait_window()

        btns = ttk.Frame(sku_frame)
        btns.grid(row=5, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        ttk.Button(btns, text="Додати", command=add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Редагувати", command=edit_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Видалити", command=delete_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Вгору", command=lambda: move_rule(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Вниз", command=lambda: move_rule(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Тест", command=test_rule).pack(side=tk.LEFT, padx=2)

        currency_frame = ttk.LabelFrame(self.defaults_tab, text="Валюти")
        currency_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        currencies = db.list_currencies(active_only=False)
        currency_codes = [c["code"] for c in currencies]
        currency_var = self._add_var(
            "defaults.currency.base_code", tk.StringVar(value=self._value_for_path("defaults.currency.base_code"))
        )
        ttk.Label(currency_frame, text="Базова валюта:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(currency_frame, textvariable=currency_var, values=currency_codes, width=12, state="readonly").grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

    def build_files_tab(self) -> None:
        workdir_var = self._add_var("files.working_dir", tk.StringVar(value=self._value_for_path("files.working_dir")))
        ttk.Label(self.files_tab, text="Робоча директорія:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(self.files_tab, textvariable=workdir_var, width=40).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(self.files_tab, text="Огляд", command=lambda: self.choose_workdir(workdir_var)).grid(
            row=0, column=2, padx=4, pady=4
        )

        recent_limit_var = self._add_var("files.recent_limit", tk.IntVar(value=self._value_for_path("files.recent_limit")))
        ttk.Label(self.files_tab, text="Кількість недавніх:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.files_tab, from_=0, to=50, textvariable=recent_limit_var, width=8).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        self.recent_label = ttk.Label(
            self.files_tab,
            text=f"Збережено недавніх: {len(self.settings.get('files', 'recent_items', default=[]))}",
        )
        self.recent_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Button(self.files_tab, text="Очистити", command=self.clear_recent).grid(row=2, column=2, padx=4, pady=4)

        encoding_var = self._add_var("files.encoding", tk.StringVar(value=self._value_for_path("files.encoding")))
        ttk.Label(self.files_tab, text="Кодування тексту:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.files_tab, textvariable=encoding_var, values=["utf-8", "cp1251", "latin-1", "utf-16"], width=12
        ).grid(row=3, column=1, sticky="w", padx=6, pady=4)

    def build_ui_tab(self) -> None:
        layout_var = self._add_var("ui.panel_layout", tk.StringVar(value=self._value_for_path("ui.panel_layout")))
        ttk.Label(self.ui_tab, text="Розташування панелей:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.ui_tab,
            textvariable=layout_var,
            values=["Авто", "Вертикально", "Горизонтально"],
            width=16,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        status_var = self._add_var("ui.status_bar", tk.BooleanVar(value=self._value_for_path("ui.status_bar")))
        ttk.Checkbutton(self.ui_tab, text="Показувати рядок стану", variable=status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        compact_var = self._add_var("ui.compact_mode", tk.BooleanVar(value=self._value_for_path("ui.compact_mode")))
        ttk.Checkbutton(self.ui_tab, text="Компактний режим", variable=compact_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        fullscreen_var = self._add_var("ui.fullscreen", tk.BooleanVar(value=self._value_for_path("ui.fullscreen")))
        ttk.Checkbutton(self.ui_tab, text="Повноекранний режим", variable=fullscreen_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        volume_var = self._add_var("ui.notifications_volume", tk.IntVar(value=self._value_for_path("ui.notifications_volume")))
        ttk.Label(self.ui_tab, text="Гучність сповіщень:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        ttk.Scale(self.ui_tab, from_=0, to=100, variable=volume_var, orient=tk.HORIZONTAL, length=160).grid(
            row=4, column=1, sticky="w", padx=6, pady=4
        )

        duration_var = self._add_var(
            "ui.notifications_duration", tk.IntVar(value=self._value_for_path("ui.notifications_duration"))
        )
        ttk.Label(self.ui_tab, text="Тривалість сповіщень (сек):").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.ui_tab, from_=1, to=30, textvariable=duration_var, width=8).grid(
            row=5, column=1, sticky="w", padx=6, pady=4
        )

    def build_editor_tab(self) -> None:
        family_var = self._add_var("editor.font_family", tk.StringVar(value=self._value_for_path("editor.font_family")))
        ttk.Label(self.editor_tab, text="Шрифт редактора:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.editor_tab, textvariable=family_var, values=sorted(tkfont.families()), width=24).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        size_var = self._add_var("editor.font_size", tk.IntVar(value=self._value_for_path("editor.font_size")))
        ttk.Label(self.editor_tab, text="Розмір шрифту:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=8, to=28, textvariable=size_var, width=6).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        syntax_var = self._add_var(
            "editor.syntax_highlighting", tk.BooleanVar(value=self._value_for_path("editor.syntax_highlighting"))
        )
        ttk.Checkbutton(self.editor_tab, text="Підсвічування синтаксису", variable=syntax_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        indent_tabs_var = self._add_var(
            "editor.indent_with_tabs", tk.BooleanVar(value=self._value_for_path("editor.indent_with_tabs"))
        )
        ttk.Checkbutton(self.editor_tab, text="Використовувати табуляцію для відступів", variable=indent_tabs_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        tab_width_var = self._add_var("editor.tab_width", tk.IntVar(value=self._value_for_path("editor.tab_width")))
        ttk.Label(self.editor_tab, text="Ширина табуляції:").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=2, to=12, textvariable=tab_width_var, width=6).grid(
            row=4, column=1, sticky="w", padx=6, pady=4
        )

        line_numbers_var = self._add_var("editor.line_numbers", tk.BooleanVar(value=self._value_for_path("editor.line_numbers")))
        ttk.Checkbutton(self.editor_tab, text="Показувати номери рядків", variable=line_numbers_var).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        minimap_var = self._add_var("editor.minimap", tk.BooleanVar(value=self._value_for_path("editor.minimap")))
        ttk.Checkbutton(self.editor_tab, text="Вмикати мінімеп", variable=minimap_var).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        auto_format_var = self._add_var("editor.auto_format", tk.BooleanVar(value=self._value_for_path("editor.auto_format")))
        ttk.Checkbutton(self.editor_tab, text="Автоматичне форматування", variable=auto_format_var).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        autocomplete_var = self._add_var("editor.autocomplete", tk.BooleanVar(value=self._value_for_path("editor.autocomplete")))
        ttk.Checkbutton(self.editor_tab, text="Автодоповнення", variable=autocomplete_var).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        length_limit_var = self._add_var(
            "editor.line_length_limit", tk.IntVar(value=self._value_for_path("editor.line_length_limit"))
        )
        ttk.Label(self.editor_tab, text="Фільтр по довжині рядка:").grid(row=9, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(self.editor_tab, from_=40, to=240, textvariable=length_limit_var, width=6).grid(
            row=9, column=1, sticky="w", padx=6, pady=4
        )

    def build_hotkeys_tab(self) -> None:
        profile_var = self._add_var("hotkeys.profile", tk.StringVar(value=self._value_for_path("hotkeys.profile")))
        ttk.Label(self.hotkeys_tab, text="Профіль клавіш:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            self.hotkeys_tab, textvariable=profile_var, values=["Типовий", "Emacs", "Vim"], width=12
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        allow_custom_var = self._add_var(
            "hotkeys.allow_custom", tk.BooleanVar(value=self._value_for_path("hotkeys.allow_custom"))
        )
        ttk.Checkbutton(self.hotkeys_tab, text="Дозволити переназначення", variable=allow_custom_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

    def build_support_tab(self) -> None:
        log_var = self._add_var("support.log_level", tk.StringVar(value=self._value_for_path("support.log_level")))
        ttk.Label(self.support_tab, text="Рівень логування:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.support_tab, textvariable=log_var, values=["DEBUG", "INFO", "WARNING", "ERROR"], width=12).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        sysinfo_var = self._add_var(
            "support.collect_system_info", tk.BooleanVar(value=self._value_for_path("support.collect_system_info"))
        )
        ttk.Checkbutton(self.support_tab, text="Збирати системну інформацію", variable=sysinfo_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        autoreport_var = self._add_var(
            "support.auto_error_reports", tk.BooleanVar(value=self._value_for_path("support.auto_error_reports"))
        )
        ttk.Checkbutton(self.support_tab, text="Надсилати звіти про помилки автоматично", variable=autoreport_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )

        docs_var = self._add_var("support.docs_url", tk.StringVar(value=self._value_for_path("support.docs_url")))
        ttk.Label(self.support_tab, text="Документація/FAQ:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(self.support_tab, textvariable=docs_var, width=40).grid(row=3, column=1, sticky="w", padx=6, pady=4)

    def _value_for_path(self, path: str):
        if path == "general.language":
            return self.settings.get("general", "language") or ""
        if path == "general.theme":
            return self.settings.get("general", "theme") or ""
        if path == "defaults.product.unit":
            return self.settings.get("defaults", "product", "unit") or "pcs"
        if path == "defaults.product.brand":
            return self.settings.get("defaults", "product", "brand") or ""
        if path == "defaults.product.category":
            return self.settings.get("defaults", "product", "category") or ""
        if path == "defaults.product.barcode_prefix":
            return _sanitize_barcode_prefix(self.settings.get("defaults", "product", "barcode_prefix") or "")
        if path == "defaults.product.sku_generator.enabled":
            return bool(self.settings.get("defaults", "product", "sku_generator", "enabled"))
        if path == "defaults.product.sku_generator.default.prefix_template":
            return self.settings.get("defaults", "product", "sku_generator", "default", "prefix_template") or ""
        if path == "defaults.product.sku_generator.default.digits":
            return int(self.settings.get("defaults", "product", "sku_generator", "default", "digits") or 5)
        if path == "defaults.product.sku_generator.default.start_from":
            return int(self.settings.get("defaults", "product", "sku_generator", "default", "start_from") or 1)
        if path == "defaults.currency.base_code":
            return self.settings.get("defaults", "currency", "base_code") or get_base_currency_code()
        if path == "files.working_dir":
            return str(self.default_workdir())
        if path == "files.recent_limit":
            return int(self.settings.get("files", "recent_limit") or 10)
        if path == "files.encoding":
            return self.settings.get("files", "encoding") or ""
        if path == "ui.panel_layout":
            return self.settings.get("ui", "panel_layout") or ""
        if path == "ui.status_bar":
            return bool(self.settings.get("ui", "status_bar"))
        if path == "ui.compact_mode":
            return bool(self.settings.get("ui", "compact_mode"))
        if path == "ui.fullscreen":
            return bool(self.settings.get("ui", "fullscreen"))
        if path == "ui.notifications_volume":
            return int(self.settings.get("ui", "notifications_volume") or 70)
        if path == "ui.notifications_duration":
            return int(self.settings.get("ui", "notifications_duration") or 3)
        if path == "editor.font_family":
            return self.settings.get("editor", "font_family") or ""
        if path == "editor.font_size":
            return int(self.settings.get("editor", "font_size") or 10)
        if path == "editor.syntax_highlighting":
            return bool(self.settings.get("editor", "syntax_highlighting"))
        if path == "editor.indent_with_tabs":
            return bool(self.settings.get("editor", "indent_with_tabs"))
        if path == "editor.tab_width":
            return int(self.settings.get("editor", "tab_width") or 4)
        if path == "editor.line_numbers":
            return bool(self.settings.get("editor", "line_numbers"))
        if path == "editor.minimap":
            return bool(self.settings.get("editor", "minimap"))
        if path == "editor.auto_format":
            return bool(self.settings.get("editor", "auto_format"))
        if path == "editor.autocomplete":
            return bool(self.settings.get("editor", "autocomplete"))
        if path == "editor.line_length_limit":
            return int(self.settings.get("editor", "line_length_limit") or 120)
        if path == "hotkeys.profile":
            return self.settings.get("hotkeys", "profile") or ""
        if path == "hotkeys.allow_custom":
            return bool(self.settings.get("hotkeys", "allow_custom"))
        if path == "support.log_level":
            return self.settings.get("support", "log_level") or ""
        if path == "support.collect_system_info":
            return bool(self.settings.get("support", "collect_system_info"))
        if path == "support.auto_error_reports":
            return bool(self.settings.get("support", "auto_error_reports"))
        if path == "support.docs_url":
            return self.settings.get("support", "docs_url") or ""
        return ""

    def default_workdir(self) -> Path:
        path = self.settings.get("files", "working_dir") or str(get_data_dir())
        try:
            return Path(path)
        except Exception:
            return get_data_dir()

    def choose_workdir(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(initialdir=var.get() or str(self.default_workdir()))
        if path:
            var.set(path)

    def clear_recent(self) -> None:
        self.recent_cleared = True
        if self.recent_label:
            self.recent_label.configure(text="Збережено недавніх: 0")

    def _add_var(self, path: str, var: tk.Variable) -> tk.Variable:
        self.vars[path] = var
        return var

    def _on_save(self) -> None:
        for path, var in self.vars.items():
            value = var.get()
            if path == "defaults.product.barcode_prefix":
                value = _sanitize_barcode_prefix(str(value))
            keys = path.split(".")
            self.settings.set(value, *keys)
        self.settings.set(self.sku_rules_state, "defaults", "product", "sku_generator", "rules")
        base_code = str(self.vars.get("defaults.currency.base_code", tk.StringVar()).get()).strip().upper()
        if base_code:
            currencies = {c["code"]: c for c in db.list_currencies(active_only=False)}
            selected = currencies.get(base_code)
            if selected:
                self.settings.set(selected["name"], "defaults", "currency", "base_name")
                self.settings.set(int(selected["decimals"]), "defaults", "currency", "base_decimals")
            else:
                self.settings.set(base_code, "defaults", "currency", "base_name")
                self.settings.set(get_base_currency_decimals(), "defaults", "currency", "base_decimals")
        if self.recent_cleared:
            self.settings.set([], "files", "recent_items")
        self.settings.save()
        messagebox.showinfo("Налаштування", "Збережено")
        self.on_settings_saved()

    def _flatten_categories(self) -> list[dict]:
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

    def _load_sku_rules_state(self) -> None:
        rules = self.settings.get("defaults", "product", "sku_generator", "rules") or []
        try:
            self.sku_rules_state = [dict(rule) for rule in rules]
        except Exception:
            self.sku_rules_state = []

    def _refresh_sku_rules_tree(self, brand_map: dict[int, dict], category_map: dict[int, dict]) -> None:
        tree = getattr(self, "sku_rules_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for idx, rule in enumerate(self.sku_rules_state):
            match = rule.get("match") or {}
            brand_label = brand_map.get(match.get("brand_id"), {}).get("name", "Будь-який")
            category_label = category_map.get(match.get("category_id"), {}).get("label", "Будь-яка")
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    rule.get("priority", 0),
                    "Так" if rule.get("enabled") else "Ні",
                    rule.get("name", ""),
                    brand_label,
                    category_label,
                    "Так" if match.get("include_subcategories") else "",
                    match.get("name_contains", ""),
                    rule.get("prefix_template", ""),
                    rule.get("digits", ""),
                    rule.get("start_from", ""),
                ),
            )
