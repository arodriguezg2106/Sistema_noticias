"""Domain models used by collectors, rules, persistence, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Source:
    name: str
    source_type: str
    base_url: str
    state: str | None = None
    reliability_level: str = "medium"
    is_active: bool = True
    id: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CollectedPublication:
    """Collector-neutral publication before persistence."""

    source_name: str
    title: str
    url: str
    published_at: datetime | None
    author: str | None = None
    raw_text: str = ""
    external_id: str | None = None
    publication_type: str = "news"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Publication:
    source_id: int
    title: str
    url: str
    normalized_url: str
    published_at: datetime | None
    collected_at: datetime
    author: str | None
    raw_text: str
    normalized_text: str
    content_hash: str
    publication_type: str = "news"
    is_mock: bool = False
    external_id: str | None = None
    state_detected: str | None = None
    municipality_detected: str | None = None
    party_detected: str | None = None
    event_type_detected: str | None = None
    status: str = "collected"
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    duplicate_of_publication_id: int | None = None
    duplicate_reason: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Event:
    event_code: str
    title: str
    event_type: str
    state: str | None
    municipality: str | None
    start_date: datetime
    last_update: datetime
    status: str = "detected"
    priority_score: int = 0
    importance_level: str = "Bajo"
    description: str = ""
    score_reasons: list[str] = field(default_factory=list)
    needs_review: bool = False
    id: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class EventPublication:
    event_id: int
    publication_id: int
    relationship_type: str
    similarity_score: float
    is_primary_source: bool = False
    linked_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Actor:
    name: str
    actor_type: str
    party: str | None = None
    state: str | None = None
    aliases: list[str] = field(default_factory=list)
    is_active: bool = True
    is_priority: bool = False
    id: int | None = None


@dataclass(slots=True)
class EventActor:
    event_id: int
    actor_id: int
    role: str = "mentioned"
    relevance_score: float = 1.0


@dataclass(slots=True)
class RuleMatch:
    publication_id: int
    rule_name: str
    rule_type: str
    matched_value: str
    score_awarded: int
    id: int | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ClassificationResult:
    state: str | None
    municipality: str | None
    party: str | None
    event_type: str | None
    actor_names: list[str]
    matches: list[RuleMatch]
    needs_review: bool
    review_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DuplicateResult:
    is_duplicate: bool
    original_publication_id: int | None = None
    reason: str | None = None


@dataclass(slots=True)
class ProcessingSummary:
    collected: int = 0
    inserted: int = 0
    already_seen: int = 0
    duplicates: int = 0
    new_events: int = 0
    updated_events: int = 0
    review_items: int = 0
    event_ids: list[int] = field(default_factory=list)
