"""Tests for the quiz strategies, the factory and session scoring."""

from __future__ import annotations

import random

import pytest

from models import Flashcard
from quiz_engine import (
    MODE_REGISTRY,
    AdaptiveMode,
    ModeOptions,
    QuizMode,
    QuizSession,
    RandomMode,
    SequentialMode,
    SessionStats,
    available_modes,
    create_quiz_mode,
    is_correct,
    normalize_answer,
)


def drain(mode: QuizMode) -> list[str]:
    """Return the fronts of all cards a mode gives, answering each correctly."""
    fronts = []
    while (card := mode.next_card()) is not None:
        fronts.append(card.front)
        mode.record_answer(card, True)
    return fronts


# ---- Required scenarios ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected_class"),
    [
        ("sequential", SequentialMode),
        ("random", RandomMode),
        ("adaptive", AdaptiveMode),
        ("  Adaptive ", AdaptiveMode),
    ],
)
def test_quiz_mode_factory(
    cards: list[Flashcard], name: str, expected_class: type[QuizMode]
) -> None:
    mode = create_quiz_mode(name, cards)

    assert type(mode) is expected_class
    assert isinstance(mode, QuizMode)


def test_adaptive_mode_behavior(cards: list[Flashcard]) -> None:
    """A missed card comes back later in the same quiz until it is right."""
    mode = AdaptiveMode(cards, retry_gap=2)
    asked = []
    missed_once = False
    while (card := mode.next_card()) is not None:
        asked.append(card.front)
        correct = not (card.front == "Q1" and not missed_once)
        if card.front == "Q1":
            missed_once = True
        mode.record_answer(card, correct)

    # Q1 is missed first, then asked again after two other cards.
    assert asked == ["Q1", "Q2", "Q3", "Q1", "Q4"]


# ---- Factory --------------------------------------------------------------


def test_factory_rejects_unknown_mode(cards: list[Flashcard]) -> None:
    with pytest.raises(ValueError, match="Unknown quiz mode 'spaced'"):
        create_quiz_mode("spaced", cards)


def test_factory_passes_options_to_the_mode_that_needs_them(
    cards: list[Flashcard],
) -> None:
    options = ModeOptions(past_misses={"Q3": 2}, rng=random.Random(7))

    adaptive = create_quiz_mode("adaptive", cards, options)
    rand = create_quiz_mode("random", cards, options)

    assert drain(adaptive)[0] == "Q3"
    expected = [c.front for c in cards]
    random.Random(7).shuffle(expected)
    assert drain(rand) == expected


def test_available_modes_matches_registry() -> None:
    assert available_modes() == ["sequential", "random", "adaptive"]


def test_new_mode_needs_only_a_registry_entry(
    cards: list[Flashcard], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Factory is open for extension: no factory code change is needed."""

    class ReverseMode(SequentialMode):
        name = "reverse"

        def _build_order(self) -> list[Flashcard]:
            return list(reversed(self._cards))

    monkeypatch.setitem(MODE_REGISTRY, "reverse", ReverseMode)

    assert drain(create_quiz_mode("reverse", cards)) == ["Q4", "Q3", "Q2", "Q1"]


def test_quiz_mode_needs_cards() -> None:
    with pytest.raises(ValueError, match="at least one card"):
        SequentialMode([])


# ---- Sequential and random -----------------------------------------------


def test_sequential_mode_keeps_file_order(cards: list[Flashcard]) -> None:
    mode = SequentialMode(cards)

    assert drain(mode) == ["Q1", "Q2", "Q3", "Q4"]
    assert mode.next_card() is None


def test_sequential_mode_ignores_wrong_answers(cards: list[Flashcard]) -> None:
    mode = SequentialMode(cards)
    asked = []
    while (card := mode.next_card()) is not None:
        asked.append(card.front)
        mode.record_answer(card, False)

    assert asked == ["Q1", "Q2", "Q3", "Q4"]


def test_random_mode_asks_every_card_once(cards: list[Flashcard]) -> None:
    fronts = drain(RandomMode(cards, rng=random.Random(1)))

    assert sorted(fronts) == ["Q1", "Q2", "Q3", "Q4"]


def test_random_mode_is_repeatable_with_a_seed(cards: list[Flashcard]) -> None:
    first = drain(RandomMode(cards, rng=random.Random(42)))
    second = drain(RandomMode(cards, rng=random.Random(42)))

    assert first == second


def test_random_mode_does_not_change_the_input_list(cards: list[Flashcard]) -> None:
    original = list(cards)
    drain(RandomMode(cards, rng=random.Random(3)))

    assert cards == original


def test_random_mode_without_rng_still_works(cards: list[Flashcard]) -> None:
    assert len(drain(RandomMode(cards))) == 4


# ---- Adaptive -------------------------------------------------------------


def test_adaptive_puts_past_misses_first(cards: list[Flashcard]) -> None:
    mode = AdaptiveMode(cards, past_misses={"Q4": 3, "Q2": 1})

    assert drain(mode) == ["Q4", "Q2", "Q1", "Q3"]


def test_adaptive_without_history_uses_file_order(cards: list[Flashcard]) -> None:
    assert drain(AdaptiveMode(cards)) == ["Q1", "Q2", "Q3", "Q4"]


def test_adaptive_stops_repeating_after_max_attempts(cards: list[Flashcard]) -> None:
    mode = AdaptiveMode(cards[:1], max_attempts=3)
    asked = 0
    while (card := mode.next_card()) is not None:
        asked += 1
        mode.record_answer(card, False)

    assert asked == 3


def test_adaptive_retry_gap_zero_repeats_at_once(cards: list[Flashcard]) -> None:
    mode = AdaptiveMode(cards[:2], retry_gap=0)
    first = mode.next_card()
    assert first is not None
    mode.record_answer(first, False)

    assert mode.next_card() == first


def test_adaptive_retry_near_end_goes_to_back_of_queue(
    cards: list[Flashcard],
) -> None:
    mode = AdaptiveMode(cards[:2], retry_gap=5)
    first = mode.next_card()
    assert first is not None
    mode.record_answer(first, False)

    assert [mode.next_card(), mode.next_card()] == [cards[1], cards[0]]


@pytest.mark.parametrize(
    ("retry_gap", "max_attempts", "message"),
    [(-1, 3, "retry_gap"), (2, 0, "max_attempts")],
)
def test_adaptive_rejects_bad_settings(
    cards: list[Flashcard], retry_gap: int, max_attempts: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AdaptiveMode(cards, retry_gap=retry_gap, max_attempts=max_attempts)


# ---- Answer checking ------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Domain Name System", True),
        ("domain name system", True),
        ("  DOMAIN   name system ", True),
        ("Domain Name", False),
        ("", False),
    ],
)
def test_is_correct_ignores_case_and_spacing(answer: str, expected: bool) -> None:
    assert is_correct(Flashcard("DNS", "Domain Name System"), answer) is expected


def test_normalize_answer_handles_unicode_case() -> None:
    assert normalize_answer("STRASSE") == normalize_answer("straße")


# ---- Session and statistics ----------------------------------------------


def test_session_stats_start_empty() -> None:
    stats = SessionStats()

    assert (stats.total, stats.correct, stats.incorrect) == (0, 0, 0)
    assert stats.accuracy == 0.0


def test_session_stats_list_each_missed_card_once() -> None:
    stats = SessionStats()
    card = Flashcard("Q", "A")
    stats.record(card, False)
    stats.record(card, False)
    stats.record(card, True)

    assert stats.missed == [card]
    assert stats.total == 3
    assert stats.accuracy == pytest.approx(100 / 3)


def test_session_scores_answers(cards: list[Flashcard]) -> None:
    session = QuizSession(SequentialMode(cards))
    session.next_card()
    assert session.answer("a1") is True
    session.next_card()
    assert session.answer("wrong") is False

    assert session.stats.total == 2
    assert session.stats.missed == [cards[1]]


def test_session_limit_stops_early(cards: list[Flashcard]) -> None:
    session = QuizSession(SequentialMode(cards), limit=2)
    asked = 0
    while session.next_card() is not None:
        session.answer("x")
        asked += 1

    assert asked == 2


def test_session_rejects_bad_limit(cards: list[Flashcard]) -> None:
    with pytest.raises(ValueError, match="limit"):
        QuizSession(SequentialMode(cards), limit=0)


def test_session_answer_without_card_raises(cards: list[Flashcard]) -> None:
    session = QuizSession(SequentialMode(cards))

    with pytest.raises(RuntimeError, match="No card"):
        session.answer("x")


def test_session_cannot_answer_same_card_twice(cards: list[Flashcard]) -> None:
    session = QuizSession(SequentialMode(cards))
    session.next_card()
    session.answer("A1")

    with pytest.raises(RuntimeError):
        session.answer("A1")
