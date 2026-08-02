"""Mapping helpers shared by repositories."""

from __future__ import annotations

from datetime import datetime


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None

