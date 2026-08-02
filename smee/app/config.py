"""Typed access to YAML configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class ConfigLoader:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def load(self, filename: str) -> dict[str, Any]:
        path = self.config_dir / filename
        if not path.is_file():
            raise ConfigurationError(f"Configuration file not found: {path}")
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigurationError(f"The root of {path} must be a mapping")
        return data

    def load_all(self) -> dict[str, dict[str, Any]]:
        names = (
            "sources.yaml",
            "searches.yaml",
            "states.yaml",
            "parties.yaml",
            "actors.yaml",
            "event_types.yaml",
            "scoring_rules.yaml",
            "rss_sources.yaml",
            "news_sitemaps.yaml",
            "summary_rules.yaml",
        )
        return {Path(name).stem: self.load(name) for name in names}
