"""Engineer A: SLA rules and idempotent escalation (checkpoints A1-A4, A6).
Every test uses a FIXED UTC clock; nothing waits or reads the real time."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from sla import calculate_due_at, escalate_overdue, is_overdue
from workflow import (assign_ticket_logged, change_status_logged,
                      create_ticket_logged)

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def make(tickets, events, urgency="high", users=10, title="Server down", now=T0):
    """high + 10 users = critical (60 min SLA)."""
    return create_ticket_logged(tickets, events, title, "Network", urgency, users,
                                "ada", now=now)


def escalations(events, ticket_id=None):
    return [e for e in events if e["event_type"] == "ESCALATE"
            and ticket_id in (None, e["ticket_id"])]


class DueDateTests(unittest.TestCase):
    def test_sla_minutes_per_priority(self):
        expected = {"critical": 60, "high": 240, "medium": 1440, "low": 2880}
        for priority, minutes in expected.items():
            self.assertEqual(calculate_due_at(priority, T0), T0 + timedelta(minutes=minutes))

    def test_unknown_priority_rejected(self):
        with self.assertRaises(ValueError):
            calculate_due_at("urgent", T0)

    def test_new_ticket_due_at_is_created_at_plus_sla(self):
        tickets, events = [], []
        t = make(tickets, events)
        self.assertEqual(t["priority"], "critical")
        self.assertEqual(t["due_at"], "2026-10-14T11:00:00+00:00")
        self.assertEqual(t["escalation_cycle"], 0)


class OverdueBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tickets, self.events = [], []
        self.ticket = make(self.tickets, self.events)

    def test_a1_exactly_60_minutes_is_not_overdue(self):
        self.assertFalse(is_overdue(self.ticket, at(60)))

    def test_a2_61_minutes_is_overdue(self):
        self.assertTrue(is_overdue(self.ticket, at(61)))

    def test_one_second_after_due_is_overdue(self):
        self.assertTrue(is_overdue(self.ticket, at(60) + timedelta(seconds=1)))

    def test_resolved_ticket_is_never_overdue(self):
        assign_ticket_logged(self.tickets, self.events, "T001", "Bob", "ada", now=at(1))
        change_status_logged(self.tickets, self.events, "T001", "in_progress", "bob", now=at(2))
        change_status_logged(self.tickets, self.events, "T001", "resolved", "bob", now=at(3))
        self.assertFalse(is_overdue(self.ticket, at(10_000)))

    def test_in_progress_ticket_can_be_overdue(self):
        assign_ticket_logged(self.tickets, self.events, "T001", "Bob", "ada", now=at(1))
        change_status_logged(self.tickets, self.events, "T001", "in_progress", "bob", now=at(2))
        self.assertTrue(is_overdue(self.ticket, at(61)))


class EscalationTests(unittest.TestCase):
    def setUp(self):
        self.tickets, self.events = [], []
        make(self.tickets, self.events)                          # T001 critical

    def test_not_overdue_means_no_escalation(self):
        r = escalate_overdue(self.tickets, self.events, at(60), "ada")   # exactly due
        self.assertEqual((r["newly_escalated"], r["already_escalated"]), (0, 0))
        self.assertEqual(escalations(self.events), [])

    def test_a3_running_twice_creates_exactly_one_event(self):
        first = escalate_overdue(self.tickets, self.events, at(61), "ada")
        second = escalate_overdue(self.tickets, self.events, at(61), "ada")
        later = escalate_overdue(self.tickets, self.events, at(500), "bob")
        self.assertEqual((first["newly_escalated"], first["already_escalated"]), (1, 0))
        self.assertEqual((second["newly_escalated"], second["already_escalated"]), (0, 1))
        self.assertEqual((later["newly_escalated"], later["already_escalated"]), (0, 1))
        self.assertEqual(len(escalations(self.events)), 1)

    def test_escalation_changes_nothing_on_the_ticket(self):
        before = dict(self.tickets[0])
        escalate_overdue(self.tickets, self.events, at(61), "ada")
        self.assertEqual(self.tickets[0], before)        # no assign / priority / status change

    def test_only_overdue_tickets_escalate_and_counts_are_not_doubled(self):
        make(self.tickets, self.events, urgency="low", users=1, title="Slow printer")  # T002 low
        make(self.tickets, self.events, title="VPN down", now=at(30))                  # T003 due at 90
        r = escalate_overdue(self.tickets, self.events, at(61), "ada")
        self.assertEqual(r["new_ids"], ["T001"])                 # T002/T003 not overdue yet
        r = escalate_overdue(self.tickets, self.events, at(91), "ada")
        self.assertEqual((r["new_ids"], r["already_ids"]), (["T003"], ["T001"]))

    def test_a4_reopen_starts_new_cycle_and_can_escalate_again(self):
        escalate_overdue(self.tickets, self.events, at(61), "ada")            # cycle 0
        assign_ticket_logged(self.tickets, self.events, "T001", "Bob", "ada", now=at(62))
        change_status_logged(self.tickets, self.events, "T001", "in_progress", "bob", now=at(63))
        change_status_logged(self.tickets, self.events, "T001", "resolved", "bob", now=at(64))
        t = change_status_logged(self.tickets, self.events, "T001", "open", "ada", now=at(200))
        self.assertEqual(t["created_at"], "2026-10-14T10:00:00+00:00")       # preserved
        self.assertEqual(t["due_at"], "2026-10-14T14:20:00+00:00")           # 200 + 60 min
        self.assertEqual(t["escalation_cycle"], 1)
        self.assertEqual(escalate_overdue(self.tickets, self.events, at(260), "ada")["newly_escalated"], 0)
        r = escalate_overdue(self.tickets, self.events, at(261), "ada")      # overdue in cycle 1
        self.assertEqual(r["newly_escalated"], 1)
        self.assertEqual(len(escalations(self.events, "T001")), 2)           # history kept

    def test_a6_failed_run_leaves_events_untouched(self):
        make(self.tickets, self.events, title="Second outage")               # T002
        before = [dict(e) for e in self.events]
        with self.assertRaises(ValueError):                                  # blank actor
            escalate_overdue(self.tickets, self.events, at(61), "   ")
        real = __import__("history").append_event
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real(*a, **k)

        with mock.patch("history.append_event", side_effect=flaky):
            with self.assertRaises(RuntimeError):                            # fails on 2nd ticket
                escalate_overdue(self.tickets, self.events, at(61), "ada")
        self.assertEqual(self.events, before)                                # no partial run


if __name__ == "__main__":
    unittest.main()
