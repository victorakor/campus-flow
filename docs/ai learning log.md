# AI Learning Log

A record of how AI assistance (Claude) was used on this project, what was
learned, and how the output was checked. The entries below reflect the
work done in one session on 11 October 2026. Edit them to match your own
experience, and add the "Your notes" lines, which only you can write.

## Principles used

- The project (`helpdesk.py` and its tests) was written first. AI was used
  afterwards to organize and document it, not to design the rules.
- Every AI-produced change was verified by running the tests, not just
  read.
- Priority is calculated by plain Python rules. No AI is used at runtime.

## Entry 1: Splitting one file into several

**Question asked:** How many distinct files can the single-file project be split
into so two people each have something real to commit?

**What the AI suggested:** Five modules, following the section comments already
in the code (config, validation, ticket logic, storage, CLI), plus three
test files. It also suggested a two-person division and a Git workflow where
each person extracts their half on their own branch.

**What I learned:**
- Section comments in a file are good hints for where module boundaries belong.
- Dependencies should flow one way so modules never import each other in a
  circle.
- Splitting further than one responsibility per file makes code harder to read,
  not easier.

**How it was checked:** The split code was run with `python -m unittest discover`
(19 tests passing) and a scripted run of the menu.

**Your notes:** _What did you accept, change or reject?_

## Entry 2: Naming and imports

**What the AI flagged:** Naming the logic file `tickets.py` would sit awkwardly
next to local variables called `tickets`, so the file became `ticket_service.py`.
The old tests imported everything from `helpdesk`, so each test file had to
import from the new modules.

**What I learned:** Module names matter for readability, and moving code means
updating every place that imports it, including tests.

**Your notes:** _Did you hit any import errors while splitting?_

## Entry 3: Testing what was only tested indirectly

**What happened:** The validation functions were only tested through
`create_ticket`. The split added `test_validation.py` with direct tests,
including a case where a non-Western digit such as "٣" must be rejected.

**What I learned:** Python's `str.isdigit()` accepts digits from other scripts, and
`int()` converts them. Checking `isascii()` first closes that gap.

**How it was checked:** The new tests run and pass; the existing tests were moved
unchanged and still pass.

**Your notes:** _Can you think of another input that might slip through?_

## Entry 4: Documentation

**What happened:** The AI produced a README matching an earlier template, then
this log and `design_decisions.md`, derived from the code itself (names,
comments, tests).

**What I learned:** Good documentation records the reason for a choice and
its trade-off, not only what the code does. Writing the "known limitation"
lines also showed gaps worth fixing (for example, saving is not atomic).

**Your notes:** _Which statements in the docs did you verify against the code?_

## What AI did not decide

- The priority rules, workflow, and validation rules came from the original
  project.
- What to submit, and how to describe each person's contribution in Git,
  is up to the team.