from __future__ import annotations

from datetime import datetime, date
from typing import Optional


_ACCEPTED_SEPARATORS = [".", "/", "-"]


def try_parse_date_any(raw: str) -> Optional[date]:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass

    for sep in _ACCEPTED_SEPARATORS:
        if sep not in text:
            continue
        parts = text.split(sep)
        if len(parts) != 3:
            continue
        day, month, year = parts
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            continue
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def normalize_date_to_iso(raw: str, *, field_label: str = "Дата") -> str:
    parsed = try_parse_date_any(raw)
    if not parsed:
        raise ValueError(
            f"{field_label}: невірний формат. Використовуйте ДД.ММ.РРРР (напр. 24.04.2025)"
        )
    return parsed.strftime("%Y-%m-%d")


def normalize_optional_date_to_iso(raw: str | None, *, field_label: str = "Дата") -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return normalize_date_to_iso(text, field_label=field_label)


def format_iso_to_dmy(iso: str) -> str:
    if not iso:
        return ""
    parsed = datetime.strptime(iso, "%Y-%m-%d").date()
    return parsed.strftime("%d.%m.%Y")
