"""Calculate an event priority score from externalized rules."""

from __future__ import annotations

from typing import Any

from app.models import Event
from app.repositories.events import EventRepository


class EventScorer:
    def __init__(self, repository: EventRepository, config: dict[str, Any]) -> None:
        self.repository = repository
        self.base_scores = config.get("event_type_scores", {})
        self.adjustments = config.get("adjustments", {})
        self.levels = config.get("levels", {})

    def score(self, event_id: int) -> Event:
        event = self.repository.get(event_id)
        if event is None:
            raise ValueError(f"Event {event_id} does not exist")
        total = int(self.base_scores.get(event.event_type, 0))
        reasons = [f"Tipo '{event.event_type}': +{total}"]

        if self.repository.has_official_source(event_id):
            value = int(self.adjustments.get("official_source", 0))
            total += value
            reasons.append(f"Fuente oficial: {value:+d}")
        source_count = self.repository.count_sources(event_id)
        source_rule = self.adjustments.get("multiple_independent_sources", {})
        if source_count > int(source_rule.get("minimum", 3)):
            value = int(source_rule.get("score", 0))
            total += value
            reasons.append(f"{source_count} fuentes independientes: {value:+d}")
        if self.repository.has_priority_actor(event_id):
            value = int(self.adjustments.get("priority_actor", 0))
            total += value
            reasons.append(f"Actor prioritario: {value:+d}")
        if self.repository.has_duplicate_publication(event_id):
            value = int(self.adjustments.get("duplicate_publication", 0))
            total += value
            reasons.append(f"Publicación duplicada vinculada: {value:+d}")
        primary = self.repository.primary_publication(event_id)
        if primary and primary.get("publication_type") == "opinion":
            value = int(self.adjustments.get("opinion_column", 0))
            total += value
            reasons.append(f"Columna de opinión: {value:+d}")
        if primary and not primary.get("published_at"):
            value = int(self.adjustments.get("unverified_date", 0))
            total += value
            reasons.append(f"Sin fecha verificable: {value:+d}")

        level = self._level(total)
        self.repository.update_score(event_id, total, level, reasons)
        scored = self.repository.get(event_id)
        assert scored is not None
        return scored

    def _level(self, score: int) -> str:
        thresholds = sorted(
            ((int(value), str(name)) for name, value in self.levels.items()), reverse=True
        )
        return next((name for minimum, name in thresholds if score >= minimum), "Descartable")
