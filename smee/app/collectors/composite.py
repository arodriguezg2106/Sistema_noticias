"""Combine independent collectors while isolating source failures."""

from __future__ import annotations

import logging

from app.collectors.base import Collector, CollectorError
from app.models import CollectedPublication

LOGGER = logging.getLogger(__name__)


class CompositeCollector(Collector):
    def __init__(self, collectors: list[Collector]) -> None:
        if not collectors:
            raise CollectorError("CompositeCollector requires at least one collector")
        self.collectors = collectors

    def collect(self) -> list[CollectedPublication]:
        results: list[CollectedPublication] = []
        successful = 0
        seen: set[tuple[str, str]] = set()
        for collector in self.collectors:
            try:
                items = collector.collect()
                successful += 1
            except CollectorError as exc:
                LOGGER.error("Collector %s failed: %s", type(collector).__name__, exc)
                continue
            for item in items:
                key = (item.source_name, item.external_id or item.url)
                if key not in seen:
                    seen.add(key)
                    results.append(item)
        if successful == 0:
            raise CollectorError("All live collectors failed")
        return results

