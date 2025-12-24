from __future__ import annotations

import os
import tempfile

from inventorylite import db


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        category_a = db.add_category("A", parent_id=None)
        db.add_category("B", parent_id=category_a)

        tree = db.list_categories_tree(include_hidden=True)

        has_a = any(item["name"] == "A" and item.get("depth") == 0 for item in tree)
        has_b = any(
            item["name"] == "B"
            and item.get("depth") == 1
            and isinstance(item.get("label"), str)
            and item["label"].startswith(" ")
            for item in tree
        )

        assert has_a, "Category A with depth=0 not found"
        assert has_b, "Category B with depth=1 and indented label not found"

        print("Categories tree self-check passed")


if __name__ == "__main__":
    main()
