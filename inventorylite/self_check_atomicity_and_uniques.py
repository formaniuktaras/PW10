from __future__ import annotations

import os
import sqlite3
import tempfile

import db


def _scenario_atomic_post_sale() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand A")
        category_id = db.add_category("Category A")
        warehouse_id = db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier A", "supplier")
        customer_id = db.add_counterparty("Customer A", "customer")

        stocked_product_id = db.add_product("SKU-STOCK", "Stocked Item", brand_id, category_id)
        missing_product_id = db.add_product("SKU-EMPTY", "Missing Item", brand_id, category_id)

        purchase_id = db.create_purchase("2024-01-01", supplier_id, warehouse_id, "")
        db.replace_purchase_lines(purchase_id, [(stocked_product_id, 2, 10.0)], 1.0)
        db.post_purchase(purchase_id)

        sale_id = db.create_sale("2024-01-02", customer_id, warehouse_id, "")
        db.replace_sale_lines(sale_id, [(missing_product_id, 1, 25.0, 0.0)], 1.0)

        with db.get_connection() as conn:
            before_moves = conn.execute("SELECT COUNT(*) FROM StockMoves").fetchone()[0]

        try:
            db.post_sale(sale_id, allow_negative=False)
        except ValueError:
            pass
        else:
            raise AssertionError("post_sale should fail for missing stock")

        with db.get_connection() as conn:
            status = conn.execute("SELECT status FROM SalesDocuments WHERE id=?", (sale_id,)).fetchone()[0]
            cash_count = conn.execute(
                "SELECT COUNT(*) FROM CashTransactions WHERE related_doc_type='sale' AND related_doc_id=?",
                (sale_id,),
            ).fetchone()[0]
            after_moves = conn.execute("SELECT COUNT(*) FROM StockMoves").fetchone()[0]

        assert status == "draft", status
        assert cash_count == 0, cash_count
        assert after_moves == before_moves and after_moves > 0, (before_moves, after_moves)


def _scenario_unpost_purchase_rollback() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand B")
        category_id = db.add_category("Category B")
        warehouse_id = db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier B", "supplier")
        customer_id = db.add_counterparty("Customer B", "customer")
        product_id = db.add_product("SKU-ROLL", "Rollback Item", brand_id, category_id)

        purchase_id = db.create_purchase("2024-02-01", supplier_id, warehouse_id, "")
        db.replace_purchase_lines(purchase_id, [(product_id, 1, 10.0)], 1.0)
        db.post_purchase(purchase_id)

        sale_id = db.create_sale("2024-02-02", customer_id, warehouse_id, "")
        db.replace_sale_lines(sale_id, [(product_id, 1, 20.0, 0.0)], 1.0)
        db.post_sale(sale_id, allow_negative=False)

        try:
            db.unpost_purchase(purchase_id)
        except ValueError:
            pass
        else:
            raise AssertionError("unpost_purchase should fail due to insufficient stock")

        with db.get_connection() as conn:
            status = conn.execute("SELECT status FROM PurchaseDocuments WHERE id=?", (purchase_id,)).fetchone()[0]
            cash_count = conn.execute(
                "SELECT COUNT(*) FROM CashTransactions WHERE related_doc_type='purchase' AND related_doc_id=?",
                (purchase_id,),
            ).fetchone()[0]

        assert status == "posted", status
        assert cash_count > 0, cash_count


def _scenario_block_unpost_with_extra_costs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand C")
        category_id = db.add_category("Category C")
        warehouse_id = db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier C", "supplier")
        product_id = db.add_product("SKU-EXTRA", "Extra Item", brand_id, category_id)

        purchase_id = db.create_purchase("2024-03-01", supplier_id, warehouse_id, "")
        db.replace_purchase_lines(purchase_id, [(product_id, 10, 10.0)], 1.0)
        db.post_purchase(purchase_id)

        extra_id = db.create_extra_cost_document("2024-03-02", partner_id=supplier_id)
        db.replace_extra_cost_lines(extra_id, [("Shipping", 50.0)], 1.0)
        db.post_extra_cost(extra_id, [purchase_id])

        try:
            db.unpost_purchase(purchase_id)
        except ValueError as exc:
            message = str(exc)
        else:
            raise AssertionError("unpost_purchase should be blocked by extra costs")

        assert str(extra_id) in message, message


def _scenario_case_insensitive_uniques() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand D")
        category_id = db.add_category("Category D")
        db.add_warehouse("Main Warehouse")
        supplier_id = db.add_counterparty("Supplier D", "supplier")

        product_a = db.add_product("AbC", "Case Item A", brand_id, category_id)

        try:
            db.add_product("aBc", "Case Item B", brand_id, category_id)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("SKU case-insensitive uniqueness not enforced")

        product_b = db.add_product("SKU-B", "Case Item C", brand_id, category_id)
        db.replace_product_barcodes(product_a, [{"code": "BaR-1"}])

        try:
            db.replace_product_barcodes(product_b, [{"code": "bar-1"}])
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Barcode case-insensitive uniqueness not enforced")

        db.replace_product_supplier_codes(
            product_a,
            [{"supplier_id": supplier_id, "supplier_sku": "SUP-1", "is_primary": True}],
        )

        try:
            db.replace_product_supplier_codes(
                product_b,
                [{"supplier_id": supplier_id, "supplier_sku": "sup-1", "is_primary": True}],
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Supplier SKU case-insensitive uniqueness not enforced")


def main() -> None:
    _scenario_atomic_post_sale()
    _scenario_unpost_purchase_rollback()
    _scenario_block_unpost_with_extra_costs()
    _scenario_case_insensitive_uniques()
    print("Atomicity and unique indexes self-check passed.")


if __name__ == "__main__":
    main()
