"""Ticket operations that also write the audit trail.

Rule: validate -> change the ticket -> append the event. An event exists only
for an operation that succeeded; any failure leaves tickets AND events as they
were before the call."""

import history
from clock import to_iso, utc_now
from config import CATEGORIES, STATUS_EVENT, URGENCIES
from sla import calculate_due_at
from ticket_service import (assign_ticket, change_status, create_ticket,
                            detect_duplicates, find_ticket)
from validation import clean_choice, clean_title, clean_users


def _restore(ticket, snapshot, events, event_count):
    ticket.clear()
    ticket.update(snapshot)
    del events[event_count:]


def create_ticket_logged(tickets, events, title, category, urgency, users, actor,
                         now=None, confirm_duplicate=None):
    """Returns the new ticket, or None if the user declined a duplicate warning.
    confirm_duplicate(ids) -> bool is asked only when unresolved duplicates exist."""
    actor = history.clean_actor(actor)
    now = now or utc_now()
    title = clean_title(title)                         # validate EVERYTHING first
    category = clean_choice(category, CATEGORIES, "category")
    clean_choice(urgency, URGENCIES, "urgency")
    clean_users(users)

    duplicates = detect_duplicates(tickets, category, title)
    if duplicates and not (confirm_duplicate and confirm_duplicate(duplicates)):
        return None                                    # declined: no ticket, no event

    event_count = len(events)
    ticket = create_ticket(tickets, title, category, urgency, users, now=now)
    try:
        history.append_event(events, ticket["id"], "CREATE", actor, now, None, "open",
                             f"Created with priority {ticket['priority']}; "
                             f"due {ticket['due_at']}")
    except Exception:
        tickets.remove(ticket)
        del events[event_count:]
        raise
    return ticket


def assign_ticket_logged(tickets, events, ticket_id, name, actor, now=None):
    actor = history.clean_actor(actor)
    now = now or utc_now()
    ticket = find_ticket(tickets, ticket_id)
    snapshot, event_count = dict(ticket), len(events)
    assign_ticket(tickets, ticket_id, name)            # raises before mutating
    try:
        ticket["updated_at"] = to_iso(now)
        history.append_event(events, ticket["id"], "ASSIGN", actor, now,
                             snapshot["status"], ticket["status"],
                             f"Assigned to {ticket['assigned_to']}")
    except Exception:
        _restore(ticket, snapshot, events, event_count)
        raise
    return ticket


def change_status_logged(tickets, events, ticket_id, new_status, actor, now=None):
    """START / RESOLVE / REOPEN. Reopening begins a NEW SLA cycle."""
    actor = history.clean_actor(actor)
    now = now or utc_now()
    ticket = find_ticket(tickets, ticket_id)
    snapshot, event_count = dict(ticket), len(events)
    change_status(tickets, ticket_id, new_status)      # raises before mutating
    try:
        ticket["updated_at"] = to_iso(now)
        details = f"Status {snapshot['status']} -> {new_status}"
        if new_status == "open":                       # reopen: fresh SLA cycle
            ticket["due_at"] = to_iso(calculate_due_at(ticket["priority"], now))
            ticket["escalation_cycle"] = snapshot["escalation_cycle"] + 1
            details += f"; new SLA cycle {ticket['escalation_cycle']}, due {ticket['due_at']}"
        history.append_event(events, ticket["id"], STATUS_EVENT[new_status], actor, now,
                             snapshot["status"], new_status, details)
    except Exception:
        _restore(ticket, snapshot, events, event_count)
        raise
    return ticket
