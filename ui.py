"""Terminal user interface: prompts, colored feedback and summary tables.

The UI gets its input function and output stream as arguments. The real
program passes :func:`input` and ``sys.stdout``. Tests pass a scripted
function and a :class:`io.StringIO`, so a full quiz runs without a terminal.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from quiz_engine import QuizSession, SessionStats
from utils.history import CardRecord

#: Long card fronts are cut to this length in the --stats table.
MAX_CARD_COLUMN = 48

#: Answers that end the quiz early. Case is ignored.
EXIT_COMMANDS = frozenset({"exit", "quit"})

_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def supports_color(stream: TextIO) -> bool:
    """Return True if ``stream`` is a terminal that should get ANSI colors.

    Colors are off when the output is a file or pipe, when ``NO_COLOR`` is
    set (see https://no-color.org) or when ``TERM`` is ``dumb``.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


@dataclass(frozen=True)
class Palette:
    """Wraps text in ANSI color codes, or returns it unchanged if disabled."""

    enabled: bool

    def _wrap(self, code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if self.enabled else text

    def green(self, text: str) -> str:
        """Return ``text`` in green."""
        return self._wrap(_GREEN, text)

    def red(self, text: str) -> str:
        """Return ``text`` in red."""
        return self._wrap(_RED, text)

    def bold(self, text: str) -> str:
        """Return ``text`` in bold."""
        return self._wrap(_BOLD, text)


@dataclass
class QuizResult:
    """What happened in a quiz run."""

    stats: SessionStats
    stopped_early: bool


class QuizUI:
    """Runs the question-and-answer loop in a terminal."""

    def __init__(
        self,
        input_fn: Callable[[str], str],
        out: TextIO,
        palette: Palette,
    ) -> None:
        self._input = input_fn
        self._out = out
        self._palette = palette

    def _say(self, text: str = "") -> None:
        print(text, file=self._out)

    def run(self, session: QuizSession, title: str) -> QuizResult:
        """Ask cards until the session ends or the user quits.

        The user quits with "exit", "quit", Ctrl+C or Ctrl+D. All of them
        end the quiz cleanly, and the score so far is kept.
        """
        p = self._palette
        self._say(p.bold(f"Flashcard Quizzer - {title}"))
        self._say('Type your answer and press Enter. Type "exit" to stop.')

        number = 0
        while (card := session.next_card()) is not None:
            number += 1
            self._say()
            self._say(p.bold(f"Q{number}: {card.front}"))
            try:
                response = self._input("> ")
            except (KeyboardInterrupt, EOFError):
                self._say()
                self._say("Quiz stopped.")
                return QuizResult(session.stats, stopped_early=True)

            if response.strip().lower() in EXIT_COMMANDS:
                self._say("Quiz stopped.")
                return QuizResult(session.stats, stopped_early=True)

            if session.answer(response):
                self._say(p.green("Correct!"))
            else:
                self._say(p.red(f"Incorrect. The answer is: {card.back}"))

        return QuizResult(session.stats, stopped_early=False)


def format_summary(stats: SessionStats, palette: Palette) -> str:
    """Return the end-of-quiz summary table as text."""
    rows = [
        ("Total Questions", str(stats.total)),
        ("Correct", str(stats.correct)),
        ("Incorrect", str(stats.incorrect)),
        ("Accuracy", f"{stats.accuracy:.1f}%"),
    ]
    lines = [palette.bold("Session Summary"), *_table(("Metric", "Value"), rows)]

    if stats.missed:
        lines.append("")
        lines.append(palette.bold("Missed terms"))
        lines.extend(
            palette.red(f"  - {card.front}: {card.back}") for card in stats.missed
        )
    elif stats.total:
        lines.append("")
        lines.append(palette.green("No missed terms. Well done!"))
    return "\n".join(lines)


def format_card_records(records: Sequence[CardRecord], palette: Palette) -> str:
    """Return the lifetime per-card statistics table shown by ``--stats``."""
    if not records:
        return "No statistics recorded for this deck yet."
    rows = [
        (
            shorten(r.front, MAX_CARD_COLUMN),
            str(r.seen),
            str(r.missed),
            f"{r.accuracy:.0f}%",
        )
        for r in records
    ]
    header = palette.bold("Lifetime statistics (weakest cards first)")
    return "\n".join([header, *_table(("Card", "Asked", "Missed", "Accuracy"), rows)])


def shorten(text: str, width: int) -> str:
    """Return ``text`` cut to ``width`` characters, ending in "..." if cut."""
    if len(text) <= width:
        return text
    return text[: max(width - 3, 0)].rstrip() + "..."


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Return lines for a simple left-aligned text table with a rule line."""
    widths = [len(h) for h in header]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths)).rstrip()

    rule = "  ".join("-" * w for w in widths)
    return [fmt(header), rule, *(fmt(row) for row in rows)]
