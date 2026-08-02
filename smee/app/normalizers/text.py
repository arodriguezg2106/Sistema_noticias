"""Deterministic text, URL, and content normalization."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_text(value: str) -> str:
    """Normalize text for deterministic matching without losing word boundaries."""
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(value: str) -> str:
    """Canonicalize a URL and discard common tracking parameters."""
    parts = urlsplit(value.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    query_items = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query_items)), ""))


def content_hash(title: str, body: str) -> str:
    normalized = normalize_text(f"{title} {body}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

