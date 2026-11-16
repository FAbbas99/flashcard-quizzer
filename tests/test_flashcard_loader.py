"""Tests for loading, validating and saving decks and history files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from models import Flashcard
from tests.conftest import DeckWriter
from utils import file_handler
from utils.file_handler import (
    FlashcardLoadError,
    HistoryError,
    json_type_name,
    load_flashcards,
    load_history,
    save_flashcards,
    save_history,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---- Required scenarios ---------------------------------------------------


def test_load_valid_flashcards_array(write_deck: DeckWriter) -> None:
    path = write_deck(
        [{"front": "API", "back": "Application Programming Interface"}]
        + [{"front": "DNS", "back": "Domain Name System"}]
    )

    cards = load_flashcards(path)

    assert cards == [
        Flashcard("API", "Application Programming Interface"),
        Flashcard("DNS", "Domain Name System"),
    ]


def test_load_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('[{"front": "API", "back": "x"},', encoding="utf-8")

    with pytest.raises(FlashcardLoadError, match=r"not valid JSON.*line 1"):
        load_flashcards(path)


def test_load_missing_required_field(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "API", "back": "x"}, {"front": "DNS"}])

    with pytest.raises(FlashcardLoadError, match=r'Card 2 .* missing the "back"'):
        load_flashcards(path)


# ---- Supported formats and real decks ------------------------------------


def test_load_object_format(write_deck: DeckWriter) -> None:
    path = write_deck({"cards": [{"front": "def", "back": "keyword"}]})

    assert load_flashcards(path) == [Flashcard("def", "keyword")]


@pytest.mark.parametrize(
    ("filename", "count"),
    [("glossary.json", 10), ("python_basics.json", 8), ("server_acronyms.json", 12)],
)
def test_sample_decks_load(filename: str, count: int) -> None:
    assert len(load_flashcards(DATA_DIR / filename)) == count


def test_load_accepts_string_path(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "a", "back": "b"}])

    assert load_flashcards(str(path)) == [Flashcard("a", "b")]


def test_load_strips_whitespace_and_ignores_extra_keys(
    write_deck: DeckWriter,
) -> None:
    path = write_deck([{"front": "  API ", "back": " x\n", "hint": "ignored"}])

    assert load_flashcards(path) == [Flashcard("API", "x")]


def test_load_keeps_unicode(write_deck: DeckWriter) -> None:
    path = write_deck([{"front": "café", "back": "コーヒー"}])

    assert load_flashcards(path) == [Flashcard("café", "コーヒー")]


# ---- File-level errors ----------------------------------------------------


def test_load_missing_file_has_helpful_message(tmp_path: Path) -> None:
    with pytest.raises(FlashcardLoadError, match="was not found"):
        load_flashcards(tmp_path / "nope.json")


def test_load_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FlashcardLoadError, match="is not a file"):
        load_flashcards(tmp_path)


def test_load_non_utf8_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "binary.json"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(FlashcardLoadError, match="not a UTF-8"):
        load_flashcards(path)


def test_load_oversized_file_is_rejected(
    write_deck: DeckWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_deck([{"front": "a", "back": "b"}])
    monkeypatch.setattr(file_handler, "MAX_DECK_BYTES", 5)

    with pytest.raises(FlashcardLoadError, match="limit for a deck"):
        load_flashcards(path)


def test_load_unreadable_file_is_reported(
    write_deck: DeckWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_deck([{"front": "a", "back": "b"}])

    def deny(*args: Any, **kwargs: Any) -> str:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", deny)

    with pytest.raises(FlashcardLoadError, match="Permission denied"):
        load_flashcards(path)


# ---- Structure errors -----------------------------------------------------


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "contains no cards"),
        ({"cards": []}, "contains no cards"),
        ({"deck": []}, 'no "cards" key'),
        ({"cards": {"front": "a", "back": "b"}}, "must be an array.*not an object"),
        (None, "array of cards, not null"),
        ("text", "array of cards, not a string"),
        ([1], "Card 1 .* not a number"),
        ([["a", "b"]], "Card 1 .* not an array"),
        ([{"back": "b"}], 'missing the "front"'),
        ([{"front": "a", "back": ""}], 'empty or non-text "back"'),
        ([{"front": "a", "back": "   "}], 'empty or non-text "back"'),
        ([{"front": "a", "back": None}], 'empty or non-text "back"'),
        ([{"front": 42, "back": "b"}], 'empty or non-text "front"'),
    ],
)
def test_load_rejects_bad_structure(
    write_deck: DeckWriter, data: Any, message: str
) -> None:
    with pytest.raises(FlashcardLoadError, match=message):
        load_flashcards(write_deck(data))


def test_load_warns_about_duplicate_fronts(
    write_deck: DeckWriter, caplog: pytest.LogCaptureFixture
) -> None:
    path = write_deck([{"front": "API", "back": "a"}, {"front": "api", "back": "b"}])

    with caplog.at_level(logging.WARNING):
        cards = load_flashcards(path)

    assert len(cards) == 2
    assert "Duplicate card 'api'" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (True, "boolean"),
        (3, "number"),
        (2.5, "number"),
        ("s", "string"),
        ([], "array"),
        ({}, "object"),
        ((1,), "tuple"),
    ],
)
def test_json_type_name(value: Any, expected: str) -> None:
    assert json_type_name(value) == expected


# ---- Saving decks ---------------------------------------------------------


def test_save_flashcards_round_trip(tmp_path: Path) -> None:
    original = [Flashcard("API", "x"), Flashcard("café", "y")]
    path = save_flashcards(original, tmp_path / "out.json")

    assert load_flashcards(path) == original


def test_save_flashcards_reports_write_error(tmp_path: Path) -> None:
    with pytest.raises(FlashcardLoadError, match="Could not write"):
        save_flashcards([Flashcard("a", "b")], tmp_path / "no_dir" / "out.json")


# ---- History files --------------------------------------------------------


def test_history_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_history(tmp_path / "none.json") == {}


def test_history_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    history = {"deck": {"API": {"seen": 2, "missed": 1}}}

    save_history(history, path)

    assert load_history(path) == history


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"deck": []}',
        '{"deck": {"API": 3}}',
        '{"deck": {"API": {"seen": "two"}}}',
        '{"deck": {"API": {"seen": true}}}',
    ],
)
def test_history_rejects_bad_content(tmp_path: Path, content: str) -> None:
    path = tmp_path / "history.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(HistoryError, match="--no-history"):
        load_history(path)


def test_save_history_reports_write_error(tmp_path: Path) -> None:
    with pytest.raises(HistoryError, match="Could not write"):
        save_history({}, tmp_path / "no_dir" / "history.json")
