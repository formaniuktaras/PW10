from __future__ import annotations

import logging
import sqlite3
from typing import Optional, Callable

import tkinter as tk
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.text_norm import norm_text
from inventorylite.utils import show_error, Settings
from inventorylite.dialogs import category_prompt, select_category_dialog


class CategoriesTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        settings: Settings,
        flatten_categories_provider: Callable[[], list[dict]],
        on_categories_changed: Callable[[], None],
        on_products_refresh: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.settings = settings
        self.flatten_categories_provider = flatten_categories_provider
        self.on_categories_changed = on_categories_changed
        self.on_products_refresh = on_products_refresh

        self.frame = ttk.Frame(parent)

        self.categories_index: dict[int, dict] = {}
        self.category_search_var = tk.StringVar()

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self.frame)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Пошук").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.category_search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Знайти", command=self.refresh_categories).pack(side=tk.LEFT)

        btns = ttk.Frame(self.frame)
        btns.pack(fill=tk.X, padx=8)
        ttk.Button(btns, text="Коренева", command=lambda: self.add_category(parent_id=None)).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            btns,
            text="Підкатегорія",
            command=lambda: self.add_category(parent_id=self.selected_category_id()),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Перейменувати", command=self.edit_category).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Перемістити", command=self.move_category_ui).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Вище", command=lambda: self.bump_category(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Нижче", command=lambda: self.bump_category(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Службова/Прихована", command=self.toggle_category_flags).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити/Злити", command=self.delete_category).pack(side=tk.LEFT, padx=4)

        columns = ("products", "quantity", "flags")
        self.category_tree = ttk.Treeview(
            self.frame,
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
            self.on_products_refresh()
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
            self.on_products_refresh()
        except sqlite3.IntegrityError:
            show_error("Категорії", "Категорія з такою назвою вже існує.")
        except Exception as exc:
            logging.exception("Edit category error")
            show_error("Категорії", f"Не вдалося змінити категорію: {exc}")

    def move_category_ui(self) -> None:
        category_id = self.selected_category_id()
        if not category_id:
            show_error("Категорії", "Оберіть категорію для переміщення.")
            return
        exclude = {category_id}
        exclude.update(db.get_category_descendants(category_id))
        options = [(None, "(Корінь)")]
        for cat in self.flatten_categories_provider():
            if cat["id"] in exclude:
                continue
            options.append((cat["id"], cat["label"]))
        choice = select_category_dialog("Новий батько", options)
        if choice is None:
            return
        try:
            db.move_category(category_id, choice)
            self.refresh_categories()
            self.on_products_refresh()
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
            for cat in self.flatten_categories_provider():
                if cat["id"] == category_id:
                    continue
                options.append((cat["id"], cat["label"]))
            target = select_category_dialog("Цільова категорія", options)
        try:
            db.delete_category(category_id, target)
            self.refresh_categories()
            self.on_products_refresh()
        except ValueError as exc:
            show_error("Категорії", str(exc))
        except Exception as exc:
            logging.exception("Delete category error")
            show_error("Категорії", f"Не вдалося видалити категорію: {exc}")

    def refresh_categories(self) -> None:
        rows = db.list_categories(include_hidden=True)
        self.categories_index = {int(r["id"]): dict(r) for r in rows}
        search = norm_text(self.category_search_var.get())
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
            own_match = not search or search in norm_text(cat.get("name", ""))
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
        self.on_categories_changed()
