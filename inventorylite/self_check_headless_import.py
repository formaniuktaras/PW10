import os

os.environ["INVENTORYLITE_HEADLESS"] = "1"

import db


db.init_db()
print("HEADLESS IMPORT: PASSED")
