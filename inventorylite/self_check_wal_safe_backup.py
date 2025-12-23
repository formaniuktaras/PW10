import os
import tempfile
import zipfile
from pathlib import Path

os.environ["INVENTORYLITE_HEADLESS"] = "1"

_original_localappdata = os.environ.get("LOCALAPPDATA")


def _collect_wal_shm_files(base: Path) -> list[Path]:
    matches: list[Path] = []
    for pattern in ("*.db-wal", "*.db-shm", "*-wal", "*-shm"):
        matches.extend(base.glob(pattern))
    return matches


with tempfile.TemporaryDirectory() as tmp_data:
    os.environ["LOCALAPPDATA"] = tmp_data

    from inventorylite import db, utils

    db.init_db()
    data_dir = utils.get_data_dir()
    (data_dir / "data.db-wal").write_text("wal placeholder", encoding="utf-8")
    (data_dir / "data.db-shm").write_text("shm placeholder", encoding="utf-8")

    backup_path = utils.backup_all_data()

    with zipfile.ZipFile(backup_path, "r") as archive:
        names = archive.namelist()
        wal_entries = [name for name in names if utils.is_wal_file(Path(name))]
        suffix_only = [name for name in names if name.endswith("-wal") or name.endswith("-shm")]
        assert "data.db-wal" not in names, "data.db-wal must not be included in backup"
        assert "data.db-shm" not in names, "data.db-shm must not be included in backup"
        assert not wal_entries and not suffix_only, "WAL/SHM files must be excluded from backup"

    with tempfile.TemporaryDirectory() as tmp_restore:
        os.environ["LOCALAPPDATA"] = tmp_restore
        utils.restore_all_data(backup_path)
        restored_data_dir = utils.get_data_dir()
        remaining_wal = _collect_wal_shm_files(restored_data_dir)
        assert not remaining_wal, f"WAL/SHM files must not be present after restore: {remaining_wal}"

if _original_localappdata is not None:
    os.environ["LOCALAPPDATA"] = _original_localappdata
else:
    os.environ.pop("LOCALAPPDATA", None)

print("WAL-safe backup self-check passed.")
