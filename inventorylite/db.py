"""SQLite database helpers for InventoryLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
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

            CREATE TABLE IF NOT EXISTS Counterparties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('supplier','customer','other')),
                phone TEXT,
                email TEXT,
                address TEXT,
                note TEXT,
                UNIQUE(name, type)
            );

            CREATE TABLE IF NOT EXISTS Documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_type TEXT NOT NULL CHECK(doc_type IN ('IN','OUT')),
                doc_date TEXT NOT NULL,
                number TEXT,
                counterparty_id INTEGER,
                comment TEXT,
                status TEXT NOT NULL CHECK(status IN ('draft','posted')) DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(counterparty_id) REFERENCES Counterparties(id)
            );

            CREATE TABLE IF NOT EXISTS DocumentLines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY(document_id) REFERENCES Documents(id) ON DELETE CASCADE,
                FOREIGN KEY(product_id) REFERENCES Products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_document_lines_doc ON DocumentLines(document_id);

            CREATE TABLE IF NOT EXISTS StockBalances (
                product_id INTEGER PRIMARY KEY,
                quantity REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES Products(id)
            );
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


# Counterparties

def list_counterparties(counterparty_type: Optional[str] = None) -> List[sqlite3.Row]:
    query = "SELECT id, name, type, phone, email, address, note FROM Counterparties"
    params: Tuple[str, ...] = ()
    if counterparty_type:
        query += " WHERE type = ?"
        params = (counterparty_type,)
    query += " ORDER BY name"
    with get_connection() as conn:
        return list(conn.execute(query, params))


def add_counterparty(
    name: str, ctype: str, phone: str = "", email: str = "", address: str = "", note: str = ""
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Counterparties (name, type, phone, email, address, note) VALUES (?,?,?,?,?,?)",
            (name.strip(), ctype, phone.strip(), email.strip(), address.strip(), note.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_counterparty(
    counterparty_id: int,
    name: str,
    ctype: str,
    phone: str = "",
    email: str = "",
    address: str = "",
    note: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Counterparties SET name=?, type=?, phone=?, email=?, address=?, note=? WHERE id=?",
            (name.strip(), ctype, phone.strip(), email.strip(), address.strip(), note.strip(), counterparty_id),
        )
        conn.commit()


def delete_counterparty(counterparty_id: int) -> None:
    with get_connection() as conn:
        used = conn.execute("SELECT COUNT(*) FROM Documents WHERE counterparty_id=?", (counterparty_id,)).fetchone()[0]
        if used:
            raise ValueError("Контрагент використовується у документах")
        conn.execute("DELETE FROM Counterparties WHERE id=?", (counterparty_id,))
        conn.commit()


# Documents

def create_document(
    doc_type: str,
    doc_date: str,
    number: str = "",
    counterparty_id: Optional[int] = None,
    comment: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Documents (doc_type, doc_date, number, counterparty_id, comment, status) VALUES (?,?,?,?,?, 'draft')",
            (doc_type, doc_date, number.strip(), counterparty_id, comment.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_document(
    document_id: int,
    doc_type: str,
    doc_date: str,
    number: str = "",
    counterparty_id: Optional[int] = None,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM Documents WHERE id=?", (document_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "draft":
            raise ValueError("Редагування доступне лише у статусі чернетка")
        conn.execute(
            "UPDATE Documents SET doc_type=?, doc_date=?, number=?, counterparty_id=?, comment=? WHERE id=?",
            (doc_type, doc_date, number.strip(), counterparty_id, comment.strip(), document_id),
        )
        conn.commit()


def update_document_comment(document_id: int, comment: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE Documents SET comment=? WHERE id=?", (comment.strip(), document_id))
        conn.commit()


def delete_document(document_id: int) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM Documents WHERE id=?", (document_id,)).fetchone()
        if not status:
            return
        if status[0] != "draft":
            raise ValueError("Видаляти можна лише чернетки")
        conn.execute("DELETE FROM Documents WHERE id=?", (document_id,))
        conn.commit()


def set_document_status(document_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE Documents SET status=? WHERE id=?", (status, document_id))
        conn.commit()


def replace_document_lines(document_id: int, lines: Iterable[Tuple[int, float, float]]) -> None:
    with get_connection() as conn:
        current_status = conn.execute("SELECT status FROM Documents WHERE id=?", (document_id,)).fetchone()
        if not current_status:
            raise ValueError("Документ не знайдено")
        if current_status[0] != "draft":
            raise ValueError("Рядки можна змінювати лише у чернетці")
        conn.execute("DELETE FROM DocumentLines WHERE document_id=?", (document_id,))
        for product_id, qty, price in lines:
            amount = qty * price
            conn.execute(
                "INSERT INTO DocumentLines (document_id, product_id, quantity, price, amount) VALUES (?,?,?,?,?)",
                (document_id, product_id, qty, price, amount),
            )
        conn.commit()


def list_documents(
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    counterparty_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[sqlite3.Row]:
    query = (
        "SELECT d.id, d.doc_date, d.doc_type, d.number, d.counterparty_id, d.comment, d.status, c.name AS counterparty, "
        "IFNULL(SUM(dl.amount),0) AS total "
        "FROM Documents d "
        "LEFT JOIN Counterparties c ON d.counterparty_id = c.id "
        "LEFT JOIN DocumentLines dl ON dl.document_id = d.id "
    )
    clauses = []
    params: List[object] = []
    if doc_type:
        clauses.append("d.doc_type = ?")
        params.append(doc_type)
    if status:
        clauses.append("d.status = ?")
        params.append(status)
    if counterparty_id:
        clauses.append("d.counterparty_id = ?")
        params.append(counterparty_id)
    if date_from:
        clauses.append("d.doc_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("d.doc_date <= ?")
        params.append(date_to)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " GROUP BY d.id ORDER BY d.doc_date, d.id"
    with get_connection() as conn:
        return list(conn.execute(query, params))


def get_document(document_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM Documents WHERE id=?", (document_id,)).fetchone()
        return row


def list_document_lines(document_id: int) -> List[sqlite3.Row]:
    query = (
        "SELECT dl.id, dl.product_id, dl.quantity, dl.price, dl.amount, p.name as product_name, p.sku "
        "FROM DocumentLines dl JOIN Products p ON dl.product_id = p.id WHERE dl.document_id=?"
    )
    with get_connection() as conn:
        return list(conn.execute(query, (document_id,)))


def _update_balance(conn: sqlite3.Connection, product_id: int, delta: float) -> None:
    conn.execute(
        "INSERT INTO StockBalances (product_id, quantity, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(product_id) DO UPDATE SET quantity = StockBalances.quantity + excluded.quantity, "
        "updated_at=CURRENT_TIMESTAMP",
        (product_id, delta),
    )


def _get_balance(conn: sqlite3.Connection, product_id: int) -> float:
    row = conn.execute("SELECT quantity FROM StockBalances WHERE product_id=?", (product_id,)).fetchone()
    return float(row[0]) if row else 0.0


def post_document(document_id: int, allow_negative: bool = False) -> None:
    with get_connection() as conn:
        doc = conn.execute("SELECT doc_type, status FROM Documents WHERE id=?", (document_id,)).fetchone()
        if not doc:
            raise ValueError("Документ не знайдено")
        if doc["status"] != "draft":
            raise ValueError("Документ вже проведено")
        lines = list(conn.execute("SELECT product_id, quantity FROM DocumentLines WHERE document_id=?", (document_id,)))
        if not lines:
            raise ValueError("Немає рядків для проведення")
        for line in lines:
            qty = float(line["quantity"])
            if doc["doc_type"] == "OUT" and not allow_negative:
                balance = _get_balance(conn, line["product_id"])
                if balance < qty:
                    raise ValueError("Недостатньо залишку для товару")
        for line in lines:
            qty = float(line["quantity"])
            delta = qty if doc["doc_type"] == "IN" else -qty
            _update_balance(conn, line["product_id"], delta)
        conn.execute("UPDATE Documents SET status='posted' WHERE id=?", (document_id,))
        conn.commit()


def unpost_document(document_id: int) -> None:
    with get_connection() as conn:
        doc = conn.execute("SELECT doc_type, status FROM Documents WHERE id=?", (document_id,)).fetchone()
        if not doc:
            raise ValueError("Документ не знайдено")
        if doc["status"] != "posted":
            raise ValueError("Документ не проведено")
        lines = list(conn.execute("SELECT product_id, quantity FROM DocumentLines WHERE document_id=?", (document_id,)))
        for line in lines:
            qty = float(line["quantity"])
            delta = -qty if doc["doc_type"] == "IN" else qty
            _update_balance(conn, line["product_id"], delta)
        conn.execute("UPDATE Documents SET status='draft' WHERE id=?", (document_id,))
        conn.commit()


def recalc_balances() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM StockBalances")
        docs = conn.execute(
            "SELECT id, doc_type FROM Documents WHERE status='posted' ORDER BY doc_date, id"
        ).fetchall()
        for doc in docs:
            lines = conn.execute("SELECT product_id, quantity FROM DocumentLines WHERE document_id=?", (doc["id"],)).fetchall()
            for line in lines:
                qty = float(line["quantity"])
                delta = qty if doc["doc_type"] == "IN" else -qty
                _update_balance(conn, line["product_id"], delta)
        conn.commit()


def list_stock(search: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT p.id, p.name, p.sku, IFNULL(sb.quantity, 0) as quantity "
        "FROM Products p LEFT JOIN StockBalances sb ON sb.product_id = p.id"
    )
    params: Tuple[str, ...] = ()
    if search:
        query += " WHERE lower(p.name) LIKE ?"
        params = (f"%{search.lower()}%",)
    query += " ORDER BY p.name"
    with get_connection() as conn:
        return list(conn.execute(query, params))


