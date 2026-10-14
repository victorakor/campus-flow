import unittest
from datetime import datetime, timedelta, timezone

from campusflow.reports import sla_attention_queue, sla_metrics
from campusflow.sla import escalate_overdue
from campusflow.workflow import (assign_ticket_logged, change_status_logged,
                      create_ticket_logged)

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


def ids(tickets):
    return [t["id"] for t in tickets]


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def add(tickets, events, title, urgency, users, now=T0):
    return create_ticket_logged(tickets, events, title, "Network", urgency, users,
                                "ada", now=now)


class SlaQueueTests(unittest.TestCase):
    def test_overdue_first_then_due_at_then_id(self):          # B4, must-test 12
        tickets, events = [], []
        add(tickets, events, "a", "low", 1)                    # T001 low: due +2880
        add(tickets, events, "b", "high", 10)                  # T002 critical: due +60
        add(tickets, events, "c", "medium", 1)                 # T003 medium: due +1440
        add(tickets, events, "d", "low", 1, now=T0 - timedelta(minutes=2000))  # T004 due +880
        add(tickets, events, "e", "high", 10)                  # T005 critical: due +60 (tie)
        # at +61: T002/T005 overdue (tie -> ids), T004 due +880 next, T003, T001
        self.assertEqual(ids(sla_attention_queue(tickets, at(61))),
                         ["T002", "T005", "T004", "T003", "T001"])
        # at +30 nothing overdue: pure due_at order, tie broken by ID
        self.assertEqual(ids(sla_attention_queue(tickets, at(30))),
                         ["T002", "T005", "T004", "T003", "T001"])

    def test_overdue_beats_earlier_due_date(self):
        tickets, events = [], []
        add(tickets, events, "a", "low", 1, now=T0 - timedelta(minutes=2900))  # overdue
        add(tickets, events, "b", "high", 10, now=T0)                           # due +60
        self.assertEqual(ids(sla_attention_queue(tickets, at(10))), ["T001", "T002"])

    def test_resolved_excluded_and_boundary_not_overdue(self):
        tickets, events = [], []
        add(tickets, events, "a", "high", 10)
        add(tickets, events, "b", "high", 10)
        assign_ticket_logged(tickets, events, "T002", "Bob", "ada", now=at(1))
        change_status_logged(tickets, events, "T002", "in_progress", "bob", now=at(2))
        change_status_logged(tickets, events, "T002", "resolved", "bob", now=at(3))
        self.assertEqual(ids(sla_attention_queue(tickets, at(60))), ["T001"])


class MetricsTests(unittest.TestCase):
    def test_metrics_count_each_ticket_once(self):
        tickets, events = [], []
        add(tickets, events, "a", "high", 10)                  # T001 overdue + escalated
        add(tickets, events, "b", "low", 1)                    # T002 on time
        add(tickets, events, "c", "high", 10)                  # T003 resolved
        assign_ticket_logged(tickets, events, "T003", "Bob", "ada", now=at(1))
        change_status_logged(tickets, events, "T003", "in_progress", "bob", now=at(2))
        change_status_logged(tickets, events, "T003", "resolved", "bob", now=at(3))
        escalate_overdue(tickets, events, at(61), "ada")
        escalate_overdue(tickets, events, at(62), "ada")       # repeat: no double count
        m = sla_metrics(tickets, events, at(62))
        self.assertEqual((m["open"], m["in_progress"], m["resolved"]), (2, 0, 1))
        self.assertEqual((m["overdue_unresolved"], m["escalated_current_cycle"]), (1, 1))
        self.assertEqual(m["by_priority"], {"critical": 2, "high": 0, "medium": 0, "low": 1})
        self.assertEqual(sum(m["by_priority"].values()), 3)

    def test_metrics_do_not_modify_data(self):
        tickets, events = [], []
        add(tickets, events, "a", "high", 10)
        snap = ([dict(t) for t in tickets], [dict(e) for e in events])
        sla_metrics(tickets, events, at(99))
        sla_attention_queue(tickets, at(99))
        self.assertEqual((tickets, events), snap)


if __name__ == "__main__":
    unittest.main()
