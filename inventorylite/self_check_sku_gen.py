from __future__ import annotations

import os
import tempfile

from inventorylite import db, sku_gen
from inventorylite.utils import Settings


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["LOCALAPPDATA"] = temp_dir
        db.init_db()

        settings = Settings()
        settings.set("FILM-", "defaults", "product", "sku_generator", "default", "prefix_template")
        settings.set(5, "defaults", "product", "sku_generator", "default", "digits")
        settings.set(1, "defaults", "product", "sku_generator", "default", "start_from")

        brand_id = db.add_brand("FilmBrand")
        category_id = db.add_category("Films")
        brand_row = {"id": brand_id, "name": "FilmBrand"}
        category_row = {"id": category_id, "name": "Films"}

        db.add_product("FILM-00001", "Film A", brand_id, category_id)
        db.add_product("FILM-00002", "Film B", brand_id, category_id)

        next_sku = sku_gen.generate_next_sku(settings, brand_row, category_row, "Film C")
        assert next_sku == "FILM-00003", f"Expected FILM-00003, got {next_sku}"

        db.add_product("FILM-00003", "Film Existing", brand_id, category_id)

        next_after_collision = sku_gen.generate_next_sku(settings, brand_row, category_row, "Film D")
        assert next_after_collision == "FILM-00004", f"Expected FILM-00004, got {next_after_collision}"

    print("SKU generator self-check passed.")


if __name__ == "__main__":
    main()
