"""Models for the source registry and discovery results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.normalizers.text import normalize_url


@dataclass(frozen=True, slots=True)
class SourceSeed:
    name: str
    base_url: str
    states: tuple[str, ...]
    source_type: str = "media"
    priority: str = "medium"
    enabled: bool = True
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SourceSeed":
        return cls(
            name=str(data["name"]),
            base_url=normalize_url(str(data["base_url"])).rstrip("/"),
            states=tuple(str(item) for item in data.get("states", [])),
            source_type=str(data.get("source_type", "media")),
            priority=str(data.get("priority", "medium")),
            enabled=bool(data.get("enabled", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True, slots=True)
class DiscoveredEndpoint:
    endpoint_type: str
    url: str
    source: str


@dataclass(slots=True)
class DiscoveryResult:
    name: str
    base_url: str
    states: tuple[str, ...]
    source_type: str
    status: str
    robots_allowed: bool | None
    endpoints: list[DiscoveredEndpoint] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["states"] = list(self.states)
        return data

