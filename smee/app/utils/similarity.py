"""Dependency-free lexical similarity functions."""

from __future__ import annotations

from difflib import SequenceMatcher

from app.normalizers.text import normalize_text


def title_similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, normalize_text(first), normalize_text(second)).ratio()

