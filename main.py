"""Entry point for the Flashcard Quizzer CLI.

Examples::

    python main.py --help
    python main.py --mode sequential --file data/glossary.json
    python main.py -m adaptive -f data/python_basics.json --stats
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from models import Flashcard
from quiz_engine import ModeOptions, QuizSession, available_modes, create_quiz_mode
from ui import Palette, QuizUI, format_card_records, format_summary, supports_color
from utils.file_handler import (
    FlashcardLoadError,
    History,
    HistoryError,
    load_flashcards,
    load_history,
    save_flashcards,
    save_history,
)
from utils.history import deck_records, past_misses, record_answers

DEFAULT_HISTORY_FILE = ".flashcard_history.json"

#: Exit codes. 130 is the shell convention for a stop by Ctrl+C.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130

logger = logging.getLogger("flashcard_quizzer")


def positive_int(text: str) -> int:
    """argparse type: accept only whole numbers of 1 or more."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number.")
    if value < 1:
        raise argparse.ArgumentTypeError("the value must be 1 or more.")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser with all supported flags."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Quiz yourself on flashcards from a JSON deck.",
        epilog='During a quiz, type "exit" or press Ctrl+C to stop.',
    )
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        type=Path,
        help="path to the JSON deck, for example data/glossary.json",
    )
    parser.add_argument(
        "-m",
        "--mode",
        default="sequential",
        type=str.lower,
        choices=available_modes(),
        help="order of the questions (default: %(default)s)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="after the quiz, show lifetime statistics for each card",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=positive_int,
        metavar="N",
        help="ask at most N questions",
    )
    parser.add_argument(
        "--export-missed",
        type=Path,
        metavar="PATH",
        help="save the cards you missed as a new deck at PATH",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path(DEFAULT_HISTORY_FILE),
        metavar="PATH",
        help="file that stores results between sessions (default: %(default)s)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="do not read or write the history file",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="seed for random mode, to repeat the same order",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="show plain text with no colors",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show log messages about what the program does",
    )
    return parser


def configure_logging(verbose: bool, stream: TextIO) -> None:
    """Send log messages to ``stream``: INFO and up if verbose, else WARNING."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=stream,
        force=True,
    )


def main(
    argv: Sequence[str] | None = None,
    input_fn: Callable[[str], str] = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the CLI and return the process exit code.

    The input function and streams are arguments so tests can run a full
    session. The real program uses the defaults.
    """
    out = out or sys.stdout
    err = err or sys.stderr
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose, err)
    palette = Palette(enabled=not args.no_color and supports_color(out))

    try:
        return _run(args, input_fn, out, err, palette)
    except KeyboardInterrupt:
        print("\nStopped.", file=err)
        return EXIT_INTERRUPTED


def _run(
    args: argparse.Namespace,
    input_fn: Callable[[str], str],
    out: TextIO,
    err: TextIO,
    palette: Palette,
) -> int:
    """Do the work of :func:`main` after the arguments are parsed."""
    try:
        cards = load_flashcards(args.file)
    except FlashcardLoadError as exc:
        print(f"Error: {exc}", file=err)
        return EXIT_ERROR

    deck = args.file.stem
    history: History = {}
    use_history = not args.no_history
    if use_history:
        try:
            history = load_history(args.history)
        except HistoryError as exc:
            # Do not stop the quiz, and do not overwrite a file we cannot read.
            print(f"Warning: {exc}", file=err)
            use_history = False

    options = ModeOptions(
        past_misses=past_misses(history, deck),
        rng=random.Random(args.seed) if args.seed is not None else None,
    )
    mode = create_quiz_mode(args.mode, cards, options)
    session = QuizSession(mode, limit=args.limit)
    title = f"{deck} ({len(cards)} cards, {args.mode} mode)"

    result = QuizUI(input_fn, out, palette).run(session, title)
    stats = result.stats

    print(file=out)
    print(format_summary(stats, palette), file=out)

    record_answers(history, deck, stats.answers)
    if use_history and stats.answers:
        try:
            save_history(history, args.history)
            logger.info("Saved history to %s", args.history)
        except HistoryError as exc:
            print(f"Warning: {exc}", file=err)

    if args.stats:
        print(file=out)
        print(format_card_records(deck_records(history, deck), palette), file=out)

    if args.export_missed is not None:
        return _export_missed(stats.missed, args.export_missed, out, err)
    return EXIT_OK


def _export_missed(
    missed: Sequence[Flashcard], path: Path, out: TextIO, err: TextIO
) -> int:
    """Save missed cards as a new deck and report the result."""
    if not missed:
        print("No missed cards to export.", file=out)
        return EXIT_OK
    try:
        save_flashcards(list(missed), path)
    except FlashcardLoadError as exc:
        print(f"Error: {exc}", file=err)
        return EXIT_ERROR
    print(f"Saved {len(missed)} missed card(s) to {path}.", file=out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
