"""Quiz engine: card-selection strategies, a factory and session scoring.

Design patterns
---------------
* **Strategy** - :class:`QuizMode` is the strategy interface. Each subclass
  is one algorithm for choosing the next card. :class:`QuizSession` uses a
  strategy without knowing which one it is.
* **Factory** - :func:`create_quiz_mode` turns the ``--mode`` string into a
  strategy object. A new mode (for example spaced repetition) needs one new
  subclass and one new line in :data:`MODE_REGISTRY`. Nothing else changes.

This module has no ``print`` or ``input`` calls, so all of it can be tested
without a terminal.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from models import Flashcard


def normalize_answer(text: str) -> str:
    """Return ``text`` in a form that ignores case and extra whitespace.

    ``"  Domain   name SYSTEM "`` and ``"domain name system"`` give the same
    result, so the user is not marked wrong for a stray space.
    """
    return " ".join(text.split()).casefold()


def is_correct(card: Flashcard, answer: str) -> bool:
    """Return True if ``answer`` matches the back of ``card``."""
    return normalize_answer(answer) == normalize_answer(card.back)


# --------------------------------------------------------------------------
# Strategy interface and concrete strategies
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModeOptions:
    """Optional inputs a strategy may use. Each strategy takes what it needs.

    Attributes:
        past_misses: Miss counts per card front, from the history file.
        rng: Random generator. Tests pass a seeded one for a repeatable order.
    """

    past_misses: Mapping[str, int] = field(default_factory=dict)
    rng: random.Random | None = None


class QuizMode(ABC):
    """Strategy interface: decides which card the user sees next."""

    #: Name used on the command line and in the factory registry.
    name: str = ""

    def __init__(self, cards: Sequence[Flashcard]) -> None:
        if not cards:
            raise ValueError("A quiz needs at least one card.")
        self._cards: list[Flashcard] = list(cards)

    @classmethod
    def from_options(cls, cards: Sequence[Flashcard], options: ModeOptions) -> QuizMode:
        """Build the strategy from shared options. The factory calls this.

        Subclasses that need an option override this method. Thus the
        factory never needs to know which options a mode uses.
        """
        return cls(cards)

    @abstractmethod
    def next_card(self) -> Flashcard | None:
        """Return the next card to ask, or None when the quiz is finished."""

    def record_answer(self, card: Flashcard, correct: bool) -> None:
        """Tell the strategy how the user answered ``card``.

        The default does nothing. Strategies that react to answers, such as
        :class:`AdaptiveMode`, override this method.
        """


class _FixedOrderMode(QuizMode):
    """Base for strategies that ask each card once in an order set at start."""

    def __init__(self, cards: Sequence[Flashcard]) -> None:
        super().__init__(cards)
        self._order: list[Flashcard] = self._build_order()
        self._position = 0

    @abstractmethod
    def _build_order(self) -> list[Flashcard]:
        """Return the cards in the order this strategy asks them."""

    def next_card(self) -> Flashcard | None:
        if self._position >= len(self._order):
            return None
        card = self._order[self._position]
        self._position += 1
        return card


class SequentialMode(_FixedOrderMode):
    """Ask each card once, in file order: 1, 2, ..., N."""

    name = "sequential"

    def _build_order(self) -> list[Flashcard]:
        return list(self._cards)


class RandomMode(_FixedOrderMode):
    """Ask each card once, in a shuffled order."""

    name = "random"

    def __init__(
        self, cards: Sequence[Flashcard], rng: random.Random | None = None
    ) -> None:
        # Set the generator before super().__init__(), because the base
        # class calls _build_order() and _build_order() uses the generator.
        self._rng = rng or random.Random()
        super().__init__(cards)

    @classmethod
    def from_options(cls, cards: Sequence[Flashcard], options: ModeOptions) -> QuizMode:
        return cls(cards, rng=options.rng)

    def _build_order(self) -> list[Flashcard]:
        order = list(self._cards)
        self._rng.shuffle(order)
        return order


class AdaptiveMode(QuizMode):
    """Prioritize cards the user gets wrong.

    The algorithm:

    1. At the start, cards with more past misses (from the history file) come
       first. Cards with equal misses keep their file order.
    2. When the user misses a card, the card goes back into the queue
       :attr:`retry_gap` positions later, so it comes back soon but not
       immediately.
    3. The quiz ends when every card has had one correct answer, or when a
       card has been missed :attr:`max_attempts` times. The limit stops an
       endless loop on a card the user cannot answer.
    """

    name = "adaptive"

    def __init__(
        self,
        cards: Sequence[Flashcard],
        past_misses: Mapping[str, int] | None = None,
        retry_gap: int = 2,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(cards)
        if retry_gap < 0:
            raise ValueError("retry_gap must be zero or more.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be one or more.")
        self.retry_gap = retry_gap
        self.max_attempts = max_attempts
        misses = past_misses or {}
        # sorted() is stable, so cards with equal misses keep file order.
        ordered = sorted(self._cards, key=lambda c: -misses.get(c.front, 0))
        self._queue: deque[Flashcard] = deque(ordered)
        self._attempts: dict[Flashcard, int] = {}

    @classmethod
    def from_options(cls, cards: Sequence[Flashcard], options: ModeOptions) -> QuizMode:
        return cls(cards, past_misses=options.past_misses)

    def next_card(self) -> Flashcard | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def record_answer(self, card: Flashcard, correct: bool) -> None:
        self._attempts[card] = self._attempts.get(card, 0) + 1
        if correct or self._attempts[card] >= self.max_attempts:
            return
        position = min(self.retry_gap, len(self._queue))
        self._queue.insert(position, card)


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

#: Maps each ``--mode`` value to its strategy class. To add a mode, write a
#: QuizMode subclass and add one line here.
MODE_REGISTRY: dict[str, type[QuizMode]] = {
    SequentialMode.name: SequentialMode,
    RandomMode.name: RandomMode,
    AdaptiveMode.name: AdaptiveMode,
}


def available_modes() -> list[str]:
    """Return the mode names the factory accepts, in a stable order."""
    return list(MODE_REGISTRY)


def create_quiz_mode(
    mode_name: str,
    cards: Sequence[Flashcard],
    options: ModeOptions | None = None,
) -> QuizMode:
    """Factory: build the strategy object for ``mode_name``.

    Args:
        mode_name: One of :func:`available_modes`. Case is ignored.
        cards: The deck to quiz on.
        options: Optional inputs such as past misses or a seeded generator.

    Raises:
        ValueError: If ``mode_name`` is not a known mode, or ``cards`` is
            empty.
    """
    key = mode_name.strip().lower()
    mode_class = MODE_REGISTRY.get(key)
    if mode_class is None:
        choices = ", ".join(available_modes())
        raise ValueError(f"Unknown quiz mode '{mode_name}'. Choose one of: {choices}.")
    return mode_class.from_options(cards, options or ModeOptions())


# --------------------------------------------------------------------------
# Session and statistics
# --------------------------------------------------------------------------


@dataclass
class SessionStats:
    """Score for one quiz session."""

    total: int = 0
    correct: int = 0
    missed: list[Flashcard] = field(default_factory=list)
    answers: list[tuple[Flashcard, bool]] = field(default_factory=list)

    @property
    def incorrect(self) -> int:
        """Number of wrong answers."""
        return self.total - self.correct

    @property
    def accuracy(self) -> float:
        """Percentage of correct answers, from 0.0 to 100.0."""
        if self.total == 0:
            return 0.0
        return 100.0 * self.correct / self.total

    def record(self, card: Flashcard, correct: bool) -> None:
        """Add one answer to the score."""
        self.total += 1
        self.answers.append((card, correct))
        if correct:
            self.correct += 1
        elif card not in self.missed:
            self.missed.append(card)


class QuizSession:
    """Runs one quiz: gets cards from a strategy and scores the answers.

    The session does not do input or output. The UI layer asks for the
    next card, shows it, reads the answer and passes it to :meth:`answer`.
    """

    def __init__(self, mode: QuizMode, limit: int | None = None) -> None:
        if limit is not None and limit < 1:
            raise ValueError("limit must be one or more.")
        self.mode = mode
        self.limit = limit
        self.stats = SessionStats()
        self._current: Flashcard | None = None

    def next_card(self) -> Flashcard | None:
        """Return the next card, or None when the quiz is over."""
        if self.limit is not None and self.stats.total >= self.limit:
            self._current = None
            return None
        self._current = self.mode.next_card()
        return self._current

    def answer(self, response: str) -> bool:
        """Score ``response`` against the current card and return the result.

        Raises:
            RuntimeError: If no card is waiting for an answer.
        """
        if self._current is None:
            raise RuntimeError("No card is waiting for an answer.")
        card = self._current
        correct = is_correct(card, response)
        self.stats.record(card, correct)
        self.mode.record_answer(card, correct)
        self._current = None
        return correct
