import os

os.environ["INVENTORYLITE_HEADLESS"] = "1"

from inventorylite import db


db.init_db()
with db.get_connection() as conn:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert int(version) == db.LATEST_SCHEMA_VERSION

print("HEADLESS IMPORT: PASSED")
