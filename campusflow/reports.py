"""Read-only SLA queue and metrics. Nothing here modifies tickets or events."""

from .clock import parse_iso, utc_now
from .config import PRIORITIES
from .history import has_escalation_in_cycle
from .sla import is_overdue


def sla_attention_queue(tickets, now=None):
    """Unresolved tickets: overdue first, then earliest due_at, then ticket number."""
    now = now or utc_now()
    pending = [t for t in tickets if t["status"] != "resolved"]
    return sorted(pending, key=lambda t: (not is_overdue(t, now),
                                          parse_iso(t["due_at"]),
                                          int(t["id"][1:])))


def sla_metrics(tickets, events, now=None):
    """Each ticket is counted once per metric."""
    now = now or utc_now()
    unresolved = [t for t in tickets if t["status"] != "resolved"]
    return {
        "open": sum(t["status"] == "open" for t in tickets),
        "in_progress": sum(t["status"] == "in_progress" for t in tickets),
        "resolved": sum(t["status"] == "resolved" for t in tickets),
        "overdue_unresolved": sum(is_overdue(t, now) for t in unresolved),
        "escalated_current_cycle": sum(
            has_escalation_in_cycle(events, t["id"], t["escalation_cycle"])
            for t in unresolved),
        "by_priority": {p: sum(t["priority"] == p for t in tickets) for p in PRIORITIES},
    }
