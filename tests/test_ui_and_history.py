"""Tests for the terminal UI helpers and the history counters."""

from __future__ import annotations

import io

import pytest

from models import Flashcard
from quiz_engine import QuizSession, SequentialMode, SessionStats
from tests.conftest import scripted_input
from ui import (
    Palette,
    QuizUI,
    format_card_records,
    format_summary,
    shorten,
    supports_color,
)
from utils.history import CardRecord, deck_records, past_misses, record_answers

GREEN = "\033[32m"
RED = "\033[31m"


class FakeTTY(io.StringIO):
    """A text stream that says it is a terminal."""

    def isatty(self) -> bool:
        return True


def run_ui(
    cards: list[Flashcard], answers: list[str], color: bool = False
) -> tuple[str, bool, SessionStats]:
    """Run a sequential quiz with scripted answers and return the output."""
    out = io.StringIO()
    ui = QuizUI(scripted_input(answers), out, Palette(enabled=color))
    result = ui.run(QuizSession(SequentialMode(cards)), "test deck")
    return out.getvalue(), result.stopped_early, result.stats


# ---- Colors ---------------------------------------------------------------


def test_palette_disabled_returns_plain_text() -> None:
    palette = Palette(enabled=False)

    assert palette.green("ok") == "ok"
    assert palette.red("no") == "no"
    assert palette.bold("hi") == "hi"


def test_palette_enabled_adds_ansi_codes() -> None:
    palette = Palette(enabled=True)

    assert palette.green("ok") == f"{GREEN}ok\033[0m"
    assert palette.red("no").startswith(RED)


def test_supports_color_on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")

    assert supports_color(FakeTTY()) is True
    assert supports_color(io.StringIO()) is False


@pytest.mark.parametrize(("name", "value"), [("NO_COLOR", "1"), ("TERM", "dumb")])
def test_supports_color_respects_environment(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv(name, value)

    assert supports_color(FakeTTY()) is False


# ---- Quiz loop ------------------------------------------------------------


def test_ui_shows_green_for_correct_and_red_for_incorrect(
    cards: list[Flashcard],
) -> None:
    output, stopped, stats = run_ui(cards[:2], ["A1", "nope"], color=True)

    assert f"{GREEN}Correct!" in output
    assert f"{RED}Incorrect. The answer is: A2" in output
    assert stopped is False
    assert stats.total == 2


@pytest.mark.parametrize("command", ["exit", "EXIT", " quit "])
def test_ui_exit_command_stops_quiz(cards: list[Flashcard], command: str) -> None:
    output, stopped, stats = run_ui(cards, ["A1", command])

    assert stopped is True
    assert stats.total == 1
    assert "Quiz stopped." in output


def test_ui_end_of_input_stops_quiz(cards: list[Flashcard]) -> None:
    output, stopped, stats = run_ui(cards, ["A1"])

    assert stopped is True
    assert stats.total == 1


def test_ui_ctrl_c_stops_quiz_without_traceback(cards: list[Flashcard]) -> None:
    def interrupt(prompt: str) -> str:
        raise KeyboardInterrupt

    out = io.StringIO()
    result = QuizUI(interrupt, out, Palette(False)).run(
        QuizSession(SequentialMode(cards)), "deck"
    )

    assert result.stopped_early is True
    assert "Quiz stopped." in out.getvalue()


def test_ui_numbers_questions_and_shows_title(cards: list[Flashcard]) -> None:
    output, _, _ = run_ui(cards[:2], ["A1", "A2"])

    assert "Flashcard Quizzer - test deck" in output
    assert "Q1: Q1" in output
    assert "Q2: Q2" in output


# ---- Summary tables -------------------------------------------------------


def test_summary_shows_totals_accuracy_and_missed_terms() -> None:
    stats = SessionStats()
    stats.record(Flashcard("API", "Application Programming Interface"), True)
    stats.record(Flashcard("DNS", "Domain Name System"), False)

    text = format_summary(stats, Palette(False))

    assert "Total Questions  2" in text
    assert "Accuracy         50.0%" in text
    assert "DNS: Domain Name System" in text


def test_summary_with_no_misses_congratulates() -> None:
    stats = SessionStats()
    stats.record(Flashcard("API", "x"), True)

    assert "No missed terms" in format_summary(stats, Palette(False))


def test_summary_with_no_questions_has_no_missed_section() -> None:
    text = format_summary(SessionStats(), Palette(False))

    assert "Total Questions  0" in text
    assert "Missed" not in text


def test_card_records_table_and_empty_message() -> None:
    records = [CardRecord("API", seen=4, missed=1)]

    text = format_card_records(records, Palette(False))

    assert "API" in text and "75%" in text
    assert "No statistics" in format_card_records([], Palette(False))


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("short", 10, "short"),
        ("a long question here", 10, "a long..."),
        ("abc", 2, "..."),
    ],
)
def test_shorten(text: str, width: int, expected: str) -> None:
    assert shorten(text, width) == expected


# ---- History counters -----------------------------------------------------


def test_record_answers_counts_seen_and_missed() -> None:
    api, dns = Flashcard("API", "x"), Flashcard("DNS", "y")
    history = record_answers({}, "deck", [(api, False), (api, True), (dns, True)])

    assert history == {
        "deck": {"API": {"seen": 2, "missed": 1}, "DNS": {"seen": 1, "missed": 0}}
    }


def test_record_answers_adds_to_existing_history() -> None:
    history = {"deck": {"API": {"seen": 3, "missed": 2}}}
    record_answers(history, "deck", [(Flashcard("API", "x"), False)])

    assert history["deck"]["API"] == {"seen": 4, "missed": 3}


def test_past_misses_reads_one_deck_only() -> None:
    history = {
        "a": {"API": {"seen": 2, "missed": 2}},
        "b": {"DNS": {"seen": 1, "missed": 1}},
    }

    assert past_misses(history, "a") == {"API": 2}
    assert past_misses(history, "unknown") == {}


def test_deck_records_sort_weakest_first() -> None:
    history = {
        "d": {
            "good": {"seen": 2, "missed": 0},
            "bad": {"seen": 2, "missed": 2},
            "mid": {"seen": 2, "missed": 1},
        }
    }

    assert [r.front for r in deck_records(history, "d")] == ["bad", "mid", "good"]


def test_card_record_accuracy_with_no_answers() -> None:
    assert CardRecord("x", seen=0, missed=0).accuracy == 0.0
