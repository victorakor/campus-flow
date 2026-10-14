# CampusFlow Pro

A simple text-based IT help desk ticket tracker. Create tickets, assign them,
move them through a workflow, see a prioritized work queue, and view reports.
Tickets are saved to `tickets.json` so they survive restarts.

Priority is calculated by plain Python rules, not by an AI model.

## Run

Requires Python 3.8+ (no extra packages). From the project folder:

    python helpdesk.py

## Test

    python -m unittest -v

All modules and tests sit in the same folder, so run both commands from there.

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

| Path | Purpose |
|------|---------|
| `.gitignore` | specifies what to omit in staing to git hub |
| `helpdesk.py` | Entry point: text menu and user input |
| `config.py` | Shared constants (categories, urgencies, statuses, workflow moves, data file name) |
| `validation.py` | Cleaning and validating title, category, urgency and affected users |
| `ticket_service.py` | Priority rules, create/find/assign tickets, status changes, work queue, report counts |
| `storage.py` | Saving and loading `tickets.json` |
| `test_validation.py` | Tests for `validation.py` |
| `test_ticket_service.py` | Tests for `ticket_service.py` (priority, create, workflow, queue, reports) |
| `test_storage.py` | Tests for `storage.py` |
| `docs/design_decisions.md` | Why the project is built the way it is |
| `docs/ai_learning_log.md` | How AI assistance was used and checked |

Dependencies flow one way, with no circular imports:
`config` <- `validation` <- `ticket_service`, `config` <- `storage`, and
`helpdesk.py` imports from all of them.

## CampusFlow Pro additions (Engineer B: history, queues, duplicates, CLI, lab)

Run `python helpdesk.py`. You are asked for an **operator label** (traceability
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
