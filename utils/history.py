"""Pure functions that read and update the lifetime quiz history.

The history is a plain nested dictionary (see :data:`History`). File reading
and writing stay in :mod:`utils.file_handler`. This module only does the
counting, so it is simple to test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from models import Flashcard
from utils.file_handler import History

SEEN = "seen"
MISSED = "missed"


@dataclass(frozen=True)
class CardRecord:
    """Lifetime counters for one card."""

    front: str
    seen: int
    missed: int

    @property
    def accuracy(self) -> float:
        """Percentage of correct answers, from 0.0 to 100.0."""
        if self.seen == 0:
            return 0.0
        return 100.0 * (self.seen - self.missed) / self.seen


def past_misses(history: History, deck: str) -> dict[str, int]:
    """Return the lifetime miss count for each card front in ``deck``."""
    return {
        front: counters.get(MISSED, 0)
        for front, counters in history.get(deck, {}).items()
    }


def record_answers(
    history: History, deck: str, answers: Iterable[tuple[Flashcard, bool]]
) -> History:
    """Add a session's answers to ``history`` and return it.

    The dictionary is changed in place. It is also returned so that a call
    can be used in an expression.
    """
    deck_history = history.setdefault(deck, {})
    for card, correct in answers:
        counters = deck_history.setdefault(card.front, {SEEN: 0, MISSED: 0})
        counters[SEEN] = counters.get(SEEN, 0) + 1
        if not correct:
            counters[MISSED] = counters.get(MISSED, 0) + 1
    return history


def deck_records(history: History, deck: str) -> list[CardRecord]:
    """Return one record per card in ``deck``, weakest cards first.

    Cards are sorted by accuracy (low to high), then by front text, so the
    cards that need practice are at the top of the table.
    """
    records = [
        CardRecord(
            front=front,
            seen=counters.get(SEEN, 0),
            missed=counters.get(MISSED, 0),
        )
        for front, counters in history.get(deck, {}).items()
    ]
    return sorted(records, key=lambda r: (r.accuracy, r.front.casefold()))
