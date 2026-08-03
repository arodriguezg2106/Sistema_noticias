from datetime import datetime, timezone

from app.collectors.news_sitemap import NewsSitemapCollector


def test_news_sitemap_filters_by_age_and_electoral_terms() -> None:
    config = {
        "settings": {
            "respect_robots": False,
            "max_age_hours": 48,
            "max_items_per_sitemap": 10,
        },
        "sitemaps": [
            {
                "source_name": "Medio estatal",
                "sitemap_url": "https://example.test/sitemap-news.xml",
                "include_keywords": ["gubernatura", "elecciones"],
            }
        ],
    }
    payload = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"
      xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url><loc>https://example.test/aldo</loc><news:news>
        <news:publication_date>2026-07-31T13:09:00Z</news:publication_date>
        <news:title>Aldo se registra como candidato a la gubernatura</news:title>
        <news:keywords>Nuevo León, PAN, Elecciones</news:keywords>
      </news:news><image:image><image:caption>Registro político estatal</image:caption></image:image></url>
      <url><loc>https://example.test/clima</loc><news:news>
        <news:publication_date>2026-07-31T14:00:00Z</news:publication_date>
        <news:title>Lluvias en Monterrey</news:title><news:keywords>Clima</news:keywords>
      </news:news></url>
      <url><loc>https://example.test/old</loc><news:news>
        <news:publication_date>2026-07-20T14:00:00Z</news:publication_date>
        <news:title>Encuestas para la gubernatura</news:title>
      </news:news></url>
    </urlset>""".encode("utf-8")
    collector = NewsSitemapCollector(
        config, clock=lambda: datetime(2026, 8, 1, 3, 30, tzinfo=timezone.utc)
    )

    items = collector._parse_sitemap(payload, collector.sitemaps[0])

    assert len(items) == 1
    assert items[0].source_name == "Medio estatal"
    assert items[0].url == "https://example.test/aldo"
    assert "Nuevo León" in items[0].raw_text
    assert items[0].metadata["is_mock"] is False


def test_news_sitemap_exclude_keywords() -> None:
    config = {
        "settings": {
            "respect_robots": False,
            "max_age_hours": 48,
            "max_items_per_sitemap": 10,
        },
        "sitemaps": [
            {
                "source_name": "Medio nacional",
                "sitemap_url": "https://example.test/sitemap-news.xml",
                "include_keywords": ["candidatura"],
                "exclude_keywords": ["Brasil", "Lula"],
            }
        ],
    }
    payload = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url><loc>https://example.test/lula</loc><news:news>
        <news:publication_date>2026-07-31T13:09:00Z</news:publication_date>
        <news:title>Lula lanza candidatura en Brasil</news:title>
      </news:news></url>
      <url><loc>https://example.test/mexico</loc><news:news>
        <news:publication_date>2026-07-31T14:00:00Z</news:publication_date>
        <news:title>Candidatura para gubernatura en Jalisco</news:title>
      </news:news></url>
    </urlset>""".encode("utf-8")
    collector = NewsSitemapCollector(
        config, clock=lambda: datetime(2026, 8, 1, 3, 30, tzinfo=timezone.utc)
    )

    items = collector._parse_sitemap(payload, collector.sitemaps[0])

    assert len(items) == 1
    assert items[0].url == "https://example.test/mexico"


