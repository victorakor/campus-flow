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
