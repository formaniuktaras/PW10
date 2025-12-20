import os

os.environ["INVENTORYLITE_HEADLESS"] = "1"

from inventorylite import db


db.init_db()
print("HEADLESS IMPORT: PASSED")
