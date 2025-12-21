from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from inventorylite import db, labels
from inventorylite.helpers import _sanitize_barcode_prefix
from inventorylite.label_templates_ui import TemplateManagerDialog
from inventorylite.utils import open_file, show_error


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
