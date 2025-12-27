"""Reusable Tkinter UI components."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from functools import cmp_to_key
from typing import TYPE_CHECKING, Any, Callable, List, Optional
import tkinter as tk
from tkinter import messagebox, ttk

from inventorylite import dates
from inventorylite.helpers import (
    RATE_DECIMALS,
    bind_two_way_rate,
    format_rate,
    parse_decimal,
)

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
            parsed_dt = dates.try_parse_date_any(raw_text)
            if parsed_dt:
                return False, (0, datetime.combine(parsed_dt, datetime.min.time()))
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


class CalendarPopup(tk.Toplevel):
    MONTH_NAMES = [
        "СІЧЕНЬ",
        "ЛЮТИЙ",
        "БЕРЕЗЕНЬ",
        "КВІТЕНЬ",
        "ТРАВЕНЬ",
        "ЧЕРВЕНЬ",
        "ЛИПЕНЬ",
        "СЕРПЕНЬ",
        "ВЕРЕСЕНЬ",
        "ЖОВТЕНЬ",
        "ЛИСТОПАД",
        "ГРУДЕНЬ",
    ]
    DOW_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

    def __init__(self, master: tk.Widget, initial_date: date, on_select: Callable[[date], None]):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.calendar = calendar.Calendar(firstweekday=0)
        self._on_select = on_select
        self.selected_date = initial_date
        self.current_year = initial_date.year
        self.current_month = initial_date.month
        self._root = master.winfo_toplevel()
        self._bind_id_click = self._root.bind("<Button-1>", self._on_root_click, add="+")
        self._bind_id_click2 = self._root.bind("<Button-3>", self._on_root_click, add="+")

        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Left>", lambda _e: self.move_selected(-1))
        self.bind("<Right>", lambda _e: self.move_selected(1))
        self.bind("<Up>", lambda _e: self.move_selected(-7))
        self.bind("<Down>", lambda _e: self.move_selected(7))
        self.bind("<Prior>", lambda _e: self.change_month(-1))
        self.bind("<Next>", lambda _e: self.change_month(1))
        self.bind("<Control-Prior>", lambda _e: self.change_year(-1))
        self.bind("<Control-Next>", lambda _e: self.change_year(1))
        self.bind("<Return>", lambda _e: self._confirm_selection())

        style = ttk.Style(self)
        bg_candidates = [
            style.lookup("Calendar.TFrame", "background"),
            style.lookup("TFrame", "background"),
        ]
        try:
            bg_candidates.append(master.cget("background"))
        except Exception:
            bg_candidates.append(None)
        palette_bg_or_fallback = next((c for c in bg_candidates if c), None)
        if not palette_bg_or_fallback:
            theme = (style.theme_use() or "").lower()
            palette_bg_or_fallback = "#2b2b2b" if "dark" in theme else "#f2f2f2"

        outer = tk.Frame(self, bg=palette_bg_or_fallback, bd=1, relief="solid")
        outer.pack(fill="both", expand=True)

        container = ttk.Frame(outer, style="Calendar.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        nav = ttk.Frame(container, style="Calendar.TFrame")
        nav.pack(fill=tk.X, pady=(0, 8))

        month_frame = ttk.Frame(nav, style="Calendar.TFrame")
        month_frame.pack(side=tk.LEFT)
        ttk.Button(
            month_frame,
            text="◀",
            width=3,
            style="Calendar.Nav.TButton",
            command=lambda: self.change_month(-1),
        ).pack(side=tk.LEFT)
        self.month_label = ttk.Label(month_frame, text="", style="Calendar.Month.TLabel", width=12, anchor="center")
        self.month_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(
            month_frame,
            text="▶",
            width=3,
            style="Calendar.Nav.TButton",
            command=lambda: self.change_month(1),
        ).pack(side=tk.LEFT)

        year_frame = ttk.Frame(nav, style="Calendar.TFrame")
        year_frame.pack(side=tk.RIGHT)
        ttk.Button(
            year_frame,
            text="◀",
            width=3,
            style="Calendar.Nav.TButton",
            command=lambda: self.change_year(-1),
        ).pack(side=tk.LEFT)
        self.year_label = ttk.Label(year_frame, text="", style="Calendar.Year.TLabel", width=6, anchor="center")
        self.year_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(
            year_frame,
            text="▶",
            width=3,
            style="Calendar.Nav.TButton",
            command=lambda: self.change_year(1),
        ).pack(side=tk.LEFT)

        dow_row = ttk.Frame(container, style="Calendar.TFrame")
        dow_row.pack(fill=tk.X)
        for idx, name in enumerate(self.DOW_NAMES):
            ttk.Label(dow_row, text=name, style="Calendar.Dow.TLabel", width=4, anchor="center").grid(
                row=0, column=idx, padx=1, pady=(0, 4)
            )

        self.days_container = ttk.Frame(container, style="Calendar.TFrame")
        self.days_container.pack()
        self.render()
        self.update_idletasks()
        self.deiconify()
        self.focus_force()

    def _on_root_click(self, event: tk.Event) -> None:
        try:
            if event.widget.winfo_toplevel() == self:
                return
        except Exception:
            pass
        self._close()

    def _close(self) -> None:
        try:
            if hasattr(self, "_root") and getattr(self, "_bind_id_click", None):
                self._root.unbind("<Button-1>", self._bind_id_click)
            if hasattr(self, "_root") and getattr(self, "_bind_id_click2", None):
                self._root.unbind("<Button-3>", self._bind_id_click2)
        except Exception:
            pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def change_month(self, delta: int) -> None:
        new_month = self.current_month + delta
        if new_month < 1:
            self.current_month = 12
            self.current_year -= 1
        elif new_month > 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month = new_month
        self.render()

    def change_year(self, delta: int) -> None:
        self.current_year += delta
        self.render()

    def render(self) -> None:
        self.month_label.configure(text=self.MONTH_NAMES[self.current_month - 1])
        self.year_label.configure(text=str(self.current_year))

        for widget in self.days_container.winfo_children():
            widget.destroy()

        today = date.today()
        weeks = self.calendar.monthdayscalendar(self.current_year, self.current_month)
        if len(weeks) < 6:
            weeks += [[0, 0, 0, 0, 0, 0, 0]] * (6 - len(weeks))

        selected_button: ttk.Button | None = None
        for row_idx, week in enumerate(weeks):
            for col_idx, day in enumerate(week):
                if day == 0:
                    ttk.Label(
                        self.days_container,
                        text="",
                        width=4,
                        style="Calendar.Dow.TLabel",
                    ).grid(row=row_idx, column=col_idx, padx=1, pady=1)
                    continue

                day_date = date(self.current_year, self.current_month, day)
                is_weekend = col_idx in (5, 6)
                style = self._resolve_style(day_date, is_weekend, today)
                button = ttk.Button(
                    self.days_container,
                    text=f"{day:02d}",
                    width=4,
                    style=style,
                    command=lambda d=day: self._pick(d),
                )
                button.grid(row=row_idx, column=col_idx, padx=1, pady=1)
                if self.selected_date and day_date == self.selected_date:
                    selected_button = button

        if selected_button:
            selected_button.focus_set()

    def _resolve_style(self, day_date: date, is_weekend: bool, today: date) -> str:
        if day_date == self.selected_date:
            return "Calendar.Selected.TButton"
        if day_date == today:
            return "Calendar.Today.TButton"
        if is_weekend:
            return "Calendar.Weekend.TButton"
        return "Calendar.Day.TButton"

    def _pick(self, day: int) -> None:
        picked = date(self.current_year, self.current_month, day)
        self.selected_date = picked
        self._on_select(picked)
        self._close()

    def move_selected(self, delta_days: int) -> None:
        base_date = self.selected_date or date(self.current_year, self.current_month, 1)
        new_date = base_date + timedelta(days=delta_days)
        if new_date.month != self.current_month or new_date.year != self.current_year:
            self.current_year = new_date.year
            self.current_month = new_date.month
        self.selected_date = new_date
        self.render()

    def _confirm_selection(self) -> None:
        if self.selected_date is None:
            self.selected_date = date(self.current_year, self.current_month, 1)
        self._on_select(self.selected_date)
        self._close()


class DatePicker(ttk.Frame):
    """Date picker with a popup calendar."""

    def __init__(
        self,
        master: tk.Widget,
        initial: date | datetime | str | None = None,
        *,
        state: str = "normal",
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        initial_date = self._coerce_to_date(initial)
        self.selected_date = initial_date
        self.var = tk.StringVar(value=self._format_date(initial_date))

        entry = ttk.Entry(self, textvariable=self.var, width=12, state=state)
        entry.grid(row=0, column=0, sticky="w")
        entry.bind("<FocusOut>", self._on_entry_change)
        entry.bind("<Return>", self._on_entry_change)

        btn_state = state if state == "normal" else "disabled"
        ttk.Button(self, text="…", width=3, command=self._open_calendar, state=btn_state).grid(
            row=0, column=1, padx=(4, 0)
        )
        self._entry = entry
        self._state = state

    def get(self) -> str:
        return self.selected_date.strftime("%Y-%m-%d")

    def get_display(self) -> str:
        return self._format_date(self.selected_date)

    def set(self, value: date | datetime | str) -> None:
        try:
            parsed = self._coerce_to_date(value)
        except ValueError:
            return
        self.selected_date = parsed
        self.var.set(self._format_date(parsed))

    def _format_date(self, value: date) -> str:
        return value.strftime("%d.%m.%Y")

    def _coerce_to_date(self, value: date | datetime | str | None) -> date:
        if value is None:
            return date.today()
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        parsed_iso = dates.normalize_date_to_iso(str(value), field_label="Дата")
        return datetime.strptime(parsed_iso, "%Y-%m-%d").date()

    def _on_entry_change(self, _event: tk.Event) -> None:
        try:
            parsed_iso = dates.normalize_date_to_iso(self.var.get(), field_label="Дата")
            parsed = datetime.strptime(parsed_iso, "%Y-%m-%d").date()
        except ValueError:
            # Roll back to last valid value
            self.var.set(self._format_date(self.selected_date))
            return
        self.selected_date = parsed
        self.var.set(self._format_date(parsed))

    def _open_calendar(self) -> None:
        if self._state != "normal":
            return

        def on_select(selected: date) -> None:
            self.selected_date = selected
            self.var.set(self._format_date(selected))

        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        popup = CalendarPopup(self, self.selected_date, on_select)
        popup.geometry(f"+{x}+{y}")
        popup.focus_force()
        popup.wait_window(popup)


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


def rate_prompt(
    title: str,
    currency_code: str,
    base_currency: str,
    *,
    initial_date: Optional[str] = None,
    initial_direct: str = "",
    initial_inverse: str = "",
    decimals: int = RATE_DECIMALS,
) -> Optional[dict[str, Optional[str] | float]]:
    root = tk.Toplevel()
    root.title(title)
    root.grab_set()

    row = 0
    date_picker: DatePicker | None = None
    if initial_date is not None:
        ttk.Label(root, text="Дата").grid(row=row, column=0, padx=6, pady=4, sticky="w")
        date_picker = DatePicker(root, initial=initial_date)
        date_picker.grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

    ttk.Label(root, text=f"1 {currency_code} = ? {base_currency}").grid(
        row=row, column=0, padx=6, pady=4, sticky="w"
    )
    direct_var = tk.StringVar()
    direct_entry = ttk.Entry(root, textvariable=direct_var, width=30)
    direct_entry.grid(row=row, column=1, padx=6, pady=4)
    row += 1

    ttk.Label(root, text=f"1 {base_currency} = ? {currency_code}").grid(
        row=row, column=0, padx=6, pady=4, sticky="w"
    )
    inverse_var = tk.StringVar()
    inverse_entry = ttk.Entry(root, textvariable=inverse_var, width=30)
    inverse_entry.grid(row=row, column=1, padx=6, pady=4)

    sync = bind_two_way_rate(
        direct_entry,
        direct_var,
        inverse_entry,
        inverse_var,
        decimals=decimals,
    )

    if initial_direct and initial_inverse:
        sync["last"]["field"] = "direct"
        direct_var.set(initial_direct)
        inverse_var.set(initial_inverse)
    elif initial_direct:
        sync["last"]["field"] = "direct"
        direct_var.set(initial_direct)
    elif initial_inverse:
        sync["last"]["field"] = "inverse"
        inverse_var.set(initial_inverse)

    result: Optional[dict[str, Optional[str] | float]] = None

    def on_ok() -> None:
        nonlocal result
        date_value = None
        if date_picker is not None:
            try:
                date_value = dates.normalize_date_to_iso(date_picker.get(), field_label="Дата")
            except ValueError:
                messagebox.showerror("Курси", "Вкажіть дату")
                return
        last_field = sync["last"]["field"]
        if last_field == "direct":
            direct = parse_decimal(direct_var.get())
            if direct is None:
                messagebox.showerror("Курси", "Введи коректний курс")
                return
            inverse = 1.0 / direct
        else:
            inverse = parse_decimal(inverse_var.get())
            if inverse is None:
                messagebox.showerror("Курси", "Введи коректний курс")
                return
            direct = 1.0 / inverse
        direct_var.set(format_rate(direct, decimals))
        inverse_var.set(format_rate(inverse, decimals))
        result = {"date": date_value, "direct": direct, "inverse": inverse}
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    btn_frame = ttk.Frame(root)
    btn_frame.grid(row=row + 1, column=0, columnspan=2, pady=8)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Скасувати", command=on_cancel).pack(side=tk.LEFT, padx=4)
    root.bind("<Return>", lambda e: on_ok())
    root.bind("<Escape>", lambda e: on_cancel())
    direct_entry.focus_set()
    root.wait_window()
    return result
