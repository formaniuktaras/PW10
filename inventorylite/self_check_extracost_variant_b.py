from __future__ import annotations

import math
import os
import tempfile

from inventorylite import db

EPS = 1e-6


def _run_case(sold_qty: float, expected_cogs: float, expected_stock: float) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Test Brand")
        category_id = db.add_category("Test Category")
        warehouse_id = db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier", "supplier")
        customer_id = db.add_counterparty("Customer", "customer")
        product_id = db.add_product("SKU-EXTRA", "ExtraCost Widget", brand_id, category_id)

        purchase_id = db.create_purchase("2024-01-01", supplier_id, warehouse_id, "")
        db.replace_purchase_lines(purchase_id, [(product_id, 10, 10)], 1.0)
        db.post_purchase(purchase_id)

        sale_id = db.create_sale("2024-01-02", customer_id, warehouse_id, "")
        db.replace_sale_lines(sale_id, [(product_id, sold_qty, 20, 0.0)], 1.0)
        db.post_sale(sale_id, allow_negative=False)

        extra_id = db.create_extra_cost_document("2024-01-03", partner_id=supplier_id)
        db.replace_extra_cost_lines(extra_id, [("Shipping", 100.0)], 1.0)
        db.post_extra_cost(extra_id, [purchase_id])

        with db.get_connection() as conn:
            rows = conn.execute(
                "SELECT qty_sold, amount_cogs_base FROM ExtraCostCogsAllocations WHERE extra_cost_id=?",
                (extra_id,),
            ).fetchall()
            total_cogs = sum(float(row["amount_cogs_base"]) for row in rows)
            total_qty_sold = sum(float(row["qty_sold"]) for row in rows)
            extra_stock_amount = conn.execute(
                "SELECT IFNULL(SUM(amount),0) as amount FROM StockMoves WHERE reference_type='extra_cost' AND reference_id=?",
                (extra_id,),
            ).fetchone()["amount"]

        assert math.isclose(total_cogs, expected_cogs, rel_tol=0.0, abs_tol=EPS), total_cogs
        assert math.isclose(total_qty_sold, sold_qty, rel_tol=0.0, abs_tol=EPS), total_qty_sold
        assert math.isclose(float(extra_stock_amount), expected_stock, rel_tol=0.0, abs_tol=EPS), extra_stock_amount


def main() -> None:
    _run_case(sold_qty=10, expected_cogs=100.0, expected_stock=0.0)
    _run_case(sold_qty=6, expected_cogs=60.0, expected_stock=40.0)
    print("ExtraCost Variant B self-check passed.")


if __name__ == "__main__":
    main()
