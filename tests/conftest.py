"""Shared test fixtures. Tests run offline with no API key."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from coach.config import Paths

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Keep the real key and settings out of tests, and undo anything .env loads."""
    for key in ("GEMINI_API_KEY", "COACH_DATA_DIR", "COACH_MOCK"):
        monkeypatch.delenv(key, raising=False)
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def workspace(tmp_path: Path) -> Paths:
    """An empty project folder with the real .gitignore."""
    shutil.copyfile(REPO / ".gitignore", tmp_path / ".gitignore")
    return Paths(root=tmp_path, data=tmp_path / "data", rubric=tmp_path / "rubric" / "rubric.md")
