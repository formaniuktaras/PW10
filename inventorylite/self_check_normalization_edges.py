from __future__ import annotations

import os
import sqlite3
import tempfile

import db


def main() -> None:
    os.environ["INVENTORYLITE_HEADLESS"] = "1"
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        brand_id = db.add_brand("Brand Edge")
        category_id = db.add_category("Category Edge")
        supplier_id = db.add_counterparty("Supplier Edge A", "supplier")
        supplier_id_alt = db.add_counterparty("Supplier Edge B", "supplier")

        product_id = db.add_product(" A\u00A0B\u200BC \t", "Edge SKU Item", brand_id, category_id)
        product_id_b = db.add_product("SKU-B", "Edge Other Item", brand_id, category_id)

        with db.get_connection() as conn:
            stored_sku = conn.execute("SELECT sku FROM Products WHERE id=?", (product_id,)).fetchone()[0]
        assert stored_sku == "ABC", stored_sku

        try:
            db.add_product("abc", "Edge SKU Duplicate", brand_id, category_id)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Duplicate SKU should fail")

        db.update_product(product_id, " A B C ", "Edge SKU Item", brand_id, category_id)
        with db.get_connection() as conn:
            updated_sku = conn.execute("SELECT sku FROM Products WHERE id=?", (product_id,)).fetchone()[0]
        assert updated_sku == "ABC", updated_sku

        db.replace_product_barcodes(product_id, [{"code": " 12\u00A034\u200B56 "}])
        with db.get_connection() as conn:
            stored_code = conn.execute(
                "SELECT code FROM ProductBarcodes WHERE product_id=?", (product_id,)
            ).fetchone()[0]
        assert stored_code == "123456", stored_code

        try:
            db.replace_product_barcodes(product_id_b, [{"code": "123 456"}])
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Duplicate barcode should fail")

        with db.get_connection() as conn:
            barcode_count = conn.execute(
                "SELECT COUNT(*) FROM ProductBarcodes WHERE product_id=?", (product_id_b,)
            ).fetchone()[0]
        assert barcode_count == 0, barcode_count

        found = db.find_product_by_scan_code(" 12 34 56 ")
        assert found and found["id"] == product_id, found

        db.replace_product_supplier_codes(
            product_id,
            [{"supplier_id": supplier_id, "supplier_sku": "CASE\u00A0\u00A0IP11\u200B PRO", "is_primary": True}],
        )
        with db.get_connection() as conn:
            stored_supplier = conn.execute(
                "SELECT supplier_sku FROM ProductSupplierCodes WHERE product_id=? AND supplier_id=?",
                (product_id, supplier_id),
            ).fetchone()[0]
        assert stored_supplier == "CASE IP11 PRO", stored_supplier

        try:
            db.replace_product_supplier_codes(
                product_id_b,
                [{"supplier_id": supplier_id, "supplier_sku": "CASE IP11 PRO", "is_primary": True}],
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Duplicate supplier SKU should fail")

        with db.get_connection() as conn:
            supplier_count = conn.execute(
                "SELECT COUNT(*) FROM ProductSupplierCodes WHERE product_id=?", (product_id_b,)
            ).fetchone()[0]
        assert supplier_count == 0, supplier_count

        db.replace_product_supplier_codes(
            product_id_b,
            [{"supplier_id": supplier_id_alt, "supplier_sku": "CASE IP11 PRO", "is_primary": True}],
        )

        with db.get_connection() as conn:
            with db.transaction(conn):
                db._normalize_existing_codes(conn)
                db._ensure_case_insensitive_uniques(conn)

    print("Normalization edges self-check passed.")


if __name__ == "__main__":
    main()
