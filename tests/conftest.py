"""Shared fixtures and helpers for the test suite."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

# Make the project root importable when pytest runs from any folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import Flashcard  # noqa: E402

DeckWriter = Callable[[Any], Path]


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in its own temporary folder.

    The CLI writes its history file to the current folder by default. If a
    bug made a test write that file, it must not land in the project.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def write_deck(tmp_path: Path) -> DeckWriter:
    """Return a function that writes JSON data to a temporary deck file."""
    counter = {"n": 0}

    def _write(data: Any) -> Path:
        counter["n"] += 1
        path = tmp_path / f"deck_{counter['n']}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def cards() -> list[Flashcard]:
    """Four simple cards: Q1/A1 to Q4/A4."""
    return [Flashcard(f"Q{i}", f"A{i}") for i in range(1, 5)]


def scripted_input(answers: Iterable[str]) -> Callable[[str], str]:
    """Return an input() replacement that gives ``answers`` in order.

    When the answers run out it raises EOFError, the same as Ctrl+D.
    """
    remaining = iter(answers)

    def _input(prompt: str = "") -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    return _input
