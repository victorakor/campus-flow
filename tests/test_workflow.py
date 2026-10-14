import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from campusflow import history
from campusflow.ticket_service import detect_duplicates
from campusflow.workflow import (assign_ticket_logged, change_status_logged,
                      create_ticket_logged)

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)      # fixed clock


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def make(tickets, events, title="Wi-Fi down", urgency="low", users=1, now=T0, **kw):
    return create_ticket_logged(tickets, events, title, "Network", urgency, users,
                                "ada", now=now, **kw)


class AuditTrailTests(unittest.TestCase):
    def test_full_lifecycle_event_sequence(self):          # B1, must-test 8
        tickets, events = [], []
        make(tickets, events)
        assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=at(1))
        change_status_logged(tickets, events, "T001", "in_progress", "bob", now=at(2))
        change_status_logged(tickets, events, "T001", "resolved", "bob", now=at(3))
        change_status_logged(tickets, events, "T001", "open", "ada", now=at(4))
        got = [(e["event_id"], e["event_type"], e["before_status"], e["after_status"])
               for e in history.ticket_history(events, "T001")]
        self.assertEqual(got, [("E001", "CREATE", None, "open"),
                               ("E002", "ASSIGN", "open", "open"),
                               ("E003", "START", "open", "in_progress"),
                               ("E004", "RESOLVE", "in_progress", "resolved"),
                               ("E005", "REOPEN", "resolved", "open")])

    def test_rejected_transition_appends_no_event(self):   # B2, must-test 2 and 9
        tickets, events = [], []
        make(tickets, events)
        before_t, before_e = [dict(t) for t in tickets], [dict(e) for e in events]
        with self.assertRaises(ValueError):                # unassigned -> in_progress
            change_status_logged(tickets, events, "T001", "in_progress", "ada", now=at(5))
        with self.assertRaises(ValueError):                # skipping a step
            change_status_logged(tickets, events, "T001", "resolved", "ada", now=at(5))
        with self.assertRaises(ValueError):                # unknown ticket
            assign_ticket_logged(tickets, events, "T099", "Bob", "ada", now=at(5))
        with self.assertRaises(ValueError):                # blank operator label
            assign_ticket_logged(tickets, events, "T001", "Bob", "  ", now=at(5))
        self.assertEqual((tickets, events), (before_t, before_e))

    def test_event_failure_rolls_back_the_change(self):
        tickets, events = [], []
        make(tickets, events)
        assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=at(1))
        before_t, before_e = [dict(t) for t in tickets], [dict(e) for e in events]
        with mock.patch("campusflow.history.append_event", side_effect=RuntimeError("disk")):
            with self.assertRaises(RuntimeError):
                change_status_logged(tickets, events, "T001", "in_progress", "bob", now=at(2))
            with self.assertRaises(RuntimeError):
                make(tickets, events, title="Other issue")
        self.assertEqual((tickets, events), (before_t, before_e))

    def test_reopen_restarts_sla_cycle_and_keeps_history(self):   # must-test 7
        tickets, events = [], []
        make(tickets, events, urgency="high", users=10)    # critical, 60 min
        t = tickets[0]
        self.assertEqual(t["due_at"], at(60).isoformat())
        assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=at(10))
        change_status_logged(tickets, events, "T001", "in_progress", "bob", now=at(20))
        change_status_logged(tickets, events, "T001", "resolved", "bob", now=at(30))
        old_events = [dict(e) for e in events]
        change_status_logged(tickets, events, "T001", "open", "ada", now=at(500))
        self.assertEqual(t["created_at"], T0.isoformat())  # unchanged
        self.assertEqual(t["due_at"], at(560).isoformat()) # new cycle
        self.assertEqual(t["escalation_cycle"], 1)
        self.assertEqual(events[:len(old_events)], old_events)   # append-only

    def test_history_orders_tied_timestamps_by_event_id(self):
        tickets, events = [], []
        make(tickets, events)
        assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=T0)   # same instant
        change_status_logged(tickets, events, "T001", "in_progress", "bob", now=T0)
        events.reverse()
        order = [e["event_id"] for e in history.ticket_history(events, "t001")]
        self.assertEqual(order, ["E001", "E002", "E003"])


class DuplicateTests(unittest.TestCase):
    def test_normalized_match_prompts_for_confirmation(self):    # B3, must-test 10
        tickets, events = [], []
        make(tickets, events, title=" Wi-Fi   Down ")
        asked = []
        t = create_ticket_logged(tickets, events, "wi-fi down", "network", "low", 1,
                                 "ada", now=at(1),
                                 confirm_duplicate=lambda ids: asked.append(ids) or True)
        self.assertEqual(asked, [["T001"]])
        self.assertEqual(t["id"], "T002")                  # confirming may create it

    def test_declined_duplicate_creates_nothing(self):          # must-test 11
        tickets, events = [], []
        make(tickets, events, title=" Wi-Fi   Down ")
        result = create_ticket_logged(tickets, events, "wi-fi down", "Network", "low",
                                      1, "ada", now=at(1),
                                      confirm_duplicate=lambda ids: False)
        self.assertIsNone(result)
        self.assertEqual((len(tickets), len(events)), (1, 1))

    def test_no_callback_counts_as_declined(self):
        tickets, events = [], []
        make(tickets, events)
        self.assertIsNone(make(tickets, events, title="WI-FI DOWN"))
        self.assertEqual(len(tickets), 1)

    def test_only_unresolved_same_category_match(self):
        tickets, events = [], []
        make(tickets, events)
        self.assertEqual(detect_duplicates(tickets, "Hardware", "Wi-Fi down"), [])
        assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=at(1))
        change_status_logged(tickets, events, "T001", "in_progress", "bob", now=at(2))
        change_status_logged(tickets, events, "T001", "resolved", "bob", now=at(3))
        self.assertEqual(detect_duplicates(tickets, "Network", "Wi-Fi down"), [])


if __name__ == "__main__":
    unittest.main()
