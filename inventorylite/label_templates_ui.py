from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import db
import labels
from ui_components import simple_prompt
from utils import open_file, show_error


DEFAULT_TEMPLATE = {
    "code": "A4_3x8_70x35",
    "title": "A4 3x8",
    "kind": "sheet",
    "orientation": "portrait",
    "page_w_mm": 210,
    "page_h_mm": 297,
    "cols": 3,
    "rows": 8,
    "label_w_mm": 70,
    "label_h_mm": 35,
    "gap_x_mm": 2,
    "gap_y_mm": 2,
    "margin_left_mm": 5,
    "margin_right_mm": 5,
    "margin_top_mm": 10,
    "margin_bottom_mm": 10,
    "offset_x_mm": 0,
    "offset_y_mm": 0,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "is_active": 1,
    "is_default": 0,
}


class TemplateManagerDialog:
    def __init__(self, parent) -> None:
        self.parent = parent
        self.root = tk.Toplevel(parent)
        self.root.title("Шаблони етикеток")
        self.root.grab_set()
        self.root.resizable(True, True)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self.root,
            columns=(
                "is_default",
                "title",
                "code",
                "kind",
                "label_size",
                "grid",
                "page_size",
            ),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("is_default", text="Типовий")
        self.tree.heading("title", text="Назва")
        self.tree.heading("code", text="Код")
        self.tree.heading("kind", text="Тип")
        self.tree.heading("label_size", text="Розмір етикетки")
        self.tree.heading("grid", text="Сітка")
        self.tree.heading("page_size", text="Розмір сторінки")
        self.tree.column("is_default", width=70, anchor="center")
        self.tree.column("kind", width=70, anchor="center")
        self.tree.bind("<Double-1>", lambda e: self.edit_template())
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        btns = ttk.Frame(self.root)
        btns.grid(row=1, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Додати…", command=self.add_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Редагувати…", command=self.edit_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Дублювати…", command=self.duplicate_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Зробити типовим", command=self.make_default).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Експорт JSON…", command=self.export_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Імпорт JSON…", command=self.import_template).pack(side=tk.LEFT, padx=4)

        self.load_templates()
        self.root.wait_window(self.root)

    def load_templates(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            templates = db.list_label_templates(active_only=False)
        except Exception:
            logging.exception("Failed to load label templates")
            show_error("Шаблони", "Не вдалося завантажити шаблони")
            return
        for tpl in templates:
            label_size = f"{tpl['label_w_mm']}×{tpl['label_h_mm']} мм"
            grid = f"{tpl['cols']}×{tpl['rows']}"
            page_size = f"{tpl['page_w_mm']}×{tpl['page_h_mm']} мм"
            self.tree.insert(
                "",
                tk.END,
                iid=str(tpl["id"]),
                values=("✓" if tpl["is_default"] else "", tpl["title"], tpl["code"], tpl["kind"], label_size, grid, page_size),
            )

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except (TypeError, ValueError):
            return None

    def add_template(self) -> None:
        dlg = TemplateEditorDialog(self.parent)
        if dlg.saved:
            self.load_templates()

    def edit_template(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        dlg = TemplateEditorDialog(self.parent, tpl_id)
        if dlg.saved:
            self.load_templates()

    def duplicate_template(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        tpl = db.get_label_template(tpl_id)
        if not tpl:
            show_error("Шаблони", "Шаблон не знайдено")
            return
        defaults = [f"{tpl['code']}_copy", f"{tpl['title']} копія"]
        values = simple_prompt("Дублювати шаблон", ["Новий код", "Назва"], defaults)
        if not values:
            return
        try:
            db.duplicate_label_template(tpl_id, values[0], values[1])
            self.load_templates()
        except Exception as exc:
            logging.exception("Failed to duplicate template")
            show_error("Шаблони", str(exc))

    def delete_template(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        if not messagebox.askyesno("Шаблони", "Видалити вибраний шаблон?"):
            return
        try:
            db.delete_label_template(tpl_id)
            self.load_templates()
        except ValueError as exc:
            show_error("Шаблони", str(exc))
        except Exception:
            logging.exception("Failed to delete template")
            show_error("Шаблони", "Не вдалося видалити шаблон")

    def make_default(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        try:
            db.set_default_label_template(tpl_id)
            self.load_templates()
        except Exception:
            logging.exception("Failed to set default template")
            show_error("Шаблони", "Не вдалося призначити типовим")

    def export_template(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        data = db.get_label_template_full(tpl_id)
        if not data:
            show_error("Шаблони", "Шаблон не знайдено")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Експорт шаблону",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logging.exception("Failed to export template")
            show_error("Шаблони", "Не вдалося зберегти файл")

    def import_template(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Імпорт шаблону",
            filetypes=[("JSON", "*.json"), ("Усі файли", "*.*")],
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            show_error("Шаблони", "Некоректний файл JSON")
            return
        if not isinstance(data, dict) or "template" not in data or "elements" not in data:
            show_error("Шаблони", "Файл не містить даних шаблону")
            return
        tpl = data.get("template") or {}
        base_code = str(tpl.get("code") or "IMPORTED")
        new_code = base_code
        counter = 1
        while db.get_label_template_by_code(new_code):
            new_code = f"{base_code}_{counter}"
            counter += 1
        tpl["code"] = new_code
        if counter > 1:
            tpl["title"] = f"{tpl.get('title', 'Шаблон')} ({new_code})"
        payload = {"template": tpl, "elements": data.get("elements") or []}
        try:
            db.create_label_template(payload)
            self.load_templates()
        except Exception as exc:
            logging.exception("Failed to import template")
            show_error("Шаблони", str(exc))


class TemplateEditorDialog:
    def __init__(self, parent, template_id: int | None = None, settings=None) -> None:
        self.parent = parent
        self.settings = settings
        self.template_id = template_id
        self.saved = False

        self.root = tk.Toplevel(parent)
        self.root.title("Редактор шаблону")
        self.root.grab_set()
        self.root.resizable(True, True)

        self.template_vars: dict[str, tk.StringVar] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.elements: list[dict[str, Any]] = []

        self._load_data()
        self._build_ui()
        self.root.wait_window(self.root)

    def _load_data(self) -> None:
        if self.template_id:
            data = db.get_label_template_full(self.template_id)
        else:
            data = None
        tpl = data.get("template") if data else None
        elements = data.get("elements") if data else None
        tpl_data = DEFAULT_TEMPLATE.copy()
        if tpl:
            tpl_data.update({k: tpl.get(k, v) for k, v in tpl_data.items()})
            tpl_data["id"] = tpl.get("id")
        self.template_vars = {k: tk.StringVar(value=str(v)) for k, v in tpl_data.items() if k not in {"is_active", "is_default"}}
        # Explicit vars for numeric/int flags
        self.bool_vars["is_active"] = tk.BooleanVar(value=bool(tpl_data.get("is_active", 1)))
        self.bool_vars["is_default"] = tk.BooleanVar(value=bool(tpl_data.get("is_default", 0)))

        self.elements = []
        for idx, el in enumerate(elements or []):
            copied = dict(el)
            copied.setdefault("options", {})
            copied.pop("options_json", None)
            copied["sort_order"] = copied.get("sort_order", idx)
            self.elements.append(copied)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)

        tpl_frame = ttk.LabelFrame(main, text="Параметри шаблону")
        tpl_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
        tpl_frame.columnconfigure(3, weight=1)

        def add_field(label: str, key: str, row: int, col: int = 0, width: int = 12):
            ttk.Label(tpl_frame, text=label).grid(row=row, column=col * 2, padx=4, pady=2, sticky="w")
            entry = ttk.Entry(tpl_frame, textvariable=self.template_vars[key], width=width)
            entry.grid(row=row, column=col * 2 + 1, padx=4, pady=2, sticky="w")
            return entry

        add_field("Назва", "title", 0, 0, width=24)
        add_field("Код", "code", 0, 1, width=16)
        ttk.Label(tpl_frame, text="Тип").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        kind_combo = ttk.Combobox(
            tpl_frame,
            textvariable=self.template_vars.setdefault("kind", tk.StringVar(value="sheet")),
            state="readonly",
            values=["sheet", "thermal"],
            width=14,
        )
        kind_combo.grid(row=1, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(tpl_frame, text="Орієнтація").grid(row=1, column=2, padx=4, pady=2, sticky="w")
        orient_combo = ttk.Combobox(
            tpl_frame,
            textvariable=self.template_vars.setdefault("orientation", tk.StringVar(value="portrait")),
            state="readonly",
            values=["portrait", "landscape"],
            width=14,
        )
        orient_combo.grid(row=1, column=3, padx=4, pady=2, sticky="w")

        add_field("Ширина сторінки, мм", "page_w_mm", 2, 0)
        add_field("Висота сторінки, мм", "page_h_mm", 2, 1)
        add_field("Колонки", "cols", 3, 0)
        add_field("Рядки", "rows", 3, 1)
        add_field("Ширина етикетки, мм", "label_w_mm", 4, 0)
        add_field("Висота етикетки, мм", "label_h_mm", 4, 1)
        add_field("Гор. зазор, мм", "gap_x_mm", 5, 0)
        add_field("Вер. зазор, мм", "gap_y_mm", 5, 1)
        add_field("Ліве поле, мм", "margin_left_mm", 6, 0)
        add_field("Верхнє поле, мм", "margin_top_mm", 6, 1)
        add_field("Праве поле, мм", "margin_right_mm", 7, 0)
        add_field("Нижнє поле, мм", "margin_bottom_mm", 7, 1)
        add_field("Зсув X, мм", "offset_x_mm", 8, 0)
        add_field("Зсув Y, мм", "offset_y_mm", 8, 1)
        add_field("Масштаб X", "scale_x", 9, 0)
        add_field("Масштаб Y", "scale_y", 9, 1)

        ttk.Checkbutton(tpl_frame, text="Активний", variable=self.bool_vars["is_active"]).grid(
            row=10, column=0, padx=4, pady=2, sticky="w"
        )

        # Elements section
        elems_frame = ttk.LabelFrame(main, text="Елементи")
        elems_frame.grid(row=1, column=0, sticky="nsew", pady=4)
        elems_frame.columnconfigure(0, weight=1)
        elems_frame.rowconfigure(1, weight=1)

        self.elem_tree = ttk.Treeview(
            elems_frame,
            columns=("sort", "type", "field", "x", "y", "w", "h", "font", "size", "align", "active"),
            show="headings",
            selectmode="browse",
            height=12,
        )
        for col, text, width in [
            ("sort", "#", 30),
            ("type", "Тип", 70),
            ("field", "Поле", 80),
            ("x", "X", 50),
            ("y", "Y", 50),
            ("w", "W", 50),
            ("h", "H", 50),
            ("font", "Шрифт", 80),
            ("size", "Розмір", 60),
            ("align", "Вирівн.", 70),
            ("active", "Актив.", 60),
        ]:
            self.elem_tree.heading(col, text=text)
            self.elem_tree.column(col, width=width, anchor="center")
        self.elem_tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        self.elem_tree.bind("<<TreeviewSelect>>", lambda e: self._fill_element_form())

        elem_btns = ttk.Frame(elems_frame)
        elem_btns.grid(row=1, column=0, columnspan=4, pady=4)
        ttk.Button(elem_btns, text="Додати текст", command=self.add_text_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Додати штрихкод", command=self.add_barcode_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Видалити", command=self.delete_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Вгору", command=lambda: self.move_element(-1)).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Вниз", command=lambda: self.move_element(1)).pack(side=tk.LEFT, padx=3)

        # Element form
        form = ttk.LabelFrame(main, text="Властивості елемента")
        form.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=4)
        for i in range(2):
            form.columnconfigure(i, weight=1)

        self.element_vars: dict[str, tk.Variable] = {
            "element_type": tk.StringVar(value="text"),
            "field_key": tk.StringVar(value="code"),
            "x_mm": tk.StringVar(value="0"),
            "y_mm": tk.StringVar(value="0"),
            "w_mm": tk.StringVar(value="50"),
            "h_mm": tk.StringVar(value="10"),
            "rotation_deg": tk.StringVar(value="0"),
            "align": tk.StringVar(value="left"),
            "font_name": tk.StringVar(value="Helvetica"),
            "font_size": tk.StringVar(value="9"),
            "max_chars": tk.StringVar(value=""),
            "options.text_template": tk.StringVar(value="{code}"),
            "options.bar_height_mm": tk.StringVar(value="20"),
            "options.human_readable": tk.BooleanVar(value=True),
            "is_active": tk.BooleanVar(value=True),
        }

        def ef(label: str, key: str, row: int, width: int = 12):
            ttk.Label(form, text=label).grid(row=row, column=0, padx=4, pady=2, sticky="w")
            entry = ttk.Entry(form, textvariable=self.element_vars[key], width=width)
            entry.grid(row=row, column=1, padx=4, pady=2, sticky="w")
            return entry

        ef("Тип", "element_type", 0)
        ef("Поле", "field_key", 1)
        ef("X, мм", "x_mm", 2)
        ef("Y, мм", "y_mm", 3)
        ef("W, мм", "w_mm", 4)
        ef("H, мм", "h_mm", 5)
        ef("Поворот", "rotation_deg", 6)
        ttk.Label(form, text="Вирівнювання").grid(row=7, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(form, textvariable=self.element_vars["align"], values=["left", "center", "right"], state="readonly").grid(
            row=7, column=1, padx=4, pady=2, sticky="w"
        )
        ef("Шрифт", "font_name", 8)
        ef("Розмір", "font_size", 9)
        ef("Макс. символів", "max_chars", 10)
        ef("Шаблон тексту", "options.text_template", 11, width=24)
        ef("Висота штрихкоду", "options.bar_height_mm", 12)
        ttk.Checkbutton(form, text="Людське читання", variable=self.element_vars["options.human_readable"]).grid(
            row=13, column=1, padx=4, pady=2, sticky="w"
        )
        ttk.Checkbutton(form, text="Активний", variable=self.element_vars["is_active"]).grid(
            row=14, column=1, padx=4, pady=2, sticky="w"
        )

        ttk.Button(form, text="Оновити елемент", command=self.update_selected_element).grid(
            row=15, column=0, columnspan=2, pady=6
        )

        # Preview
        preview_frame = ttk.LabelFrame(main, text="Попередній перегляд")
        preview_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=4)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview_frame, height=220, background="white")
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        ttk.Button(preview_frame, text="Оновити прев'ю", command=self.draw_preview).grid(row=1, column=0, pady=4)

        action_frame = ttk.Frame(main)
        action_frame.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(action_frame, text="Тестовий PDF", command=self.generate_test_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Зберегти", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Закрити", command=self.root.destroy).pack(side=tk.LEFT, padx=5)

        self.refresh_elements_tree()
        self.draw_preview()

    def refresh_elements_tree(self) -> None:
        for i in self.elem_tree.get_children():
            self.elem_tree.delete(i)
        for idx, el in enumerate(self.elements):
            self.elem_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    idx,
                    el.get("element_type"),
                    el.get("field_key"),
                    el.get("x_mm"),
                    el.get("y_mm"),
                    el.get("w_mm"),
                    el.get("h_mm"),
                    el.get("font_name"),
                    el.get("font_size"),
                    el.get("align"),
                    "✓" if el.get("is_active", 1) else "",
                ),
            )

    def _fill_element_form(self) -> None:
        sel = self.elem_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.elements):
            return
        el = self.elements[idx]
        options = el.get("options") or {}
        mapping = {
            "element_type": el.get("element_type", "text"),
            "field_key": el.get("field_key", "code"),
            "x_mm": el.get("x_mm", 0),
            "y_mm": el.get("y_mm", 0),
            "w_mm": el.get("w_mm", 0),
            "h_mm": el.get("h_mm", 0),
            "rotation_deg": el.get("rotation_deg", 0),
            "align": el.get("align", "left"),
            "font_name": el.get("font_name", "Helvetica"),
            "font_size": el.get("font_size", 9),
            "max_chars": el.get("max_chars", ""),
            "options.text_template": options.get("text_template", "{code}"),
            "options.bar_height_mm": options.get("bar_height_mm", 20),
            "options.human_readable": bool(options.get("human_readable", True)),
            "is_active": bool(el.get("is_active", 1)),
        }
        for key, value in mapping.items():
            var = self.element_vars.get(key)
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            elif var is not None:
                var.set(str(value))

    def add_text_element(self) -> None:
        el = {
            "element_type": "text",
            "field_key": "name",
            "x_mm": 2,
            "y_mm": 2,
            "w_mm": 60,
            "h_mm": 8,
            "rotation_deg": 0,
            "align": "left",
            "font_name": "Helvetica",
            "font_size": 9,
            "max_chars": 0,
            "wrap": 0,
            "options": {"text_template": "{name}"},
            "sort_order": len(self.elements),
            "is_active": 1,
        }
        self.elements.append(el)
        self.refresh_elements_tree()

    def add_barcode_element(self) -> None:
        el = {
            "element_type": "barcode",
            "field_key": "code",
            "x_mm": 2,
            "y_mm": 12,
            "w_mm": 60,
            "h_mm": 20,
            "rotation_deg": 0,
            "align": "center",
            "font_name": "Helvetica",
            "font_size": 9,
            "max_chars": None,
            "wrap": 0,
            "options": {"bar_height_mm": 18, "human_readable": True},
            "sort_order": len(self.elements),
            "is_active": 1,
        }
        self.elements.append(el)
        self.refresh_elements_tree()

    def delete_element(self) -> None:
        sel = self.elem_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.elements):
            return
        self.elements.pop(idx)
        self.refresh_elements_tree()

    def move_element(self, direction: int) -> None:
        sel = self.elem_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.elements):
            return
        self.elements[idx], self.elements[new_idx] = self.elements[new_idx], self.elements[idx]
        self.refresh_elements_tree()
        self.elem_tree.selection_set(str(new_idx))

    def update_selected_element(self) -> None:
        sel = self.elem_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.elements):
            return
        el = self.elements[idx]
        options = el.get("options") or {}
        try:
            el.update(
                {
                    "element_type": self.element_vars["element_type"].get().strip(),
                    "field_key": self.element_vars["field_key"].get().strip() or None,
                    "x_mm": float(self.element_vars["x_mm"].get() or 0),
                    "y_mm": float(self.element_vars["y_mm"].get() or 0),
                    "w_mm": float(self.element_vars["w_mm"].get() or 0),
                    "h_mm": float(self.element_vars["h_mm"].get() or 0),
                    "rotation_deg": float(self.element_vars["rotation_deg"].get() or 0),
                    "align": self.element_vars["align"].get() or "left",
                    "font_name": self.element_vars["font_name"].get() or "Helvetica",
                    "font_size": float(self.element_vars["font_size"].get() or 9),
                    "max_chars": int(self.element_vars["max_chars"].get() or 0) or None,
                    "is_active": int(bool(self.element_vars["is_active"].get())),
                }
            )
            options["text_template"] = self.element_vars["options.text_template"].get() or "{code}"
            try:
                options["bar_height_mm"] = float(self.element_vars["options.bar_height_mm"].get() or 0)
            except ValueError:
                options["bar_height_mm"] = 0
            options["human_readable"] = bool(self.element_vars["options.human_readable"].get())
            el["options"] = options
            self.refresh_elements_tree()
        except ValueError:
            show_error("Елементи", "Некоректні значення елемента")

    def _collect_template_data(self) -> dict:
        tpl = {}
        for key, var in self.template_vars.items():
            value = var.get()
            tpl[key] = value
        tpl["is_active"] = 1 if self.bool_vars["is_active"].get() else 0
        tpl["is_default"] = 1 if self.bool_vars.get("is_default", tk.BooleanVar(value=0)).get() else 0

        try:
            tpl["page_w_mm"] = float(tpl.get("page_w_mm") or 0)
            tpl["page_h_mm"] = float(tpl.get("page_h_mm") or 0)
            tpl["cols"] = int(tpl.get("cols") or 0)
            tpl["rows"] = int(tpl.get("rows") or 0)
            tpl["label_w_mm"] = float(tpl.get("label_w_mm") or 0)
            tpl["label_h_mm"] = float(tpl.get("label_h_mm") or 0)
            tpl["gap_x_mm"] = float(tpl.get("gap_x_mm") or 0)
            tpl["gap_y_mm"] = float(tpl.get("gap_y_mm") or 0)
            tpl["margin_left_mm"] = float(tpl.get("margin_left_mm") or 0)
            tpl["margin_right_mm"] = float(tpl.get("margin_right_mm") or 0)
            tpl["margin_top_mm"] = float(tpl.get("margin_top_mm") or 0)
            tpl["margin_bottom_mm"] = float(tpl.get("margin_bottom_mm") or 0)
            tpl["offset_x_mm"] = float(tpl.get("offset_x_mm") or 0)
            tpl["offset_y_mm"] = float(tpl.get("offset_y_mm") or 0)
            tpl["scale_x"] = float(tpl.get("scale_x") or 0)
            tpl["scale_y"] = float(tpl.get("scale_y") or 0)
        except ValueError:
            raise ValueError("Некоректні числові поля")
        return tpl

    def _validate_template(self, tpl: dict) -> None:
        required_positive = [
            "page_w_mm",
            "page_h_mm",
            "cols",
            "rows",
            "label_w_mm",
            "label_h_mm",
            "scale_x",
            "scale_y",
        ]
        for key in required_positive:
            if tpl.get(key) is None or float(tpl[key]) <= 0:
                raise ValueError(f"Поле {key} має бути більше 0")

    def _collect_elements(self) -> list[dict]:
        for idx, el in enumerate(self.elements):
            el["sort_order"] = idx
            if "options" not in el:
                el["options"] = {}
        return self.elements

    def save(self) -> None:
        try:
            tpl = self._collect_template_data()
            self._validate_template(tpl)
            payload = {"template": tpl, "elements": self._collect_elements()}
            if self.template_id:
                db.update_label_template(self.template_id, payload)
            else:
                self.template_id = db.create_label_template(payload)
            self.saved = True
            self.root.destroy()
        except Exception as exc:
            logging.exception("Failed to save template")
            show_error("Шаблон", str(exc))

    def draw_preview(self) -> None:
        self.canvas.delete("all")
        try:
            tpl = self._collect_template_data()
        except Exception:
            return
        label_w = float(tpl.get("label_w_mm") or 1)
        label_h = float(tpl.get("label_h_mm") or 1)
        padding = 10
        canvas_w = int(self.canvas.winfo_width() or 300)
        canvas_h = int(self.canvas.winfo_height() or 200)
        scale = min((canvas_w - 2 * padding) / label_w, (canvas_h - 2 * padding) / label_h)
        scale = max(scale, 1)
        ox = padding
        oy = padding
        self.canvas.create_rectangle(ox, oy, ox + label_w * scale, oy + label_h * scale, outline="black")
        for el in self.elements:
            if not el.get("is_active", 1):
                color = "#cccccc"
            else:
                color = "#4287f5"
            x1 = ox + float(el.get("x_mm", 0)) * scale
            y1 = oy + float(el.get("y_mm", 0)) * scale
            x2 = x1 + float(el.get("w_mm", 0)) * scale
            y2 = y1 + float(el.get("h_mm", 0)) * scale
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color)
            self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=el.get("element_type"), fill=color)

    def generate_test_pdf(self) -> None:
        try:
            tpl = self._collect_template_data()
            self._validate_template(tpl)
            payload = {"template": tpl, "elements": self._collect_elements()}
            prefix = ""
            if self.settings:
                try:
                    prefix = self.settings.get("defaults", "product", "barcode_prefix") or ""
                except Exception:
                    prefix = ""
            tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
            labels.generate_product_labels_pdf_v2(
                tmp,
                [
                    {"sku": "TEST123", "name": "Тестовий товар", "aliases": []},
                ],
                barcode_prefix=prefix,
                qty_each=1,
                template_full=payload,
                include_aliases=False,
                start_row=1,
                start_col=1,
            )
            open_file(tmp)
        except Exception as exc:
            logging.exception("Failed to generate test PDF")
            show_error("Шаблон", str(exc))
