from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigLoader


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def configs(project_root: Path) -> dict:
    return ConfigLoader(project_root / "config").load_all()

