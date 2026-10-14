# Design Decisions

This document records why CampusFlow is built the way it is. Each entry gives
the decision, the reason, and the trade-off.

## 1. Priority uses plain Python rules, not AI

**Decision:** `calculate_priority` is a short if-chain; the first matching rule wins.

**Why:** Help desk staff need to predict and explain why a ticket got its
priority. Fixed rules are deterministic, instantly testable, and need no
network or external service.

**Trade-off:** The rules are blunt (only urgency and user count). Changing them
means editing code. Adding factors such as category would need a rule redesign.

## 2. Priority is checked in order, with fixed thresholds

**Decision:** high urgency and 10+ users is critical; high urgency or 10+ users
is high; medium urgency or 3+ users is medium; everything else is low.

**Why:** Ordering the checks from most to least severe removes ambiguity. A
ticket can match several rules, and the first match decides. Tests cover each
boundary (9 vs 10 users, 2 vs 3 users).

**Trade-off:** The thresholds (10 and 3) are magic numbers inside the function.
They are not yet named constants in `config.py`.

## 3. Strict one-step workflow

**Decision:** `NEXT_STATUS` allows only `open -> in_progress -> resolved -> open`.
Steps cannot be skipped.

**Why:** A lookup table makes the allowed moves visible in one place and keeps
`change_status` small. Forcing every ticket through `in_progress` keeps the
reports meaningful.

**Trade-off:** There is no shortcut for trivial tickets and no way to move
backwards from `in_progress` to `open`.

## 4. Assignment is required before work starts

**Decision:** A ticket cannot move to `in_progress` without an `assigned_to` value.

**Why:** Work should always have an owner; otherwise the queue can show tickets
"in progress" that nobody is handling.

## 5. Resolved tickets are locked until reopened

**Decision:** `assign_ticket` rejects resolved tickets. The only way to change
one is the explicit reopen step (`resolved -> open`).

**Why:** It prevents accidental edits to finished work and makes reopening a
deliberate, visible action.

## 6. Ticket IDs come from the highest existing number

**Decision:** The next ID is `max(existing numbers) + 1`, formatted `T001`, `T002`, ...

**Why:** Using `len(tickets) + 1` would produce duplicates if a ticket were ever
removed. The max approach also stays correct after reloading from disk (tested
in `test_storage.py`).

**Trade-off:** IDs have three digits of padding; past `T999` they simply grow
longer (`T1000`), which is fine for logic but misaligns the printed table.

## 7. Validation happens in one place and raises `ValueError`

**Decision:** `validation.py` cleans input (trim, case-insensitive match) and
raises `ValueError` with a human-readable message. The menu catches it and
reprints the message; the `ask` helper re-prompts until the input is valid.

**Why:** The logic functions never trust their callers, so they are safe to call
from tests or any future interface. The CLI stays simple because it only
displays the message.

## 8. Affected users must be ASCII digits

**Decision:** `clean_users` checks `isascii()` and `isdigit()` before `int()`.

**Why:** `"٣".isdigit()` is `True` and `int("٣")` returns 3 in Python, so without
the ASCII check, non-Western digits would be silently accepted. Rejecting
them keeps input predictable. `test_validation.py` includes this case.

## 9. Work queue sorts by priority, then ticket number

**Decision:** Unresolved tickets are sorted by position in `PRIORITIES`, then by
numeric ID.

**Why:** The tie-break makes the order fully deterministic, and older tickets
(lower numbers) are served first within the same priority. The numeric
sort avoids string-order bugs once IDs reach `T010` and beyond; a test
covers this.

## 10. Tickets are plain dictionaries in a list

**Decision:** A ticket is a `dict`; the collection is a `list` passed into
every function. No classes and no global state.

**Why:** It maps directly onto JSON, so saving and loading need no conversion,
and each function can be tested with a small hand-built list. For a project of
this size, classes would add ceremony without adding clarity.

**Trade-off:** Field names are strings, so a typo fails at runtime rather than
being caught early.

## 11. JSON file storage, saved after every change

**Decision:** Tickets are stored in `tickets.json`. The menu saves after every
option that modifies data (create, assign, start, resolve, reopen).

**Why:** JSON is human-readable and needs no database. Saving after each change
means a crash loses at most one action.

## 12. A damaged data file is never overwritten

**Decision:** `load_tickets` raises a `ValueError` for invalid JSON or the wrong
structure. `main` prints the message and exits before the first save.

**Why:** Starting with an empty list and saving would destroy the user's
only copy of their tickets. A missing file is different: that is a normal
first run, so the program starts fresh.

**Known limitation:** `save_tickets` writes directly to the file. A crash
during a write could still corrupt it. Writing to a temporary file and
renaming it would fix this. Also, loading checks that the required fields
exist, but not that their values are valid.

## 13. Module structure

**Decision:** Five modules, each with one job:

| Module | Responsibility |
|--------|----------------|
| `config.py` | Constants shared everywhere |
| `validation.py` | Input cleaning |
| `ticket_service.py` | Business rules |
| `storage.py` | File reading and writing |
| `helpdesk.py` | Menu and user interaction |

**Why:** The original single file already had clear sections, so the split
follows them. Dependencies flow one way (`config` <- `validation` <-
`ticket_service`; `config` <- `storage`; `helpdesk` imports all), which
avoids circular imports. The logic module is called `ticket_service.py`
rather than `tickets.py` to avoid confusion with the many local variables
named `tickets`. The split also gives two people separate files to work on.

**Trade-off:** The flat layout means all modules and tests sit in one folder.
A package (`campusflow/` plus `tests/`) would be tidier if the project grows.

## 14. Tests target logic, not the menu

**Decision:** Unit tests cover validation, ticket logic and storage. The
interactive menu is only smoke-tested by hand.

**Why:** All the rules live in functions that take plain arguments and return
values, so they are easy to test. Testing `input()` loops adds complexity for
little extra confidence.

**Trade-off:** Menu wiring bugs (for example, a wrong option number) are not
caught automatically.

---

# Engineer B additions

## 15. Logged operations live in `workflow.py`, not inside `ticket_service.py`

**Decision:** `create_ticket_logged`, `assign_ticket_logged` and `change_status_logged`
call the ORIGINAL `create_ticket`, `assign_ticket` and `change_status`, then append the event.

**Why:** The original rules and their tests stay untouched (regression safety). The order is
validate -> change -> append event; if appending fails, the ticket and event list are restored.
**Trade-off:** Callers must use the logged versions; calling the originals directly skips history.

## 16. Current status AND history are both stored

Status answers "where is it now" in O(1); events answer "who did what and when". Events are
append-only and only written for successful changes, so a rejected action never appears as if it happened.

## 17. Duplicates warn, they do not block

**Decision:** `detect_duplicates(tickets, category, title)` returns unresolved matches (title trimmed,
casefolded, whitespace collapsed; same category). The CLI asks for confirmation.
**Why:** Repeat reports can be legitimate (the fault came back, a different room). Silent blocking would lose
information; silent acceptance adds noise. **Trade-off:** One extra prompt for the user.

## 18. Escalation marker and `escalation_cycle`

`escalation_cycle` counts SLA cycles (0, +1 on each reopen). An ESCALATE event's details end with
`cycle=N`; "already escalated" is DERIVED from the event list, so there is no second flag that could drift
out of sync. Metric "escalated in current cycle" counts unresolved tickets (each once) that have an
ESCALATE event for their current cycle. **Trade-off:** the marker is in a text field; a dedicated event
field would be sturdier (schema change agreed with Engineer A).

## 19. Two queues, two questions

Original Open Work Queue = "what matters most" (priority, then ID, unchanged). SLA Attention Queue = "what is
running out of time" (overdue, then `due_at`, then ID). They can legitimately disagree.

## 20. Knowledge Lab is isolated and strict

`run_lab` takes no ticket data. Only exact capital `A/B/C/D` is accepted. Scoring is a pure function
(`score_answers`) so it can be tested. Explanations are stored, never auto-graded; at least three are forced.
**Known limitation:** a user could guess letters; the explanation requirement and live mentor questions are the
defence, not the score.
