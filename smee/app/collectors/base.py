"""Collector contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import CollectedPublication


class CollectorError(RuntimeError):
    """Raised when a collector cannot obtain or parse its input."""


class Collector(ABC):
    @abstractmethod
    def collect(self) -> list[CollectedPublication]:
        """Collect publications normalized to the shared input model."""

