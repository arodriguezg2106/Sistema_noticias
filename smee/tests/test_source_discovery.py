from pathlib import Path

from app.config import ConfigLoader
from app.source_discovery.detector import SourceDiscovery
from app.source_discovery.models import SourceSeed
from app.source_discovery.queries import boolean_audit_query


def test_discovers_declared_rss_and_news_sitemap(monkeypatch) -> None:
    discovery = SourceDiscovery(
        {"delay_between_sources_seconds": 0, "max_candidates_per_source": 2}
    )
    responses = {
        "https://medio.test/robots.txt": b"""User-agent: *
Allow: /
Sitemap: https://medio.test/sitemap-news.xml
""",
        "https://medio.test": b"""<html><head><link rel="alternate"
          type="application/rss+xml" href="/feed.xml"></head></html>""",
        "https://medio.test/sitemap-news.xml": b"""<?xml version="1.0"?>
          <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
           xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
           <url><loc>https://medio.test/a</loc><news:news><news:title>A</news:title></news:news></url>
          </urlset>""",
        "https://medio.test/feed.xml": b"""<?xml version="1.0"?><rss version="2.0"><channel/></rss>""",
    }

    monkeypatch.setattr(
        discovery.http,
        "download",
        lambda url, accept: responses[url],
    )
    result = discovery.discover(
        SourceSeed("Medio", "https://medio.test", ("Nuevo León",))
    )

    assert result.status == "active"
    assert result.robots_allowed is True
    assert {(item.endpoint_type, item.url) for item in result.endpoints} == {
        ("news_sitemap", "https://medio.test/sitemap-news.xml"),
        ("rss", "https://medio.test/feed.xml"),
    }


def test_registry_maps_all_federal_entities(project_root: Path) -> None:
    loader = ConfigLoader(project_root / "config")
    states = {item["name"] for item in loader.load("states.yaml")["states"]}
    sources = [SourceSeed.from_mapping(item) for item in loader.load("source_registry.yaml")["sources"]]
    mapped = {state for source in sources for state in source.states}
    assert len(states) == 32
    assert states <= mapped
    assert len(sources) >= 40


def test_boolean_query_contains_state_date_and_exclusions() -> None:
    query = boolean_audit_query("Nuevo León", ["nuevo leon", "NL"])
    assert '"Nuevo León"' in query
    assert '"gubernatura" OR "elecciones 2027"' in query
    assert "after:" in query
    assert "-fútbol -deportes" in query

