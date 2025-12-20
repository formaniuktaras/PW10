from __future__ import annotations

import os
import tempfile

from inventorylite import db


def _assert_close(actual: float, expected: float, tol: float = 1e-6) -> None:
    if abs(actual - expected) > tol:
        raise AssertionError(f"Expected {expected}, got {actual}")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand I")
        category_id = db.add_category("Category I")
        warehouse_id = db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier I", "supplier")

        product_id = db.add_product("SKU-INV", "Inventory Item", brand_id, category_id)

        purchase_id = db.create_purchase("2024-01-01", supplier_id, warehouse_id, "")
        db.replace_purchase_lines(purchase_id, [(product_id, 10, 100.0)], 1.0)
        db.post_purchase(purchase_id)

        inv_id = db.create_inventory_document("2024-01-02", warehouse_id, "")
        db.replace_inventory_lines(
            inv_id,
            [
                {
                    "product_id": product_id,
                    "expected_qty": 10.0,
                    "counted_qty": 8.0,
                    "cost_override": None,
                    "note": "",
                }
            ],
        )
        db.post_inventory(inv_id)

        with db.get_connection() as conn:
            balance = conn.execute(
                "SELECT quantity, average_cost FROM StockBalances WHERE product_id=? AND warehouse_id=?",
                (product_id, warehouse_id),
            ).fetchone()
            move = conn.execute(
                "SELECT qty_out FROM StockMoves WHERE reference_type='inventory' AND reference_id=?",
                (inv_id,),
            ).fetchone()

        _assert_close(balance["quantity"], 8.0)
        _assert_close(balance["average_cost"], 100.0)
        _assert_close(move["qty_out"], 2.0)

        inv_id_2 = db.create_inventory_document("2024-01-03", warehouse_id, "")
        db.replace_inventory_lines(
            inv_id_2,
            [
                {
                    "product_id": product_id,
                    "expected_qty": 8.0,
                    "counted_qty": 12.0,
                    "cost_override": 110.0,
                    "note": "",
                }
            ],
        )
        db.post_inventory(inv_id_2)

        with db.get_connection() as conn:
            balance = conn.execute(
                "SELECT quantity, average_cost FROM StockBalances WHERE product_id=? AND warehouse_id=?",
                (product_id, warehouse_id),
            ).fetchone()

        _assert_close(balance["quantity"], 12.0)
        _assert_close(balance["average_cost"], (8 * 100.0 + 4 * 110.0) / 12)

        db.unpost_inventory(inv_id_2)

        with db.get_connection() as conn:
            balance = conn.execute(
                "SELECT quantity, average_cost FROM StockBalances WHERE product_id=? AND warehouse_id=?",
                (product_id, warehouse_id),
            ).fetchone()

        _assert_close(balance["quantity"], 8.0)
        _assert_close(balance["average_cost"], 100.0)

        warehouse_id_2 = db.add_warehouse("Second Warehouse")
        product_a = db.add_product("SKU-A", "Product A", brand_id, category_id)
        product_b = db.add_product("SKU-B", "Product B", brand_id, category_id)

        purchase_id_2 = db.create_purchase("2024-02-01", supplier_id, warehouse_id_2, "")
        db.replace_purchase_lines(
            purchase_id_2,
            [(product_a, 5, 50.0), (product_b, 3, 70.0)],
            1.0,
        )
        db.post_purchase(purchase_id_2)

        inv_id_3 = db.create_inventory_document("2024-02-02", warehouse_id_2, "")
        db.replace_inventory_lines(
            inv_id_3,
            [
                {
                    "product_id": product_a,
                    "expected_qty": 5.0,
                    "counted_qty": 0.0,
                    "cost_override": None,
                    "note": "",
                },
                {
                    "product_id": product_b,
                    "expected_qty": 3.0,
                    "counted_qty": 0.0,
                    "cost_override": None,
                    "note": "",
                },
            ],
        )
        db.post_inventory(inv_id_3)

        with db.get_connection() as conn:
            balance_a = conn.execute(
                "SELECT quantity FROM StockBalances WHERE product_id=? AND warehouse_id=?",
                (product_a, warehouse_id_2),
            ).fetchone()
            balance_b = conn.execute(
                "SELECT quantity FROM StockBalances WHERE product_id=? AND warehouse_id=?",
                (product_b, warehouse_id_2),
            ).fetchone()

        _assert_close(balance_a["quantity"], 0.0)
        _assert_close(balance_b["quantity"], 0.0)

    print("Inventory self-check passed.")


if __name__ == "__main__":
    main()
