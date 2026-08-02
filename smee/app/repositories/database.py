"""SQLite connection and schema lifecycle."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    base_url TEXT NOT NULL,
    state TEXT,
    reliability_level TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    external_id TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    author TEXT,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    state_detected TEXT,
    municipality_detected TEXT,
    party_detected TEXT,
    event_type_detected TEXT,
    publication_type TEXT NOT NULL,
    is_mock INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons TEXT NOT NULL DEFAULT '[]',
    duplicate_of_publication_id INTEGER REFERENCES publications(id),
    duplicate_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_publications_normalized_url ON publications(normalized_url);
CREATE INDEX IF NOT EXISTS idx_publications_content_hash ON publications(content_hash);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    state TEXT,
    municipality TEXT,
    start_date TEXT NOT NULL,
    last_update TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('detected','active','updated','closed','discarded')),
    priority_score INTEGER NOT NULL DEFAULT 0,
    importance_level TEXT NOT NULL,
    description TEXT NOT NULL,
    score_reasons TEXT NOT NULL DEFAULT '[]',
    needs_review INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_grouping ON events(state, event_type, last_update);

CREATE TABLE IF NOT EXISTS event_publications (
    event_id INTEGER NOT NULL REFERENCES events(id),
    publication_id INTEGER NOT NULL REFERENCES publications(id),
    relationship_type TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    is_primary_source INTEGER NOT NULL DEFAULT 0,
    linked_at TEXT NOT NULL,
    PRIMARY KEY(event_id, publication_id)
);

CREATE TABLE IF NOT EXISTS actors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL,
    party TEXT,
    state TEXT,
    aliases TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_priority INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_actors (
    event_id INTEGER NOT NULL REFERENCES events(id),
    actor_id INTEGER NOT NULL REFERENCES actors(id),
    role TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    PRIMARY KEY(event_id, actor_id)
);

CREATE TABLE IF NOT EXISTS rule_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL REFERENCES publications(id),
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    matched_value TEXT NOT NULL,
    score_awarded INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rule_matches_publication ON rule_matches(publication_id);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.executescript(SCHEMA)
            publication_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(publications)").fetchall()
            }
            if "is_mock" not in publication_columns:
                connection.execute(
                    "ALTER TABLE publications ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0"
                )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except (sqlite3.Error, ValueError, TypeError):
            connection.rollback()
            raise
        finally:
            connection.close()
