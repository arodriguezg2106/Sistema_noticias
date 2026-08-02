"""Actor catalog and event relationship persistence."""

from __future__ import annotations

import json

from app.models import Actor
from app.repositories.database import Database


class ActorRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, actor: Actor) -> Actor:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO actors
                   (name, actor_type, party, state, aliases, is_active, is_priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET actor_type=excluded.actor_type,
                   party=excluded.party, state=excluded.state, aliases=excluded.aliases,
                   is_active=excluded.is_active, is_priority=excluded.is_priority""",
                (
                    actor.name, actor.actor_type, actor.party, actor.state,
                    json.dumps(actor.aliases, ensure_ascii=False), int(actor.is_active),
                    int(actor.is_priority),
                ),
            )
            row = connection.execute("SELECT id FROM actors WHERE name=?", (actor.name,)).fetchone()
        assert row is not None
        actor.id = int(row["id"])
        return actor

    def get_by_names(self, names: list[str]) -> list[Actor]:
        if not names:
            return []
        placeholders = ",".join("?" for _ in names)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM actors WHERE name IN ({placeholders})", names
            ).fetchall()
        return [
            Actor(
                id=row["id"], name=row["name"], actor_type=row["actor_type"],
                party=row["party"], state=row["state"], aliases=json.loads(row["aliases"]),
                is_active=bool(row["is_active"]), is_priority=bool(row["is_priority"]),
            )
            for row in rows
        ]

