from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4


class LabelTemplate:
    def __init__(self, name: str, page_size, cols: int, rows: int, label_width_mm: float, label_height_mm: float, gap_mm: float = 2.0):
        self.name = name
        self.page_size = page_size
        self.cols = cols
        self.rows = rows
        self.label_width = label_width_mm * mm
        self.label_height = label_height_mm * mm
        self.gap = gap_mm * mm


TEMPLATES: dict[str, LabelTemplate] = {
    "A4_3x8_70x35": LabelTemplate("A4_3x8_70x35", A4, cols=3, rows=8, label_width_mm=68, label_height_mm=35, gap_mm=2),
    "THERMAL_58x40": LabelTemplate("THERMAL_58x40", (58 * mm, 40 * mm), cols=1, rows=1, label_width_mm=58, label_height_mm=40, gap_mm=0),
}


def _truncate(text: str, max_length: int) -> str:
    return text if len(text) <= max_length else text[: max_length - 1] + "…"


def _iter_labels(items: list[dict], qty_each: int, include_aliases: bool) -> Iterable[tuple[str, str]]:
    for item in items:
        name = str(item.get("name") or "")
        sku = str(item.get("sku") or "")
        for _ in range(max(qty_each, 0)):
            yield sku, name
        if include_aliases:
            for alias in item.get("aliases") or []:
                yield str(alias), name


def _draw_label(c: canvas.Canvas, x: float, y: float, width: float, height: float, code_value: str, name: str) -> None:
    padding = 2 * mm
    barcode_height = height / 2
    barcode_obj = code128.Code128(code_value, barHeight=barcode_height - padding, humanReadable=False)
    barcode_x = x + (width - barcode_obj.width) / 2
    barcode_y = y + height - barcode_height
    barcode_obj.drawOn(c, barcode_x, barcode_y)

    c.setFont("Helvetica", 8)
    c.drawCentredString(x + width / 2, barcode_y - 4, code_value)
    c.setFont("Helvetica", 9)
    c.drawString(x + padding, y + padding, _truncate(name, 32))


def generate_product_labels_pdf(
    output_path: Path,
    items: list[dict],
    *,
    barcode_prefix: str,
    qty_each: int,
    template: str,
    include_aliases: bool,
) -> None:
    tpl = TEMPLATES.get(template) or TEMPLATES["A4_3x8_70x35"]
    prefix = barcode_prefix or ""
    c = canvas.Canvas(str(output_path), pagesize=tpl.page_size)

    label_width = tpl.label_width
    label_height = tpl.label_height
    gap = tpl.gap
    page_width, page_height = tpl.page_size

    col_margin = max((page_width - (tpl.cols * label_width + (tpl.cols - 1) * gap)) / 2, 0)
    row_margin = max((page_height - (tpl.rows * label_height + (tpl.rows - 1) * gap)) / 2, 0)

    current_col = 0
    current_row = 0

    for code, name in _iter_labels(items, qty_each, include_aliases):
        if current_row >= tpl.rows:
            c.showPage()
            current_row = 0
            current_col = 0

        x = col_margin + current_col * (label_width + gap)
        y = page_height - row_margin - label_height - current_row * (label_height + gap)

        _draw_label(c, x, y, label_width, label_height, f"{prefix}{code}", name)

        current_col += 1
        if current_col >= tpl.cols:
            current_col = 0
            current_row += 1

    c.save()
