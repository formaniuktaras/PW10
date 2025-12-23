import os
import tempfile

os.environ["INVENTORYLITE_HEADLESS"] = "1"

with tempfile.TemporaryDirectory() as tmp:
    os.environ["LOCALAPPDATA"] = tmp

    from inventorylite import db

    db.init_db()
    with db.get_connection() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert int(version) == db.LATEST_SCHEMA_VERSION

print("HEADLESS IMPORT: PASSED")
