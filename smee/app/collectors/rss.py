"""Respectful RSS/Atom collector for configured public feeds."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import Collector, CollectorError
from app.collectors.http import RespectfulHTTPClient
from app.models import CollectedPublication
from app.normalizers.text import normalize_text

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RSSFeedConfig:
    source_name: str
    feed_url: str
    publication_type: str = "news"
    max_items: int = 15
    include_keywords: tuple[str, ...] = ()
    filter_scope: str = "title"

    @classmethod
    def from_mapping(cls, data: dict[str, Any], default_max_items: int) -> "RSSFeedConfig":
        try:
            source_name = str(data["source_name"])
            feed_url = str(data["feed_url"])
        except KeyError as exc:
            raise CollectorError(f"Missing RSS feed setting: {exc}") from exc
        if urlsplit(feed_url).scheme not in {"http", "https"}:
            raise CollectorError(f"RSS feed must use HTTP or HTTPS: {feed_url}")
        max_items = int(data.get("max_items", default_max_items))
        if not 1 <= max_items <= 100:
            raise CollectorError(f"max_items must be between 1 and 100 for {source_name}")
        filter_scope = str(data.get("filter_scope", "title"))
        if filter_scope not in {"title", "title_and_summary"}:
            raise CollectorError(f"Invalid filter_scope for {source_name}: {filter_scope}")
        return cls(
            source_name=source_name,
            feed_url=feed_url,
            publication_type=str(data.get("publication_type", "news")),
            max_items=max_items,
            include_keywords=tuple(str(item) for item in data.get("include_keywords", [])),
            filter_scope=filter_scope,
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []

    def handle_data(self, data: str) -> None:
        self.fragments.append(data)


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(value))
    parser.close()
    return " ".join(" ".join(parser.fragments).split())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class RSSCollector(Collector):
    """Collect a small, filtered batch from RSS/Atom without scraping article pages."""

    def __init__(self, config: dict[str, Any]) -> None:
        settings = config.get("settings", {})
        self.delay_seconds = float(settings.get("delay_between_feeds_seconds", 1))
        self.respect_robots = bool(settings.get("respect_robots", True))
        if not 0 <= self.delay_seconds <= 60:
            raise CollectorError("delay_between_feeds_seconds must be between 0 and 60")
        self.http = RespectfulHTTPClient(settings)
        default_max = int(settings.get("max_items_per_feed", 15))
        feeds = config.get("feeds", [])
        if not isinstance(feeds, list) or not feeds:
            raise CollectorError("rss_sources.yaml must define at least one feed")
        self.feeds: list[RSSFeedConfig] = []
        for item in feeds:
            if not isinstance(item, dict):
                raise CollectorError("Each RSS feed setting must be a mapping")
            if item.get("enabled", True):
                self.feeds.append(RSSFeedConfig.from_mapping(item, default_max))
        if not self.feeds:
            raise CollectorError("No RSS feeds are enabled")

    def collect(self) -> list[CollectedPublication]:
        publications: list[CollectedPublication] = []
        successful_feeds = 0
        seen: set[tuple[str, str]] = set()
        for index, feed in enumerate(self.feeds):
            if index:
                time.sleep(self.delay_seconds)
            try:
                if self.respect_robots and not self._robots_allows(feed.feed_url):
                    LOGGER.warning("robots.txt does not allow feed: %s", feed.feed_url)
                    continue
                payload = self._download(
                    feed.feed_url,
                    "application/rss+xml, application/atom+xml, application/xml, text/xml",
                )
                items = self._parse_feed(payload, feed)
                successful_feeds += 1
                for item in items:
                    key = (item.source_name, item.url)
                    if key not in seen:
                        seen.add(key)
                        publications.append(item)
                LOGGER.info("RSS %s: %d relevant items", feed.source_name, len(items))
            except CollectorError as exc:
                LOGGER.error("RSS feed failed for %s: %s", feed.source_name, exc)
        if successful_feeds == 0:
            raise CollectorError("All configured RSS feeds failed or were disallowed")
        return publications

    def _robots_allows(self, feed_url: str) -> bool:
        return self.http.robots_allows(feed_url)

    def _download(self, url: str, accept: str) -> bytes:
        return self.http.download(url, accept)

    def _parse_feed(self, payload: bytes, feed: RSSFeedConfig) -> list[CollectedPublication]:
        try:
            root = ElementTree.fromstring(payload)
        except (ElementTree.ParseError, DefusedXmlException) as exc:
            raise CollectorError(f"Invalid XML from {feed.feed_url}: {exc}") from exc
        entry_nodes = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
        results: list[CollectedPublication] = []
        for node in entry_nodes:
            title = self._child_text(node, "title")
            url = self._entry_url(node)
            if not title or not url:
                continue
            summary = self._child_text(node, "description", "summary", "encoded", "content") or ""
            body = _html_to_text(summary)
            searchable = normalize_text(
                title if feed.filter_scope == "title" else f"{title} {body}"
            )
            if feed.include_keywords and not any(
                normalize_text(keyword) in searchable for keyword in feed.include_keywords
            ):
                continue
            date_text = self._child_text(node, "pubdate", "published", "updated", "date")
            results.append(
                CollectedPublication(
                    source_name=feed.source_name,
                    external_id=self._child_text(node, "guid", "id") or url,
                    title=_html_to_text(title),
                    url=url.strip(),
                    published_at=self._parse_date(date_text),
                    author=self._child_text(node, "creator", "author"),
                    raw_text=body,
                    publication_type=feed.publication_type,
                    metadata={"is_mock": False, "feed_url": feed.feed_url},
                )
            )
            if len(results) >= feed.max_items:
                break
        return results

    @staticmethod
    def _child_text(node: Any, *names: str) -> str | None:
        expected = {name.lower() for name in names}
        for child in list(node):
            if _local_name(child.tag) in expected:
                text = "".join(child.itertext()).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _entry_url(node: Any) -> str | None:
        for child in list(node):
            if _local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href")
            rel = child.attrib.get("rel", "alternate")
            if href and rel in {"alternate", ""}:
                return href
            if child.text and child.text.strip():
                return child.text.strip()
        return None

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
