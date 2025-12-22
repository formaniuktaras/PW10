"""Search dialog for table views."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from inventorylite.ui_components import TableFrame


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
    focused = root.focus_get()
    table = _find_parent_tableframe(focused)
    if table is None:
        return

    dialog = tk.Toplevel(root)
    dialog.title("Пошук у таблиці")
    dialog.transient(root)
    dialog.resizable(False, False)

    query_var = tk.StringVar()
    case_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="0/0")
    matches: list[str] = []
    current_index = {"value": 0}

    def set_status() -> None:
        if not matches:
            status_var.set("0/0")
            return
        status_var.set(f"{current_index['value'] + 1}/{len(matches)}")

    def select_match(index: int) -> None:
        if not matches:
            return
        current_index["value"] = index % len(matches)
        iid = matches[current_index["value"]]
        table.tree.selection_set(iid)
        table.tree.focus(iid)
        table.tree.see(iid)
        set_status()

    def rebuild_matches() -> None:
        query = query_var.get()
        matches.clear()
        if query:
            for iid in table.tree.get_children(""):
                values = table.tree.item(iid, "values")
                joined = " | ".join(str(v) for v in values)
                haystack = joined if case_var.get() else joined.lower()
                needle = query if case_var.get() else query.lower()
                if needle in haystack:
                    matches.append(iid)
        current_index["value"] = 0
        if matches:
            select_match(0)
        else:
            set_status()

    def next_match() -> None:
        if not matches:
            return
        select_match(current_index["value"] + 1)

    def prev_match() -> None:
        if not matches:
            return
        select_match(current_index["value"] - 1)

    def close_dialog() -> None:
        dialog.destroy()

    query_entry = ttk.Entry(dialog, textvariable=query_var, width=40)
    query_entry.grid(row=0, column=0, columnspan=3, padx=12, pady=(12, 6), sticky="ew")

    case_check = ttk.Checkbutton(dialog, text="Регістр", variable=case_var, command=rebuild_matches)
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

    query_var.trace_add("write", lambda *_: rebuild_matches())

    dialog.bind("<Return>", lambda _event: next_match())
    dialog.bind("<Shift-Return>", lambda _event: prev_match())
    dialog.bind("<Escape>", lambda _event: close_dialog())

    query_entry.focus_set()
    dialog.grab_set()

