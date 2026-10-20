# CampusFlow Pro

A text-based IT help desk: create tickets, assign them, move them through a workflow, see work queues,
SLA deadlines, escalation, an audit history, reports, and an Engineering Knowledge Lab quiz.
Priority is calculated by plain Python rules (no AI at runtime). Python 3.8+, no extra packages.

    python main.py              # run (data is saved to data/tickets.json automatically)
    python -m unittest -v       # test (run from the project root)

## Project structure

```
campusflow-simple/
├── main.py                  menu and user interaction (the only entry point)
├── campusflow/
│   ├── logic.py             all rules: validation, priority, workflow, SLA, escalation, history, queues, reports
│   ├── storage.py           validated, atomic JSON save/load (schema v2)
│   └── lab.py               Engineering Knowledge Lab quiz
├── tests/test_campusflow.py all tests
├── docs/                    design decisions, AI learning log, reflections, experiments
├── lab_sessions/            saved quiz sessions (JSON)
└── data/                    tickets.json is created here on first save
```

Dependencies flow one way: `main.py` -> `lab.py`, `logic.py`, `storage.py`; `storage.py` -> `logic.py`.

## Rules

- **Fields:** id, title, category, urgency, affected_users, priority, status, assigned_to
  (plus created_at, updated_at, due_at, escalation_cycle). IDs are automatic: T001, T002, ...
- **Categories:** Network, Hardware, Software, Other. **Urgency:** low, medium, high (case-insensitive).
  Title cannot be blank; affected users must be a positive whole number.
- **Priority (first match wins):** high + 10+ users = critical; high or 10+ users = high;
  medium or 3+ users = medium; otherwise low.
- **Workflow:** open -> in_progress -> resolved -> open (reopen). No skipping. A ticket must be assigned
  before it can start. A resolved ticket cannot be changed until reopened.
- **Work queue (menu 4):** unresolved tickets, critical -> low, ties to the lower ticket number.
- **SLA:** critical 60 min, high 240, medium 1440, low 2880. `due_at = cycle start + SLA`. Overdue only when
  now is strictly later than `due_at` and the ticket is unresolved. Reopening starts a new SLA cycle.
- **SLA Attention Queue (menu 5):** unresolved; overdue first, then earliest `due_at`, then ticket number.
- **Escalation (menu 7):** one ESCALATE event per overdue ticket per cycle; re-running adds nothing.
  Never assigns, re-prioritises or changes status. All-or-nothing.
- **Audit trail (menu 6):** CREATE, ASSIGN, START, RESOLVE, REOPEN, ESCALATE events are added only after
  the operation succeeds. Rejected actions change nothing. The operator label is for traceability only.
- **Duplicate warning:** same normalised title + category among unresolved tickets shows the matching IDs
  and asks for confirmation; declining creates nothing.
- **Saving:** automatic after every change (menu 9 saves or reloads manually). A missing file starts fresh.
  A damaged, inconsistent or old list-style file stops the program with a clear message and is never overwritten.
  Writes are atomic (temp file + `os.replace`).
- **Reports (menu 8):** totals, counts by status and priority, overdue and escalated tickets.
  Options 5, 7 and 8 accept an optional UTC time (blank = now) so overdue behaviour can be demonstrated.
- **Knowledge Lab (menu 10):** 10 scenario questions, exact capital `A/B/C/D` only, at least 3 written
  explanations, score + revision topics, session saved to `lab_sessions/`. It never touches ticket data.
