"""Persistence operations for source catalogs."""

from __future__ import annotations

from app.models import Source
from app.repositories.database import Database
from app.repositories.helpers import from_iso, to_iso


class SourceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, source: Source) -> Source:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sources
                    (name, source_type, base_url, state, reliability_level, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    source_type=excluded.source_type,
                    base_url=excluded.base_url,
                    state=excluded.state,
                    reliability_level=excluded.reliability_level,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (
                    source.name,
                    source.source_type,
                    source.base_url,
                    source.state,
                    source.reliability_level,
                    int(source.is_active),
                    to_iso(source.created_at),
                    to_iso(source.updated_at),
                ),
            )
            row = connection.execute("SELECT * FROM sources WHERE name = ?", (source.name,)).fetchone()
        assert row is not None
        return self._from_row(row)

    def get_by_name(self, name: str) -> Source | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM sources WHERE name = ?", (name,)).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: object) -> Source:
        return Source(
            id=row["id"], name=row["name"], source_type=row["source_type"],
            base_url=row["base_url"], state=row["state"],
            reliability_level=row["reliability_level"], is_active=bool(row["is_active"]),
            created_at=from_iso(row["created_at"]), updated_at=from_iso(row["updated_at"]),
        )

