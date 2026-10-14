"""Append-only audit trail. Events are only ever ADDED, and callers must append
an event only AFTER the business operation has succeeded."""

import re

from clock import parse_iso, to_iso
from config import EVENT_TYPES


def clean_actor(value):
    """Operator label for traceability. It is NOT verified identity."""
    actor = " ".join(str(value).split())
    if not actor:
        raise ValueError("Operator label must not be blank.")
    return actor


def _number(event_id):
    return int(event_id[1:])


def next_event_id(events):
    return f"E{max((_number(e['event_id']) for e in events), default=0) + 1:03d}"


def append_event(events, ticket_id, event_type, actor, timestamp,
                 before_status, after_status, details=""):
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type '{event_type}'.")
    event = {
        "event_id": next_event_id(events),
        "ticket_id": ticket_id,
        "event_type": event_type,
        "actor": clean_actor(actor),
        "timestamp": to_iso(timestamp),
        "before_status": before_status,
        "after_status": after_status,
        "details": str(details),
    }
    events.append(event)
    return event


def ticket_history(events, ticket_id):
    """Chronological events for one ticket; tied timestamps ordered by event_id."""
    mine = [e for e in events if e["ticket_id"] == str(ticket_id).strip().upper()]
    return sorted(mine, key=lambda e: (parse_iso(e["timestamp"]), _number(e["event_id"])))


def escalation_marker(cycle):
    return f"cycle={cycle}"


def has_escalation_in_cycle(events, ticket_id, cycle):
    """Derived check: has this ticket already been escalated in this SLA cycle?"""
    marker = escalation_marker(cycle)
    pattern = re.compile(rf"\b{re.escape(marker)}$")
    return any(e["ticket_id"] == ticket_id and e["event_type"] == "ESCALATE"
               and pattern.search(e["details"]) for e in events)


def format_event(e):
    before = e["before_status"] or "-"
    return (f"{e['event_id']}  {e['timestamp']}  {e['ticket_id']}  "
            f"{e['event_type']:<8} {before} -> {e['after_status']}  "
            f"by {e['actor']}  {e['details']}")
