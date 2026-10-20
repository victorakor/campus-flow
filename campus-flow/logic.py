"""CampusFlow core rules: validation, priority, workflow, SLA, escalation,
audit history and reports. Pure Python, no file access (see storage.py)."""

from datetime import datetime, timedelta, timezone

CATEGORIES = ["Network", "Hardware", "Software", "Other"]
URGENCIES = ["low", "medium", "high"]
PRIORITIES = ["critical", "high", "medium", "low"]            # queue order
STATUSES = ["open", "in_progress", "resolved"]
NEXT_STATUS = {"open": "in_progress", "in_progress": "resolved", "resolved": "open"}
EVENT_FOR = {"in_progress": "START", "resolved": "RESOLVE", "open": "REOPEN"}
SLA_MINUTES = {"critical": 60, "high": 240, "medium": 1440, "low": 2880}
FIELDS = ["id", "title", "category", "urgency", "affected_users", "priority",
          "status", "assigned_to"]
TICKET_FIELDS = FIELDS + ["created_at", "updated_at", "due_at", "escalation_cycle"]


# ---------- Small helpers ----------


def parse(text):
    """ISO-8601 text with an explicit offset -> aware UTC datetime."""
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{text}' is not a valid ISO-8601 time.")
    if moment.tzinfo is None:
        raise ValueError(f"'{text}' needs a timezone, e.g. 2026-10-14T10:00:00+00:00.")
    return moment.astimezone(timezone.utc)


def ask(prompt, cleaner, input_fn=None, output_fn=None):
    """Keep asking until `cleaner` accepts the answer (it raises ValueError if not)."""
    while True:
        try:
            return cleaner((input_fn or input)(prompt))
        except ValueError as e:
            (output_fn or print)(f"  Error: {e}")


def clean_actor(value):
    """Operator label for traceability (not verified identity)."""
    actor = " ".join(str(value).split())
    if not actor:
        raise ValueError("Operator label must not be blank.")
    return actor


def clean_fields(title, category, urgency, users):
    """Validate and clean the four user-entered ticket fields."""
    def choice(value, options, label):
        for option in options:
            if str(value).strip().lower() == option.lower():
                return option
        raise ValueError(f"Invalid {label} '{value}'. Choose from: {', '.join(options)}.")

    title = str(title).strip()
    if not title:
        raise ValueError("Title must not be blank.")
    text = str(users).strip()
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise ValueError(f"Affected users must be a positive whole number (got '{users}').")
    return (title, choice(category, CATEGORIES, "category"),
            choice(urgency, URGENCIES, "urgency"), int(text))


def calc_priority(urgency, users):
    """First matching rule wins."""
    if urgency == "high" and users >= 10:
        return "critical"
    if urgency == "high" or users >= 10:
        return "high"
    if urgency == "medium" or users >= 3:
        return "medium"
    return "low"



def find_ticket(tickets, ticket_id):
    for t in tickets:
        if t["id"] == str(ticket_id).strip().upper():
            return t
    raise ValueError(f"Unknown ticket ID '{ticket_id}'.")


# ---------- Audit trail (append-only) ----------

def log(events, ticket_id, kind, actor, when, before, after, details=""):
    """Append one event. Call it only AFTER the operation has succeeded."""
    number = max((int(e["event_id"][1:]) for e in events), default=0) + 1
    events.append({"event_id": f"E{number:03d}", "ticket_id": ticket_id,
                   "event_type": kind, "actor": clean_actor(actor),
                   "timestamp": when.isoformat(), "before_status": before,
                   "after_status": after, "details": details})


def ticket_history(events, ticket_id):
    """Chronological events of one ticket (ties ordered by event number)."""
    mine = [e for e in events if e["ticket_id"] == ticket_id]
    return sorted(mine, key=lambda e: (parse(e["timestamp"]), int(e["event_id"][1:])))


# ---------- Ticket operations (validate first, then change, then log) ----------

def create_ticket(tickets, events, title, category, urgency, users, actor,
                  when=None, confirm=None):
    """Returns the new ticket, or None if the user declined the duplicate warning."""
    actor, when = clean_actor(actor), when or now()
    title, category, urgency, users = clean_fields(title, category, urgency, users)

    same = lambda text: " ".join(text.split()).casefold()
    dupes = [t["id"] for t in tickets
             if t["status"] != "resolved" and t["category"] == category
             and same(t["title"]) == same(title)]
    if dupes and not (confirm and confirm(dupes)):
        return None                                   # declined: nothing changes

    priority = calc_priority(urgency, users)
    number = max((int(t["id"][1:]) for t in tickets), default=0) + 1
    ticket = {"id": f"T{number:03d}", "title": title, "category": category,
              "urgency": urgency, "affected_users": users, "priority": priority,
              "status": "open", "assigned_to": None, "created_at": when.isoformat(),
              "updated_at": when.isoformat(), "due_at": due_at(priority, when),
              "escalation_cycle": 0}
    tickets.append(ticket)
    log(events, ticket["id"], "CREATE", actor, when, None, "open",
        f"Created with priority {priority}; due {ticket['due_at']}")
    return ticket


def assign_ticket(tickets, events, ticket_id, name, actor, when=None):
    actor, when = clean_actor(actor), when or now()
    ticket = find_ticket(tickets, ticket_id)
    name = str(name).strip()
    if not name:
        raise ValueError("Staff member name must not be blank.")
    if ticket["status"] == "resolved":
        raise ValueError(f"{ticket['id']} is resolved. Reopen it before changing it.")
    ticket["assigned_to"], ticket["updated_at"] = name, when.isoformat()
    log(events, ticket["id"], "ASSIGN", actor, when, ticket["status"],
        ticket["status"], f"Assigned to {name}")
    return ticket


def change_status(tickets, events, ticket_id, new_status, actor, when=None):
    """START / RESOLVE / REOPEN. Reopening begins a NEW SLA cycle."""
    actor, when = clean_actor(actor), when or now()
    ticket = find_ticket(tickets, ticket_id)
    old = ticket["status"]
    if NEXT_STATUS[old] != new_status:
        raise ValueError(f"{ticket['id']} is '{old}'; it can only move to '{NEXT_STATUS[old]}'.")
    if new_status == "in_progress" and not ticket["assigned_to"]:
        raise ValueError(f"{ticket['id']} is unassigned. Assign it before starting work.")
    details = f"Status {old} -> {new_status}"
    ticket["status"], ticket["updated_at"] = new_status, when.isoformat()
    if new_status == "open":
        ticket["escalation_cycle"] += 1
        ticket["due_at"] = due_at(ticket["priority"], when)
        details += f"; new SLA cycle {ticket['escalation_cycle']}, due {ticket['due_at']}"
    log(events, ticket["id"], EVENT_FOR[new_status], actor, when, old, new_status, details)
    return ticket



# ---------- Queues and reports (read-only) ----------

def work_queue(tickets):
    """Original queue: unresolved, critical first, ties to the lower ticket number."""
    pending = [t for t in tickets if t["status"] != "resolved"]
    return sorted(pending, key=lambda t: (PRIORITIES.index(t["priority"]), int(t["id"][1:])))


def sla_queue(tickets, when=None):
    """Unresolved: overdue first, then earliest due_at, then ticket number."""
    when = when or now()
    pending = [t for t in tickets if t["status"] != "resolved"]
    return sorted(pending, key=lambda t: (not is_overdue(t, when), parse(t["due_at"]),
                                          int(t["id"][1:])))


def report(tickets, events, when=None):
    when = when or now()
    pending = [t for t in tickets if t["status"] != "resolved"]
    return {"total": len(tickets),
            "status": {s: sum(t["status"] == s for t in tickets) for s in STATUSES},
            "priority": {p: sum(t["priority"] == p for t in tickets) for p in PRIORITIES},
            "overdue": sum(is_overdue(t, when) for t in pending),
            "escalated": sum(escalated(events, t) for t in pending)}
