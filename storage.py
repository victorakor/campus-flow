"""Saving and loading tickets as JSON."""

import json
import os

from config import DATA_FILE, FIELDS


def save_tickets(tickets, path=DATA_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)


def load_tickets(path=DATA_FILE):
    if not os.path.exists(path):
        return []                      # no file yet: fresh start
    try:
        with open(path, encoding="utf-8") as f:
            tickets = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"'{path}' is not valid JSON ({e}). The file was not "
                         "changed; fix or move it, then restart.")
    if not isinstance(tickets, list) or not all(
            isinstance(t, dict) and t.keys() >= set(FIELDS) for t in tickets):
        raise ValueError(f"'{path}' does not contain valid ticket data. "
                         "The file was not changed.")
    return tickets


# ---------- Schema version 2 (tickets + events) ----------
# Engineer A owns this section; implemented to the agreed contract so the CLI
# can be integrated. Keep the signatures: load_state(path) / save_state(...).

import tempfile

from clock import parse_iso
from config import (EVENT_FIELDS, EVENT_TYPES, PRIORITIES, SCHEMA_VERSION, STATUSES,
                    TICKET_FIELDS_V2)


def validate_state(data, path="data"):
    """Raise ValueError for anything malformed or inconsistent."""
    def bad(msg):
        raise ValueError(f"'{path}' is invalid: {msg}. The file was not changed.")

    if isinstance(data, list):
        bad("this is the old list-style format (migration is a separate, user-invoked step)")
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        bad(f"expected an object with schema_version {SCHEMA_VERSION}")
    tickets, events = data.get("tickets"), data.get("events")
    if not isinstance(tickets, list) or not isinstance(events, list):
        bad("'tickets' and 'events' must both be lists")
    ids = set()
    for t in tickets:
        if not isinstance(t, dict) or not set(TICKET_FIELDS_V2) <= t.keys():
            bad("a ticket is missing required fields")
        if (t["status"] not in STATUSES or t["priority"] not in PRIORITIES
                or not isinstance(t["escalation_cycle"], int)
                or isinstance(t["escalation_cycle"], bool) or t["escalation_cycle"] < 0):
            bad(f"ticket {t.get('id')} has an invalid status, priority or cycle")
        if not (isinstance(t["id"], str) and t["id"][:1] == "T" and t["id"][1:].isdigit()):
            bad(f"bad ticket id {t['id']!r}")
        if t["id"] in ids:
            bad(f"duplicate ticket id {t['id']}")
        ids.add(t["id"])
        try:
            for f in ("created_at", "updated_at", "due_at"):
                parse_iso(t[f])
        except (ValueError, TypeError):
            bad(f"ticket {t['id']} has a bad timestamp")
    event_ids = set()
    for e in events:
        if not isinstance(e, dict) or not set(EVENT_FIELDS) <= e.keys():
            bad("an event is missing required fields")
        if not (isinstance(e["event_id"], str) and e["event_id"][:1] == "E"
                and e["event_id"][1:].isdigit()) or e["event_id"] in event_ids:
            bad(f"bad or duplicate event id {e.get('event_id')!r}")
        event_ids.add(e["event_id"])
        if e["event_type"] not in EVENT_TYPES or e["ticket_id"] not in ids:
            bad(f"event {e['event_id']} has an unknown type or ticket")
        if e["after_status"] not in STATUSES or e["before_status"] not in STATUSES + [None]:
            bad(f"event {e['event_id']} has an invalid status")
        try:
            parse_iso(e["timestamp"])
        except (ValueError, TypeError):
            bad(f"event {e['event_id']} has a bad timestamp")
    return tickets, events


def save_state(tickets, events, path=DATA_FILE):
    """Atomic: write a temp file in the same folder, then os.replace."""
    data = {"schema_version": SCHEMA_VERSION, "tickets": tickets, "events": events}
    validate_state(json.loads(json.dumps(data)), path)     # never save bad data
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_state(path=DATA_FILE):
    """Returns (tickets, events). Missing file = fresh start. Never mutates callers."""
    if not os.path.exists(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"'{path}' is not valid JSON ({e}). The file was not changed.")
    return validate_state(data, path)
