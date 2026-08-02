"""Application service coordinating the complete prototype workflow."""

from __future__ import annotations

import logging
from datetime import timezone
from pathlib import Path
from typing import Any

from app.collectors.base import Collector
from app.models import Actor, ProcessingSummary, Publication, RuleMatch, Source, utc_now
from app.normalizers.text import content_hash, normalize_text, normalize_url
from app.repositories import (
    ActorRepository,
    Database,
    EventRepository,
    PublicationRepository,
    RuleMatchRepository,
    SourceRepository,
)
from app.event_grouping import EventGrouper
from app.rules import RuleEngine
from app.scoring import EventScorer
from app.summaries import SummaryGenerator

LOGGER = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when the configured pipeline cannot process a publication."""


class ProcessingPipeline:
    def __init__(self, database: Database, configs: dict[str, dict[str, Any]]) -> None:
        self.database = database
        self.configs = configs
        self.sources = SourceRepository(database)
        self.publications = PublicationRepository(database)
        self.actors = ActorRepository(database)
        self.events = EventRepository(database)
        self.rule_matches = RuleMatchRepository(database)
        self.rules = RuleEngine(configs)
        self.grouper = EventGrouper(
            self.events, configs["scoring_rules"].get("grouping", {})
        )
        self.scorer = EventScorer(self.events, configs["scoring_rules"])
        self.summaries = SummaryGenerator(configs)

    def initialize(self) -> None:
        self.database.initialize()
        for item in self.configs["sources"].get("sources", []):
            self.sources.upsert(Source(**item))
        for item in self.configs["actors"].get("actors", []):
            self.actors.upsert(Actor(**item))

    def run(self, collector: Collector) -> ProcessingSummary:
        summary = ProcessingSummary()
        for collected in collector.collect():
            summary.collected += 1
            source = self.sources.get_by_name(collected.source_name)
            if source is None or source.id is None:
                raise PipelineError(f"Unconfigured source: {collected.source_name}")
            if collected.external_id and self.publications.external_id_exists(
                source.id, collected.external_id
            ):
                summary.already_seen += 1
                LOGGER.info(
                    "Previously collected RSS/publication item skipped: %s", collected.title
                )
                continue
            now = utc_now()
            published_at = collected.published_at
            if published_at and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            normalized_body = normalize_text(f"{collected.title} {collected.raw_text}")
            canonical_url = normalize_url(collected.url)
            digest = content_hash(collected.title, collected.raw_text)
            duplicate = self.publications.find_exact_duplicate(canonical_url, digest)
            publication = Publication(
                source_id=source.id,
                external_id=collected.external_id,
                title=collected.title,
                url=collected.url,
                normalized_url=canonical_url,
                published_at=published_at,
                collected_at=now,
                author=collected.author,
                raw_text=collected.raw_text,
                normalized_text=normalized_body,
                content_hash=digest,
                publication_type=collected.publication_type,
                is_mock=bool(collected.metadata.get("is_mock", False)),
                status="duplicate" if duplicate.is_duplicate else "collected",
                duplicate_of_publication_id=duplicate.original_publication_id,
                duplicate_reason=duplicate.reason,
            )
            if duplicate.is_duplicate:
                publication.needs_review = False
                self.publications.add(publication)
                summary.inserted += 1
                summary.duplicates += 1
                if publication.id is not None and duplicate.original_publication_id is not None:
                    event_id = self.events.event_id_for_publication(duplicate.original_publication_id)
                    if event_id is not None:
                        self.events.link_publication(
                            event_id, publication.id, "duplicate", 1.0, False, publication.collected_at
                        )
                        self.scorer.score(event_id)
                LOGGER.info("Duplicate publication retained: %s (%s)", publication.title, duplicate.reason)
                continue

            publication = self.publications.add(publication)
            summary.inserted += 1
            classification = self.rules.classify(publication)
            if classification.state is None and source.state:
                classification.state = source.state
                classification.review_reasons = [
                    reason
                    for reason in classification.review_reasons
                    if reason != "No se detectó una entidad federativa"
                ]
                classification.matches.append(
                    RuleMatch(
                        publication_id=publication.id or 0,
                        rule_name=f"source_default_state:{source.name}",
                        rule_type="source_context",
                        matched_value=source.state,
                        score_awarded=0,
                    )
                )
                classification.needs_review = bool(classification.review_reasons)
            publication.state_detected = classification.state
            publication.municipality_detected = classification.municipality
            publication.party_detected = classification.party
            publication.event_type_detected = classification.event_type
            publication.needs_review = classification.needs_review
            publication.review_reasons = classification.review_reasons
            publication.status = "review" if classification.needs_review else "classified"
            publication.updated_at = utc_now()
            self.publications.update_classification(publication)
            self.rule_matches.add_many(classification.matches)
            detected_actors = self.actors.get_by_names(classification.actor_names)
            description = self.summaries.generate(publication, detected_actors)
            grouping = self.grouper.group(publication, detected_actors, description)
            if grouping.action == "review":
                publication.needs_review = True
                if grouping.reason and grouping.reason not in publication.review_reasons:
                    publication.review_reasons.append(grouping.reason)
                publication.status = "review"
                self.publications.update_classification(publication)
                summary.review_items += 1
                continue
            assert grouping.event is not None and grouping.event.id is not None
            if grouping.action == "created":
                summary.new_events += 1
            else:
                summary.updated_events += 1
            if publication.needs_review:
                summary.review_items += 1
            if grouping.event.id not in summary.event_ids:
                summary.event_ids.append(grouping.event.id)
            self.scorer.score(grouping.event.id)
        self.refresh_summaries()
        return summary

    def refresh_summaries(self) -> None:
        """Backfill summaries so stored events adopt the latest deterministic rules."""
        for event_id in self.events.list_ids():
            row = self.events.primary_publication(event_id)
            if not row:
                continue
            publication = self.publications.from_row(row)
            actors = self.actors.get_by_names(sorted(self.events.actor_names(event_id)))
            description = self.summaries.generate(publication, actors)
            self.events.update_description(event_id, description)
