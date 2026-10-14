"""SLA rules. Engineer A owns this module; this version implements the agreed
contract so Engineer B's code can be integrated and tested. Keep the signatures."""

from datetime import timedelta

from . import history
from .clock import parse_iso, utc_now
from .config import SLA_MINUTES


def calculate_due_at(priority, cycle_start):
    """cycle_start (aware datetime) -> due datetime (cycle_start + SLA minutes)."""
    if priority not in SLA_MINUTES:
        raise ValueError(f"Unknown priority '{priority}'.")
    return cycle_start + timedelta(minutes=SLA_MINUTES[priority])


def is_overdue(ticket, now=None):
    """Overdue only when now is STRICTLY later than due_at and not resolved."""
    now = now or utc_now()
    return ticket["status"] != "resolved" and now > parse_iso(ticket["due_at"])


def escalate_overdue(tickets, events, now=None, actor="system"):
    """One ESCALATE event per ticket per SLA cycle (derived from the event list).

    All-or-nothing: events are staged on a copy and only added to ``events`` once
    every one succeeded, so a failure can never leave a half-finished run.
    Tickets are never modified (no assignment, priority or status change)."""
    actor = history.clean_actor(actor)                 # reject a blank label up front
    now = now or utc_now()
    staged = list(events)
    new, already = [], []
    for t in sorted(tickets, key=lambda t: int(t["id"][1:])):
        if not is_overdue(t, now):
            continue
        if history.has_escalation_in_cycle(staged, t["id"], t["escalation_cycle"]):
            already.append(t["id"])
            continue
        history.append_event(staged, t["id"], "ESCALATE", actor, now, t["status"],
                             t["status"], "SLA overdue; "
                             + history.escalation_marker(t["escalation_cycle"]))
        new.append(t["id"])
    events.extend(staged[len(events):])                # commit only after full success
    return {"newly_escalated": len(new), "already_escalated": len(already),
            "new_ids": new, "already_ids": already}
