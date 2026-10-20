"""Saving and loading the data file: {schema_version: 2, tickets, events}.
Data is validated before it is used or saved, and writes are atomic."""

import json
import os
import re
import tempfile
from datetime import timedelta

from .logic import (CATEGORIES, SLA_MINUTES, STATUSES, TICKET_FIELDS, URGENCIES,
                    calc_priority, parse)

SCHEMA_VERSION = 2
EVENT_FIELDS = ["event_id", "ticket_id", "event_type", "actor", "timestamp",
                "before_status", "after_status", "details"]
EVENT_TYPES = ["CREATE", "ASSIGN", "START", "RESOLVE", "REOPEN", "ESCALATE"]


def need(condition, message):
    if not condition:
        raise ValueError(message)


def check(data):
    """Raise ValueError for anything malformed or inconsistent."""
    need(isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION,
         f"expected an object with schema_version {SCHEMA_VERSION} (old list files are rejected)")
    tickets, events = data["tickets"], data["events"]
    need(isinstance(tickets, list) and isinstance(events, list),
         "'tickets' and 'events' must both be lists")

    ids = set()
    for t in tickets:
        need(isinstance(t, dict) and set(TICKET_FIELDS) <= t.keys(),
             "a ticket is missing required fields")
        tid = t["id"]
        need(isinstance(tid, str) and re.fullmatch(r"T\d+", tid) and tid not in ids,
             f"bad or duplicate ticket id {tid!r}")
        ids.add(tid)
        need(isinstance(t["title"], str) and t["title"].strip(), f"{tid} has a blank title")
        need(t["category"] in CATEGORIES and t["urgency"] in URGENCIES
             and t["status"] in STATUSES, f"{tid} has an invalid category, urgency or status")
        users, who = t["affected_users"], t["assigned_to"]
        need(type(users) is int and users >= 1, f"{tid} has invalid affected_users")
        need(t["priority"] == calc_priority(t["urgency"], users),
             f"{tid} priority does not match its urgency and affected users")
        need(who is None or (isinstance(who, str) and who.strip()),
             f"{tid} has an invalid assigned_to")
        need(t["status"] != "in_progress" or who, f"{tid} is in_progress but unassigned")
        need(type(t["escalation_cycle"]) is int and t["escalation_cycle"] >= 0,
             f"{tid} has an invalid escalation_cycle")
        created, updated, due = (parse(t[k]) for k in ("created_at", "updated_at", "due_at"))
        need(updated >= created, f"{tid} was updated before it was created")
        need(due >= created + timedelta(minutes=SLA_MINUTES[t["priority"]]),
             f"{tid} due_at is earlier than its SLA allows")

    event_ids = set()
    for e in events:
        need(isinstance(e, dict) and set(EVENT_FIELDS) <= e.keys(),
             "an event is missing required fields")
        eid = e["event_id"]
        need(isinstance(eid, str) and re.fullmatch(r"E\d+", eid) and eid not in event_ids,
             f"bad or duplicate event id {eid!r}")
        event_ids.add(eid)
        need(e["ticket_id"] in ids and e["event_type"] in EVENT_TYPES,
             f"event {eid} has an unknown type or ticket")
        need(e["after_status"] in STATUSES and e["before_status"] in STATUSES + [None],
             f"event {eid} has an invalid status")
        need((e["before_status"] is None) == (e["event_type"] == "CREATE"),
             f"event {eid}: only CREATE may have no before_status")
        need(isinstance(e["actor"], str) and e["actor"].strip()
             and isinstance(e["details"], str), f"event {eid} has an invalid actor or details")
        parse(e["timestamp"])


def validate(data, path):
    try:
        check(data)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise ValueError(f"'{path}' is invalid: {e}. The file was not changed.")
    return data["tickets"], data["events"]


def save_state(tickets, events, path):
    """Validate, write a temp file next to the target, then os.replace it.
    A crash mid-write leaves the old file intact; bad data is never written."""
    data = {"schema_version": SCHEMA_VERSION, "tickets": tickets, "events": events}
    validate(json.loads(json.dumps(data)), path)
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


def load_state(path):
    """Returns (tickets, events). Missing file = fresh start. A damaged file raises
    ValueError and is never overwritten."""
    if not os.path.exists(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:                      # bad JSON or undecodable text
        raise ValueError(f"'{path}' is not valid JSON ({e}). The file was not changed.")
    return validate(data, path)
