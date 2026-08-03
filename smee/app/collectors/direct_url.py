"""Collector for direct article URLs configured manually or seed URLs."""

from __future__ import annotations

import logging

from re import search
from html.parser import HTMLParser
from datetime import datetime
from typing import Any

from app.collectors.base import Collector, CollectorError
from app.collectors.http import RespectfulHTTPClient
from app.models import CollectedPublication

LOGGER = logging.getLogger(__name__)


class _HTMLArticleExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.in_title: bool = False
        self.paragraphs: list[str] = []
        self.in_paragraph: bool = False
        self.current_p: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title" and not self.title:
            self.in_title = True
        elif tag_lower == "meta":
            attr_dict = {k.lower(): (v or "") for k, v in attrs}
            if attr_dict.get("property") in {"og:title", "twitter:title"} and not self.title:
                self.title = attr_dict.get("content", "").strip()
        elif tag_lower == "p":
            self.in_paragraph = True
            self.current_p = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = False
        elif tag_lower == "p" and self.in_paragraph:
            self.in_paragraph = False
            text = " ".join(self.current_p).strip()
            if len(text) > 20:
                self.paragraphs.append(text)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif self.in_paragraph:
            self.current_p.append(data)


class DirectURLCollector(Collector):
    """Fetch and parse specific article URLs directly."""

    def __init__(self, configs: dict[str, Any]) -> None:
        direct_data = configs.get("direct_urls", {})
        if isinstance(direct_data, dict):
            self.items = direct_data.get("direct_urls", [])
        elif isinstance(direct_data, list):
            self.items = direct_data
        else:
            self.items = []
        
        settings = configs.get("settings", {})
        self.http_client = RespectfulHTTPClient(settings)

    def collect(self) -> list[CollectedPublication]:
        results: list[CollectedPublication] = []
        for item in self.items:
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            source_name = str(item.get("source_name", "URL Directa"))
            publication_type = str(item.get("publication_type", "news"))
            
            try:
                raw_bytes = self.http_client.download(url, "text/html")
                html_text = raw_bytes.decode("utf-8", errors="ignore")
                
                extractor = _HTMLArticleExtractor()
                extractor.feed(html_text)
                
                title = extractor.title.strip()
                if not title:
                    title = url.split("/")[-1].replace("-", " ").capitalize()
                    
                body = " ".join(extractor.paragraphs).strip()
                if not body:
                    body = title

                pub = CollectedPublication(
                    source_name=source_name,
                    title=title,
                    url=url,
                    published_at=datetime.now().astimezone(),
                    raw_text=body,
                    publication_type=publication_type,
                )
                results.append(pub)
                LOGGER.info("DirectURLCollector: successfully fetched %s (%s)", title, url)
            except CollectorError as exc:
                LOGGER.warning("DirectURLCollector: failed to fetch %s: %s", url, exc)
            except Exception as exc:
                LOGGER.warning("DirectURLCollector: unexpected error fetching %s: %s", url, exc)

        return results
