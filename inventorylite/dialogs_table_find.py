"""Search dialog for table views."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from inventorylite.ui_components import TableFrame
from inventorylite.text_norm import norm_text


def _find_parent_tableframe(widget: tk.Widget | None) -> TableFrame | None:
    current = widget
    while current is not None:
        if hasattr(current, "copy_selection_to_clipboard") and hasattr(current, "tree"):
            if isinstance(current, TableFrame):
                return current
            return current
        current = getattr(current, "master", None)
    return None


def open_table_find_dialog(root: tk.Tk) -> None:
    existing = getattr(root, "_table_find_dialog", None)
    if existing and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return

    focused = root.focus_get()
    table = _find_parent_tableframe(focused)
    if table is None:
        return

    dialog = tk.Toplevel(root)
    root._table_find_dialog = dialog
    dialog.title("Пошук у таблиці")
    dialog.transient(root)
    dialog.resizable(False, False)

    query_var = tk.StringVar()
    case_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="0/0")
    matches: list[str] = []
    current_index = {"value": 0}
    pending = {"after_id": None}
    original_tags: dict[str, tuple[str, ...]] = {}
    normalized_values: dict[str, str] = {}

    table.tree.tag_configure("find_match", background="#FFF3BF")
    table.tree.tag_configure("find_current", background="#FFD43B")

    for iid in table.tree.get_children(""):
        original_tags[iid] = tuple(table.tree.item(iid, "tags") or ())

    def set_status() -> None:
        if not matches:
            status_var.set("0/0")
            return
        status_var.set(f"{current_index['value'] + 1}/{len(matches)}")

    def _apply_tags() -> None:
        for iid, base in original_tags.items():
            if not table.tree.exists(iid):
                continue
            base_clean = tuple(t for t in base if t not in ("find_match", "find_current"))
            extra = []
            if iid in matches:
                extra.append("find_match")
            table.tree.item(iid, tags=base_clean + tuple(extra))
        if matches:
            cur = matches[current_index["value"]]
            if table.tree.exists(cur):
                base = tuple(table.tree.item(cur, "tags") or ())
                if "find_current" not in base:
                    table.tree.item(cur, tags=base + ("find_current",))

    def select_match(index: int) -> None:
        if not matches:
            return
        current_index["value"] = index % len(matches)
        iid = matches[current_index["value"]]
        table.tree.selection_set(iid)
        table.tree.focus(iid)
        table.tree.see(iid)
        _apply_tags()
        set_status()

    def rebuild_matches() -> None:
        query = query_var.get()
        matches.clear()
        normalized_values.clear()
        for iid in table.tree.get_children(""):
            if iid not in original_tags:
                original_tags[iid] = tuple(table.tree.item(iid, "tags") or ())
        if query:
            use_case = case_var.get()
            needle = query if use_case else norm_text(query)
            for iid in table.tree.get_children(""):
                values = table.tree.item(iid, "values")
                joined = " | ".join(str(v) for v in values)
                if use_case:
                    haystack = joined
                else:
                    haystack = normalized_values.setdefault(iid, norm_text(joined))
                if needle in haystack:
                    matches.append(iid)
        current_index["value"] = 0
        _apply_tags()
        if matches:
            select_match(0)
        else:
            set_status()

    def schedule_rebuild() -> None:
        if pending["after_id"]:
            dialog.after_cancel(pending["after_id"])
        pending["after_id"] = dialog.after(180, rebuild_matches)

    def next_match() -> None:
        if not matches:
            return
        select_match(current_index["value"] + 1)

    def prev_match() -> None:
        if not matches:
            return
        select_match(current_index["value"] - 1)

    def close_dialog() -> None:
        if pending["after_id"]:
            dialog.after_cancel(pending["after_id"])
        if original_tags:
            for iid, tags in original_tags.items():
                if table.tree.exists(iid):
                    table.tree.item(iid, tags=tags)
        dialog.destroy()

    query_entry = ttk.Entry(dialog, textvariable=query_var, width=40)
    query_entry.grid(row=0, column=0, columnspan=3, padx=12, pady=(12, 6), sticky="ew")

    case_check = ttk.Checkbutton(dialog, text="Регістр", variable=case_var, command=schedule_rebuild)
    case_check.grid(row=1, column=0, padx=12, pady=6, sticky="w")

    status_label = ttk.Label(dialog, textvariable=status_var)
    status_label.grid(row=1, column=1, padx=12, pady=6, sticky="e")

    prev_button = ttk.Button(dialog, text="Попередній", command=prev_match)
    prev_button.grid(row=2, column=0, padx=12, pady=(6, 12), sticky="w")

    next_button = ttk.Button(dialog, text="Наступний", command=next_match)
    next_button.grid(row=2, column=1, padx=12, pady=(6, 12), sticky="w")

    close_button = ttk.Button(dialog, text="Закрити", command=close_dialog)
    close_button.grid(row=2, column=2, padx=12, pady=(6, 12), sticky="e")

    dialog.columnconfigure(0, weight=1)
    dialog.columnconfigure(1, weight=0)
    dialog.columnconfigure(2, weight=0)

    query_var.trace_add("write", lambda *_: schedule_rebuild())

    dialog.bind("<Return>", lambda _event: next_match())
    dialog.bind("<Shift-Return>", lambda _event: prev_match())
    dialog.bind("<F3>", lambda _event: next_match())
    dialog.bind("<Shift-F3>", lambda _event: prev_match())
    dialog.bind("<Escape>", lambda _event: close_dialog())
    dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    query_entry.focus_set()
    dialog.grab_set()
