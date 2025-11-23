"""SQLite database helpers for InventoryLite with cash-basis accounting.

This module stores reference data (brands, categories, products, warehouses,
channels, counterparties) and operational documents (purchases, sales,
cash transactions). Inventory is valued using moving-average cost per
product and warehouse. Income and expenses are recognized only when cash
actually moves (cash basis). Direct-costing is applied: COGS includes only
variable costs from purchase price; fixed costs are captured via cash
transactions but are not added into inventory cost.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from utils import get_db_path


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create database schema if it does not exist."""
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

            CREATE TABLE IF NOT EXISTS Warehouses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS SalesChannels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS Products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT UNIQUE NOT NULL,
                unit TEXT NOT NULL DEFAULT 'pcs',
                brand_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (brand_id) REFERENCES Brands(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_products_sku_lower ON Products(lower(sku));
            CREATE INDEX IF NOT EXISTS idx_products_name_lower ON Products(lower(name));

            CREATE TABLE IF NOT EXISTS Counterparties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('supplier','customer','both','other')),
                phone TEXT,
                email TEXT,
                address TEXT,
                note TEXT,
                UNIQUE(name, type)
            );

            CREATE TABLE IF NOT EXISTS PurchaseDocuments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_date TEXT NOT NULL,
                supplier_id INTEGER,
                warehouse_id INTEGER NOT NULL,
                channel TEXT,
                status TEXT NOT NULL CHECK(status IN ('draft','posted')) DEFAULT 'draft',
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES Counterparties(id),
                FOREIGN KEY (warehouse_id) REFERENCES Warehouses(id)
            );

            CREATE TABLE IF NOT EXISTS PurchaseLines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                purchase_price REAL NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (purchase_id) REFERENCES PurchaseDocuments(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES Products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_purchase_lines_purchase ON PurchaseLines(purchase_id);

            CREATE TABLE IF NOT EXISTS SalesDocuments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_date TEXT NOT NULL,
                customer_id INTEGER,
                warehouse_id INTEGER NOT NULL,
                channel TEXT,
                status TEXT NOT NULL CHECK(status IN ('draft','posted')) DEFAULT 'draft',
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES Counterparties(id),
                FOREIGN KEY (warehouse_id) REFERENCES Warehouses(id)
            );

            CREATE TABLE IF NOT EXISTS SalesLines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                sale_price REAL NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES SalesDocuments(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES Products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sales_lines_sale ON SalesLines(sale_id);

            CREATE TABLE IF NOT EXISTS StockBalances (
                product_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                average_cost REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (product_id, warehouse_id),
                FOREIGN KEY (product_id) REFERENCES Products(id),
                FOREIGN KEY (warehouse_id) REFERENCES Warehouses(id)
            );

            CREATE TABLE IF NOT EXISTS StockMoves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                move_date TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                qty_in REAL NOT NULL DEFAULT 0,
                qty_out REAL NOT NULL DEFAULT 0,
                cost_per_unit REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                reference_type TEXT NOT NULL,
                reference_id INTEGER NOT NULL,
                channel TEXT,
                counterparty_id INTEGER,
                FOREIGN KEY (product_id) REFERENCES Products(id),
                FOREIGN KEY (warehouse_id) REFERENCES Warehouses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_stock_moves_ref ON StockMoves(reference_type, reference_id);

            CREATE TABLE IF NOT EXISTS CashTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL CHECK(type IN (
                    'sale_payment','purchase_payment','other_income','other_variable_expense','fixed_expense'
                )),
                counterparty_id INTEGER,
                related_doc_type TEXT,
                related_doc_id INTEGER,
                channel TEXT,
                comment TEXT,
                FOREIGN KEY(counterparty_id) REFERENCES Counterparties(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cash_date ON CashTransactions(date);
            """
        )
        _migrate_schema(conn)
    logging.info("Database initialized at %s", db_path)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        logging.info("Adding missing column %s.%s", table, column)
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Ensure legacy databases get new columns required by current version."""

    _ensure_column(conn, "Products", "unit", "TEXT NOT NULL DEFAULT 'pcs'")
    _ensure_column(conn, "Products", "is_active", "INTEGER NOT NULL DEFAULT 1")

    _ensure_column(conn, "Counterparties", "type", "TEXT NOT NULL DEFAULT 'other'")
    _ensure_column(conn, "Counterparties", "phone", "TEXT")
    _ensure_column(conn, "Counterparties", "email", "TEXT")
    _ensure_column(conn, "Counterparties", "address", "TEXT")
    _ensure_column(conn, "Counterparties", "note", "TEXT")

    _ensure_column(conn, "Warehouses", "description", "TEXT")
    _ensure_column(conn, "Warehouses", "is_active", "INTEGER NOT NULL DEFAULT 1")

    _ensure_column(conn, "SalesChannels", "is_active", "INTEGER NOT NULL DEFAULT 1")

    _ensure_column(conn, "PurchaseDocuments", "channel", "TEXT")
    _ensure_column(conn, "PurchaseDocuments", "status", "TEXT NOT NULL DEFAULT 'draft'")
    _ensure_column(conn, "PurchaseDocuments", "comment", "TEXT")
    _ensure_column(conn, "PurchaseDocuments", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

    _ensure_column(conn, "PurchaseLines", "amount", "REAL NOT NULL DEFAULT 0")

    _ensure_column(conn, "SalesDocuments", "channel", "TEXT")
    _ensure_column(conn, "SalesDocuments", "status", "TEXT NOT NULL DEFAULT 'draft'")
    _ensure_column(conn, "SalesDocuments", "comment", "TEXT")
    _ensure_column(conn, "SalesDocuments", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

    _ensure_column(conn, "SalesLines", "amount", "REAL NOT NULL DEFAULT 0")

    _ensure_column(conn, "StockMoves", "channel", "TEXT")
    _ensure_column(conn, "StockMoves", "counterparty_id", "INTEGER")

    _ensure_column(conn, "CashTransactions", "type", "TEXT NOT NULL DEFAULT 'other_income'")
    _ensure_column(conn, "CashTransactions", "counterparty_id", "INTEGER")
    _ensure_column(conn, "CashTransactions", "related_doc_type", "TEXT")
    _ensure_column(conn, "CashTransactions", "related_doc_id", "INTEGER")
    _ensure_column(conn, "CashTransactions", "channel", "TEXT")
    _ensure_column(conn, "CashTransactions", "comment", "TEXT")

    _migrate_stock_balances(conn)

    conn.commit()


def _migrate_stock_balances(conn: sqlite3.Connection) -> None:
    """Rebuild StockBalances table if it misses expected columns or PK."""

    cur = conn.execute("PRAGMA table_info(StockBalances)")
    columns = {row[1]: row[5] for row in cur.fetchall()}  # name -> pk position
    expected_columns = {"product_id", "warehouse_id", "quantity", "average_cost", "updated_at"}
    has_all_columns = expected_columns.issubset(columns)
    has_composite_pk = columns.get("product_id") and columns.get("warehouse_id")

    if has_all_columns and has_composite_pk:
        return

    logging.info("Rebuilding StockBalances schema to include warehouse-level balances")
    conn.execute("ALTER TABLE StockBalances RENAME TO StockBalances_old")
    conn.execute(
        """
        CREATE TABLE StockBalances (
            product_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            average_cost REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (product_id, warehouse_id),
            FOREIGN KEY (product_id) REFERENCES Products(id),
            FOREIGN KEY (warehouse_id) REFERENCES Warehouses(id)
        )
        """
    )

    default_wh = conn.execute("SELECT id FROM Warehouses ORDER BY id LIMIT 1").fetchone()
    if not default_wh:
        default_wh_id = conn.execute(
            "INSERT INTO Warehouses (name, description, is_active) VALUES ('Main warehouse','',1)"
        ).lastrowid
    else:
        default_wh_id = int(default_wh[0])

    old_columns = {row[1] for row in conn.execute("PRAGMA table_info(StockBalances_old)").fetchall()}
    if "warehouse_id" in old_columns:
        conn.execute(
            """
            INSERT INTO StockBalances (product_id, warehouse_id, quantity, average_cost, updated_at)
            SELECT product_id, warehouse_id, quantity, average_cost, updated_at
            FROM StockBalances_old
            """
        )
    else:
        conn.execute(
            """
            INSERT INTO StockBalances (product_id, warehouse_id, quantity, average_cost, updated_at)
            SELECT product_id, ?, quantity, average_cost, updated_at
            FROM StockBalances_old
            """,
            (default_wh_id,),
        )

    conn.execute("DROP TABLE StockBalances_old")


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
        "SELECT p.id, p.sku, p.name, p.unit, p.is_active, b.name AS brand, c.name AS category, p.brand_id, p.category_id "
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


def add_product(sku: str, name: str, brand_id: int, category_id: int, unit: str = "pcs", is_active: bool = True) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Products (sku, name, brand_id, category_id, unit, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            (sku.strip(), name.strip(), brand_id, category_id, unit.strip() or "pcs", 1 if is_active else 0),
        )
        conn.commit()
        return cur.lastrowid


def update_product(
    product_id: int, sku: str, name: str, brand_id: int, category_id: int, unit: str = "pcs", is_active: bool = True
) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Products SET sku=?, name=?, brand_id=?, category_id=?, unit=?, is_active=? WHERE id=?",
            (sku.strip(), name.strip(), brand_id, category_id, unit.strip() or "pcs", 1 if is_active else 0, product_id),
        )
        conn.commit()


def delete_product(product_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM Products WHERE id=?", (product_id,))
        conn.commit()


# Warehouses and channels

def list_warehouses(active_only: bool = False) -> List[sqlite3.Row]:
    query = "SELECT id, name, description, is_active FROM Warehouses"
    if active_only:
        query += " WHERE is_active=1"
    query += " ORDER BY name"
    with get_connection() as conn:
        return list(conn.execute(query))


def add_warehouse(name: str, description: str = "", is_active: bool = True) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Warehouses (name, description, is_active) VALUES (?,?,?)", (name.strip(), description.strip(), 1 if is_active else 0)
        )
        conn.commit()
        return cur.lastrowid


def update_warehouse(warehouse_id: int, name: str, description: str = "", is_active: bool = True) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Warehouses SET name=?, description=?, is_active=? WHERE id=?",
            (name.strip(), description.strip(), 1 if is_active else 0, warehouse_id),
        )
        conn.commit()


def delete_warehouse(warehouse_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM Warehouses WHERE id=?", (warehouse_id,))
        conn.commit()


def list_channels(active_only: bool = False) -> List[sqlite3.Row]:
    query = "SELECT id, name, is_active FROM SalesChannels"
    if active_only:
        query += " WHERE is_active=1"
    query += " ORDER BY name"
    with get_connection() as conn:
        return list(conn.execute(query))


def add_channel(name: str, is_active: bool = True) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO SalesChannels (name, is_active) VALUES (?, ?)",
            (name.strip(), 1 if is_active else 0),
        )
        conn.commit()
        return cur.lastrowid


def update_channel(channel_id: int, name: str, is_active: bool = True) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE SalesChannels SET name=?, is_active=? WHERE id=?",
            (name.strip(), 1 if is_active else 0, channel_id),
        )
        conn.commit()


def delete_channel(channel_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM SalesChannels WHERE id=?", (channel_id,))
        conn.commit()


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
        used_purchase = conn.execute(
            "SELECT COUNT(*) FROM PurchaseDocuments WHERE supplier_id=?", (counterparty_id,)
        ).fetchone()[0]
    with get_connection() as conn:
        used_sales = conn.execute("SELECT COUNT(*) FROM SalesDocuments WHERE customer_id=?", (counterparty_id,)).fetchone()[0]
        if used_purchase or used_sales:
            raise ValueError("Контрагент використовується у документах")
        conn.execute("DELETE FROM Counterparties WHERE id=?", (counterparty_id,))
        conn.commit()


# Helpers for balances

def _get_balance(conn: sqlite3.Connection, product_id: int, warehouse_id: int) -> Tuple[float, float]:
    row = conn.execute(
        "SELECT quantity, average_cost FROM StockBalances WHERE product_id=? AND warehouse_id=?",
        (product_id, warehouse_id),
    ).fetchone()
    if not row:
        return 0.0, 0.0
    return float(row[0]), float(row[1])


def _set_balance(conn: sqlite3.Connection, product_id: int, warehouse_id: int, quantity: float, average_cost: float) -> None:
    conn.execute(
        "INSERT INTO StockBalances (product_id, warehouse_id, quantity, average_cost, updated_at) "
        "VALUES (?,?,?,?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(product_id, warehouse_id) DO UPDATE SET quantity=excluded.quantity, average_cost=excluded.average_cost, updated_at=CURRENT_TIMESTAMP",
        (product_id, warehouse_id, quantity, average_cost),
    )


# Purchases

def create_purchase(doc_date: str, supplier_id: Optional[int], warehouse_id: int, channel: str, comment: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO PurchaseDocuments (doc_date, supplier_id, warehouse_id, channel, comment, status) VALUES (?,?,?,?,?, 'draft')",
            (doc_date, supplier_id, warehouse_id, channel.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_purchase(purchase_id: int, doc_date: str, supplier_id: Optional[int], warehouse_id: int, channel: str, comment: str) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "draft":
            raise ValueError("Редагування можливе лише у чернетці")
        conn.execute(
            "UPDATE PurchaseDocuments SET doc_date=?, supplier_id=?, warehouse_id=?, channel=?, comment=? WHERE id=?",
            (doc_date, supplier_id, warehouse_id, channel.strip(), comment.strip(), purchase_id),
        )
        conn.commit()


def replace_purchase_lines(purchase_id: int, lines: Iterable[Tuple[int, float, float]]) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()
        if not status or status[0] != "draft":
            raise ValueError("Рядки можна змінювати лише у чернетці")
        conn.execute("DELETE FROM PurchaseLines WHERE purchase_id=?", (purchase_id,))
        for product_id, qty, price in lines:
            amount = qty * price
            conn.execute(
                "INSERT INTO PurchaseLines (purchase_id, product_id, quantity, purchase_price, amount) VALUES (?,?,?,?,?)",
                (purchase_id, product_id, qty, price, amount),
            )
        conn.commit()


def list_purchases(status: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT p.id, p.doc_date, p.status, p.comment, p.channel, p.supplier_id, c.name as supplier, w.name as warehouse, "
        "IFNULL(SUM(pl.amount),0) as total "
        "FROM PurchaseDocuments p "
        "LEFT JOIN Counterparties c ON c.id = p.supplier_id "
        "LEFT JOIN Warehouses w ON w.id = p.warehouse_id "
        "LEFT JOIN PurchaseLines pl ON pl.purchase_id = p.id"
    )
    clauses: List[str] = []
    params: List[object] = []
    if status:
        clauses.append("p.status=?")
        params.append(status)
    if date_from:
        clauses.append("p.doc_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("p.doc_date <= ?")
        params.append(date_to)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " GROUP BY p.id ORDER BY p.doc_date, p.id"
    with get_connection() as conn:
        return list(conn.execute(query, params))


def get_purchase(purchase_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()


def list_purchase_lines(purchase_id: int) -> List[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                "SELECT pl.id, pl.product_id, pl.quantity, pl.purchase_price, pl.amount, p.name as product_name, p.sku "
                "FROM PurchaseLines pl JOIN Products p ON p.id = pl.product_id WHERE pl.purchase_id=?",
                (purchase_id,),
            )
        )


# Sales

def create_sale(doc_date: str, customer_id: Optional[int], warehouse_id: int, channel: str, comment: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO SalesDocuments (doc_date, customer_id, warehouse_id, channel, comment, status) VALUES (?,?,?,?,?, 'draft')",
            (doc_date, customer_id, warehouse_id, channel.strip(), comment.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_sale(sale_id: int, doc_date: str, customer_id: Optional[int], warehouse_id: int, channel: str, comment: str) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "draft":
            raise ValueError("Редагування можливе лише у чернетці")
        conn.execute(
            "UPDATE SalesDocuments SET doc_date=?, customer_id=?, warehouse_id=?, channel=?, comment=? WHERE id=?",
            (doc_date, customer_id, warehouse_id, channel.strip(), comment.strip(), sale_id),
        )
        conn.commit()


def replace_sale_lines(sale_id: int, lines: Iterable[Tuple[int, float, float]]) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()
        if not status or status[0] != "draft":
            raise ValueError("Рядки можна змінювати лише у чернетці")
        conn.execute("DELETE FROM SalesLines WHERE sale_id=?", (sale_id,))
        for product_id, qty, price in lines:
            amount = qty * price
            conn.execute(
                "INSERT INTO SalesLines (sale_id, product_id, quantity, sale_price, amount) VALUES (?,?,?,?,?)",
                (sale_id, product_id, qty, price, amount),
            )
        conn.commit()


def list_sales(status: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT s.id, s.doc_date, s.status, s.comment, s.channel, s.customer_id, c.name as customer, w.name as warehouse, "
        "IFNULL(SUM(sl.amount),0) as total "
        "FROM SalesDocuments s "
        "LEFT JOIN Counterparties c ON c.id = s.customer_id "
        "LEFT JOIN Warehouses w ON w.id = s.warehouse_id "
        "LEFT JOIN SalesLines sl ON sl.sale_id = s.id"
    )
    clauses: List[str] = []
    params: List[object] = []
    if status:
        clauses.append("s.status=?")
        params.append(status)
    if date_from:
        clauses.append("s.doc_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("s.doc_date <= ?")
        params.append(date_to)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " GROUP BY s.id ORDER BY s.doc_date, s.id"
    with get_connection() as conn:
        return list(conn.execute(query, params))


def get_sale(sale_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()


def list_sale_lines(sale_id: int) -> List[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                "SELECT sl.id, sl.product_id, sl.quantity, sl.sale_price, sl.amount, p.name as product_name, p.sku "
                "FROM SalesLines sl JOIN Products p ON p.id = sl.product_id WHERE sl.sale_id=?",
                (sale_id,),
            )
        )


# Posting and stock movements

def _apply_purchase_line(conn: sqlite3.Connection, move_date: str, purchase_id: int, line: sqlite3.Row) -> None:
    qty = float(line["quantity"])
    price = float(line["purchase_price"])
    product_id = int(line["product_id"])
    warehouse_id = int(line["warehouse_id"])
    old_qty, old_avg = _get_balance(conn, product_id, warehouse_id)
    new_qty = old_qty + qty
    new_avg = (old_qty * old_avg + qty * price) / new_qty if new_qty else 0
    _set_balance(conn, product_id, warehouse_id, new_qty, new_avg)
    conn.execute(
        "INSERT INTO StockMoves (move_date, product_id, warehouse_id, qty_in, qty_out, cost_per_unit, amount, reference_type, reference_id, channel, counterparty_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (move_date, product_id, warehouse_id, qty, 0, price, qty * price, "purchase", purchase_id, line["channel"], line["supplier_id"]),
    )


def _apply_sale_line(conn: sqlite3.Connection, move_date: str, sale_id: int, line: sqlite3.Row, allow_negative: bool) -> None:
    qty = float(line["quantity"])
    product_id = int(line["product_id"])
    warehouse_id = int(line["warehouse_id"])
    current_qty, avg_cost = _get_balance(conn, product_id, warehouse_id)
    if qty > current_qty and not allow_negative:
        raise ValueError("Недостатньо залишку для товару")
    new_qty = current_qty - qty
    _set_balance(conn, product_id, warehouse_id, new_qty, avg_cost)
    amount = -qty * avg_cost
    conn.execute(
        "INSERT INTO StockMoves (move_date, product_id, warehouse_id, qty_in, qty_out, cost_per_unit, amount, reference_type, reference_id, channel, counterparty_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (move_date, product_id, warehouse_id, 0, qty, avg_cost, amount, "sale", sale_id, line["channel"], line["customer_id"]),
    )


def recalc_stock(allow_negative: bool = False) -> None:
    """Rebuild stock balances and stock moves from posted documents."""
    with get_connection() as conn:
        conn.execute("DELETE FROM StockBalances")
        conn.execute("DELETE FROM StockMoves")
        # process purchases then sales ordered by date/id to preserve moving average
        purchases = conn.execute(
            "SELECT p.id, p.doc_date, p.supplier_id, p.warehouse_id, p.channel FROM PurchaseDocuments p WHERE p.status='posted' ORDER BY p.doc_date, p.id"
        ).fetchall()
        for pdoc in purchases:
            lines = conn.execute(
                "SELECT pl.product_id, pl.quantity, pl.purchase_price, ? as warehouse_id, ? as channel, ? as supplier_id FROM PurchaseLines pl WHERE pl.purchase_id=?",
                (pdoc["warehouse_id"], pdoc["channel"], pdoc["supplier_id"], pdoc["id"]),
            ).fetchall()
            for ln in lines:
                _apply_purchase_line(conn, pdoc["doc_date"], pdoc["id"], ln)
        sales = conn.execute(
            "SELECT s.id, s.doc_date, s.customer_id, s.warehouse_id, s.channel FROM SalesDocuments s WHERE s.status='posted' ORDER BY s.doc_date, s.id"
        ).fetchall()
        for sdoc in sales:
            lines = conn.execute(
                "SELECT sl.product_id, sl.quantity, sl.sale_price, ? as warehouse_id, ? as channel, ? as customer_id FROM SalesLines sl WHERE sl.sale_id=?",
                (sdoc["warehouse_id"], sdoc["channel"], sdoc["customer_id"], sdoc["id"]),
            ).fetchall()
            for ln in lines:
                _apply_sale_line(conn, sdoc["doc_date"], sdoc["id"], ln, allow_negative)
        conn.commit()


def post_purchase(purchase_id: int) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "draft":
            raise ValueError("Документ вже проведено")
        has_lines = conn.execute("SELECT COUNT(*) FROM PurchaseLines WHERE purchase_id=?", (purchase_id,)).fetchone()[0]
        if not has_lines:
            raise ValueError("Немає рядків для проведення")
        conn.execute("UPDATE PurchaseDocuments SET status='posted' WHERE id=?", (purchase_id,))
        conn.commit()
    recalc_stock()


def unpost_purchase(purchase_id: int) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "posted":
            raise ValueError("Документ не проведено")
        conn.execute("UPDATE PurchaseDocuments SET status='draft' WHERE id=?", (purchase_id,))
        conn.commit()
    recalc_stock()


def post_sale(sale_id: int, allow_negative: bool = False) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "draft":
            raise ValueError("Документ вже проведено")
        has_lines = conn.execute("SELECT COUNT(*) FROM SalesLines WHERE sale_id=?", (sale_id,)).fetchone()[0]
        if not has_lines:
            raise ValueError("Немає рядків для проведення")
        conn.execute("UPDATE SalesDocuments SET status='posted' WHERE id=?", (sale_id,))
        conn.commit()
    recalc_stock(allow_negative=allow_negative)


def unpost_sale(sale_id: int) -> None:
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()
        if not status:
            raise ValueError("Документ не знайдено")
        if status[0] != "posted":
            raise ValueError("Документ не проведено")
        conn.execute("UPDATE SalesDocuments SET status='draft' WHERE id=?", (sale_id,))
        conn.commit()
    recalc_stock()


# Stock listing

def list_stock(search: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT p.id as product_id, p.name, p.sku, w.name as warehouse, sb.warehouse_id, IFNULL(sb.quantity,0) as quantity, IFNULL(sb.average_cost,0) as average_cost "
        "FROM Products p "
        "JOIN Warehouses w ON 1=1 "
        "LEFT JOIN StockBalances sb ON sb.product_id = p.id AND sb.warehouse_id = w.id"
    )
    params: Tuple[str, ...] = ()
    if search:
        query += " WHERE lower(p.name) LIKE ?"
        params = (f"%{search.lower()}%",)
    query += " ORDER BY p.name, w.name"
    with get_connection() as conn:
        return list(conn.execute(query, params))


# Cash transactions

def add_cash_transaction(
    date: str,
    amount: float,
    ctype: str,
    counterparty_id: Optional[int],
    related_doc_type: Optional[str],
    related_doc_id: Optional[int],
    channel: str = "",
    comment: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO CashTransactions (date, amount, type, counterparty_id, related_doc_type, related_doc_id, channel, comment) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (date, amount, ctype, counterparty_id, related_doc_type, related_doc_id, channel.strip(), comment.strip()),
        )
        conn.commit()
        return cur.lastrowid


def list_cash(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[sqlite3.Row]:
    query = (
        "SELECT ct.id, ct.date, ct.amount, ct.type, ct.counterparty_id, cp.name as counterparty, ct.related_doc_type, ct.related_doc_id, ct.channel, ct.comment "
        "FROM CashTransactions ct LEFT JOIN Counterparties cp ON cp.id = ct.counterparty_id"
    )
    clauses: List[str] = []
    params: List[object] = []
    if date_from:
        clauses.append("ct.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("ct.date <= ?")
        params.append(date_to)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY ct.date, ct.id"
    with get_connection() as conn:
        return list(conn.execute(query, params))


# Reporting helpers

def _sale_income_by_product(date_from: Optional[str], date_to: Optional[str]) -> Dict[int, float]:
    """Distribute sale payments across products proportionally to line amounts."""
    result: Dict[int, float] = {}
    with get_connection() as conn:
        payments = conn.execute(
            "SELECT id, amount, related_doc_id FROM CashTransactions WHERE type='sale_payment'"
            + (" AND date >= ?" if date_from else "")
            + (" AND date <= ?" if date_to else ""),
            tuple(x for x in [date_from, date_to] if x),
        ).fetchall()
        for pay in payments:
            sale_id = pay["related_doc_id"]
            if not sale_id:
                continue
            lines = conn.execute("SELECT product_id, amount FROM SalesLines WHERE sale_id=?", (sale_id,)).fetchall()
            total = sum(float(l["amount"]) for l in lines)
            if not total:
                continue
            for ln in lines:
                share = float(ln["amount"]) / total
                result[ln["product_id"]] = result.get(ln["product_id"], 0.0) + pay["amount"] * share
    return result


def profit_by_product(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[dict]:
    income_map = _sale_income_by_product(date_from, date_to)
    with get_connection() as conn:
        params: List[object] = []
        query = "SELECT product_id, SUM(amount) as cogs FROM StockMoves WHERE reference_type='sale'"
        if date_from:
            query += " AND move_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND move_date <= ?"
            params.append(date_to)
        query += " GROUP BY product_id"
        cogs_rows = conn.execute(query, params).fetchall()
        product_names = {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM Products")}
    results: List[dict] = []
    for row in cogs_rows:
        pid = row["product_id"]
        cogs = abs(float(row["cogs"]))
        income = income_map.get(pid, 0.0)
        results.append({"product_id": pid, "product": product_names.get(pid, ""), "income": income, "cogs": cogs, "gross_profit": income - cogs})
    # include products with income but no cogs (services?)
    for pid, income in income_map.items():
        if not any(r["product_id"] == pid for r in results):
            results.append({"product_id": pid, "product": product_names.get(pid, ""), "income": income, "cogs": 0.0, "gross_profit": income})
    return sorted(results, key=lambda r: r["product"])


def cash_flow_summary(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[dict]:
    clauses: List[str] = []
    params: List[object] = []
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = "SELECT type, SUM(amount) as total FROM CashTransactions" + where + " GROUP BY type"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"type": row["type"], "total": float(row["total"])} for row in rows]


def export_table_to_csv(table: str, output_path: Path) -> None:
    import csv

    with get_connection() as conn, output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        rows = conn.execute(f"SELECT * FROM {table}")
        writer.writerow([col[0] for col in rows.description])
        writer.writerows(rows)
    logging.info("Exported %s to %s", table, output_path)


