from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from inventorylite import db, dates
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings, show_error
from inventorylite.dialogs_documents import cash_prompt


class CashTab:
    def __init__(self, parent: ttk.Notebook, settings: Settings) -> None:
        self.frame = ttk.Frame(parent)
        self.settings = settings

        self.cash_date_from_var = tk.StringVar()
        self.cash_date_to_var = tk.StringVar()

        self.cash_table: TableFrame | None = None
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self.frame)
        top.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(top, text="Дата з:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.cash_date_from_var, width=10).pack(side=tk.LEFT, padx=2)

        ttk.Label(top, text="по:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.cash_date_to_var, width=10).pack(side=tk.LEFT, padx=2)

        ttk.Button(top, text="Фільтр", command=self.refresh_cash).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Додати рух", command=self.add_cash).pack(side=tk.LEFT, padx=6)

        columns = [
            ("date", "Дата", 90),
            ("type", "Тип", 140),
            ("amount_doc", "Сума (вал)", 110),
            ("currency", "Валюта", 70),
            ("rate", "Курс", 80),
            ("amount", "Сума (база)", 110),
            ("counterparty", "Контрагент", 160),
            ("channel", "Канал", 120),
            ("related", "Документ", 120),
            ("comment", "Коментар", 220),
        ]
        self.cash_table = TableFrame(self.frame, columns)
        self.cash_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.frame.after_idle(self.refresh_cash)

    def refresh_cash(self) -> None:
        if not self.cash_table:
            return
        try:
            rows = db.list_cash(
                self.cash_date_from_var.get().strip() or None,
                self.cash_date_to_var.get().strip() or None,
            )
        except ValueError as exc:
            show_error("Каса", str(exc))
            return
        type_labels = {
            "sale_payment": "Оплата від клієнта",
            "purchase_payment": "Оплата постачальнику",
            "other_income": "Інший дохід",
            "other_variable_expense": "Змінна витрата",
            "fixed_expense": "Постійна витрата",
        }
        self.cash_table.set_rows(
            [
                {
                    "id": r["id"],
                    "date": dates.format_iso_to_dmy(r["date"]),
                    "type": type_labels.get(r["type"], r["type"]),
                    "amount_doc": f"{r['amount_doc']:.2f}",
                    "currency": r["currency_code"],
                    "rate": f"{r['exchange_rate']:.4f}",
                    "amount": f"{r['amount']:.2f}",
                    "counterparty": r["counterparty"] or "-",
                    "channel": r["channel"] or "-",
                    "related": f"{r['related_doc_type'] or ''} #{r['related_doc_id'] or ''}",
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        )

    def add_cash(self) -> None:
        counterparties = db.list_counterparties()
        channels = db.list_channels(active_only=True)
        transactions = cash_prompt(counterparties, channels)
        if not transactions:
            return
        try:
            for tx in transactions:
                db.add_cash_transaction(**tx)
            self.refresh_cash()
        except Exception:
            logging.exception("Add cash error")
            show_error("Каса", "Не вдалося зберегти рух коштів")
