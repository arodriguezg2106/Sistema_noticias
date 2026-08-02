"""JSON-backed collector used for development and tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.collectors.base import Collector, CollectorError
from app.models import CollectedPublication


class MockCollector(Collector):
    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path

    def collect(self) -> list[CollectedPublication]:
        try:
            with self.input_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError as exc:
            raise CollectorError(f"Mock input not found: {self.input_path}") from exc
        except json.JSONDecodeError as exc:
            raise CollectorError(f"Invalid JSON in {self.input_path}: {exc}") from exc
        if not isinstance(payload, list):
            raise CollectorError("Mock input must contain a JSON array")

        publications: list[CollectedPublication] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise CollectorError(f"Item {index} must be an object")
            try:
                published_at = (
                    datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                    if item.get("published_at")
                    else None
                )
                publications.append(
                    CollectedPublication(
                        source_name=item["source_name"],
                        title=item["title"],
                        url=item["url"],
                        published_at=published_at,
                        author=item.get("author"),
                        raw_text=item.get("raw_text", ""),
                        external_id=item.get("external_id"),
                        publication_type=item.get("publication_type", "news"),
                        metadata={**item.get("metadata", {}), "is_mock": True},
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CollectorError(f"Invalid mock item at index {index}: {exc}") from exc
        return publications
