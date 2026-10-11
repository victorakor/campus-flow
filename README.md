# CampusFlow

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
| `helpdesk.py` | Entry point: text menu and user input |
| `config.py` | Shared constants (categories, urgencies, statuses, workflow moves, data file name) |
| `validation.py` | Cleaning and validating title, category, urgency and affected users |
| `ticket_service.py` | Priority rules, create/find/assign tickets, status changes, work queue, report counts |
| `storage.py` | Saving and loading `tickets.json` |
| `test_validation.py` | Tests for `validation.py` |
| `test_ticket_service.py` | Tests for `ticket_service.py` (priority, create, workflow, queue, reports) |
| `test_storage.py` | Tests for `storage.py` |

Dependencies flow one way, with no circular imports:
`config` <- `validation` <- `ticket_service`, `config` <- `storage`, and
`helpdesk.py` imports from all of them.