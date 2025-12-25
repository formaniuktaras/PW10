from __future__ import annotations

import re
from typing import Any

from inventorylite import db
from inventorylite.utils import Settings


def sanitize_prefix(text: str) -> str:
    cleaned = (text or "").upper().replace(" ", "")
    return re.sub(r"[^A-Z0-9_-]", "", cleaned)


def _shorten(value: str) -> str:
    return (value or "")[:3]


def render_prefix(template: str, brand: str, category: str) -> str:
    if not template:
        return ""
    rendered = template.format(
        brand=brand or "",
        brand3=_shorten(brand or ""),
        category=category or "",
        category3=_shorten(category or ""),
    )
    return sanitize_prefix(rendered)


def _get_rule_settings(settings: Settings | None) -> dict[str, Any]:
    return (settings.get("defaults", "product", "sku_generator") if settings else None) or {}


def pick_rule(settings: Settings, brand_id: int | None, category_id: int | None, name: str) -> dict | None:
    rules = (_get_rule_settings(settings) or {}).get("rules") or []
    enabled_rules = [r for r in rules if r.get("enabled")]
    enabled_rules.sort(key=lambda r: r.get("priority", 0))
    name_lower = (name or "").lower()

    for rule in enabled_rules:
        match = rule.get("match") or {}
        match_brand = match.get("brand_id")
        match_category = match.get("category_id")
        include_subcategories = bool(match.get("include_subcategories"))
        name_contains = (match.get("name_contains") or "").strip().lower()

        if match_brand is not None and brand_id != match_brand:
            continue

        if match_category is not None:
            if category_id is None:
                continue
            if include_subcategories:
                if category_id != match_category and category_id not in db.get_category_descendants(match_category):
                    continue
            elif category_id != match_category:
                continue

        if name_contains and name_contains not in name_lower:
            continue

        return rule

    return None


def _extract_generator_defaults(settings: Settings | None) -> dict[str, Any]:
    generator_settings = _get_rule_settings(settings)
    default_rule = generator_settings.get("default") or {}
    return {
        "prefix_template": default_rule.get("prefix_template") or "",
        "digits": int(default_rule.get("digits") or 5),
        "start_from": int(default_rule.get("start_from") or 1),
    }


def _pick_active_rule(settings: Settings | None, brand_id: int | None, category_id: int | None, name: str) -> dict[str, Any]:
    default_rule = _extract_generator_defaults(settings)
    if not settings:
        return default_rule
    matched = pick_rule(settings, brand_id, category_id, name)
    if not matched:
        return default_rule
    return {
        "prefix_template": matched.get("prefix_template") or default_rule["prefix_template"],
        "digits": int(matched.get("digits") or default_rule["digits"]),
        "start_from": int(matched.get("start_from") or default_rule["start_from"]),
    }


def _max_existing_number(prefix: str) -> int:
    regex = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_n = 0
    for row in db.list_skus_by_prefix(prefix):
        sku = row["sku"] if isinstance(row, dict) else row[0] if isinstance(row, (list, tuple)) else getattr(row, "sku", None)
        sku = str(sku or "")
        m = regex.match(sku)
        if m:
            try:
                num = int(m.group(1))
            except ValueError:
                continue
            max_n = max(max_n, num)
    return max_n


def generate_next_sku(settings: Settings | None, brand_row, category_row, name: str) -> str:
    brand_name = (brand_row or {}).get("name") if isinstance(brand_row, dict) else getattr(brand_row, "name", None)
    brand_id = (brand_row or {}).get("id") if isinstance(brand_row, dict) else getattr(brand_row, "id", None)
    category_name = (category_row or {}).get("name") if isinstance(category_row, dict) else getattr(category_row, "name", None)
    category_id = (category_row or {}).get("id") if isinstance(category_row, dict) else getattr(category_row, "id", None)

    rule = _pick_active_rule(settings, brand_id, category_id, name)
    prefix = render_prefix(rule.get("prefix_template") or "", str(brand_name or ""), str(category_name or ""))
    digits = max(1, int(rule.get("digits") or 1))
    start_from = max(1, int(rule.get("start_from") or 1))

    max_n = _max_existing_number(prefix) if prefix is not None else 0
    if max_n < start_from - 1:
        max_n = start_from - 1
    next_n = max_n + 1

    while True:
        candidate = f"{prefix}{str(next_n).zfill(digits)}"
        if not db.find_product_by_sku_or_name(candidate, None):
            return candidate
        next_n += 1
