"""Helpers for consistent text normalization and search matching."""
from __future__ import annotations

import re

_APOSTROPHES = ("'", "’", "ʼ", "`")
_HYPHENS = ("-", "–", "—", "‑", "−")


def norm_text(s: str) -> str:
    """
    Normalize text for search:
    - coerce to string, strip edges
    - casefold
    - remove apostrophes/hyphens
    - collapse whitespace and remove it
    """

    text = str(s or "")
    text = text.strip().casefold()
    translation = {ord(ch): None for ch in (*_APOSTROPHES, *_HYPHENS)}
    cleaned = text.translate(translation)
    collapsed = " ".join(cleaned.split())
    return collapsed.replace(" ", "")
