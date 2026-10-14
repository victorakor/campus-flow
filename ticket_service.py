"""Core ticket logic: priority rules, workflow, queue and reports."""

from clock import to_iso, utc_now
from config import CATEGORIES, NEXT_STATUS, PRIORITIES, STATUSES, URGENCIES
from sla import calculate_due_at
from validation import clean_choice, clean_title, clean_users


# ---------- Priority (checked in order, first match wins) ----------

def calculate_priority(urgency, affected_users):
    if urgency == "high" and affected_users >= 10:
        return "critical"
    if urgency == "high" or affected_users >= 10:
        return "high"
    if urgency == "medium" or affected_users >= 3:
        return "medium"
    return "low"


# ---------- Ticket operations ----------

def create_ticket(tickets, title, category, urgency, users, now=None):
    title = clean_title(title)
    category = clean_choice(category, CATEGORIES, "category")
    urgency = clean_choice(urgency, URGENCIES, "urgency")
    users = clean_users(users)

    now = now or utc_now()
    priority = calculate_priority(urgency, users)
    last_number = max((int(t["id"][1:]) for t in tickets), default=0)
    ticket = {
        "id": f"T{last_number + 1:03d}",
        "title": title,
        "category": category,
        "urgency": urgency,
        "affected_users": users,
        "priority": priority,
        "status": "open",
        "assigned_to": None,
        "created_at": to_iso(now),
        "updated_at": to_iso(now),
        "due_at": to_iso(calculate_due_at(priority, now)),
        "escalation_cycle": 0,
    }
    tickets.append(ticket)
    return ticket


def normalize_title(title):
    """Trim, casefold and collapse repeated whitespace."""
    return " ".join(str(title).split()).casefold()


def detect_duplicates(tickets, category, title):
    """IDs of UNRESOLVED tickets with the same normalized title and category.
    Read-only: it only warns, it never blocks."""
    wanted = (normalize_title(title), clean_choice(category, CATEGORIES, "category"))
    return [t["id"] for t in tickets
            if t["status"] != "resolved"
            and (normalize_title(t["title"]), t["category"]) == wanted]


def find_ticket(tickets, ticket_id):
    for ticket in tickets:
        if ticket["id"] == str(ticket_id).strip().upper():
            return ticket
    raise ValueError(f"Unknown ticket ID '{ticket_id}'.")


def assign_ticket(tickets, ticket_id, name):
    ticket = find_ticket(tickets, ticket_id)
    if not str(name).strip():
        raise ValueError("Staff member name must not be blank.")
    if ticket["status"] == "resolved":
        raise ValueError(f"{ticket['id']} is resolved. Reopen it before changing it.")
    ticket["assigned_to"] = str(name).strip()
    return ticket


def change_status(tickets, ticket_id, new_status):
    ticket = find_ticket(tickets, ticket_id)
    current = ticket["status"]
    if NEXT_STATUS[current] != new_status:
        raise ValueError(f"{ticket['id']} is '{current}'; it can only move to "
                         f"'{NEXT_STATUS[current]}'.")
    if new_status == "in_progress" and not ticket["assigned_to"]:
        raise ValueError(f"{ticket['id']} is unassigned. Assign it before starting work.")
    ticket["status"] = new_status
    return ticket


def work_queue(tickets):
    """Unresolved tickets, critical first; ties go to the lower ticket number."""
    pending = [t for t in tickets if t["status"] != "resolved"]
    return sorted(pending, key=lambda t: (PRIORITIES.index(t["priority"]),
                                          int(t["id"][1:])))

def report(tickets):
    return {
        "total": len(tickets),
        "status": {s: sum(t["status"] == s for t in tickets) for s in STATUSES},
        "priority": {p: sum(t["priority"] == p for t in tickets) for p in PRIORITIES},
    }
