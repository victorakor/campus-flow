"""Saving and loading tickets as JSON."""

import json
import os

from .config import DATA_FILE, FIELDS


def save_tickets(tickets, path=DATA_FILE):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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

import shutil
import tempfile
from datetime import timedelta

from .clock import parse_iso, to_iso, utc_now
from .config import (CATEGORIES, EVENT_FIELDS, EVENT_TYPES, PRIORITIES, SCHEMA_VERSION,
                    SLA_MINUTES, STATUSES, TICKET_FIELDS_V2, URGENCIES)
from .sla import calculate_due_at
from .ticket_service import calculate_priority

LEGACY_BACKUP_SUFFIX = ".legacy-backup"


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_state(data, path="data"):
    """Raise ValueError for anything malformed or inconsistent. Pure: it only
    reads ``data``, so callers' in-memory state is never touched."""
    def bad(msg):
        raise ValueError(f"'{path}' is invalid: {msg}. The file was not changed.")

    if isinstance(data, list):
        bad("this is the old list-style format (migration is a separate, user-invoked "
            "step: python main.py --migrate)")
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        bad(f"expected an object with schema_version {SCHEMA_VERSION}")
    tickets, events = data.get("tickets"), data.get("events")
    if not isinstance(tickets, list) or not isinstance(events, list):
        bad("'tickets' and 'events' must both be lists")

    ids = set()
    for t in tickets:
        if not isinstance(t, dict) or not set(TICKET_FIELDS_V2) <= t.keys():
            bad("a ticket is missing required fields")
        if not (isinstance(t["id"], str) and t["id"][:1] == "T" and t["id"][1:].isdigit()):
            bad(f"bad ticket id {t['id']!r}")
        if t["id"] in ids:
            bad(f"duplicate ticket id {t['id']}")
        ids.add(t["id"])
        tid = t["id"]
        if not isinstance(t["title"], str) or not t["title"].strip():
            bad(f"ticket {tid} has a blank or non-text title")
        if (t["category"] not in CATEGORIES or t["urgency"] not in URGENCIES
                or t["status"] not in STATUSES or t["priority"] not in PRIORITIES):
            bad(f"ticket {tid} has an invalid category, urgency, status or priority")
        if not _is_int(t["affected_users"]) or t["affected_users"] < 1:
            bad(f"ticket {tid} has invalid affected_users")
        if calculate_priority(t["urgency"], t["affected_users"]) != t["priority"]:
            bad(f"ticket {tid} priority does not match its urgency and affected users")
        assigned = t["assigned_to"]
        if assigned is not None and (not isinstance(assigned, str) or not assigned.strip()):
            bad(f"ticket {tid} has an invalid assigned_to")
        if t["status"] == "in_progress" and assigned is None:
            bad(f"ticket {tid} is in_progress but unassigned")
        if not _is_int(t["escalation_cycle"]) or t["escalation_cycle"] < 0:
            bad(f"ticket {tid} has an invalid escalation_cycle")
        try:
            created, updated, due = (parse_iso(t[f]) for f in
                                     ("created_at", "updated_at", "due_at"))
        except (ValueError, TypeError):
            bad(f"ticket {tid} has a bad timestamp")
        if updated < created:
            bad(f"ticket {tid} was updated before it was created")
        if due < created + timedelta(minutes=SLA_MINUTES[t["priority"]]):
            bad(f"ticket {tid} due_at is earlier than its SLA allows")

    event_ids = set()
    for e in events:
        if not isinstance(e, dict) or not set(EVENT_FIELDS) <= e.keys():
            bad("an event is missing required fields")
        if not (isinstance(e["event_id"], str) and e["event_id"][:1] == "E"
                and e["event_id"][1:].isdigit()) or e["event_id"] in event_ids:
            bad(f"bad or duplicate event id {e.get('event_id')!r}")
        event_ids.add(e["event_id"])
        if (not isinstance(e["ticket_id"], str) or e["ticket_id"] not in ids
                or e["event_type"] not in EVENT_TYPES):
            bad(f"event {e['event_id']} has an unknown type or ticket")
        if e["after_status"] not in STATUSES or e["before_status"] not in STATUSES + [None]:
            bad(f"event {e['event_id']} has an invalid status")
        if (e["before_status"] is None) != (e["event_type"] == "CREATE"):
            bad(f"event {e['event_id']}: only CREATE may have no before_status")
        if (not isinstance(e["actor"], str) or not e["actor"].strip()
                or not isinstance(e["details"], str)):
            bad(f"event {e['event_id']} has an invalid actor or details")
        try:
            parse_iso(e["timestamp"])
        except (ValueError, TypeError):
            bad(f"event {e['event_id']} has a bad timestamp")
    return tickets, events


def save_state(tickets, events, path=DATA_FILE):
    """Atomic: validate, write a temp file in the same folder, fsync, os.replace.
    A crash before os.replace leaves the old file untouched; invalid data is
    refused before any file is created."""
    data = {"schema_version": SCHEMA_VERSION, "tickets": tickets, "events": events}
    validate_state(json.loads(json.dumps(data)), path)     # never save bad data
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
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
    """Returns (tickets, events). Missing file = fresh start. Validation finishes
    BEFORE anything is returned, so a bad file can never half-replace live state."""
    if not os.path.exists(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"'{path}' is not valid JSON ({e}). The file was not changed.")
    except UnicodeDecodeError as e:
        raise ValueError(f"'{path}' is not readable text ({e}). The file was not changed.")
    return validate_state(data, path)


# ---------- Optional stretch: explicit legacy migration ----------

def is_legacy_format(path=DATA_FILE):
    """True if the file is a readable old list-style CampusFlow file."""
    try:
        with open(path, encoding="utf-8") as f:
            return isinstance(json.load(f), list)
    except (OSError, ValueError):
        return False


def migrate_legacy(src=DATA_FILE, dest=None, now=None):
    """User-invoked only. Reads an old list-style file and writes schema v2.

    * The original is copied byte-for-byte to '<src>.legacy-backup' first; the
      backup is never overwritten.
    * Nothing historic is invented: the legacy file has no timestamps, so
      created_at/updated_at/due_at are set to the MIGRATION moment, and no events
      are created. Old tickets therefore start with an empty history.
    * Everything is validated in memory before any file is written."""
    dest = dest or src
    if not os.path.exists(src):
        raise ValueError(f"'{src}' does not exist; nothing to migrate.")
    legacy = load_tickets(src)                          # validates the legacy shape
    if os.path.abspath(dest) != os.path.abspath(src) and os.path.exists(dest):
        raise ValueError(f"'{dest}' already exists; refusing to overwrite it.")
    backup = src + LEGACY_BACKUP_SUFFIX
    if os.path.exists(backup):
        raise ValueError(f"Backup '{backup}' already exists; move it away first.")
    moment = now or utc_now()
    stamp = to_iso(moment)
    tickets = []
    for t in legacy:
        ticket = {k: t[k] for k in FIELDS}
        ticket.update(created_at=stamp, updated_at=stamp,
                      due_at=to_iso(calculate_due_at(t["priority"], moment)),
                      escalation_cycle=0)
        tickets.append(ticket)
    validate_state(json.loads(json.dumps(
        {"schema_version": SCHEMA_VERSION, "tickets": tickets, "events": []})), src)
    shutil.copy2(src, backup)
    save_state(tickets, [], dest)
    return {"migrated": len(tickets), "backup": backup, "dest": dest}
