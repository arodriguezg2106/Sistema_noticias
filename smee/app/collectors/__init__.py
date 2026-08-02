"""Publication collectors."""

from .base import Collector, CollectorError
from .composite import CompositeCollector
from .mock import MockCollector
from .news_sitemap import NewsSitemapCollector
from .rss import RSSCollector

__all__ = [
    "Collector", "CollectorError", "CompositeCollector", "MockCollector",
    "NewsSitemapCollector", "RSSCollector",
]
