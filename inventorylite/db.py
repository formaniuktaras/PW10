"""SQLite database helpers for InventoryLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple
import logging

from utils import get_db_path


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT UNIQUE NOT NULL,
                brand_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                FOREIGN KEY (brand_id) REFERENCES Brands(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_products_sku_lower ON Products(lower(sku));
            CREATE INDEX IF NOT EXISTS idx_products_name_lower ON Products(lower(name));
            """
        )
    logging.info("Database initialized at %s", db_path)


# Brand CRUD

def list_brands() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return list(conn.execute("SELECT id, name FROM Brands ORDER BY name"))


def add_brand(name: str) -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO Brands (name) VALUES (?)", (name.strip(),))
        conn.commit()
        return cur.lastrowid


def update_brand(brand_id: int, name: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE Brands SET name=? WHERE id=?", (name.strip(), brand_id))
        conn.commit()


def delete_brand(brand_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM Brands WHERE id=?", (brand_id,))
        conn.commit()


# Category CRUD

def list_categories() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return list(conn.execute("SELECT id, name FROM Categories ORDER BY name"))


def add_category(name: str) -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO Categories (name) VALUES (?)", (name.strip(),))
        conn.commit()
        return cur.lastrowid


def update_category(category_id: int, name: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE Categories SET name=? WHERE id=?", (name.strip(), category_id))
        conn.commit()


def delete_category(category_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM Categories WHERE id=?", (category_id,))
        conn.commit()


# Product CRUD

def list_products(search: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT p.id, p.sku, p.name, b.name AS brand, c.name AS category, p.brand_id, p.category_id "
        "FROM Products p "
        "JOIN Brands b ON p.brand_id = b.id "
        "JOIN Categories c ON p.category_id = c.id "
        "ORDER BY p.name"
    )
    params: Tuple[str, ...] = ()
    if search:
        term = f"%{search.lower()}%"
        query = query.replace("ORDER BY p.name", "WHERE lower(p.sku) LIKE ? OR lower(p.name) LIKE ? ORDER BY p.name")
        params = (term, term)
    with get_connection() as conn:
        return list(conn.execute(query, params))


def add_product(sku: str, name: str, brand_id: int, category_id: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Products (sku, name, brand_id, category_id) VALUES (?, ?, ?, ?)",
            (sku.strip(), name.strip(), brand_id, category_id),
        )
        conn.commit()
        return cur.lastrowid


def update_product(product_id: int, sku: str, name: str, brand_id: int, category_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Products SET sku=?, name=?, brand_id=?, category_id=? WHERE id=?",
            (sku.strip(), name.strip(), brand_id, category_id, product_id),
        )
        conn.commit()


def delete_product(product_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM Products WHERE id=?", (product_id,))
        conn.commit()


def export_table_to_csv(table: str, output_path: Path) -> None:
    import csv

    with get_connection() as conn, output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        rows = conn.execute(f"SELECT * FROM {table}")
        writer.writerow([col[0] for col in rows.description])
        writer.writerows(rows)
    logging.info("Exported %s to %s", table, output_path)


