"""End-to-end tests: run ``main()`` with scripted answers and real files."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import main as cli
from tests.conftest import DeckWriter, scripted_input

GLOSSARY = Path(__file__).resolve().parent.parent / "data" / "glossary.json"


def run_cli(args: list[str], answers: list[str] | None = None) -> tuple[int, str, str]:
    """Run the CLI and return (exit code, stdout text, stderr text)."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(args, scripted_input(answers or []), out, err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def three_card_deck(write_deck: DeckWriter) -> Path:
    return write_deck(
        {
            "cards": [
                {"front": "API", "back": "Application Programming Interface"},
                {"front": "DNS", "back": "Domain Name System"},
                {"front": "SSH", "back": "Secure Shell"},
            ]
        }
    )


# ---- Required scenario ----------------------------------------------------


def test_full_session(three_card_deck: Path, tmp_path: Path) -> None:
    """A user answers 3 questions (2 right, 1 wrong) and sees correct stats."""
    code, out, err = run_cli(
        ["-m", "sequential", "-f", str(three_card_deck), "--no-history"],
        ["application programming interface", "Domain Name Server", "SECURE SHELL"],
    )

    assert code == 0
    assert err == ""
    assert out.count("Correct!") == 2
    assert "Incorrect. The answer is: Domain Name System" in out
    assert "Total Questions  3" in out
    assert "Correct          2" in out
    assert "Incorrect        1" in out
    assert "Accuracy         66.7%" in out
    assert "DNS: Domain Name System" in out


# ---- Modes through the CLI -----------------------------------------------


def test_adaptive_session_repeats_missed_card(three_card_deck: Path) -> None:
    code, out, _ = run_cli(
        ["-m", "adaptive", "-f", str(three_card_deck), "--no-history"],
        [
            "wrong",
            "Domain Name System",
            "Secure Shell",
            "Application Programming Interface",
        ],
    )

    assert code == 0
    assert out.count("Q1: API") == 1
    assert "Q4: API" in out
    assert "Total Questions  4" in out


def test_random_mode_with_seed_is_repeatable(three_card_deck: Path) -> None:
    args = ["-m", "random", "--seed", "5", "-f", str(three_card_deck), "--no-history"]

    assert run_cli(args)[1] == run_cli(args)[1]


def test_mode_flag_is_case_insensitive(three_card_deck: Path) -> None:
    code, out, _ = run_cli(["-m", "SEQUENTIAL", "-f", str(three_card_deck)])

    assert code == 0
    assert "sequential mode" in out


def test_limit_flag_caps_questions(three_card_deck: Path) -> None:
    _, out, _ = run_cli(
        ["-f", str(three_card_deck), "--limit", "1", "--no-history"], ["x", "y"]
    )

    assert "Total Questions  1" in out


# ---- History, --stats and export -----------------------------------------


def test_history_drives_adaptive_order_in_next_session(
    three_card_deck: Path, tmp_path: Path
) -> None:
    history = tmp_path / "history.json"
    base = ["-f", str(three_card_deck), "--history", str(history)]

    run_cli([*base, "-m", "sequential"], ["Application Programming Interface", "no"])
    _, out, _ = run_cli([*base, "-m", "adaptive", "--stats"], [])

    assert "Q1: DNS" in out
    assert "Lifetime statistics" in out
    saved = json.loads(history.read_text(encoding="utf-8"))
    assert saved[three_card_deck.stem]["DNS"] == {"seen": 1, "missed": 1}


def test_stats_without_history_uses_this_session(three_card_deck: Path) -> None:
    _, out, _ = run_cli(["-f", str(three_card_deck), "--no-history", "--stats"], ["x"])

    assert "Lifetime statistics" in out
    assert "API" in out


def test_no_history_writes_no_file(
    three_card_deck: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    run_cli(["-f", str(three_card_deck), "--no-history"], ["x"])

    assert not (tmp_path / cli.DEFAULT_HISTORY_FILE).exists()


def test_corrupt_history_warns_and_is_not_overwritten(
    three_card_deck: Path, tmp_path: Path
) -> None:
    history = tmp_path / "history.json"
    history.write_text("{broken", encoding="utf-8")

    code, _, err = run_cli(
        ["-f", str(three_card_deck), "--history", str(history)], ["x"]
    )

    assert code == 0
    assert "Warning:" in err
    assert history.read_text(encoding="utf-8") == "{broken"


def test_history_write_failure_is_a_warning(
    three_card_deck: Path, tmp_path: Path
) -> None:
    history = tmp_path / "no_dir" / "history.json"

    code, _, err = run_cli(
        ["-f", str(three_card_deck), "--history", str(history)], ["x"]
    )

    assert code == 0
    assert "Could not write history" in err


def test_export_missed_writes_loadable_deck(
    three_card_deck: Path, tmp_path: Path
) -> None:
    target = tmp_path / "missed.json"

    code, out, _ = run_cli(
        ["-f", str(three_card_deck), "--no-history", "--export-missed", str(target)],
        ["x", "Domain Name System", "y"],
    )

    assert code == 0
    assert "Saved 2 missed card(s)" in out
    fronts = [c["front"] for c in json.loads(target.read_text("utf-8"))["cards"]]
    assert fronts == ["API", "SSH"]


def test_export_with_nothing_missed(three_card_deck: Path, tmp_path: Path) -> None:
    target = tmp_path / "missed.json"

    _, out, _ = run_cli(
        ["-f", str(three_card_deck), "--no-history", "--export-missed", str(target)],
        ["Application Programming Interface"],
    )

    assert "No missed cards to export." in out
    assert not target.exists()


def test_export_failure_returns_error(three_card_deck: Path, tmp_path: Path) -> None:
    target = tmp_path / "no_dir" / "missed.json"

    code, _, err = run_cli(
        ["-f", str(three_card_deck), "--no-history", "--export-missed", str(target)],
        ["x"],
    )

    assert code == 1
    assert "Error: Could not write" in err


# ---- Errors and flags -----------------------------------------------------


def test_missing_file_prints_friendly_error(tmp_path: Path) -> None:
    code, out, err = run_cli(["-f", str(tmp_path / "nope.json")])

    assert code == 1
    assert err.startswith("Error: Deck file")
    assert "Traceback" not in err + out


def test_malformed_file_prints_friendly_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")

    code, _, err = run_cli(["-f", str(bad)])

    assert code == 1
    assert "not valid JSON" in err


def test_help_lists_all_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    text = capsys.readouterr().out
    for flag in ("--file", "--mode", "--stats", "--limit", "--export-missed"):
        assert flag in text


@pytest.mark.parametrize(
    "args",
    [
        ["-m", "adaptive"],
        ["-f", "x.json", "-m", "spaced"],
        ["-f", "x.json", "--limit", "0"],
        ["-f", "x.json", "--limit", "two"],
    ],
)
def test_bad_arguments_exit_with_usage_error(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(args)

    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_ctrl_c_outside_the_quiz_exits_cleanly(
    three_card_deck: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(path: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_flashcards", interrupt)

    code, _, err = run_cli(["-f", str(three_card_deck)])

    assert code == cli.EXIT_INTERRUPTED
    assert "Stopped." in err


def test_sample_deck_runs_end_to_end() -> None:
    code, out, _ = run_cli(
        ["-m", "sequential", "-f", str(GLOSSARY), "--no-history"], ["exit"]
    )

    assert code == 0
    assert "glossary (10 cards, sequential mode)" in out
