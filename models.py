"""Core data types shared by the loader, the quiz engine and the UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Flashcard:
    """One flashcard: the prompt on the front and the answer on the back.

    The dataclass is frozen so a card can be used as a dictionary key and so
    no strategy can change a card by accident during a quiz.
    """

    front: str
    back: str
