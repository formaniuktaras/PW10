from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import sys
import os
import logging
import datetime


_UNICODE_FONT_MAPPING: dict[str, str] | None = None


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


def _candidate_font_paths() -> list[Path]:
    paths: list[Path] = []

    base_dir = Path(__file__).resolve().parent
    assets_dir = base_dir / "assets" / "fonts"
    paths.extend([
        assets_dir / "DejaVuSans.ttf",
        assets_dir / "DejaVuSans-Bold.ttf",
    ])

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_assets = Path(meipass) / "assets" / "fonts"
        paths.extend(
            [
                meipass_assets / "DejaVuSans.ttf",
                meipass_assets / "DejaVuSans-Bold.ttf",
            ]
        )

    windir = os.environ.get("WINDIR") or os.environ.get("windir")
    if windir:
        fonts_dir = Path(windir) / "Fonts"
        paths.extend(
            [
                fonts_dir / "arial.ttf",
                fonts_dir / "arialbd.ttf",
                fonts_dir / "segoeui.ttf",
                fonts_dir / "seguisb.ttf",
            ]
        )

    paths.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ]
    )

    return paths


def _find_first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def ensure_unicode_fonts_registered() -> dict:
    global _UNICODE_FONT_MAPPING
    if _UNICODE_FONT_MAPPING is not None:
        return _UNICODE_FONT_MAPPING

    mapping = {"regular": "IL_SANS", "bold": "IL_SANS_BOLD"}
    registered = set(pdfmetrics.getRegisteredFontNames())
    if mapping["regular"] in registered:
        _UNICODE_FONT_MAPPING = mapping
        return mapping

    candidates = _candidate_font_paths()

    regular_candidates = [
        path
        for path in candidates
        if path.name in {"DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"}
    ]
    bold_candidates = [
        path
        for path in candidates
        if path.name in {"DejaVuSans-Bold.ttf", "arialbd.ttf", "seguisb.ttf", "Arial Bold.ttf"}
    ]

    regular_path = _find_first_existing(regular_candidates)
    bold_path = _find_first_existing(bold_candidates)

    if regular_path is None:
        searched = "\n".join(str(p) for p in regular_candidates)
        raise RuntimeError(f"Unicode font not found. Checked paths:\n{searched}")

    if bold_path is None:
        bold_path = regular_path

    pdfmetrics.registerFont(TTFont(mapping["regular"], str(regular_path)))
    pdfmetrics.registerFont(TTFont(mapping["bold"], str(bold_path)))

    _UNICODE_FONT_MAPPING = mapping
    return mapping


def _truncate(text: str, max_length: int) -> str:
    return text if len(text) <= max_length else text[: max_length - 1] + "…"


def _iter_labels(items: list[dict], qty_each: int, include_aliases: bool) -> Iterable[tuple[str, str, str, int]]:
    for item in items:
        name = str(item.get("name") or "")
        sku = str(item.get("sku") or "")
        for _ in range(max(qty_each, 0)):
            yield sku, name, sku, 0
        if include_aliases:
            for alias in item.get("aliases") or []:
                yield str(alias), name, sku, 1


def _apply_text_template(template: str, context: dict) -> str:
    try:
        return template.format(**context)
    except Exception:
        return template


def _draw_element(c: canvas.Canvas, element: dict, origin_x: float, origin_y: float, context: dict) -> None:
    etype = element.get("element_type")
    options = element.get("options") or {}
    x = origin_x + element.get("x_mm", 0) * mm
    y = origin_y + element.get("y_mm", 0) * mm
    width = element.get("w_mm", 0) * mm
    height = element.get("h_mm", 0) * mm
    rotation_deg = float(element.get("rotation_deg") or 0)

    def _with_rotation(draw_fn):
        if rotation_deg:
            c.saveState()
            c.translate(x + width / 2, y + height / 2)
            c.rotate(rotation_deg)
            draw_fn(-width / 2, -height / 2)
            c.restoreState()
        else:
            draw_fn(x, y)
    if etype == "barcode":
        code_value = str(context.get(element.get("field_key") or "code") or "")
        bar_height_mm = options.get("bar_height_mm")
        bar_height = bar_height_mm * mm if bar_height_mm is not None else max(0, height - 2 * mm)

        def draw_barcode(px: float, py: float) -> None:
            try:
                barcode_obj = code128.Code128(code_value, barHeight=bar_height, humanReadable=bool(options.get("human_readable")))
                if barcode_obj.width > width and barcode_obj.width > 0:
                    ratio = width / barcode_obj.width
                    barcode_obj.barWidth *= ratio
                barcode_x = px + (width - barcode_obj.width) / 2
                barcode_obj.drawOn(c, barcode_x, py)
            except Exception:
                logging.warning("Не вдалося намалювати штрихкод %s", code_value)

        _with_rotation(lambda px, py: draw_barcode(px, py))
    elif etype == "text":
        text_value = _apply_text_template(options.get("text_template") or "{code}", context)
        max_chars = element.get("max_chars")
        if max_chars:
            text_value = _truncate(text_value, int(max_chars))

        def draw_text(px: float, py: float) -> None:
            c.saveState()
            font_map = ensure_unicode_fonts_registered()
            requested_font = element.get("font_name") or font_map["regular"]
            contains_cyrillic = any("\u0400" <= ch <= "\u04FF" for ch in text_value)
            bold_flag = bool(element.get("bold") or options.get("bold"))
            if contains_cyrillic or requested_font in {"Helvetica", "Times-Roman", "Courier", font_map["regular"], font_map["bold"]}:
                font_name = font_map["bold"] if bold_flag else font_map["regular"]
            else:
                font_name = requested_font
            font_size = float(element.get("font_size") or 9)
            c.setFont(font_name, font_size)
            align = element.get("align") or "left"
            if element.get("wrap"):
                lines = simpleSplit(text_value, font_name, font_size, width)
                line_h = font_size * 1.2
                current_y = py + height - line_h
                for line in lines:
                    if current_y < py:
                        break
                    if align == "center":
                        c.drawCentredString(px + width / 2, current_y, line)
                    elif align == "right":
                        c.drawRightString(px + width, current_y, line)
                    else:
                        c.drawString(px, current_y, line)
                    current_y -= line_h
            else:
                if align == "center":
                    c.drawCentredString(px + width / 2, py, text_value)
                elif align == "right":
                    c.drawRightString(px + width, py, text_value)
                else:
                    c.drawString(px, py, text_value)
            c.restoreState()

        _with_rotation(lambda px, py: draw_text(px, py))
    elif etype == "rect":
        _with_rotation(lambda px, py: c.rect(px, py, width, height))
    elif etype == "line":
        _with_rotation(lambda px, py: c.line(px, py, px + width, py + height))


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
    ensure_unicode_fonts_registered()
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

    for barcode_value, name, base_sku, is_alias in _iter_labels(items, qty_each, include_aliases):
        if current_row >= tpl.rows:
            c.showPage()
            current_row = 0
            current_col = 0

        x = col_margin + current_col * (label_width + gap)
        y = page_height - row_margin - label_height - current_row * (label_height + gap)

        _draw_label(c, x, y, label_width, label_height, f"{prefix}{barcode_value}", name)

        current_col += 1
        if current_col >= tpl.cols:
            current_col = 0
            current_row += 1

    c.save()


def generate_product_labels_pdf_v2(
    output_path: Path,
    items: list[dict],
    *,
    barcode_prefix: str,
    qty_each: int,
    template_full: dict,
    include_aliases: bool,
    start_row: int = 1,
    start_col: int = 1,
) -> None:
    ensure_unicode_fonts_registered()
    tpl = template_full.get("template") if template_full else None
    elements = template_full.get("elements") if template_full else []
    if not tpl:
        tpl_obj = TEMPLATES.get("A4_3x8_70x35")
        tpl = {
            "page_w_mm": tpl_obj.page_size[0] / mm,
            "page_h_mm": tpl_obj.page_size[1] / mm,
            "cols": tpl_obj.cols,
            "rows": tpl_obj.rows,
            "label_w_mm": tpl_obj.label_width / mm,
            "label_h_mm": tpl_obj.label_height / mm,
            "gap_x_mm": tpl_obj.gap / mm,
            "gap_y_mm": tpl_obj.gap / mm,
            "margin_left_mm": 0,
            "margin_right_mm": 0,
            "margin_top_mm": 0,
            "margin_bottom_mm": 0,
            "offset_x_mm": 0,
            "offset_y_mm": 0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "orientation": "portrait",
            "kind": "sheet",
        }
        elements = []

    page_w = float(tpl.get("page_w_mm", 0)) * mm
    page_h = float(tpl.get("page_h_mm", 0)) * mm
    orientation = str(tpl.get("orientation") or "portrait").lower()
    if orientation == "landscape":
        page_w, page_h = page_h, page_w
    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))
    cols = int(tpl.get("cols", 1))
    rows = int(tpl.get("rows", 1))
    label_w = float(tpl.get("label_w_mm", 0)) * mm
    label_h = float(tpl.get("label_h_mm", 0)) * mm
    gap_x = float(tpl.get("gap_x_mm", 0)) * mm
    gap_y = float(tpl.get("gap_y_mm", 0)) * mm
    margin_left = float(tpl.get("margin_left_mm", 0)) * mm
    margin_right = float(tpl.get("margin_right_mm", 0)) * mm
    margin_top = float(tpl.get("margin_top_mm", 0)) * mm
    margin_bottom = float(tpl.get("margin_bottom_mm", 0)) * mm
    offset_x = float(tpl.get("offset_x_mm", 0)) * mm
    offset_y = float(tpl.get("offset_y_mm", 0)) * mm
    scale_x = float(tpl.get("scale_x", 1))
    scale_y = float(tpl.get("scale_y", 1))
    kind = tpl.get("kind") or "sheet"

    prefix = barcode_prefix or ""
    today = datetime.date.today().isoformat()

    labels_iterator = _iter_labels(items, qty_each, include_aliases)
    total_cells = max(cols * rows, 1)
    try:
        start_index = (max(start_row, 1) - 1) * cols + (max(start_col, 1) - 1)
    except Exception:
        start_index = 0
    if start_index < 0 or start_index >= total_cells:
        start_index = 0
    printed_on_page = 0

    def apply_page_transform():
        c.saveState()
        c.scale(scale_x, scale_y)
        c.translate(offset_x / scale_x, offset_y / scale_y)

    def reset_page_state():
        c.restoreState()
        c.showPage()
        apply_page_transform()

    apply_page_transform()
    first_label = True

    for barcode_value, name, base_sku, is_alias in labels_iterator:
        if kind == "thermal":
            if not first_label:
                reset_page_state()
            first_label = False
            col = row = 0
        else:
            idx = start_index + printed_on_page
            if idx >= total_cells:
                reset_page_state()
                printed_on_page = 0
                start_index = 0
                idx = 0
            row = idx // cols
            col = idx % cols

        x = margin_left + col * (label_w + gap_x)
        y = page_h - margin_top - label_h - row * (label_h + gap_y)
        context = {
            "code": f"{prefix}{barcode_value}",
            "raw_code": barcode_value,
            "name": name,
            "sku": base_sku,
            "is_alias": is_alias,
            "date": today,
        }
        for element in elements:
            if not element.get("is_active", 1):
                continue
            _draw_element(c, element, x, y, context)
        printed_on_page += 1
        if kind == "thermal":
            pass

    c.restoreState()
    c.save()
