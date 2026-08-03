from datetime import timezone

from app.collectors.rss import RSSCollector


def collector_config() -> dict:
    return {
        "settings": {
            "respect_robots": False,
            "delay_between_feeds_seconds": 0,
            "max_items_per_feed": 5,
        },
        "feeds": [
            {
                "source_name": "Fuente RSS",
                "feed_url": "https://example.test/feed.xml",
                "include_keywords": ["electoral"],
            }
        ],
    }


def test_parse_rss_filters_items_and_cleans_html() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item><title>Calendario electoral en Puebla</title>
        <link>https://example.test/electoral</link>
        <guid>notice-1</guid>
        <pubDate>Fri, 31 Jul 2026 12:00:00 GMT</pubDate>
        <description><![CDATA[<p>El instituto public&oacute; el calendario electoral.</p>]]></description>
      </item>
      <item><title>Resultados deportivos</title>
        <link>https://example.test/sports</link><description>Calendario electoral citado fuera de contexto</description>
      </item>
    </channel></rss>"""
    collector = RSSCollector(collector_config())

    items = collector._parse_feed(payload, collector.feeds[0])

    assert len(items) == 1
    assert items[0].title == "Calendario electoral en Puebla"
    assert items[0].raw_text == "El instituto publicó el calendario electoral."
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo == timezone.utc
    assert items[0].metadata["is_mock"] is False


def test_parse_atom_uses_href_and_iso_date() -> None:
    config = collector_config()
    config["feeds"][0]["include_keywords"] = []
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Resoluci&#243;n del tribunal</title>
        <link rel="alternate" href="https://example.test/resolucion"/>
        <id>tag:example.test,2026:1</id><updated>2026-07-31T10:30:00Z</updated>
        <summary>Sentencia electoral</summary><author><name>Redacci&#243;n</name></author>
      </entry>
    </feed>"""
    collector = RSSCollector(config)

    items = collector._parse_feed(payload, collector.feeds[0])

    assert len(items) == 1
    assert items[0].url == "https://example.test/resolucion"
    assert items[0].author == "Redacción"
    assert items[0].published_at is not None
    assert items[0].published_at.isoformat() == "2026-07-31T10:30:00+00:00"


def test_exclude_keywords_filters_international_news() -> None:
    config = {
        "settings": {
            "respect_robots": False,
            "delay_between_feeds_seconds": 0,
            "max_items_per_feed": 5,
        },
        "feeds": [
            {
                "source_name": "Medio nacional",
                "feed_url": "https://example.test/feed.xml",
                "include_keywords": ["candidatura"],
                "exclude_keywords": ["Brasil", "Lula", "Trump"],
            }
        ],
    }
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item><title>Lula lanza candidatura en Brasil</title>
        <link>https://example.test/lula</link>
        <pubDate>Fri, 31 Jul 2026 12:00:00 GMT</pubDate>
        <description>Lula se registra como candidato.</description>
      </item>
      <item><title>Candidatura para la gubernatura de Nuevo Le&#xF3;n</title>
        <link>https://example.test/nl</link>
        <pubDate>Fri, 31 Jul 2026 13:00:00 GMT</pubDate>
        <description>Se registra candidato del PAN.</description>
      </item>
    </channel></rss>"""
    collector = RSSCollector(config)

    items = collector._parse_feed(payload, collector.feeds[0])

    assert len(items) == 1
    assert items[0].title == "Candidatura para la gubernatura de Nuevo León"


def test_require_mexico_context_rejects_non_mexican_items() -> None:
    config = {
        "settings": {
            "respect_robots": False,
            "delay_between_feeds_seconds": 0,
            "max_items_per_feed": 5,
            "mexico_context_terms": ["México", "INE", "gubernatura", "Nuevo León"],
        },
        "feeds": [
            {
                "source_name": "Medio amplio",
                "feed_url": "https://example.test/feed.xml",
                "include_keywords": ["candidatura", "elección"],
                "require_mexico_context": True,
            }
        ],
    }
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item><title>Elecciones anticipadas en Francia</title>
        <link>https://example.test/francia</link>
        <pubDate>Fri, 31 Jul 2026 12:00:00 GMT</pubDate>
        <description>Macron convoca a elecciones anticipadas.</description>
      </item>
      <item><title>INE publica calendario de elecciones en M&#xE9;xico</title>
        <link>https://example.test/ine</link>
        <pubDate>Fri, 31 Jul 2026 13:00:00 GMT</pubDate>
        <description>El INE public&#xF3; el calendario electoral.</description>
      </item>
    </channel></rss>"""
    collector = RSSCollector(config)

    items = collector._parse_feed(payload, collector.feeds[0])

    assert len(items) == 1
    assert "INE" in items[0].title

