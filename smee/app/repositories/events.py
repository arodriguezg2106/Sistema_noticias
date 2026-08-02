"""Event persistence, grouping queries, and report projections."""

from __future__ import annotations

import json
from datetime import datetime

from app.models import Actor, Event
from app.repositories.database import Database
from app.repositories.helpers import from_iso, to_iso


class EventRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, event: Event) -> Event:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO events (
                   event_code, title, event_type, state, municipality, start_date, last_update,
                   status, priority_score, importance_level, description, score_reasons,
                   needs_review, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_code, event.title, event.event_type, event.state,
                    event.municipality, to_iso(event.start_date), to_iso(event.last_update),
                    event.status, event.priority_score, event.importance_level, event.description,
                    json.dumps(event.score_reasons, ensure_ascii=False), int(event.needs_review),
                    to_iso(event.created_at), to_iso(event.updated_at),
                ),
            )
            event.id = int(cursor.lastrowid)
        return event

    def get(self, event_id: int) -> Event | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_ids(self) -> list[int]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT id FROM events ORDER BY id").fetchall()
        return [int(row["id"]) for row in rows]

    def find_candidates(
        self,
        state: str | None,
        event_type: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Event]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM events
                   WHERE state IS ? AND event_type=? AND status NOT IN ('closed','discarded')
                     AND last_update BETWEEN ? AND ?
                   ORDER BY last_update DESC""",
                (state, event_type, to_iso(window_start), to_iso(window_end)),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def link_publication(
        self,
        event_id: int,
        publication_id: int,
        relationship_type: str,
        similarity_score: float,
        is_primary_source: bool,
        linked_at: datetime,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO event_publications
                   (event_id, publication_id, relationship_type, similarity_score,
                    is_primary_source, linked_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event_id, publication_id, relationship_type, similarity_score,
                    int(is_primary_source), to_iso(linked_at),
                ),
            )

    def attach_actors(self, event_id: int, actors: list[Actor]) -> None:
        valid = [actor for actor in actors if actor.id is not None]
        if not valid:
            return
        with self.database.transaction() as connection:
            connection.executemany(
                """INSERT INTO event_actors (event_id, actor_id, role, relevance_score)
                   VALUES (?, ?, 'mentioned', 1.0)
                   ON CONFLICT(event_id, actor_id) DO UPDATE SET
                   relevance_score=MAX(relevance_score, excluded.relevance_score)""",
                [(event_id, actor.id) for actor in valid],
            )

    def actor_names(self, event_id: int) -> set[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT a.name FROM actors a
                   JOIN event_actors ea ON ea.actor_id=a.id WHERE ea.event_id=?""",
                (event_id,),
            ).fetchall()
        return {str(row["name"]) for row in rows}

    def event_id_for_publication(self, publication_id: int) -> int | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT event_id FROM event_publications WHERE publication_id=? LIMIT 1",
                (publication_id,),
            ).fetchone()
        return int(row["event_id"]) if row else None

    def mark_updated(self, event_id: int, updated_at: datetime, needs_review: bool = False) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE events SET last_update=?, status='updated',
                   needs_review=MAX(needs_review, ?), updated_at=? WHERE id=?""",
                (to_iso(updated_at), int(needs_review), to_iso(updated_at), event_id),
            )

    def update_description(self, event_id: int, description: str) -> None:
        """Replace an event summary when later evidence offers a better description."""
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE events SET description=?, updated_at=? WHERE id=?",
                (description, to_iso(datetime.now().astimezone()), event_id),
            )

    def update_score(self, event_id: int, score: int, level: str, reasons: list[str]) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE events SET priority_score=?, importance_level=?,
                   score_reasons=?, updated_at=? WHERE id=?""",
                (
                    score, level, json.dumps(reasons, ensure_ascii=False),
                    to_iso(datetime.now().astimezone()), event_id,
                ),
            )

    def count_sources(self, event_id: int) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT p.source_id) FROM publications p
                   JOIN event_publications ep ON ep.publication_id=p.id WHERE ep.event_id=?""",
                (event_id,),
            ).fetchone()
        return int(row[0])

    def has_official_source(self, event_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT EXISTS(
                   SELECT 1 FROM sources s JOIN publications p ON p.source_id=s.id
                   JOIN event_publications ep ON ep.publication_id=p.id
                   WHERE ep.event_id=? AND s.source_type='official')""",
                (event_id,),
            ).fetchone()
        return bool(row[0])

    def has_priority_actor(self, event_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT EXISTS(SELECT 1 FROM actors a
                   JOIN event_actors ea ON ea.actor_id=a.id
                   WHERE ea.event_id=? AND a.is_priority=1)""",
                (event_id,),
            ).fetchone()
        return bool(row[0])

    def has_duplicate_publication(self, event_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT EXISTS(SELECT 1 FROM publications p
                   JOIN event_publications ep ON ep.publication_id=p.id
                   WHERE ep.event_id=? AND p.status='duplicate')""",
                (event_id,),
            ).fetchone()
        return bool(row[0])

    def primary_publication(self, event_id: int) -> dict[str, object] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.* FROM publications p
                   JOIN event_publications ep ON ep.publication_id=p.id
                   WHERE ep.event_id=? ORDER BY ep.is_primary_source DESC, ep.linked_at ASC LIMIT 1""",
                (event_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_report_data(self) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            events = connection.execute(
                "SELECT * FROM events WHERE status != 'discarded' ORDER BY priority_score DESC, last_update DESC"
            ).fetchall()
            result: list[dict[str, object]] = []
            for event_row in events:
                item = dict(event_row)
                item["score_reasons"] = json.loads(str(item["score_reasons"]))
                item["actors"] = [
                    row["name"]
                    for row in connection.execute(
                        """SELECT a.name FROM actors a JOIN event_actors ea ON ea.actor_id=a.id
                           WHERE ea.event_id=? ORDER BY a.name""",
                        (item["id"],),
                    ).fetchall()
                ]
                item["publications"] = [
                    dict(row)
                    for row in connection.execute(
                        """SELECT p.title, p.url, p.published_at, p.is_mock, s.name AS source_name,
                                  ep.relationship_type, ep.is_primary_source
                           FROM publications p JOIN sources s ON s.id=p.source_id
                           JOIN event_publications ep ON ep.publication_id=p.id
                           WHERE ep.event_id=? ORDER BY ep.is_primary_source DESC, p.published_at""",
                        (item["id"],),
                    ).fetchall()
                ]
                result.append(item)
        return result

    @staticmethod
    def _from_row(row: object) -> Event:
        return Event(
            id=row["id"], event_code=row["event_code"], title=row["title"],
            event_type=row["event_type"], state=row["state"], municipality=row["municipality"],
            start_date=from_iso(row["start_date"]), last_update=from_iso(row["last_update"]),
            status=row["status"], priority_score=row["priority_score"],
            importance_level=row["importance_level"], description=row["description"],
            score_reasons=json.loads(row["score_reasons"]), needs_review=bool(row["needs_review"]),
            created_at=from_iso(row["created_at"]), updated_at=from_iso(row["updated_at"]),
        )
