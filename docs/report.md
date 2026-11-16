# AI-Assisted Development Project Report

**Student Name:** Fazal Abbas
**Project Title:** Flashcard Quizzer
**Date:** 2026-11-15

## Executive Summary

I built the Flashcard Quizzer, a command-line app that helps new team members
learn server acronyms. It loads a deck from a JSON file and asks one question
at a time. It checks each answer and shows the result in green or red. At the
end, it shows the score and a list of missed terms.

It has three modes: sequential, random and adaptive. Adaptive mode repeats
missed cards and asks them first in the next session.

An AI agent, Claude Code, wrote the code. My work was to write the prompts,
review each result and send a better prompt when the result was wrong. I did
not edit the Python by hand.

## Project Overview

### Problem Statement

New hires must learn many server acronyms, such as DNS and LDAP. The brief
asked for a small terminal tool with clean code that is easy to extend.

### Solution Approach

I divided the work into four phases: data, quiz logic, user interface and
tests. Each phase had its own prompt. Each module has one responsibility:

- `utils/file_handler.py` reads and validates the JSON files.
- `quiz_engine.py` holds the quiz modes, the factory and the scoring.
- `ui.py` shows questions and reads answers. It has no quiz logic.
- `main.py` reads the flags and connects the parts.

The app uses only the Python standard library. I used `pip` and `venv` for
the development tools.

### Final Features

- [x] Load decks in array format and object format
- [x] Clear error messages for bad files, with no traceback
- [x] Sequential, random and adaptive modes
- [x] Case-insensitive answers, with extra spaces ignored
- [x] Session summary with accuracy and missed terms
- [x] Lifetime statistics for each card (`--stats`)
- [x] Export of missed cards as a new deck (`--export-missed`)
- [x] Question limit (`--limit`) and repeatable random order (`--seed`)
- [x] Clean exit with "exit", Ctrl+C or Ctrl+D

## AI Collaboration Experience

### AI Tools Used

- [x] Claude (Claude Code in the terminal)

### Collaboration Workflow

Each prompt named the file, the function names and the error cases. The
loader prompt listed eight failure cases. The more cases I named, the fewer
gaps I found later.

After each phase, I read the code against the review checklist. Then I ran
black, flake8, mypy and pytest, and I ran the app by hand with bad input. For
each problem, I wrote a new prompt with the expected result.

### Most Valuable AI Interactions

The edit log has eight entries. Three of them taught me the most.

**Example 1: The factory.** I asked for the Strategy pattern and a factory.
The AI made both, but the factory had an `if` for each mode that needed
options. A new mode would need a change in the factory, which removes the
reason for the pattern. A second prompt asked for a `ModeOptions` object and
a `from_options()` method on each mode. Now the factory only looks up the
class. A test adds a new mode to the registry and proves that the factory
needs no change.

**Example 2: A hidden type error.** mypy passed in strict mode. But one
function had a type that was too wide, and a `# type: ignore` comment hid the
error. I found it only when I read the code. A second prompt fixed the type
and removed the comment.

**Example 3: Tests that passed too easily.** The AI wrote 130 tests, and all
passed on the first run with 100% coverage. I did not trust this. I broke the
code in six places, one at a time. The tests caught all six (see Challenge 2).

### Challenges with AI Collaboration

The AI was strong on structure and on the cases that I named. It was weaker
on things that I did not name. For example, it used Python type names such as
"NoneType" in messages for users, and it made a table too wide for long
questions.

The main pattern was this: the AI makes code that passes the tools. But a
passing tool is not the same as correct behavior. Manual runs and code
reading found five of the eight problems in the log.

## Software Engineering Practices

### Code Quality Measures

- [x] Code formatting (black, isort)
- [x] Linting (flake8: zero errors)
- [x] Type checking (mypy in strict mode: zero errors)
- [x] Type hints on all functions
- [x] Docstrings on all public modules, classes and functions
- [x] Error handling with custom exceptions and exit codes

### Testing Strategy

The suite has 130 tests in five files, with the six required test names.
Unit tests cover each module. Integration tests run `main()` with scripted
answers and real files. Edge cases include empty decks, Unicode, bad flags,
Ctrl+C and failed writes.

Line coverage is 100%. I did not use strict test-driven development. But the
test prompt gave the required names, so the tests followed the specification
and not the code.

### Design Patterns Used

- **Strategy:** `QuizMode` is an abstract class with `next_card()` and
  `record_answer()`. `SequentialMode`, `RandomMode` and `AdaptiveMode` are
  three algorithms for one task: select the next card. `QuizSession` does not
  know which mode it uses. I chose this pattern because the brief asks for a
  spaced repetition mode in the future. With Strategy, that mode is one new
  class.
- **Factory:** `create_quiz_mode()` turns the `--mode` text into a mode
  object through `MODE_REGISTRY`. The CLI reads its choices from the same
  registry.

### Code Structure and Organization

The quiz engine has no `print` or `input` calls. The UI gets its input
function and output stream as arguments, so tests can run a full quiz
without a terminal.

## Technical Challenges and Solutions

### Challenge 1: An adaptive mode that always ends

**Problem:** If a missed card always goes back in the queue, a user who cannot
answer it is stuck.
**Solution:** A card leaves the queue after three misses.
**AI Involvement:** I put this risk in the prompt, and the AI added the limit.
I traced a quiz by hand to check the order.
**Lessons Learned:** Name the risk in the prompt. That costs less than a fix.

### Challenge 2: Tests that touched the project folder

**Problem:** A broken guard let tests write a history file into the project.
**Solution:** I broke the code in six places to test the tests. One break
showed this problem. An autouse fixture now runs each test in a temporary
folder.
**AI Involvement:** The AI wrote the fixture after a short, specific prompt.
**Lessons Learned:** Check the default paths that a program uses, not only
the paths that a test gives.

## Code Quality Analysis

### Metrics

- Lines of code: 1,097 (application), 1,114 (tests)
- Test coverage: 100%
- Number of functions and classes: 59 functions, 15 classes
- Linting score: flake8 0 errors, mypy 0 errors, black and isort clean

### Self-Assessment

- **Code Readability:** 5. The modules are small and each function has a
  docstring.
- **Code Maintainability:** 5. A new mode needs one class and one registry
  line, and a test proves this.
- **Test Quality:** 4. The tests caught all six broken versions. A tool for
  full mutation testing could find more gaps.
- **Documentation:** 4. The README has a diagram, examples and every flag.

## Learning Outcomes

I learned to write prompts like a ticket. A good prompt names the files, the
error cases and the test names. Review is most of the work. The code has the
gaps of the prompt, and my job is to find them.

## Reflection

### What Worked Well

Phase-by-phase prompts worked well. A small result is easy to review. The
mutation check was the most useful step, because it tested the tests.

### What Could Be Improved

I wrote the tests after the code. Next time, I will ask for the tests first.
I will also add a tool such as `mutmut` for full mutation testing.

### Future Enhancements

- A spaced repetition mode, with a review date for each card
- Partial credit for answers that are almost correct

## Conclusion

AI-assisted development is fast, but the speed moves the work to review. The
AI gave me clean structure and good tests. It also gave me a hidden type
error and a factory that did not fully follow the pattern. The tools did not
find these. Reading and running the code did. I will keep the same loop in
future work: a clear prompt, a small result, a careful review.

## Appendices

### Appendix A: AI Interaction Log

See `docs/ai_edit_log.md`. The key entries are Entry 2 (factory), Entry 4
(hidden type error) and Entries 6 and 7 (mutation check and test isolation).

### Appendix B: Code Statistics

See `docs/coverage_report.txt`.
