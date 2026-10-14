"""Shared constants for CampusFlow."""

DATA_FILE = "tickets.json"

CATEGORIES = ["Network", "Hardware", "Software", "Other"]
URGENCIES = ["low", "medium", "high"]
PRIORITIES = ["critical", "high", "medium", "low"]   # queue order
STATUSES = ["open", "in_progress", "resolved"]
FIELDS = ["id", "title", "category", "urgency", "affected_users",
          "priority", "status", "assigned_to"]

# Allowed workflow moves: current status -> the one status it may move to.
NEXT_STATUS = {"open": "in_progress", "in_progress": "resolved", "resolved": "open"}


# ---- CampusFlow Pro additions ----
SCHEMA_VERSION = 2
TICKET_FIELDS_V2 = FIELDS + ["created_at", "updated_at", "due_at", "escalation_cycle"]
EVENT_FIELDS = ["event_id", "ticket_id", "event_type", "actor", "timestamp",
                "before_status", "after_status", "details"]
EVENT_TYPES = ["CREATE", "ASSIGN", "START", "RESOLVE", "REOPEN", "ESCALATE"]
# status we are moving INTO -> audit event type
STATUS_EVENT = {"in_progress": "START", "resolved": "RESOLVE", "open": "REOPEN"}
SLA_MINUTES = {"critical": 60, "high": 240, "medium": 1440, "low": 2880}
LAB_SESSIONS_DIR = "lab_sessions"
