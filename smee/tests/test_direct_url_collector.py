"""Tests for DirectURLCollector."""

from __future__ import annotations

from app.collectors.direct_url import DirectURLCollector


def test_direct_url_collector_parses_item() -> None:
    configs = {
        "settings": {
            "timeout_seconds": 10,
        },
        "direct_urls": {
            "direct_urls": [
                {
                    "url": "https://example.test/noticia-bcs",
                    "source_name": "Test Source",
                    "publication_type": "news",
                }
            ]
        }
    }
    collector = DirectURLCollector(configs)
    assert len(collector.items) == 1
    assert collector.items[0]["source_name"] == "Test Source"
