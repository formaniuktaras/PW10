from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from inventorylite import db
from inventorylite import labels
from inventorylite.ui_components import simple_prompt
from inventorylite.utils import open_file, show_error


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
    def __init__(self, parent, settings=None) -> None:
        self.parent = parent
        self.settings = settings or getattr(parent, "settings", None)
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
        dlg = TemplateEditorDialog(self.parent, settings=self.settings)
        if dlg.saved:
            self.load_templates()

    def edit_template(self) -> None:
        tpl_id = self._selected_id()
        if not tpl_id:
            messagebox.showwarning("Шаблони", "Оберіть шаблон")
            return
        dlg = TemplateEditorDialog(self.parent, tpl_id, settings=self.settings)
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
        tpl["is_default"] = 0
        payload = {"template": tpl, "elements": data.get("elements") or []}
        try:
            db.create_label_template(payload)
            self.load_templates()
        except Exception as exc:
            logging.exception("Failed to import template")
            show_error("Шаблони", str(exc))


class ElementPropertiesDialog:
    def __init__(self, parent: TemplateEditorDialog):
        self.parent = parent
        self.root = tk.Toplevel(parent.root)
        self.root.title("Властивості елемента")
        self.root.transient(parent.root)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.withdraw()

        form = ttk.Frame(self.root, padding=8)
        form.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)

        for i in range(2):
            form.columnconfigure(i, weight=1)

        def ef(label: str, key: str, row: int, width: int = 12):
            ttk.Label(form, text=label).grid(row=row, column=0, padx=4, pady=2, sticky="w")
            entry = ttk.Entry(form, textvariable=self.parent.element_vars[key], width=width)
            entry.grid(row=row, column=1, padx=4, pady=2, sticky="w")
            return entry

        ttk.Label(form, text="Тип").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.parent.element_vars["element_type"],
            values=["text", "barcode", "rect", "line"],
            state="readonly",
        ).grid(row=0, column=1, padx=4, pady=2, sticky="w")
        ef("Поле", "field_key", 1)
        ef("X, мм", "x_mm", 2)
        ef("Y, мм", "y_mm", 3)
        ef("W, мм", "w_mm", 4)
        ef("H, мм", "h_mm", 5)
        ef("Поворот", "rotation_deg", 6)
        ttk.Label(form, text="Вирівнювання").grid(row=7, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.parent.element_vars["align"],
            values=["left", "center", "right"],
            state="readonly",
        ).grid(row=7, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(form, text="Шрифт").grid(row=8, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.parent.element_vars["font_name"],
            values=["IL_SANS", "IL_SANS_BOLD", "Helvetica"],
            state="normal",
        ).grid(row=8, column=1, padx=4, pady=2, sticky="w")
        ef("Розмір", "font_size", 9)
        self.parent._max_chars_entry = ef("Макс. символів", "max_chars", 10)
        ttk.Checkbutton(form, text="Перенос рядків (wrap)", variable=self.parent.element_vars["wrap"]).grid(
            row=11, column=1, padx=4, pady=2, sticky="w"
        )
        ef("Шаблон тексту", "options.text_template", 12, width=24)
        ef("Висота штрихкоду", "options.bar_height_mm", 13)
        ttk.Checkbutton(form, text="Людське читання", variable=self.parent.element_vars["options.human_readable"]).grid(
            row=14, column=1, padx=4, pady=2, sticky="w"
        )
        ttk.Checkbutton(form, text="Активний", variable=self.parent.element_vars["is_active"]).grid(
            row=15, column=1, padx=4, pady=2, sticky="w"
        )

        btns = ttk.Frame(form)
        btns.grid(row=16, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Оновити елемент", command=self.parent.update_selected_element).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Закрити", command=self.hide).pack(side=tk.LEFT, padx=4)

    def show_for_selected(self) -> None:
        if not self.parent.elem_tree.selection():
            messagebox.showwarning("Елементи", "Оберіть елемент")
            return
        self.parent._fill_element_form()
        self.bring_to_front()

    def bring_to_front(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

class TemplateEditorDialog:
    def __init__(self, parent, template_id: int | None = None, settings=None) -> None:
        self.parent = parent
        self.settings = settings
        self.template_id = template_id
        self.saved = False
        self.dirty = False

        self.root = tk.Toplevel(parent)
        self.root.title("Редактор шаблону")
        self.root.grab_set()
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(1200, int(sw * 0.92))
        h = min(820, int(sh * 0.88))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(950, w), min(650, h))

        self.base_title = "Редактор шаблону"

        self.template_vars: dict[str, tk.StringVar] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.elements: list[dict[str, Any]] = []
        self._code_entry = None

        self._preview_scale: float = 1.0
        self._elem_rect_ids: dict[int, int] = {}
        self._elem_handle_ids: dict[int, list[int]] = {}
        self._active_elem_index: int | None = None
        self._drag_mode: str | None = None
        self._resize_handle: str | None = None
        self._drag_start: dict[str, float] | None = None
        self._drag_last_values: tuple[float, float, float, float] | None = None
        self._preview_redraw_job: str | None = None

        self.snap_enabled_var = tk.BooleanVar(value=True)
        self.snap_step_var = tk.StringVar(value="0.5")
        self.status_var = tk.StringVar(value="")

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
        if self.template_id is None:
            base_code = str(tpl_data.get("code") or "")
            new_code = base_code
            counter = 1
            while new_code and db.get_label_template_by_code(new_code):
                new_code = f"{base_code}_{counter}"
                counter += 1
            if new_code and new_code != base_code:
                tpl_data["code"] = new_code
                if tpl_data.get("title"):
                    tpl_data["title"] = f"{tpl_data['title']} ({new_code})"
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
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        content = ttk.Frame(outer)
        content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(1, weight=1)

        tpl_frame = ttk.LabelFrame(content, text="Параметри шаблону")
        tpl_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
        tpl_frame.columnconfigure(3, weight=1)

        def add_field(label: str, key: str, row: int, col: int = 0, width: int = 12):
            ttk.Label(tpl_frame, text=label).grid(row=row, column=col * 2, padx=4, pady=2, sticky="w")
            entry = ttk.Entry(tpl_frame, textvariable=self.template_vars[key], width=width)
            entry.grid(row=row, column=col * 2 + 1, padx=4, pady=2, sticky="w")
            if key == "code":
                self._code_entry = entry
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
        elems_frame = ttk.LabelFrame(content, text="Елементи")
        elems_frame.grid(row=1, column=0, sticky="nsew", pady=4)
        elems_frame.columnconfigure(0, weight=1)
        elems_frame.rowconfigure(0, weight=1)

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
        self.elem_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.elem_tree.bind("<Double-1>", lambda e: self.properties_dialog.show_for_selected())

        self.element_vars: dict[str, tk.Variable] = {
            "element_type": tk.StringVar(value="text"),
            "field_key": tk.StringVar(value="code"),
            "x_mm": tk.StringVar(value="0"),
            "y_mm": tk.StringVar(value="0"),
            "w_mm": tk.StringVar(value="50"),
            "h_mm": tk.StringVar(value="10"),
            "rotation_deg": tk.StringVar(value="0"),
            "align": tk.StringVar(value="left"),
            "font_name": tk.StringVar(value="IL_SANS"),
            "font_size": tk.StringVar(value="9"),
            "max_chars": tk.StringVar(value=""),
            "wrap": tk.BooleanVar(value=False),
            "options.text_template": tk.StringVar(value="{code}"),
            "options.bar_height_mm": tk.StringVar(value="20"),
            "options.human_readable": tk.BooleanVar(value=True),
            "is_active": tk.BooleanVar(value=True),
        }

        self._max_chars_entry: ttk.Entry | None = None
        self.properties_dialog = ElementPropertiesDialog(self)

        elem_btns = ttk.Frame(elems_frame)
        elem_btns.grid(row=1, column=0, columnspan=4, pady=4)
        ttk.Button(elem_btns, text="Додати текст", command=self.add_text_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Додати штрихкод", command=self.add_barcode_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Видалити", command=self.delete_element).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Вгору", command=lambda: self.move_element(-1)).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Вниз", command=lambda: self.move_element(1)).pack(side=tk.LEFT, padx=3)
        ttk.Button(elem_btns, text="Властивості…", command=lambda: self.properties_dialog.show_for_selected()).pack(
            side=tk.LEFT, padx=3
        )

        # Preview
        preview_frame = ttk.LabelFrame(content, text="Попередній перегляд")
        preview_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=4)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview_frame, height=220, background="white")
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.canvas.bind("<Button-1>", self._on_canvas_button_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_button_release)
        self.canvas.bind("<Motion>", self._on_canvas_hover)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<KeyPress>", self._on_preview_keypress)

        snap_bar = ttk.Frame(preview_frame)
        snap_bar.grid(row=1, column=0, sticky="ew", padx=4)
        snap_bar.columnconfigure(3, weight=1)
        ttk.Checkbutton(snap_bar, text="Snap", variable=self.snap_enabled_var).grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Label(snap_bar, text="Крок, мм").grid(row=0, column=1, padx=4, pady=2, sticky="w")
        ttk.Entry(snap_bar, width=6, textvariable=self.snap_step_var).grid(row=0, column=2, padx=2, pady=2, sticky="w")
        ttk.Label(snap_bar, textvariable=self.status_var, foreground="#444").grid(row=0, column=3, padx=6, pady=2, sticky="w")

        ttk.Button(preview_frame, text="Оновити прев'ю", command=self.draw_preview).grid(row=2, column=0, pady=4)

        action_bar = ttk.Frame(outer)
        action_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(action_bar, text="Закрити", command=self.on_close).pack(side=tk.RIGHT, padx=5, pady=6)
        ttk.Button(action_bar, text="Зберегти шаблон", command=self.save_template).pack(side=tk.RIGHT, padx=5, pady=6)
        ttk.Button(action_bar, text="Тестовий PDF", command=self.generate_test_pdf).pack(side=tk.RIGHT, padx=5, pady=6)

        self.refresh_elements_tree()
        self.draw_preview()
        self._bind_dirty_traces()
        self._update_title()

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

    def _set_var_safe(self, var: tk.Variable, value: Any) -> None:
        if isinstance(var, tk.BooleanVar):
            var.set(bool(value))
            return
        if value is None:
            var.set("")
            return
        var.set(str(value))

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
            "font_name": el.get("font_name", "IL_SANS"),
            "font_size": el.get("font_size", 9),
            "max_chars": "" if el.get("max_chars") is None else el.get("max_chars"),
            "wrap": el.get("wrap", 0),
            "options.text_template": options.get("text_template", "{code}"),
            "options.bar_height_mm": options.get("bar_height_mm", 20),
            "options.human_readable": bool(options.get("human_readable", True)),
            "is_active": bool(el.get("is_active", 1)),
        }
        for key, value in mapping.items():
            var = self.element_vars.get(key)
            if var is not None:
                self._set_var_safe(var, value)

    def _on_tree_select(self, *_: Any) -> None:
        sel = self.elem_tree.selection()
        idx = int(sel[0]) if sel else None
        if idx is not None and idx < len(self.elements):
            self._active_elem_index = idx
            self._update_status_for_idx(idx)
        else:
            self._active_elem_index = None
            self.status_var.set("")
        self._fill_element_form()
        self.canvas.focus_set()
        self.draw_preview()

    def _parse_float(self, raw: str | None, default: float = 0.0) -> float:
        s = (raw or "").strip()
        if s == "":
            return float(default)
        s = s.replace(",", ".")
        return float(s)

    def _parse_optional_int(self, raw: str | None) -> int | None:
        s = (raw or "").strip()
        if s == "" or s.lower() in ("none", "null"):
            return None
        s = s.replace(",", ".")
        if s.endswith(".0"):
            s = s[:-2]
        return int(s)

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
            "font_name": "IL_SANS",
            "font_size": 9,
            "max_chars": 0,
            "wrap": 0,
            "options": {"text_template": "{name}"},
            "sort_order": len(self.elements),
            "is_active": 1,
        }
        self.elements.append(el)
        self.refresh_elements_tree()
        self.mark_dirty()

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
        self.mark_dirty()

    def delete_element(self) -> None:
        sel = self.elem_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.elements):
            return
        self.elements.pop(idx)
        self.refresh_elements_tree()
        self.mark_dirty()

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
        self.mark_dirty()

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
            max_chars = self._parse_optional_int(self.element_vars["max_chars"].get())
        except ValueError:
            show_error("Елементи", "Поле 'Макс. символів' має бути числом або порожнім.")
            if hasattr(self, "_max_chars_entry") and self._max_chars_entry:
                self._max_chars_entry.focus_set()
                self._max_chars_entry.selection_range(0, tk.END)
            return
        try:
            el.update(
                {
                    "element_type": self.element_vars["element_type"].get().strip(),
                    "field_key": self.element_vars["field_key"].get().strip() or None,
                    "x_mm": self._parse_float(self.element_vars["x_mm"].get(), 0),
                    "y_mm": self._parse_float(self.element_vars["y_mm"].get(), 0),
                    "w_mm": self._parse_float(self.element_vars["w_mm"].get(), 0),
                    "h_mm": self._parse_float(self.element_vars["h_mm"].get(), 0),
                    "rotation_deg": self._parse_float(self.element_vars["rotation_deg"].get(), 0),
                    "align": self.element_vars["align"].get() or "left",
                    "font_name": self.element_vars["font_name"].get() or "IL_SANS",
                    "font_size": self._parse_float(self.element_vars["font_size"].get(), 9),
                    "max_chars": max_chars,
                    "wrap": 1 if self.element_vars["wrap"].get() else 0,
                    "is_active": int(bool(self.element_vars["is_active"].get())),
                }
            )
            options["text_template"] = self.element_vars["options.text_template"].get() or "{code}"
            try:
                options["bar_height_mm"] = self._parse_float(self.element_vars["options.bar_height_mm"].get(), 0)
            except ValueError:
                options["bar_height_mm"] = 0
            options["human_readable"] = bool(self.element_vars["options.human_readable"].get())
            if el.get("element_type") == "barcode":
                try:
                    h_mm = float(el.get("h_mm", 0))
                    bar_h = float(options.get("bar_height_mm") or 0)
                    if bar_h > h_mm:
                        options["bar_height_mm"] = max(h_mm - 2, 1)
                        messagebox.showwarning(
                            "Елементи",
                            "Висота штрихкоду перевищує висоту елемента. Значення зменшено автоматично.",
                        )
                except Exception:
                    pass
            el["options"] = options
            self.refresh_elements_tree()
            self.mark_dirty()
            self.draw_preview()
            self._update_status_for_idx(idx)
        except ValueError:
            show_error("Елементи", "Перевірте числа (X, Y, W, H, Розмір, Макс. символів).")

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
        if not str(tpl.get("title", "")).strip():
            raise ValueError("Поле title не може бути порожнім")
        if not str(tpl.get("code", "")).strip():
            raise ValueError("Поле code не може бути порожнім")
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
        cleaned = []
        for idx, el in enumerate(self.elements):
            copy = dict(el)
            copy.pop("options_json", None)
            copy["sort_order"] = idx
            copy["wrap"] = 1 if copy.get("wrap") else 0
            copy["is_active"] = 1 if copy.get("is_active", 1) else 0
            copy["options"] = dict(copy.get("options") or {})
            cleaned.append(copy)
        return cleaned

    def build_payload(self) -> dict:
        tpl = self._collect_template_data()
        self._validate_template(tpl)
        elements = self._collect_elements()
        return {"template": tpl, "elements": elements}

    def save_template(self) -> bool:
        try:
            payload = self.build_payload()
            if self.template_id:
                db.update_label_template(self.template_id, payload)
            else:
                self.template_id = db.create_label_template(payload)
            self.dirty = False
            self.saved = True
            self._update_title()
            messagebox.showinfo("Збережено", "Шаблон збережено")
            return True
        except sqlite3.IntegrityError as exc:
            msg = str(exc)
            if "LabelTemplates.code" in msg or "UNIQUE constraint failed: LabelTemplates.code" in msg:
                show_error("Шаблон", "Код шаблону має бути унікальним. Змініть поле 'Код' і спробуйте знову.")
                if hasattr(self, "_code_entry") and self._code_entry:
                    self._code_entry.focus_set()
                    self._code_entry.selection_range(0, tk.END)
            else:
                show_error("Шаблон", msg)
        except Exception as exc:
            logging.exception("Failed to save template")
            show_error("Шаблон", str(exc))
        return False

    def on_close(self) -> None:
        if self.dirty:
            res = messagebox.askyesnocancel("Незбережені зміни", "Зберегти зміни шаблону?")
            if res is None:
                return
            if res is True:
                if not self.save_template():
                    return
        if hasattr(self, "properties_dialog"):
            try:
                self.properties_dialog.root.destroy()
            except Exception:
                pass
        self.root.destroy()

    def mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _bind_dirty_traces(self) -> None:
        for var in list(self.template_vars.values()) + list(self.bool_vars.values()):
            var.trace_add("write", lambda *_, self=self: self.mark_dirty())

    def _update_title(self) -> None:
        title = self.template_vars.get("title").get().strip() if self.template_vars.get("title") else ""
        code = self.template_vars.get("code").get().strip() if self.template_vars.get("code") else ""
        suffix = title or code
        base = "Редактор шаблону"
        if suffix:
            base = f"{base} — {suffix}"
        self.base_title = base
        self.root.title(f"{self.base_title}{' *' if self.dirty else ''}")

    def _get_label_size_mm(self) -> tuple[float, float]:
        try:
            tpl = self._collect_template_data()
        except Exception:
            return (1.0, 1.0)
        label_w = float(tpl.get("label_w_mm") or 1.0)
        label_h = float(tpl.get("label_h_mm") or 1.0)
        return (label_w, label_h)

    def _get_snap_step_mm(self) -> float:
        s = (self.snap_step_var.get() or "").strip().replace(",", ".")
        try:
            v = float(s)
        except Exception:
            v = 0.5
        return max(0.05, min(v, 10.0))

    def _snap_mm(self, v: float, step: float) -> float:
        return round(v / step) * step

    def _apply_snap_and_clamp(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        label_w_mm: float,
        label_h_mm: float,
        step: float,
        do_snap: bool,
    ) -> tuple[float, float, float, float]:
        # min sizes
        w = max(1.0, w)
        h = max(1.0, h)

        if do_snap:
            x = self._snap_mm(x, step)
            y = self._snap_mm(y, step)
            w = self._snap_mm(w, step)
            h = self._snap_mm(h, step)
            w = max(1.0, w)
            h = max(1.0, h)

        # clamp to bounds
        x = max(0.0, min(x, label_w_mm - w))
        y = max(0.0, min(y, label_h_mm - h))
        return x, y, w, h

    def _update_status_for_idx(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.elements):
            self.status_var.set("")
            return
        el = self.elements[idx]
        self.status_var.set(f"X={el['x_mm']:.2f}  Y={el['y_mm']:.2f}  W={el['w_mm']:.2f}  H={el['h_mm']:.2f} мм")

    def _mm_to_px(self, value_mm: float) -> float:
        return float(value_mm or 0.0) * (self._preview_scale or 1.0)

    def _px_to_mm(self, value_px: float) -> float:
        if not self._preview_scale:
            return 0.0
        return float(value_px) / self._preview_scale

    def _set_active_element(self, idx: int | None, redraw: bool = True, update_tree: bool = True) -> None:
        if idx is None or idx >= len(self.elements):
            return
        self._active_elem_index = idx
        if update_tree:
            self.elem_tree.selection_set(str(idx))
            self.elem_tree.see(str(idx))
        self._fill_element_form()
        self._update_status_for_idx(idx)
        if redraw:
            self.draw_preview()

    def _update_element_vars_live(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
        if not getattr(self, "properties_dialog", None):
            return
        if not self.properties_dialog.root.winfo_viewable():
            return
        for key, val in {
            "x_mm": f"{x_mm:.2f}",
            "y_mm": f"{y_mm:.2f}",
            "w_mm": f"{w_mm:.2f}",
            "h_mm": f"{h_mm:.2f}",
        }.items():
            var = self.element_vars.get(key)
            if var is not None:
                self._set_var_safe(var, val)

    def _update_canvas_geometry(self, idx: int, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
        rect_id = self._elem_rect_ids.get(idx)
        if not rect_id:
            return
        margin = 10
        scale = self._preview_scale or 1.0
        x1 = margin + x_mm * scale
        y1 = margin + y_mm * scale
        x2 = x1 + w_mm * scale
        y2 = y1 + h_mm * scale
        self.canvas.coords(rect_id, x1, y1, x2, y2)
        coords = {
            "nw": (x1, y1),
            "ne": (x2, y1),
            "sw": (x1, y2),
            "se": (x2, y2),
        }
        handle_size = 6
        half = handle_size / 2
        for handle_id in self._elem_handle_ids.get(idx, []):
            tags = self.canvas.gettags(handle_id)
            handle_tag = next((t for t in tags if t in coords), None)
            if handle_tag:
                hx, hy = coords[handle_tag]
                self.canvas.coords(handle_id, hx - half, hy - half, hx + half, hy + half)

    def _on_canvas_button_press(self, event: tk.Event) -> None:
        self._drag_mode = None
        self._resize_handle = None
        self._drag_start = None
        self._drag_last_values = None
        item = self.canvas.find_withtag("current")
        if not item:
            return
        item_id = item[0]
        tags = self.canvas.gettags(item_id)
        elem_tag = next((t for t in tags if t.startswith("elem:")), None)
        if not elem_tag:
            return
        try:
            idx = int(elem_tag.split(":", 1)[1])
        except (TypeError, ValueError):
            return
        if idx is None or idx >= len(self.elements):
            self._drag_mode = None
            return
        self.canvas.focus_set()
        if "handle" in tags:
            handle_tag = next((t for t in tags if t in ("nw", "ne", "sw", "se")), None)
            if not handle_tag:
                return
            self._drag_mode = "resize"
            self._resize_handle = handle_tag
        else:
            self._drag_mode = "move"
        self._set_active_element(idx, redraw=True)
        el = self.elements[idx]
        self._drag_start = {
            "x_px": float(event.x),
            "y_px": float(event.y),
            "orig_x_mm": float(el.get("x_mm", 0.0)),
            "orig_y_mm": float(el.get("y_mm", 0.0)),
            "orig_w_mm": float(el.get("w_mm", 0.0)),
            "orig_h_mm": float(el.get("h_mm", 0.0)),
        }

    def _on_canvas_hover(self, event: tk.Event) -> None:
        item = self.canvas.find_withtag("current")
        cursor = ""
        if item:
            tags = self.canvas.gettags(item[0])
            if "handle" in tags:
                if "nw" in tags or "se" in tags:
                    cursor = "size_nw_se"
                elif "ne" in tags or "sw" in tags:
                    cursor = "size_ne_sw"
            elif "elem" in tags:
                cursor = "fleur"
        self.canvas.configure(cursor=cursor)

    def _on_canvas_leave(self, _: tk.Event) -> None:
        self.canvas.configure(cursor="")

    def _on_canvas_configure(self, _: tk.Event) -> None:
        if self._preview_redraw_job:
            try:
                self.root.after_cancel(self._preview_redraw_job)
            except Exception:
                pass
        self._preview_redraw_job = self.root.after(80, self.draw_preview)

    def _compute_drag_values(self, dx_mm: float, dy_mm: float, label_w: float, label_h: float) -> tuple[float, float, float, float]:
        if not self._drag_start:
            return (0.0, 0.0, 0.0, 0.0)
        min_size = 1.0
        handle = self._resize_handle or ""
        orig_x = self._drag_start["orig_x_mm"]
        orig_y = self._drag_start["orig_y_mm"]
        orig_w = self._drag_start["orig_w_mm"]
        orig_h = self._drag_start["orig_h_mm"]
        if self._drag_mode == "move":
            new_x = min(max(orig_x + dx_mm, 0.0), max(0.0, label_w - orig_w))
            new_y = min(max(orig_y + dy_mm, 0.0), max(0.0, label_h - orig_h))
            return (new_x, new_y, orig_w, orig_h)

        x1 = orig_x
        y1 = orig_y
        x2 = orig_x + orig_w
        y2 = orig_y + orig_h
        if "w" in handle:
            x1 += dx_mm
        if "n" in handle:
            y1 += dy_mm
        if "e" in handle:
            x2 += dx_mm
        if "s" in handle:
            y2 += dy_mm
        x1 = max(0.0, x1)
        y1 = max(0.0, y1)
        x2 = min(label_w, x2)
        y2 = min(label_h, y2)
        if x2 - x1 < min_size:
            if "w" in handle:
                x1 = x2 - min_size
            else:
                x2 = x1 + min_size
        if y2 - y1 < min_size:
            if "n" in handle:
                y1 = y2 - min_size
            else:
                y2 = y1 + min_size
        x1 = min(max(0.0, x1), max(0.0, label_w - min_size))
        y1 = min(max(0.0, y1), max(0.0, label_h - min_size))
        x2 = min(label_w, max(x1 + min_size, x2))
        y2 = min(label_h, max(y1 + min_size, y2))
        return (x1, y1, x2 - x1, y2 - y1)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self._drag_mode not in ("move", "resize") or self._active_elem_index is None or not self._drag_start:
            return
        label_w, label_h = self._get_label_size_mm()
        step = self._get_snap_step_mm()
        snap_enabled = self.snap_enabled_var.get()
        alt_pressed = bool(event.state & 0x0008)
        do_snap = snap_enabled and (not alt_pressed)
        dx_px = float(event.x) - self._drag_start.get("x_px", 0.0)
        dy_px = float(event.y) - self._drag_start.get("y_px", 0.0)
        dx_mm = self._px_to_mm(dx_px)
        dy_mm = self._px_to_mm(dy_px)
        new_x, new_y, new_w, new_h = self._compute_drag_values(dx_mm, dy_mm, label_w, label_h)
        new_x, new_y, new_w, new_h = self._apply_snap_and_clamp(
            new_x, new_y, new_w, new_h, label_w, label_h, step, do_snap
        )
        self._drag_last_values = (new_x, new_y, new_w, new_h)
        self._update_element_vars_live(new_x, new_y, new_w, new_h)
        self.status_var.set(f"X={new_x:.2f}  Y={new_y:.2f}  W={new_w:.2f}  H={new_h:.2f} мм")
        self._update_canvas_geometry(self._active_elem_index, new_x, new_y, new_w, new_h)

    def _on_canvas_button_release(self, event: tk.Event) -> None:
        if self._drag_mode not in ("move", "resize") or self._active_elem_index is None:
            return
        idx = self._active_elem_index
        if idx >= len(self.elements):
            return
        label_w, label_h = self._get_label_size_mm()
        step = self._get_snap_step_mm()
        snap_enabled = self.snap_enabled_var.get()
        alt_pressed = bool(event.state & 0x0008)
        do_snap = snap_enabled and (not alt_pressed)
        if self._drag_start and not self._drag_last_values:
            dx_mm = self._px_to_mm(float(event.x) - self._drag_start.get("x_px", 0.0))
            dy_mm = self._px_to_mm(float(event.y) - self._drag_start.get("y_px", 0.0))
            self._drag_last_values = self._compute_drag_values(dx_mm, dy_mm, label_w, label_h)
        if not self._drag_last_values:
            return
        new_x, new_y, new_w, new_h = self._drag_last_values
        new_x, new_y, new_w, new_h = self._apply_snap_and_clamp(
            new_x, new_y, new_w, new_h, label_w, label_h, step, do_snap
        )
        el = self.elements[idx]
        orig_vals = (
            float(el.get("x_mm", 0.0)),
            float(el.get("y_mm", 0.0)),
            float(el.get("w_mm", 0.0)),
            float(el.get("h_mm", 0.0)),
        )
        if all(abs(n - o) < 1e-6 for n, o in zip((new_x, new_y, new_w, new_h), orig_vals)):
            self._drag_mode = None
            self._resize_handle = None
            self._drag_start = None
            self._drag_last_values = None
            return
        el.update({"x_mm": float(new_x), "y_mm": float(new_y), "w_mm": float(new_w), "h_mm": float(new_h)})
        self._update_tree_item(idx, el)
        self._update_status_for_idx(idx)
        self.mark_dirty()
        self.draw_preview()
        self._drag_mode = None
        self._resize_handle = None
        self._drag_start = None
        self._drag_last_values = None

    def _on_preview_keypress(self, event: tk.Event) -> str | None:
        if self._active_elem_index is None or self._active_elem_index >= len(self.elements):
            return None
        if event.keysym not in ("Left", "Right", "Up", "Down"):
            return None
        idx = self._active_elem_index
        el = self.elements[idx]
        base_step = self._get_snap_step_mm() if self.snap_enabled_var.get() else 0.5
        if event.state & 0x0001:
            base_step *= 10
        if event.state & 0x0004:
            base_step *= 0.2
        dx = dy = 0.0
        if event.keysym == "Left":
            dx = -base_step
        elif event.keysym == "Right":
            dx = base_step
        elif event.keysym == "Up":
            dy = -base_step
        elif event.keysym == "Down":
            dy = base_step
        label_w, label_h = self._get_label_size_mm()
        new_x = float(el.get("x_mm", 0.0)) + dx
        new_y = float(el.get("y_mm", 0.0)) + dy
        do_snap = self.snap_enabled_var.get() and not bool(event.state & 0x0008)
        new_x, new_y, new_w, new_h = self._apply_snap_and_clamp(
            new_x, new_y, float(el.get("w_mm", 0.0)), float(el.get("h_mm", 0.0)), label_w, label_h, base_step, do_snap
        )
        el.update({"x_mm": float(new_x), "y_mm": float(new_y)})
        self._update_tree_item(idx, el)
        self._update_element_vars_live(new_x, new_y, new_w, new_h)
        self._update_status_for_idx(idx)
        self.mark_dirty()
        self.draw_preview()
        return "break"

    def _update_tree_item(self, idx: int, el: dict[str, Any]) -> None:
        if str(idx) not in self.elem_tree.get_children():
            return
        values = list(self.elem_tree.item(str(idx), "values"))
        if len(values) >= 7:
            values[3] = el.get("x_mm")
            values[4] = el.get("y_mm")
            values[5] = el.get("w_mm")
            values[6] = el.get("h_mm")
        self.elem_tree.item(str(idx), values=values)

    def draw_preview(self) -> None:
        self._preview_redraw_job = None
        self.canvas.update_idletasks()
        self.canvas.delete("all")
        self._elem_rect_ids.clear()
        self._elem_handle_ids.clear()
        label_w, label_h = self._get_label_size_mm()
        canvas_w = int(self.canvas.winfo_width() or 300)
        canvas_h = int(self.canvas.winfo_height() or 200)
        scale = min((canvas_w - 20) / label_w, (canvas_h - 20) / label_h)
        scale = max(0.2, min(scale, 12.0))
        self._preview_scale = scale
        margin = 10
        ox = margin
        oy = margin
        self.canvas.create_rectangle(ox, oy, ox + label_w * scale, oy + label_h * scale, outline="black")
        selected = self._active_elem_index
        if selected is None:
            sel = self.elem_tree.selection()
            if sel:
                try:
                    selected = int(sel[0])
                except ValueError:
                    selected = None
        for idx, el in enumerate(self.elements):
            if not el.get("is_active", 1):
                continue
            color = "#4287f5"
            x1 = ox + float(el.get("x_mm", 0)) * scale
            y1 = oy + float(el.get("y_mm", 0)) * scale
            x2 = x1 + float(el.get("w_mm", 0)) * scale
            y2 = y1 + float(el.get("h_mm", 0)) * scale
            is_selected = selected == idx
            rect = self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline=color,
                width=2 if is_selected else 1,
                tags=("elem", f"elem:{idx}", "rect"),
            )
            self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=el.get("element_type"),
                fill=color,
                tags=("elem", f"elem:{idx}", "label"),
            )
            self._elem_rect_ids[idx] = rect
            if is_selected:
                handles = []
                handle_size = 6
                half = handle_size / 2
                for hx, hy, tag in [
                    (x1, y1, "nw"),
                    (x2, y1, "ne"),
                    (x1, y2, "sw"),
                    (x2, y2, "se"),
                ]:
                    hid = self.canvas.create_rectangle(
                        hx - half,
                        hy - half,
                        hx + half,
                        hy + half,
                        fill="#ff8800",
                        outline="black",
                        tags=("elem", f"elem:{idx}", "handle", tag),
                    )
                    handles.append(hid)
                self._elem_handle_ids[idx] = handles
        if selected is not None and selected < len(self.elements):
            self._update_status_for_idx(selected)
        else:
            self.status_var.set("")

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
