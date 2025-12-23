import os
import tempfile


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["LOCALAPPDATA"] = tmp
        from inventorylite import db

        db.init_db()
        with db.get_connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert int(version) == 2
            db.audit_event("TEST", "hello", details={"a": 1}, conn=conn)
            count = conn.execute("SELECT COUNT(*) FROM AuditLog WHERE event_type='TEST'").fetchone()[0]
            assert int(count) == 1
    print("AuditLog self-check passed.")


if __name__ == "__main__":
    main()
