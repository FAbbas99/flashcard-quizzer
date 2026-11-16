# AI Edit Log

This log records the AI interactions for the Flashcard Quizzer. Each entry
gives the prompt, the AI output, the problem that review found, and the
change. The review used `ai_guidance/code_review_checklist.md`, the quality
tools (black, flake8, mypy, pytest) and manual runs of the program.

**AI tool for all entries:** Claude Code (Claude Opus 5.5), in the terminal.

**Workflow for each phase:**

1. Write a prompt that names the files, the behavior and the error cases.
2. Read the generated code against the review checklist.
3. Run `black`, `flake8`, `mypy` and `pytest`.
4. Run the program by hand with good and bad input.
5. Write a new prompt for each problem. Do not edit the Python by hand.

---

## Entry 1: 2026-11-15 - Error messages in the deck loader

**Context:** Phase 1 needed a loader for two JSON formats. A bad file must
give a clear message, not a traceback.

**Prompt/Request:**
"Create `utils/file_handler.py` and a frozen `Flashcard` dataclass in
`models.py`. `load_flashcards(path)` must accept a plain list of
`{"front", "back"}` objects and a `{"cards": [...]}` wrapper. Raise one custom
exception, `FlashcardLoadError`, for these cases: missing file, directory,
file over 5 MB, non-UTF-8 text, bad JSON, wrong top-level type, empty deck,
and a card without a non-empty `front` or `back` string. Put the card number
in the message. Use type hints on all functions."

**AI Response:** The AI wrote the loader, the exception and the model. The
loader handled all of the listed cases. It also logged a warning for
duplicate card fronts.

**Problem found:** I made ten bad deck files and loaded each one. All ten
gave a `FlashcardLoadError`. But three messages used Python type names:

- `Card 1 ... must be an object ..., not a int.`
- `... must contain a list of cards, not a NoneType.`
- `... must contain a list of cards, not a dict.`

A user writes JSON, not Python. "NoneType" and "dict" mean nothing to that
user, and "a int" is bad grammar. The last message was also wrong: the file
had a `"cards"` key, but its value was an object, not an array.

**Changes Made:** A new prompt asked for JSON type names and correct
articles. The AI added `json_type_name()` and `_with_article()`. It also added
a separate message for a `"cards"` value that is not an array.

**Outcome:** The messages now read "not a number", "not null" and
`The "cards" key ... must be an array of cards, not an object.`
A parametrized test covers each JSON type.

**Lessons Learned:** The tool output passed every check. Only a manual run
with bad files showed the problem. Error messages are part of the user
interface. I must read them as a user reads them.

---

## Entry 2: 2026-11-15 - Factory that did not follow the Strategy pattern

**Context:** Phase 2 needed three quiz modes with the Strategy pattern and a
Factory to select the mode.

**Prompt/Request:**
"Create `quiz_engine.py`. Add an abstract base class `QuizMode` with
`next_card()` and `record_answer(card, correct)`. Add `SequentialMode`,
`RandomMode` and `AdaptiveMode`. Add a factory `create_quiz_mode(name, cards)`
that selects the class from a registry dictionary. `RandomMode` must accept a
seeded `random.Random` for tests. `AdaptiveMode` must accept past miss counts.
Do not use `print` or `input` in this module."

**AI Response:** The AI wrote the base class, the three modes, a
`MODE_REGISTRY` dictionary and the factory. The code worked. But the factory
had a special branch for each mode with options:

```python
if key == AdaptiveMode.name:
    return AdaptiveMode(cards, past_misses=past_misses)
if key == RandomMode.name:
    return RandomMode(cards, rng=rng)
return MODE_REGISTRY[key](cards)
```

**Problem found:** The registry was not the only place to change for a new
mode. A "Spaced Repetition" mode with its own options needs a new `if` in the
factory. The project brief gives this exact case as the reason for the
pattern. Review also found the same `next_card()` code in `SequentialMode`
and `RandomMode`.

**Changes Made:** A new prompt asked for these changes:

- A `ModeOptions` dataclass that holds all optional inputs.
- A `from_options()` class method on `QuizMode`. Each mode takes only the
  options it needs.
- A factory that only looks up the class and calls `from_options()`.
- A `_FixedOrderMode` base class for the shared `next_card()` code.

Before the change, I recorded the output for a seeded random order and for
an adaptive order with history. After the change, the outputs were the same.

**Outcome:** A new mode now needs one subclass and one registry line. The
test `test_new_mode_needs_only_a_registry_entry` proves this. It adds a
`ReverseMode` to the registry, and the factory uses it with no code change.

**Lessons Learned:** The AI named the pattern correctly, but the first
version did not give the benefit of the pattern. A pattern is correct only
when the change it promises is easy. I now ask "what must change to add one
more?" for each pattern.

---

## Entry 3: 2026-11-15 - Endless loop risk in adaptive mode

**Context:** Adaptive mode must prioritize cards that the user gets wrong.

**Prompt/Request:**
"In `AdaptiveMode`, put cards with more past misses first, and keep file order
for equal misses. When the user misses a card, put it back in the queue two
positions later. End the quiz when each card has one correct answer. A user
who cannot answer a card must not be stuck in an endless loop."

**AI Response:** The AI used a `deque`. It sorted the cards by past misses
with a stable sort. It put a missed card back at position `retry_gap`. It
also added `max_attempts=3`, so a card leaves the queue after three misses.

**Problem found:** No defect in the code. But the behavior was not clear from
the code alone. I traced a four-card quiz by hand. The user got Q1 and Q4
right, missed Q2 once and missed Q3 every time.

| Step | Card | Result |
|------|------|--------|
| 1 | Q1 | correct |
| 2 | Q2 | wrong |
| 3 | Q3 | wrong |
| 4 | Q4 | correct |
| 5 | Q2 | correct |
| 6 | Q3 | wrong |
| 7 | Q3 | wrong, card removed |

Total 7, correct 3, accuracy 42.9%, missed Q2 and Q3. This matches the rules.

**Changes Made:** I kept the code. I added tests for each rule: past-miss
order, the retry gap, the end-of-queue case and the three-attempt limit.

**Outcome:** The required test `test_adaptive_mode_behavior` checks the
exact order `Q1, Q2, Q3, Q1, Q4`.

**Lessons Learned:** I put the endless-loop risk in the prompt, so the AI
handled it. A risk named in the prompt costs less than a bug found later.

---

## Entry 4: 2026-11-15 - A `type: ignore` that hid a typing gap

**Context:** Phase 3 needed the CLI. It needed `argparse` flags `-f`, `-m`
and `--stats`, colors, and a clean exit on "exit" or Ctrl+C.

**Prompt/Request:**
"Create `ui.py` and `main.py`. Use `argparse` with `-f/--file`, `-m/--mode`
(choices from the factory registry) and `--stats`. Also add `--limit N`,
`--export-missed PATH`, `--history PATH`, `--no-history`, `--seed`,
`--no-color` and `--verbose`. Show green for correct and red for incorrect.
Turn colors off if the output is not a terminal or `NO_COLOR` is set. Stop
cleanly on "exit", "quit", Ctrl+C and Ctrl+D. Give the UI its input function
and output stream as arguments so that tests can run a full quiz."

**AI Response:** The AI wrote both modules. All flags worked. mypy in strict
mode found no errors.

**Problem found:** Manual review of `main.py` found this:

```python
def _export_missed(missed: Sequence[object], ...):
    save_flashcards(list(missed), path)  # type: ignore[arg-type]
```

The parameter type was too wide. The comment told mypy to ignore the error
that this caused. mypy passed only because of the comment. This is a hidden
failure: the tool shows success, but the check is off.

**Changes Made:** A new prompt asked for the correct type,
`Sequence[Flashcard]`, and no `type: ignore` comments. The AI made the change.
mypy still passed, now with a real check.

**Outcome:** The project has no `type: ignore` comments.

**Lessons Learned:** A passing tool is not proof. AI-generated code can
silence a tool. I now search for `type: ignore`, `noqa` and bare `except`
before I accept a module.

---

## Entry 5: 2026-11-15 - Statistics table too wide

**Context:** `--stats` shows lifetime results for each card, weakest first.

**Prompt/Request:** Part of the Entry 4 prompt: "With `--stats`, after the
summary, show a table with Card, Asked, Missed and Accuracy for this deck."

**AI Response:** The AI wrote `format_card_records()` and a small `_table()`
helper.

**Problem found:** I ran `python main.py -m adaptive -f
data/python_basics.json --stats`. The questions in that deck are long, so the
table was about 95 characters wide. It wrapped in a normal terminal and was
hard to read.

**Changes Made:** A new prompt asked to cut the card column at 48 characters
and end it with "...". The AI added `shorten()` and `MAX_CARD_COLUMN`.

**Outcome:** The table now fits in 80 columns. A parametrized test covers
`shorten()`, which includes a width that is too small for the text.

**Lessons Learned:** The AI tested the layout with short data in its head.
Real data showed the problem. I must run each feature with every sample deck.

---

## Entry 6: 2026-11-15 - Test suite passed on the first run

**Context:** The project needs the required test names and more than 80%
coverage.

**Prompt/Request:**
"Write a pytest suite. Use these exact names:
`test_load_valid_flashcards_array`, `test_load_invalid_json`,
`test_load_missing_required_field` in `tests/test_flashcard_loader.py`;
`test_quiz_mode_factory` and `test_adaptive_mode_behavior` in
`tests/test_quiz_modes.py`; `test_full_session` in
`tests/test_integration.py`. Also test edge cases: empty deck, whitespace
answers, Unicode, exit during a quiz, Ctrl+C, unknown mode and a failed file
write. Use `tmp_path` for all files."

**AI Response:** The AI wrote 130 tests in five files. All passed on the first
run, with 100% line coverage.

**Problem found:** A suite that never fails proves little. Coverage shows
that a line ran. It does not show that a test checks the result of that line.
So I did a small mutation check. I broke the code in six places, one at a
time, and ran the suite each time:

| Change to the code | Caught by |
|--------------------|-----------|
| Adaptive mode does not put a missed card back | `test_adaptive_mode_behavior` and 2 more |
| Answer check is case-sensitive | `test_session_scores_answers` and more |
| Adaptive mode ignores history | `test_adaptive_puts_past_misses_first` |
| Loader accepts an empty `front` | `test_load_rejects_bad_structure` |
| UI does not catch Ctrl+C | `test_ui_ctrl_c_stops_quiz_without_traceback` |
| History is written with `--no-history` | `test_corrupt_history_warns_and_is_not_overwritten` |

The suite caught all six. But the last one showed a new problem (Entry 7).

**Changes Made:** No change to the tests for this entry.

**Outcome:** I trust the suite more because it failed when it should.

**Lessons Learned:** 100% coverage was easy for the AI to get. Coverage is a
minimum, not a goal. A mutation check is a fast way to test the tests.

---

## Entry 7: 2026-11-15 - Tests wrote a file into the project folder

**Context:** This came from the last mutation in Entry 6.

**Problem found:** After that mutation, a file `.flashcard_history.json`
appeared in the project root. The CLI writes history to the current folder
by default. pytest runs in the project folder. So a bug in the
`--no-history` guard made the tests write into the repository. In the normal
code, this does not occur. But a test must not depend on that.

**Prompt/Request:**
"Add an autouse fixture in `tests/conftest.py` that changes the current
folder to `tmp_path` for every test, so that no test can write into the
project."

**AI Response:** The AI added the `isolated_cwd` fixture with
`monkeypatch.chdir(tmp_path)`.

**Changes Made:** I deleted the stray file. Then I ran the same mutation
again.

**Outcome:** The test still fails on the mutation, and the project folder
stays clean.

**Lessons Learned:** Tests must not touch the real working folder. The AI
used `tmp_path` for the files it named. It did not think about the default
path that the program uses when no path is given.

---

## Entry 8: 2026-11-15 - mypy error in the tests

**Context:** The final check runs `mypy .`, so it also checks the tests.

**Problem found:** mypy reported one error:

```
tests/test_quiz_modes.py:214: error: Argument 2 to "AdaptiveMode" has
incompatible type "**dict[str, int]"; expected "Mapping[str, int] | None"
```

The test passed settings as `AdaptiveMode(cards, **kwargs)`. mypy cannot tell
which key goes to which parameter. One of the parameters, `past_misses`, does
not accept an `int`.

**Prompt/Request:** "Rewrite `test_adaptive_rejects_bad_settings` with
explicit `retry_gap` and `max_attempts` parameters instead of `**kwargs`."

**AI Response and Changes Made:** The AI changed the parametrize to three
explicit values per case.

**Outcome:** `mypy .` reports no errors in 13 source files.

**Lessons Learned:** Tests are code. The same quality rules apply to them.

---

## Rejected options

- **Unused dependencies.** The starter `requirements.txt` listed `requests`,
  `click`, `pydantic`, `sphinx`, `safety` and `pre-commit`. The program uses
  none of them. I removed them so that the file shows the real dependencies.
  The program uses only the standard library.
- **A color library.** A package such as `colorama` was not necessary. Four
  ANSI codes and a `NO_COLOR` check do the work with no new dependency.
- **Empty answer prompts again.** One option was to ask again when the user
  presses Enter with no text. I rejected it. An empty answer is counted as
  wrong and the correct answer is shown, which helps the user learn.
