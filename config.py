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
