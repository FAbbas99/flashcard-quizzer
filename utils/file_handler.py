"""Read and write flashcard decks and quiz history as JSON.

Two deck formats are supported:

* Array format: ``[{"front": "...", "back": "..."}, ...]``
* Object format: ``{"cards": [{"front": "...", "back": "..."}, ...]}``

Every failure is raised as :class:`FlashcardLoadError` with a message that a
user can act on. The CLI catches that one exception type and prints the
message, so the user never sees a Python traceback.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from models import Flashcard

logger = logging.getLogger(__name__)

#: Decks larger than this are refused. A flashcard deck is small text; a very
#: large file is almost certainly the wrong file.
MAX_DECK_BYTES = 5 * 1024 * 1024

REQUIRED_FIELDS = ("front", "back")

#: Shape of the history file: deck name -> card front -> counter name -> value.
History = dict[str, dict[str, dict[str, int]]]


def json_type_name(value: Any) -> str:
    """Return the JSON name of a decoded value's type, for user messages.

    Python names such as ``NoneType`` or ``dict`` mean nothing to a user who
    wrote a JSON file, so messages use the JSON words instead.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


class FlashcardLoadError(Exception):
    """Raised when a deck file is missing, unreadable or has a bad structure."""


class HistoryError(Exception):
    """Raised when the quiz history file cannot be read or written."""


def load_flashcards(path: str | Path) -> list[Flashcard]:
    """Load and validate a flashcard deck from a JSON file.

    Args:
        path: Path to a JSON file in array format or object format.

    Returns:
        The cards in the order they appear in the file.

    Raises:
        FlashcardLoadError: If the file is missing, too large, not valid
            UTF-8 JSON, has the wrong structure, is empty, or contains a card
            without a non-empty ``front`` and ``back`` string.
    """
    deck_path = Path(path)
    raw_text = _read_deck_text(deck_path)

    try:
        data: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise FlashcardLoadError(
            f"'{deck_path}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc

    raw_cards = _extract_card_list(data, deck_path)
    cards = [
        _parse_card(item, index, deck_path)
        for index, item in enumerate(raw_cards, start=1)
    ]
    _warn_about_duplicates(cards, deck_path)
    logger.info("Loaded %d cards from %s", len(cards), deck_path)
    return cards


def _read_deck_text(deck_path: Path) -> str:
    """Return the text of a deck file after basic file-level checks."""
    if not deck_path.exists():
        raise FlashcardLoadError(
            f"Deck file '{deck_path}' was not found. Check the path and try again."
        )
    if not deck_path.is_file():
        raise FlashcardLoadError(f"'{deck_path}' is not a file.")
    size = deck_path.stat().st_size
    if size > MAX_DECK_BYTES:
        raise FlashcardLoadError(
            f"'{deck_path}' is {size} bytes. The limit for a deck is "
            f"{MAX_DECK_BYTES} bytes."
        )
    try:
        return deck_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FlashcardLoadError(
            f"'{deck_path}' is not a UTF-8 text file."
        ) from exc
    except OSError as exc:
        raise FlashcardLoadError(
            f"Could not read '{deck_path}': {exc.strerror}."
        ) from exc


def _extract_card_list(data: Any, deck_path: Path) -> list[Any]:
    """Return the list of raw card objects from either supported format."""
    if isinstance(data, dict):
        if "cards" not in data:
            raise FlashcardLoadError(
                f"'{deck_path}' is a JSON object but has no \"cards\" key. "
                'Use {"cards": [...]} or a plain list of cards.'
            )
        data = data["cards"]
        if not isinstance(data, list):
            raise FlashcardLoadError(
                f'The "cards" key in \'{deck_path}\' must be an array of cards, '
                f"not {_with_article(json_type_name(data))}."
            )

    if not isinstance(data, list):
        raise FlashcardLoadError(
            f"'{deck_path}' must contain an array of cards, "
            f"not {_with_article(json_type_name(data))}."
        )
    if not data:
        raise FlashcardLoadError(f"'{deck_path}' contains no cards.")
    return data


def _with_article(type_name: str) -> str:
    """Return ``type_name`` with "a" or "an" in front, or bare for null."""
    if type_name == "null":
        return "null"
    article = "an" if type_name[0] in "aeiou" else "a"
    return f"{article} {type_name}"


def _parse_card(item: Any, index: int, deck_path: Path) -> Flashcard:
    """Validate one raw card object and convert it to a :class:`Flashcard`."""
    if not isinstance(item, dict):
        raise FlashcardLoadError(
            f"Card {index} in '{deck_path}' must be an object with "
            f'"front" and "back", not {_with_article(json_type_name(item))}.'
        )

    values: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        if field not in item:
            raise FlashcardLoadError(
                f'Card {index} in \'{deck_path}\' is missing the "{field}" field.'
            )
        value = item[field]
        if not isinstance(value, str) or not value.strip():
            raise FlashcardLoadError(
                f'Card {index} in \'{deck_path}\' has an empty or non-text '
                f'"{field}" field.'
            )
        values[field] = value.strip()

    return Flashcard(front=values["front"], back=values["back"])


def _warn_about_duplicates(cards: list[Flashcard], deck_path: Path) -> None:
    """Log a warning for each front that appears more than once."""
    seen: set[str] = set()
    for card in cards:
        key = card.front.casefold()
        if key in seen:
            logger.warning("Duplicate card '%s' in %s", card.front, deck_path)
        seen.add(key)


def save_flashcards(cards: list[Flashcard], path: str | Path) -> Path:
    """Write cards to ``path`` in object format so they can be loaded again.

    Args:
        cards: The cards to write.
        path: Destination file. Parent directories must already exist.

    Returns:
        The path that was written.

    Raises:
        FlashcardLoadError: If the file cannot be written.
    """
    out_path = Path(path)
    payload = {"cards": [{"front": c.front, "back": c.back} for c in cards]}
    try:
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise FlashcardLoadError(
            f"Could not write '{out_path}': {exc.strerror}."
        ) from exc
    return out_path


def load_history(path: str | Path) -> History:
    """Load the quiz history file, or return an empty history if it is absent.

    Raises:
        HistoryError: If the file exists but is not a valid history file.
    """
    history_path = Path(path)
    if not history_path.exists():
        return {}
    try:
        data: Any = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoryError(
            f"History file '{history_path}' could not be read. "
            "Delete it or use --no-history."
        ) from exc
    if not _is_valid_history(data):
        raise HistoryError(
            f"History file '{history_path}' has an unexpected structure. "
            "Delete it or use --no-history."
        )
    result: History = data
    return result


def _is_valid_history(data: Any) -> bool:
    """Return True if ``data`` matches the :data:`History` shape."""
    if not isinstance(data, dict):
        return False
    for deck in data.values():
        if not isinstance(deck, dict):
            return False
        for counters in deck.values():
            if not isinstance(counters, dict):
                return False
            if not all(
                isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
                for k, v in counters.items()
            ):
                return False
    return True


def save_history(history: History, path: str | Path) -> None:
    """Write the quiz history file.

    Raises:
        HistoryError: If the file cannot be written.
    """
    history_path = Path(path)
    try:
        history_path.write_text(
            json.dumps(history, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise HistoryError(
            f"Could not write history file '{history_path}': {exc.strerror}."
        ) from exc
