"""Discover declared public XML endpoints without scraping article pages."""

from __future__ import annotations

import logging
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import CollectorError
from app.collectors.http import RespectfulHTTPClient
from app.source_discovery.models import DiscoveryResult, DiscoveredEndpoint, SourceSeed

LOGGER = logging.getLogger(__name__)


class _AlternateLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attributes = {key.lower(): value or "" for key, value in attrs}
        rel_tokens = {part.lower() for part in attributes.get("rel", "").split()}
        media_type = attributes.get("type", "").lower()
        href = attributes.get("href")
        if href and "alternate" in rel_tokens and media_type in {
            "application/rss+xml", "application/atom+xml", "application/xml", "text/xml"
        }:
            self.urls.append(urljoin(self.base_url, href))


class SourceDiscovery:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        settings = settings or {}
        self.http = RespectfulHTTPClient(settings)
        self.delay_seconds = float(settings.get("delay_between_sources_seconds", 1))
        self.max_candidates = int(settings.get("max_candidates_per_source", 7))
        if not 0 <= self.delay_seconds <= 60:
            raise ValueError("delay_between_sources_seconds must be between 0 and 60")
        if not 1 <= self.max_candidates <= 12:
            raise ValueError("max_candidates_per_source must be between 1 and 12")

    def discover_many(self, seeds: list[SourceSeed]) -> list[DiscoveryResult]:
        results: list[DiscoveryResult] = []
        for index, seed in enumerate(seeds):
            if index:
                time.sleep(self.delay_seconds)
            LOGGER.info("Discovering public endpoints for %s", seed.name)
            results.append(self.discover(seed))
        return results

    def discover(self, seed: SourceSeed) -> DiscoveryResult:
        result = DiscoveryResult(
            name=seed.name,
            base_url=seed.base_url,
            states=seed.states,
            source_type=seed.source_type,
            status="pending",
            robots_allowed=None,
        )
        robots_url = self._robots_url(seed.base_url)
        try:
            robots_text = self.http.download(robots_url, "text/plain").decode("utf-8", "replace")
        except CollectorError as exc:
            result.status = "robots_unavailable"
            result.errors.append(str(exc))
            return result

        robot_parser = RobotFileParser()
        robot_parser.set_url(robots_url)
        robot_parser.parse(robots_text.splitlines())
        result.robots_allowed = robot_parser.can_fetch(self.http.user_agent, seed.base_url)
        if not result.robots_allowed:
            result.status = "blocked_by_robots"
            return result

        candidates: list[tuple[str, str]] = []
        for line in robots_text.splitlines():
            if line.lower().startswith("sitemap:"):
                candidates.append((line.split(":", 1)[1].strip(), "robots"))
        try:
            homepage = self.http.download(seed.base_url, "text/html, application/xhtml+xml").decode(
                "utf-8", "replace"
            )
            parser = _AlternateLinkParser(seed.base_url)
            parser.feed(homepage)
            parser.close()
            candidates.extend((url, "html_link") for url in parser.urls)
        except CollectorError as exc:
            result.errors.append(str(exc))

        parts = urlsplit(seed.base_url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        candidates.extend(
            (urljoin(origin, path), "common_path")
            for path in ("/feed.xml", "/feed/", "/rss.xml", "/sitemap-news.xml", "/sitemap.xml")
        )
        unique_candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        for url, origin_type in candidates:
            if url and url not in seen and robot_parser.can_fetch(self.http.user_agent, url):
                seen.add(url)
                unique_candidates.append((url, origin_type))
            if len(unique_candidates) >= self.max_candidates:
                break

        for url, origin_type in unique_candidates:
            try:
                payload = self.http.download(
                    url, "application/rss+xml, application/atom+xml, application/xml, text/xml"
                )
                endpoint_type = self._identify_xml(payload)
                if endpoint_type:
                    result.endpoints.append(DiscoveredEndpoint(endpoint_type, url, origin_type))
            except CollectorError as exc:
                if origin_type != "common_path":
                    result.errors.append(str(exc))
        result.status = "active" if result.endpoints else "reachable_without_xml"
        return result

    @staticmethod
    def _robots_url(base_url: str) -> str:
        parts = urlsplit(base_url)
        return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    @staticmethod
    def _identify_xml(payload: bytes) -> str | None:
        try:
            root = ElementTree.fromstring(payload)
        except (ElementTree.ParseError, DefusedXmlException):
            return None
        local_name = root.tag.rsplit("}", 1)[-1].lower()
        if local_name == "rss" or local_name == "rdf":
            return "rss"
        if local_name == "feed":
            return "atom"
        if local_name == "sitemapindex":
            return "sitemap_index"
        if local_name == "urlset":
            has_news = any(
                node.tag.rsplit("}", 1)[-1].lower() == "news" for node in root.iter()
            )
            return "news_sitemap" if has_news else "sitemap"
        return None
