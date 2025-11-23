"""Reusable Tkinter UI components."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional


class TableFrame(ttk.Frame):
    def __init__(self, master: tk.Widget, columns: List[tuple], **kwargs):
        super().__init__(master, **kwargs)
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for col_id, col_title, width in columns:
            self.tree.heading(col_id, text=col_title)
            self.tree.column(col_id, width=width, anchor="w")
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def set_rows(self, rows: List[dict]):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            values = [row[col] for col in self.tree.cget("columns")]
            self.tree.insert("", "end", iid=row["id"], values=values)

    def selected_id(self) -> Optional[int]:
        item = self.tree.selection()
        if not item:
            return None
        return int(item[0])


def simple_prompt(title: str, fields: List[str], initial: Optional[List[str]] = None) -> Optional[List[str]]:
    """Prompt user for simple text fields; returns list of values or None."""
    root = tk.Toplevel()
    root.title(title)
    root.grab_set()
    entries = []
    initial = initial or [""] * len(fields)
    for i, field in enumerate(fields):
        ttk.Label(root, text=field).grid(row=i, column=0, padx=6, pady=4, sticky="w")
        var = tk.StringVar(value=initial[i])
        ent = ttk.Entry(root, textvariable=var, width=30)
        ent.grid(row=i, column=1, padx=6, pady=4)
        entries.append(var)
    result: Optional[List[str]] = None

    def on_ok() -> None:
        nonlocal result
        values = [v.get().strip() for v in entries]
        if any(not v for v in values):
            messagebox.showerror("Validation", "Усі поля мають бути заповнені.")
            return
        result = values
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    btn_frame = ttk.Frame(root)
    btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=8)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    root.bind("<Return>", lambda e: on_ok())
    root.bind("<Escape>", lambda e: on_cancel())
    root.wait_window()
    return result

