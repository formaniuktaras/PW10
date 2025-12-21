from __future__ import annotations

import logging
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from inventorylite import db
from inventorylite.utils import get_data_dir, show_error


class ExportTab:
    def __init__(self, parent: ttk.Notebook) -> None:
        self.frame = ttk.Frame(parent)
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self.frame,
            text="Експорт таблиць у CSV",
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=10)

        tables = [
            ("Brands", "Бренди"),
            ("Categories", "Категорії"),
            ("Products", "Товари"),
            ("AdditionalProductCategories", "Додаткові категорії"),
            ("Counterparties", "Контрагенти"),
            ("Warehouses", "Склади"),
            ("SalesChannels", "Канали"),
            ("PurchaseDocuments", "Закупівлі"),
            ("PurchaseLines", "Рядки закупівель"),
            ("SalesDocuments", "Продажі"),
            ("SalesLines", "Рядки продажів"),
            ("StockBalances", "Залишки"),
            ("StockMoves", "Рухи товарів"),
            ("CashTransactions", "Каса"),
        ]

        for table, label in tables:
            ttk.Button(
                self.frame,
                text=f"Експорт {label}",
                command=lambda t=table: self.export_csv(t),
            ).pack(pady=4)

    def export_csv(self, table: str) -> None:
        file_path = get_data_dir() / f"{table.lower()}_export.csv"
        try:
            db.export_table_to_csv(table, file_path)
            messagebox.showinfo("Експорт", f"Файл збережено: {file_path}")
        except Exception:
            logging.exception("Export error")
            show_error("Експорт", "Не вдалося експортувати таблицю.")
