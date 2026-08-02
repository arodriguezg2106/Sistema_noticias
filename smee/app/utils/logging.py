"""Application logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path, verbose: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for handler in (
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "smee.log", encoding="utf-8"),
    ):
        handler.setFormatter(formatter)
        root.addHandler(handler)

