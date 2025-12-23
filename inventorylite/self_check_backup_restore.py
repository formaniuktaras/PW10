import os
import sqlite3
import tempfile
from pathlib import Path

os.environ["INVENTORYLITE_HEADLESS"] = "1"


def _count_products(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM Products").fetchone()[0])
    finally:
        conn.close()


with tempfile.TemporaryDirectory() as tmp_data:
    os.environ["LOCALAPPDATA"] = tmp_data

    from inventorylite import db, utils

    db.init_db()
    brand_id = db.add_brand("Smoke Brand")
    category_id = db.add_category("Smoke Category")
    db.add_product("SMOKE-SKU", "Smoke Product", brand_id, category_id)

    backup_path = utils.backup_all_data()

    with tempfile.TemporaryDirectory() as tmp_restore:
        os.environ["LOCALAPPDATA"] = tmp_restore
        utils.restore_all_data(backup_path)
        restored_db_path = utils.get_db_path()
        assert restored_db_path.exists(), "Database was not restored"
        assert _count_products(restored_db_path) == 1, "Unexpected product count after restore"

print("Backup/Restore self-check passed.")
