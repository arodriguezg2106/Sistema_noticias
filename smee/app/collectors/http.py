"""Shared bounded HTTP access for public XML collectors."""

from __future__ import annotations

import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from app.collectors.base import CollectorError

import ssl

LOGGER = logging.getLogger(__name__)


def _create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class RespectfulHTTPClient:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.timeout_seconds = float(settings.get("timeout_seconds", 15))
        self.max_response_bytes = int(settings.get("max_feed_bytes", 2_000_000))
        self.user_agent = str(
            settings.get("user_agent", "SMEE/0.2 (respectful public XML reader)")
        )
        self.ssl_context = _create_ssl_context()
        if not 1 <= self.timeout_seconds <= 60:
            raise CollectorError("timeout_seconds must be between 1 and 60")
        if not 1_024 <= self.max_response_bytes <= 10_000_000:
            raise CollectorError("max_feed_bytes must be between 1024 and 10000000")

    def robots_allows(self, target_url: str) -> bool:
        parts = urlsplit(target_url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        try:
            content = self.download(robots_url, "text/plain").decode("utf-8", "replace")
        except CollectorError as exc:
            LOGGER.warning("Could not verify robots.txt for %s: %s (defaulting to allowed)", target_url, exc)
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(content.splitlines())
        return parser.can_fetch(self.user_agent, target_url)

    def download(self, url: str, accept: str) -> bytes:
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": accept})
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                payload = response.read(self.max_response_bytes + 1)
        except (HTTPError, URLError, TimeoutError, ValueError, Exception) as exc:
            raise CollectorError(f"Could not download {url}: {exc}") from exc
        if len(payload) > self.max_response_bytes:
            raise CollectorError(f"Response exceeds {self.max_response_bytes} bytes: {url}")
        return payload

