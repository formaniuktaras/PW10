from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

from inventorylite import db
from inventorylite.ui_components import TableFrame
from inventorylite.utils import show_error, Settings
from inventorylite.dialogs import channel_prompt


class ChannelsTab:
    def __init__(self, parent: ttk.Notebook, settings: Settings) -> None:
        self.parent = parent
        self.settings = settings
        self.frame = ttk.Frame(parent)
        self.channel_table: TableFrame | None = None
        self._build()

    def _build(self) -> None:
        columns = [("name", "Назва", 240), ("is_active", "Активний", 100)]
        self.channel_table = TableFrame(self.frame, columns)
        self.channel_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.channel_table.on_double_click(self.edit_channel)
        self.channel_table.register_context_menu(self.edit_channel, self.delete_channel)

        btns = ttk.Frame(self.frame)
        btns.pack(pady=4)
        ttk.Button(btns, text="Додати", command=self.add_channel).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Змінити", command=self.edit_channel).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Видалити", command=self.delete_channel).pack(side=tk.LEFT, padx=4)

        self.frame.after_idle(self.refresh_channels)

    def refresh_channels(self) -> None:
        if not self.channel_table:
            return
        rows = db.list_channels()
        self.channel_table.set_rows(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "is_active": "Так" if r["is_active"] else "Ні",
                }
                for r in rows
            ]
        )

    def add_channel(self) -> None:
        values = channel_prompt()
        if not values:
            return
        name, is_active = values
        try:
            db.add_channel(name, is_active)
            self.refresh_channels()
        except sqlite3.IntegrityError:
            show_error("Канали", "Канал з такою назвою вже існує.")
        except Exception:
            logging.exception("Add channel error")
            show_error("Канали", "Не вдалося додати канал.")

    def edit_channel(self) -> None:
        if not self.channel_table:
            return
        channel_id = self.channel_table.selected_id()
        if not channel_id:
            show_error("Канали", "Оберіть канал.")
            return
        rows = [c for c in db.list_channels() if c["id"] == channel_id]
        if not rows:
            return
        c = rows[0]
        values = channel_prompt((c["name"], bool(c["is_active"])))
        if not values:
            return
        name, is_active = values
        try:
            db.update_channel(channel_id, name, is_active)
            self.refresh_channels()
        except sqlite3.IntegrityError:
            show_error("Канали", "Канал з такою назвою вже існує.")
        except Exception:
            logging.exception("Edit channel error")
            show_error("Канали", "Не вдалося змінити канал.")

    def delete_channel(self) -> None:
        if not self.channel_table:
            return
        channel_id = self.channel_table.selected_id()
        if not channel_id:
            show_error("Канали", "Оберіть канал для видалення.")
            return
        if not messagebox.askyesno("Підтвердження", "Видалити канал?"):
            return
        try:
            db.delete_channel(channel_id)
            self.refresh_channels()
        except Exception as exc:
            logging.exception("Delete channel error")
            show_error("Канали", str(exc))
