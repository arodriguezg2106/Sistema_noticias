"""Rule match audit trail."""

from __future__ import annotations

from app.models import RuleMatch
from app.repositories.database import Database
from app.repositories.helpers import to_iso


class RuleMatchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add_many(self, matches: list[RuleMatch]) -> None:
        if not matches:
            return
        with self.database.transaction() as connection:
            connection.executemany(
                """INSERT INTO rule_matches
                   (publication_id, rule_name, rule_type, matched_value, score_awarded, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        match.publication_id, match.rule_name, match.rule_type,
                        match.matched_value, match.score_awarded, to_iso(match.created_at),
                    )
                    for match in matches
                ],
            )

    def for_publication(self, publication_id: int) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rule_matches WHERE publication_id=? ORDER BY id", (publication_id,)
            ).fetchall()
        return [dict(row) for row in rows]

