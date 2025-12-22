"""Reusable Tkinter UI components."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import calendar
from datetime import date, datetime
from functools import cmp_to_key
from typing import TYPE_CHECKING, Any, Callable, List, Optional

if TYPE_CHECKING:
    from inventorylite.utils import Settings


class TableFrame(ttk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        columns: List[tuple],
        selectmode: str = "browse",
        settings: Settings | None = None,
        persist_key: str | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._sort_col: str | None = None
        self._sort_desc = False
        self._base_headings: dict[str, str] = {}
        self._settings = settings
        self._persist_key = persist_key
        self.tree = ttk.Treeview(
            self, columns=[c[0] for c in columns], show="headings", selectmode=selectmode
        )
        for col_id, col_title, width in columns:
            self._base_headings[col_id] = col_title
            self.tree.heading(col_id, text=col_title, command=lambda c=col_id: self._on_heading_click(c))
            self.tree.column(col_id, width=width, anchor="w")
        if self._settings and self._persist_key:
            widths = (
                self._settings.get("ui_state", "table_columns", self._persist_key, default={}) or {}
            )
            for col_id in self.tree.cget("columns"):
                if col_id in widths:
                    self.tree.column(col_id, width=int(widths[col_id]))
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
            tags = row.get("tags", ())
            self.tree.insert("", "end", iid=row["id"], values=values, tags=tags)
        if self._sort_col:
            self._apply_sort()

    def tag_configure(self, tag: str, **kwargs) -> None:
        self.tree.tag_configure(tag, **kwargs)

    def persist_column_widths(self) -> None:
        if not self._settings or not self._persist_key:
            return
        widths = {col: int(self.tree.column(col, "width")) for col in self.tree.cget("columns")}
        self._settings.set(widths, "ui_state", "table_columns", self._persist_key)

    def selected_id(self) -> Optional[str | int]:
        item = self.tree.selection()
        if not item:
            return None
        try:
            return int(item[0])
        except ValueError:
            return item[0]

    def get_selected_row_ids(self) -> list[int]:
        """
        Return selected row ids as ints.
        Assumes first column in Treeview values contains database id, or that iid is id.
        Prefer iid if it is numeric; otherwise read from values[0].
        """

        result: list[int] = []
        for item in self.tree.selection():
            try:
                result.append(int(item))
                continue
            except (TypeError, ValueError):
                pass
            values = self.tree.item(item, "values")
            if values:
                try:
                    result.append(int(values[0]))
                except (TypeError, ValueError):
                    continue
        return result

    def on_select(self, callback: Callable[[], None]) -> None:
        self.tree.bind("<<TreeviewSelect>>", lambda e: callback())

    def on_double_click(self, callback: Callable[[], None]) -> None:
        def handler(event: tk.Event) -> None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
                callback()

        self.tree.bind("<Double-1>", handler)

    def register_context_menu(self, on_edit: Callable[[], None], on_delete: Callable[[], None]) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Редагувати", command=on_edit)
        menu.add_command(label="Видалити", command=on_delete)

        def show_menu(event: tk.Event) -> None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
                self.tree.focus(row_id)
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

        self.tree.bind("<Button-3>", show_menu)
        self.context_menu = menu

    def register_context_menu_actions(self, actions: list[tuple[str, Callable[[], None] | None]]) -> None:
        """
        Register a custom context menu for the table.

        actions: list of (label, callback). If callback is None or label == '---', a separator is added.
        On right-click the row under cursor becomes selected and the menu is shown. Clicking on empty
        space does not open the menu.
        """

        menu = tk.Menu(self, tearoff=0)
        for label, callback in actions:
            if callback is None or label == "---":
                menu.add_separator()
                continue
            menu.add_command(label=label, command=callback)

        def show_menu(event: tk.Event) -> None:
            row_id = self.tree.identify_row(event.y)
            if not row_id:
                return
            selected = set(self.tree.selection())
            if row_id not in selected:
                self.tree.selection_set(row_id)
            self.tree.focus(row_id)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.tree.bind("<Button-3>", show_menu)
        self.context_menu = menu

    def copy_selection_to_clipboard(
        self,
        include_headers: bool = False,
        delimiter: str = "\t",
    ) -> bool:
        items = list(self.tree.selection())
        if not items:
            focus = self.tree.focus()
            if focus:
                items = [focus]
            else:
                return False
        cols = list(self.tree.cget("columns"))
        lines: list[str] = []
        if include_headers:
            headers = [self._base_headings.get(c, c) for c in cols]
            lines.append(delimiter.join(headers))
        for iid in items:
            values = self.tree.item(iid, "values")
            line = delimiter.join(str(v) for v in values)
            lines.append(line)
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        return True

    def _on_heading_click(self, col_id: str) -> None:
        if col_id == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col_id
            self._sort_desc = False
        self._apply_sort()

    def _apply_sort(self) -> None:
        if not self._sort_col:
            return
        col_id = self._sort_col
        columns = list(self.tree.cget("columns"))
        try:
            col_index = columns.index(col_id)
        except ValueError:
            return

        selection = self.tree.selection()
        focus = self.tree.focus()

        items: list[tuple[str, tuple[int, Any], int, bool]] = []
        for idx, iid in enumerate(self.tree.get_children("")):
            values = self.tree.item(iid, "values")
            raw_value = values[col_index] if col_index < len(values) else ""
            is_empty, sort_value = self._coerce_sort_value(raw_value, col_id)
            items.append((iid, sort_value, idx, is_empty))

        non_empty = [item for item in items if not item[3]]
        empty = [item for item in items if item[3]]

        def compare_items(left: tuple[str, tuple[int, Any], int, bool],
                          right: tuple[str, tuple[int, Any], int, bool]) -> int:
            if left[1] == right[1]:
                if left[2] == right[2]:
                    return 0
                return -1 if left[2] < right[2] else 1
            if self._sort_desc:
                return -1 if left[1] > right[1] else 1
            return -1 if left[1] < right[1] else 1

        non_empty_sorted = sorted(non_empty, key=cmp_to_key(compare_items))
        empty_sorted = sorted(empty, key=lambda item: item[2])
        ordered_items = non_empty_sorted + empty_sorted

        for new_index, (iid, _value, _idx, _empty) in enumerate(ordered_items):
            self.tree.move(iid, "", new_index)

        for heading_id in columns:
            base_text = self._base_headings.get(heading_id, heading_id)
            if heading_id == col_id:
                indicator = "▼" if self._sort_desc else "▲"
                text = f"{base_text} {indicator}"
            else:
                text = base_text
            self.tree.heading(
                heading_id, text=text, command=lambda c=heading_id: self._on_heading_click(c)
            )

        if selection:
            existing_selection = [iid for iid in selection if self.tree.exists(iid)]
            if existing_selection:
                self.tree.selection_set(existing_selection)
        if focus and self.tree.exists(focus):
            self.tree.focus(focus)

    def _coerce_sort_value(self, raw: Any, _col_id: str) -> tuple[bool, tuple[int, Any]]:
        empty_markers = {"", "-", "—"}
        if raw is None:
            return True, (2, "")
        raw_text = str(raw).strip()
        if raw_text in empty_markers:
            return True, (2, "")

        try:
            parsed_dt = datetime.fromisoformat(raw_text)
            return False, (0, parsed_dt)
        except ValueError:
            pass

        normalized = raw_text.replace(" ", "")
        if not normalized:
            return True, (2, "")
        if normalized.startswith("0") and len(normalized) > 1:
            return False, (2, raw_text.casefold())
        stripped_numeric = normalized.replace(",", "").replace(".", "")
        if len(stripped_numeric) > 10 and stripped_numeric.isdigit():
            return False, (2, raw_text.casefold())
        candidate = normalized.replace(",", ".")
        if candidate.count(".") <= 1 and candidate.replace(".", "").isdigit():
            try:
                return False, (1, float(candidate))
            except ValueError:
                pass

        return False, (2, raw_text.casefold())


class DatePicker(ttk.Frame):
    """Date picker with a popup calendar."""

    def __init__(self, master: tk.Widget, initial: date | None = None, **kwargs):
        super().__init__(master, **kwargs)
        initial_date = initial or date.today()
        self.selected_date = initial_date
        self.var = tk.StringVar(value=self._format_date(initial_date))

        entry = ttk.Entry(self, textvariable=self.var, width=12)
        entry.grid(row=0, column=0, sticky="w")
        entry.bind("<FocusOut>", self._on_entry_change)

        ttk.Button(self, text="…", width=3, command=self._open_calendar).grid(row=0, column=1, padx=(4, 0))

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: date | str) -> None:
        if isinstance(value, str):
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return
        else:
            parsed = value
        self.selected_date = parsed
        self.var.set(self._format_date(parsed))

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _on_entry_change(self, _event: tk.Event) -> None:
        try:
            parsed = datetime.strptime(self.var.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            return
        self.selected_date = parsed
        self.var.set(self._format_date(parsed))

    def _open_calendar(self) -> None:
        top = tk.Toplevel(self)
        top.title("Оберіть дату")
        top.grab_set()
        top.resizable(False, False)

        header = ttk.Frame(top)
        header.pack(fill=tk.X, padx=8, pady=6)

        current = [self.selected_date.year, self.selected_date.month]

        month_label = ttk.Label(header, text="")
        month_label.pack(side=tk.LEFT, expand=True)

        def refresh_calendar() -> None:
            year, month = current
            month_label.configure(text=f"{year}-{month:02d}")
            for widget in body.winfo_children():
                widget.destroy()
            cal = calendar.Calendar().monthdayscalendar(year, month)
            days_header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
            for idx, name in enumerate(days_header):
                ttk.Label(body, text=name, width=4).grid(row=0, column=idx)
            for row_idx, week in enumerate(cal, start=1):
                for col_idx, day in enumerate(week):
                    if day == 0:
                        ttk.Label(body, text="", width=4).grid(row=row_idx, column=col_idx)
                        continue
                    btn = ttk.Button(body, text=f"{day:02d}", width=4)
                    btn.grid(row=row_idx, column=col_idx, padx=1, pady=1)
                    btn.configure(command=lambda d=day: on_pick(d))

        def shift_month(delta: int) -> None:
            year, month = current
            month += delta
            if month < 1:
                month = 12
                year -= 1
            elif month > 12:
                month = 1
                year += 1
            current[0], current[1] = year, month
            refresh_calendar()

        ttk.Button(header, text="<", width=3, command=lambda: shift_month(-1)).pack(side=tk.LEFT)
        ttk.Button(header, text=">", width=3, command=lambda: shift_month(1)).pack(side=tk.RIGHT)

        body = ttk.Frame(top)
        body.pack(padx=8, pady=(0, 8))

        def on_pick(day: int) -> None:
            year, month = current
            self.selected_date = date(year, month, day)
            self.var.set(self._format_date(self.selected_date))
            top.destroy()

        refresh_calendar()
        top.wait_window(top)


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
