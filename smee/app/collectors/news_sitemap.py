"""Collector for public Google News sitemap XML documents."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import Collector, CollectorError
from app.collectors.http import RespectfulHTTPClient
from app.models import CollectedPublication, utc_now
from app.normalizers.text import normalize_text

LOGGER = logging.getLogger(__name__)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


@dataclass(frozen=True, slots=True)
class NewsSitemapConfig:
    source_name: str
    sitemap_url: str
    max_items: int
    max_age_hours: int
    include_keywords: tuple[str, ...]
    required_path_prefixes: tuple[str, ...]
    filter_scope: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any], settings: dict[str, Any]) -> "NewsSitemapConfig":
        try:
            source_name = str(data["source_name"])
            sitemap_url = str(data["sitemap_url"])
        except KeyError as exc:
            raise CollectorError(f"Missing news sitemap setting: {exc}") from exc
        if urlsplit(sitemap_url).scheme not in {"http", "https"}:
            raise CollectorError(f"News sitemap must use HTTP or HTTPS: {sitemap_url}")
        max_items = int(data.get("max_items", settings.get("max_items_per_sitemap", 30)))
        max_age = int(data.get("max_age_hours", settings.get("max_age_hours", 48)))
        if not 1 <= max_items <= 100:
            raise CollectorError(f"max_items must be between 1 and 100 for {source_name}")
        if not 1 <= max_age <= 168:
            raise CollectorError(f"max_age_hours must be between 1 and 168 for {source_name}")
        filter_scope = str(data.get("filter_scope", "title"))
        if filter_scope not in {"title", "title_and_metadata"}:
            raise CollectorError(f"Invalid filter_scope for {source_name}: {filter_scope}")
        return cls(
            source_name=source_name,
            sitemap_url=sitemap_url,
            max_items=max_items,
            max_age_hours=max_age,
            include_keywords=tuple(str(item) for item in data.get("include_keywords", [])),
            required_path_prefixes=tuple(
                str(item) for item in data.get("required_path_prefixes", [])
            ),
            filter_scope=filter_scope,
        )


class NewsSitemapCollector(Collector):
    def __init__(
        self,
        config: dict[str, Any],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        settings = config.get("settings", {})
        self.http = RespectfulHTTPClient(settings)
        self.respect_robots = bool(settings.get("respect_robots", True))
        self.delay_seconds = float(settings.get("delay_between_sitemaps_seconds", 1))
        if not 0 <= self.delay_seconds <= 60:
            raise CollectorError("delay_between_sitemaps_seconds must be between 0 and 60")
        self.clock = clock
        raw_sitemaps = config.get("sitemaps", [])
        if not isinstance(raw_sitemaps, list) or not raw_sitemaps:
            raise CollectorError("news_sitemaps.yaml must define at least one sitemap")
        self.sitemaps: list[NewsSitemapConfig] = []
        for item in raw_sitemaps:
            if not isinstance(item, dict):
                raise CollectorError("Each news sitemap setting must be a mapping")
            if item.get("enabled", True):
                self.sitemaps.append(NewsSitemapConfig.from_mapping(item, settings))
        if not self.sitemaps:
            raise CollectorError("No news sitemaps are enabled")

    def collect(self) -> list[CollectedPublication]:
        results: list[CollectedPublication] = []
        successful = 0
        for index, sitemap in enumerate(self.sitemaps):
            if index:
                time.sleep(self.delay_seconds)
            try:
                if self.respect_robots and not self.http.robots_allows(sitemap.sitemap_url):
                    LOGGER.warning("robots.txt does not allow sitemap: %s", sitemap.sitemap_url)
                    continue
                payload = self.http.download(sitemap.sitemap_url, "application/xml, text/xml")
                items = self._parse_sitemap(payload, sitemap)
                successful += 1
                results.extend(items)
                LOGGER.info("News sitemap %s: %d relevant items", sitemap.source_name, len(items))
            except CollectorError as exc:
                LOGGER.error("News sitemap failed for %s: %s", sitemap.source_name, exc)
        if successful == 0:
            raise CollectorError("All configured news sitemaps failed or were disallowed")
        return results

    def _parse_sitemap(
        self, payload: bytes, sitemap: NewsSitemapConfig
    ) -> list[CollectedPublication]:
        try:
            root = ElementTree.fromstring(payload)
        except (ElementTree.ParseError, DefusedXmlException) as exc:
            raise CollectorError(f"Invalid XML from {sitemap.sitemap_url}: {exc}") from exc
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        oldest = now - timedelta(hours=sitemap.max_age_hours)
        results: list[CollectedPublication] = []
        for url_node in [node for node in list(root) if _local_name(node.tag) == "url"]:
            url = self._descendant_text(url_node, "loc")
            title = self._descendant_text(url_node, "title")
            date_text = self._descendant_text(url_node, "publication_date")
            if not url or not title or not date_text:
                continue
            published_at = self._parse_date(date_text)
            if published_at is None or published_at < oldest or published_at > now + timedelta(hours=1):
                continue
            keywords = self._descendant_text(url_node, "keywords") or ""
            caption = self._descendant_text(url_node, "caption") or ""
            path = urlsplit(url).path
            if sitemap.required_path_prefixes and not any(
                path.startswith(prefix) for prefix in sitemap.required_path_prefixes
            ):
                continue
            searchable = normalize_text(
                title
                if sitemap.filter_scope == "title"
                else f"{title} {keywords} {caption}"
            )
            if sitemap.include_keywords and not any(
                normalize_text(keyword) in searchable for keyword in sitemap.include_keywords
            ):
                continue
            results.append(
                CollectedPublication(
                    source_name=sitemap.source_name,
                    external_id=url,
                    title=title,
                    url=url,
                    published_at=published_at,
                    author=None,
                    raw_text=" ".join(part for part in (keywords, caption) if part),
                    publication_type="news",
                    metadata={"is_mock": False, "sitemap_url": sitemap.sitemap_url},
                )
            )
        results.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return results[: sitemap.max_items]

    @staticmethod
    def _descendant_text(node: Any, name: str) -> str | None:
        for descendant in node.iter():
            if _local_name(descendant.tag) == name:
                text = "".join(descendant.itertext()).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
