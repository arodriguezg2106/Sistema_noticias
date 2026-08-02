"""Publication persistence and exact-duplicate lookup."""

from __future__ import annotations

import json

from app.models import DuplicateResult, Publication
from app.repositories.database import Database
from app.repositories.helpers import from_iso, to_iso


class PublicationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def find_exact_duplicate(self, normalized_url: str, digest: str) -> DuplicateResult:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT id, normalized_url, content_hash FROM publications
                   WHERE status != 'duplicate'
                     AND (normalized_url = ? OR content_hash = ?)
                   ORDER BY id LIMIT 1""",
                (normalized_url, digest),
            ).fetchone()
        if not row:
            return DuplicateResult(False)
        reason = "exact_url" if row["normalized_url"] == normalized_url else "exact_content_hash"
        return DuplicateResult(True, row["id"], reason)

    def external_id_exists(self, source_id: int, external_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT EXISTS(SELECT 1 FROM publications
                   WHERE source_id=? AND external_id=?)""",
                (source_id, external_id),
            ).fetchone()
        return bool(row[0])

    def add(self, publication: Publication) -> Publication:
        fields = (
            publication.source_id, publication.external_id, publication.title, publication.url,
            publication.normalized_url, to_iso(publication.published_at),
            to_iso(publication.collected_at), publication.author, publication.raw_text,
            publication.normalized_text, publication.content_hash, publication.state_detected,
            publication.municipality_detected, publication.party_detected,
            publication.event_type_detected, publication.publication_type, int(publication.is_mock),
            publication.status,
            int(publication.needs_review), json.dumps(publication.review_reasons, ensure_ascii=False),
            publication.duplicate_of_publication_id,
            publication.duplicate_reason, to_iso(publication.created_at), to_iso(publication.updated_at),
        )
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO publications (
                    source_id, external_id, title, url, normalized_url, published_at, collected_at,
                    author, raw_text, normalized_text, content_hash, state_detected,
                    municipality_detected, party_detected, event_type_detected, publication_type,
                    is_mock, status, needs_review, review_reasons, duplicate_of_publication_id, duplicate_reason,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                fields,
            )
            publication.id = int(cursor.lastrowid)
        return publication

    def update_classification(self, publication: Publication) -> None:
        if publication.id is None:
            raise ValueError("Cannot update a publication without an id")
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE publications SET state_detected=?, municipality_detected=?,
                   party_detected=?, event_type_detected=?, status=?, needs_review=?,
                   review_reasons=?, updated_at=?
                   WHERE id=?""",
                (
                    publication.state_detected, publication.municipality_detected,
                    publication.party_detected, publication.event_type_detected,
                    publication.status, int(publication.needs_review),
                    json.dumps(publication.review_reasons, ensure_ascii=False),
                    to_iso(publication.updated_at), publication.id,
                ),
            )

    def list_review_items(self) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT p.id, p.title, p.url, p.status, p.state_detected,
                          p.event_type_detected, p.duplicate_reason, p.review_reasons, p.is_mock,
                          s.name AS source_name
                   FROM publications p JOIN sources s ON s.id=p.source_id
                   WHERE p.needs_review=1 ORDER BY p.collected_at DESC"""
            ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["review_reasons"] = json.loads(str(item["review_reasons"]))
        return items

    def count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0])

    @staticmethod
    def from_row(row: object) -> Publication:
        return Publication(
            id=row["id"], source_id=row["source_id"], external_id=row["external_id"],
            title=row["title"], url=row["url"], normalized_url=row["normalized_url"],
            published_at=from_iso(row["published_at"]), collected_at=from_iso(row["collected_at"]),
            author=row["author"], raw_text=row["raw_text"], normalized_text=row["normalized_text"],
            content_hash=row["content_hash"], state_detected=row["state_detected"],
            municipality_detected=row["municipality_detected"], party_detected=row["party_detected"],
            event_type_detected=row["event_type_detected"], publication_type=row["publication_type"],
            is_mock=bool(row["is_mock"]),
            status=row["status"], needs_review=bool(row["needs_review"]),
            review_reasons=json.loads(row["review_reasons"]),
            duplicate_of_publication_id=row["duplicate_of_publication_id"],
            duplicate_reason=row["duplicate_reason"], created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
        )
