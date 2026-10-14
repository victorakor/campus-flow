# CampusFlow Pro

A simple text-based IT help desk ticket tracker. Create tickets, assign them,
move them through a workflow, see a prioritized work queue, and view reports.
Tickets are saved to `tickets.json` so they survive restarts.

Priority is calculated by plain Python rules, not by an AI model.

## Run

Requires Python 3.8+ (no extra packages). From the project folder (data is stored in `data/tickets.json`):

    python main.py

## Test

    python -m unittest -v

Run both commands from the project root. `python -m unittest` finds everything in `tests/`.

## Rules

**Fields:** id, title, category, urgency, affected_users, priority, status, assigned_to

- IDs are automatic: T001, T002, ...
- Categories: Network, Hardware, Software, Other
- Urgency: low, medium, high (input is case-insensitive)
- Title cannot be blank; affected users must be a positive whole number

**Priority (first match wins):**

1. high urgency and 10+ users: critical
2. high urgency or 10+ users: high
3. medium urgency or 3+ users: medium
4. otherwise: low

**Workflow:** open -> in_progress -> resolved -> open (reopen)

- A ticket must be assigned before it can be started.
- A resolved ticket cannot be changed until it is reopened (back to open).
- Status moves cannot be skipped; each status has exactly one allowed next step.

**Work queue:** all unresolved tickets (open and in_progress), sorted
critical -> high -> medium -> low; ties go to the lower ticket number.

**Saving:** automatic after every change. A missing file starts fresh. A
damaged `tickets.json` stops the program with a clear message and is never
overwritten.

## Project structure

```
campus-flow/
├── main.py                  entry point (python main.py [--migrate])
├── README.md
├── .gitignore
├── campusflow/              the application package
│   ├── cli.py               text menu and user interaction
│   ├── config.py            shared constants and file locations
│   ├── validation.py        cleaning title, category, urgency, affected users
│   ├── ticket_service.py    priority rules, create/assign/status, work queue, duplicates
│   ├── workflow.py          logged operations (change ticket, then append event)
│   ├── history.py           append-only audit trail
│   ├── sla.py               due dates, overdue check, idempotent escalation
│   ├── reports.py           SLA attention queue and metrics (read-only)
│   ├── storage.py           JSON save/load (v2, atomic), legacy migration
│   ├── clock.py             UTC time helpers
│   └── knowledge_lab.py     Engineering Knowledge Lab quiz
├── tests/                   unittest suites (original + new)
├── docs/                    design decisions, AI learning log, reflections, experiments
├── lab_sessions/            saved quiz sessions for mentors
└── data/                    tickets.json lives here (git-ignored, created on first save)
```

Dependencies flow one way, with no circular imports:
modules inside `campusflow/` use relative imports; `cli.py` imports from all of them and `main.py` only calls `cli`.

## CampusFlow Pro additions (Engineer B: history, queues, duplicates, CLI, lab)

Run `python main.py`. You are asked for an **operator label** (traceability
only, not verified identity). Menu: 1 Create, 2 Assign, 3 Start/resolve/reopen,
4 Original Open Work Queue, 5 SLA Attention Queue, 6 Ticket history,
7 Check and escalate overdue, 8 Reports, 9 Save/load, 10 Engineering Knowledge
Lab, 11 List all tickets, 12 View one ticket, 0 Exit. Options 5, 7 and 8 accept an
optional UTC time (blank = now) so overdue behaviour can be demonstrated.

- **Audit trail:** CREATE, ASSIGN, START, RESOLVE, REOPEN and ESCALATE append an
  event only after the operation succeeds. Rejected actions change nothing.
- **Duplicate warning:** same normalized title + category among unresolved tickets
  shows the matching IDs and asks for confirmation; declining creates nothing.
- **SLA Attention Queue:** unresolved tickets, overdue first, then earliest `due_at`,
  then ticket number. The original work queue (option 4) is unchanged.
- **Knowledge Lab:** 10 scenario questions, exact `A/B/C/D` only, explanations
  (at least 3 required), score + revision topics, session saved as JSON in
  `lab_sessions/`. It never receives or changes ticket data.
- **Data file:** `tickets.json` is now `{schema_version: 2, tickets, events}`. An old
  list-style file is rejected with a message (not overwritten).

New files: `clock.py`, `history.py`, `workflow.py`, `reports.py`, `sla.py`*,
`knowledge_lab.py`, and `test_workflow.py`, `test_reports.py`,
`test_knowledge_lab.py`, `test_cli.py`. (*`sla.py` and the v2 section of `storage.py`
are Engineer A's area, implemented to the agreed contract so B's work runs.)

## CampusFlow Pro additions (Engineer A: SLA, escalation, data integrity)

- **SLA:** critical 60 min, high 240, medium 1440, low 2880. `due_at = cycle_start + SLA`. Overdue only when
  `now` is strictly later than `due_at` and the ticket is not resolved. Reopening starts a new SLA cycle.
- **Escalation (menu 7):** one ESCALATE event per overdue ticket per cycle; re-running creates no duplicates. It never
  assigns, re-prioritises or changes status. Runs all-or-nothing.
- **Persistence:** `{schema_version: 2, tickets, events}`, validated before use, saved atomically (temp file +
  `os.replace`). A corrupt or inconsistent file is rejected and never overwritten.
- **Legacy file:** an old list-style `tickets.json` is rejected with a hint. Run `python main.py --migrate` to convert it;
  the original is kept as `tickets.json.legacy-backup` and no history or timestamps are invented.
- **Tests:** `test_clock.py`, `test_sla.py`, `test_state_storage.py` (Engineer A). Run everything with `python -m unittest -v`.
- **Experiments:** `docs/lesson_experiments.py` (Lessons A-D).

