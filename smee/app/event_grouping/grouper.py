"""Decide whether a publication creates or updates an event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from app.models import Actor, Event, Publication
from app.repositories.events import EventRepository
from app.utils.similarity import title_similarity


@dataclass(slots=True)
class GroupingResult:
    action: str
    event: Event | None
    similarity_score: float = 0.0
    reason: str = ""


class EventGrouper:
    def __init__(self, repository: EventRepository, settings: dict[str, Any]) -> None:
        self.repository = repository
        self.settings = settings

    def group(
        self,
        publication: Publication,
        actors: list[Actor],
        description: str | None = None,
    ) -> GroupingResult:
        if publication.id is None:
            raise ValueError("Publication must have an id before grouping")
        if publication.event_type_detected is None or publication.published_at is None:
            return GroupingResult(
                "review", None, reason="Falta el tipo de evento o una fecha verificable"
            )
        if publication.state_detected is None:
            return GroupingResult("review", None, reason="Falta entidad o ámbito geográfico")

        window_days = int(self.settings.get("temporal_window_days", 3))
        candidates = self.repository.find_candidates(
            publication.state_detected,
            publication.event_type_detected,
            publication.published_at - timedelta(days=window_days),
            publication.published_at + timedelta(days=window_days),
        )
        actor_names = {actor.name for actor in actors}
        ranked: list[tuple[float, Event]] = []
        for candidate in candidates:
            title_score = title_similarity(publication.title, candidate.title)
            shared_actor = bool(actor_names & self.repository.actor_names(candidate.id or 0))
            score = title_score + (float(self.settings.get("shared_actor_bonus", 0.2)) if shared_actor else 0.0)
            ranked.append((min(score, 1.0), candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)

        threshold = float(self.settings.get("similarity_threshold", 0.62))
        if ranked and ranked[0][0] >= threshold:
            margin = float(self.settings.get("ambiguity_margin", 0.05))
            if len(ranked) > 1 and ranked[0][0] - ranked[1][0] <= margin:
                publication.needs_review = True
                publication.review_reasons.append("Coincide de forma similar con más de un evento")
                return GroupingResult(
                    "review", None, ranked[0][0], "Coincidencia ambigua con eventos existentes"
                )
            event = ranked[0][1]
            self.repository.link_publication(
                event.id or 0, publication.id, "additional_evidence", ranked[0][0], False,
                publication.collected_at,
            )
            self.repository.attach_actors(event.id or 0, actors)
            self.repository.mark_updated(
                event.id or 0, publication.published_at, publication.needs_review
            )
            if description and (
                not (35 <= len(event.description.split()) <= 60)
                or len(description.split()) > len(event.description.split())
            ):
                self.repository.update_description(event.id or 0, description)
            refreshed = self.repository.get(event.id or 0)
            return GroupingResult("updated", refreshed, ranked[0][0], "Matched existing event")

        event = Event(
            event_code=f"SMEE-{publication.published_at:%Y%m%d}-{uuid4().hex[:8].upper()}",
            title=publication.title,
            event_type=publication.event_type_detected,
            state=publication.state_detected,
            municipality=publication.municipality_detected,
            start_date=publication.published_at,
            last_update=publication.published_at,
            status="detected",
            description=description or (publication.raw_text.strip() or publication.title)[:500],
            needs_review=publication.needs_review,
        )
        event = self.repository.add(event)
        self.repository.link_publication(
            event.id or 0, publication.id, "primary_evidence", 1.0, True,
            publication.collected_at,
        )
        self.repository.attach_actors(event.id or 0, actors)
        return GroupingResult("created", event, 1.0, "No suitable existing event")
