"""All tests for CampusFlow Pro. Run from the project root:  python -m unittest -v"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import main
from campusflow import lab, logic, storage

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


def make(*specs, actor="ana"):
    """Create tickets at T0. spec = (title, category, urgency, users)."""
    tickets, events = [], []
    for s in specs:
        logic.create_ticket(tickets, events, *s, actor, when=T0)
    return tickets, events


class ValidationAndPriority(unittest.TestCase):
    def test_priority_rules_and_boundaries(self):
        cases = [("high", 10, "critical"), ("high", 9, "high"), ("low", 10, "high"),
                 ("medium", 1, "medium"), ("low", 3, "medium"), ("low", 2, "low")]
        for urgency, users, expected in cases:
            self.assertEqual(logic.calc_priority(urgency, users), expected)

    def test_clean_fields_accepts_any_case_and_trims(self):
        self.assertEqual(logic.clean_fields("  VPN ", " network ", "HIGH", " 5 "),
                         ("VPN", "Network", "high", 5))

    def test_clean_fields_rejects_bad_input(self):
        for bad in [("  ", "Network", "low", "1"), ("x", "Cloud", "low", "1"),
                    ("x", "Network", "urgent", "1"), ("x", "Network", "low", "0"),
                    ("x", "Network", "low", "-2"), ("x", "Network", "low", "1.5"),
                    ("x", "Network", "low", "abc")]:
            with self.assertRaises(ValueError):
                logic.clean_fields(*bad)

    def test_blank_actor_rejected(self):
        with self.assertRaises(ValueError):
            logic.clean_actor("   ")


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tickets, self.events = make(("Wifi down", "Network", "high", 12))

    def test_ids_are_automatic(self):
        logic.create_ticket(self.tickets, self.events, "B", "Other", "low", 1, "ana", T0)
        self.assertEqual([t["id"] for t in self.tickets], ["T001", "T002"])

    def test_full_cycle_logs_events_and_reopen_starts_new_sla_cycle(self):
        later = T0 + timedelta(hours=5)
        logic.assign_ticket(self.tickets, self.events, "t001", "Sam", "ana", T0)
        logic.change_status(self.tickets, self.events, "T001", "in_progress", "ana", T0)
        logic.change_status(self.tickets, self.events, "T001", "resolved", "ana", T0)
        t = logic.change_status(self.tickets, self.events, "T001", "open", "ana", later)
        self.assertEqual([e["event_type"] for e in self.events],
                         ["CREATE", "ASSIGN", "START", "RESOLVE", "REOPEN"])
        self.assertEqual(t["escalation_cycle"], 1)
        self.assertEqual(t["due_at"], logic.due_at("critical", later))
        self.assertEqual(t["created_at"], T0.isoformat())

    def test_rejected_operations_change_nothing(self):
        before = json.dumps([self.tickets, self.events])
        for call in (
            lambda: logic.change_status(self.tickets, self.events, "T001", "in_progress", "ana"),  # unassigned
            lambda: logic.change_status(self.tickets, self.events, "T001", "resolved", "ana"),     # skipped step
            lambda: logic.assign_ticket(self.tickets, self.events, "T001", "  ", "ana"),
            lambda: logic.assign_ticket(self.tickets, self.events, "T999", "Sam", "ana"),
            lambda: logic.change_status(self.tickets, self.events, "T001", "in_progress", " "),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(json.dumps([self.tickets, self.events]), before)

    def test_resolved_ticket_is_locked_until_reopened(self):
        logic.assign_ticket(self.tickets, self.events, "T001", "Sam", "ana", T0)
        logic.change_status(self.tickets, self.events, "T001", "in_progress", "ana", T0)
        logic.change_status(self.tickets, self.events, "T001", "resolved", "ana", T0)
        with self.assertRaises(ValueError):
            logic.assign_ticket(self.tickets, self.events, "T001", "Kim", "ana")

    def test_duplicate_warning_needs_confirmation(self):
        args = (self.tickets, self.events, "  WIFI   down ", "network", "low", 1, "ana", T0)
        self.assertIsNone(logic.create_ticket(*args))                       # no confirm callback
        self.assertIsNone(logic.create_ticket(*args, confirm=lambda ids: False))
        self.assertEqual(len(self.tickets), 1)
        self.assertEqual(len(self.events), 1)
        seen = []
        logic.create_ticket(*args, confirm=lambda ids: seen.append(ids) or True)
        self.assertEqual((seen, len(self.tickets)), ([["T001"]], 2))

    def test_resolved_tickets_are_not_duplicates(self):
        logic.assign_ticket(self.tickets, self.events, "T001", "Sam", "ana", T0)
        for s in ("in_progress", "resolved"):
            logic.change_status(self.tickets, self.events, "T001", s, "ana", T0)
        self.assertIsNotNone(logic.create_ticket(self.tickets, self.events, "Wifi down",
                                                 "Network", "low", 1, "ana", T0))


class SlaAndEscalation(unittest.TestCase):
    def setUp(self):
        self.tickets, self.events = make(("Crit", "Network", "high", 12),
                                         ("Low", "Other", "low", 1))

    def test_overdue_is_strictly_after_due(self):
        t = self.tickets[0]
        self.assertFalse(logic.is_overdue(t, T0 + timedelta(minutes=60)))
        self.assertTrue(logic.is_overdue(t, T0 + timedelta(minutes=60, seconds=1)))

    def test_escalation_is_idempotent_per_cycle_and_never_edits_tickets(self):
        snapshot = json.dumps(self.tickets)
        late = T0 + timedelta(hours=2)
        self.assertEqual(logic.escalate_overdue(self.tickets, self.events, "ana", late),
                         (["T001"], []))
        self.assertEqual(logic.escalate_overdue(self.tickets, self.events, "ana", late),
                         ([], ["T001"]))
        self.assertEqual(sum(e["event_type"] == "ESCALATE" for e in self.events), 1)
        self.assertEqual(json.dumps(self.tickets), snapshot)

    def test_new_cycle_after_reopen_can_escalate_again(self):
        logic.assign_ticket(self.tickets, self.events, "T001", "Sam", "ana", T0)
        for s in ("in_progress", "resolved"):
            logic.change_status(self.tickets, self.events, "T001", s, "ana", T0)
        logic.escalate_overdue(self.tickets, self.events, "ana", T0 + timedelta(hours=2))
        logic.change_status(self.tickets, self.events, "T001", "open", "ana", T0 + timedelta(hours=3))
        new, _ = logic.escalate_overdue(self.tickets, self.events, "ana", T0 + timedelta(hours=5))
        self.assertEqual(new, ["T001"])

    def test_blank_actor_escalation_changes_nothing(self):
        with self.assertRaises(ValueError):
            logic.escalate_overdue(self.tickets, self.events, " ", T0 + timedelta(days=9))
        self.assertEqual(len(self.events), 2)

    def test_queues(self):
        tickets, _ = make(("a", "Other", "low", 1), ("b", "Other", "high", 12),
                          ("c", "Other", "medium", 1), ("d", "Other", "high", 12))
        self.assertEqual([t["id"] for t in logic.work_queue(tickets)],
                         ["T002", "T004", "T003", "T001"])
        # 2h later b/d (60 min SLA) are overdue; c (24h) is due before a (48h)
        self.assertEqual([t["id"] for t in logic.sla_queue(tickets, T0 + timedelta(hours=2))],
                         ["T002", "T004", "T003", "T001"])
        tickets[0]["due_at"] = (T0 + timedelta(minutes=5)).isoformat()      # a is earliest
        self.assertEqual(logic.sla_queue(tickets, T0)[0]["id"], "T001")

    def test_report_counts_each_ticket_once(self):
        logic.escalate_overdue(self.tickets, self.events, "ana", T0 + timedelta(hours=2))
        r = logic.report(self.tickets, self.events, T0 + timedelta(hours=2))
        self.assertEqual((r["total"], r["overdue"], r["escalated"]), (2, 1, 1))
        self.assertEqual(r["status"]["open"], 2)
        self.assertEqual(r["priority"]["critical"], 1)

    def test_history_is_chronological(self):
        logic.assign_ticket(self.tickets, self.events, "T001", "Sam", "ana", T0 + timedelta(minutes=1))
        h = logic.ticket_history(self.events, "T001")
        self.assertEqual([e["event_type"] for e in h], ["CREATE", "ASSIGN"])


class Storage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "data", "tickets.json")

    def test_missing_file_is_a_fresh_start(self):
        self.assertEqual(storage.load_state(self.path), ([], []))

    def test_round_trip_and_no_temp_files_left(self):
        tickets, events = make(("Wifi", "Network", "high", 12))
        storage.save_state(tickets, events, self.path)
        self.assertEqual(storage.load_state(self.path), (tickets, events))
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["tickets.json"])

    def _write(self, text):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_damaged_files_are_rejected_and_never_overwritten(self):
        good, _ = make(("Wifi", "Network", "high", 12))
        broken = json.loads(json.dumps(good))
        broken[0]["priority"] = "low"                                   # inconsistent
        for text in ["{not json", "[]", '{"schema_version": 1}',
                     json.dumps({"schema_version": 2, "tickets": broken, "events": []}),
                     json.dumps({"schema_version": 2, "tickets": "x", "events": []})]:
            self._write(text)
            with self.assertRaises(ValueError):
                storage.load_state(self.path)
            with open(self.path, encoding="utf-8") as f:
                self.assertEqual(f.read(), text)

    def test_invalid_data_is_never_saved(self):
        tickets, events = make(("Wifi", "Network", "high", 12))
        tickets[0]["status"] = "in_progress"                            # unassigned
        with self.assertRaises(ValueError):
            storage.save_state(tickets, events, self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_event_for_unknown_ticket_rejected(self):
        tickets, events = make(("Wifi", "Network", "high", 12))
        events[0]["ticket_id"] = "T099"
        with self.assertRaises(ValueError):
            storage.save_state(tickets, events, self.path)


class KnowledgeLab(unittest.TestCase):
    def run_lab(self, answers):
        feed = iter(answers)
        out = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        record = lab.run_lab(tmp.name, lambda _p: next(feed), out.append, when=T0)
        return record, out, tmp.name

    def test_scoring_and_revision_topics(self):
        right = {q[0]: q[4] for q in lab.QUESTIONS}
        self.assertEqual(lab.score(right), (10, []))
        right["Q1"] = "A"
        self.assertEqual(lab.score(right), (9, ["SLA boundaries"]))

    def test_session_flow_enforces_exact_letters_and_three_explanations(self):
        # Participant: lowercase and "X" are rejected, then "A". Q1-Q7 explanations are
        # skipped, so Q8-Q10 become required (a too-short one is rejected first).
        answers = ["a", "X", "A"]
        for q in lab.QUESTIONS:
            answers.append(q[4])
            if q[0] in ("Q8", "Q9", "Q10"):
                answers += ["too short", "a proper explanation here"]
            else:
                answers.append("")
        record, out, folder = self.run_lab(answers)
        self.assertEqual((record["participant"], record["score"]), ("A", 10))
        self.assertEqual(sorted(record["explanations"]), ["Q10", "Q8", "Q9"])
        self.assertTrue(any("Error" in line for line in out))
        files = os.listdir(folder)
        self.assertEqual(len(files), 1)
        with open(os.path.join(folder, files[0]), encoding="utf-8") as f:
            self.assertEqual(json.load(f), record)


class Cli(unittest.TestCase):
    def drive(self, lines, path=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = path or os.path.join(tmp.name, "data", "tickets.json")
        out = []
        with mock.patch("builtins.input", side_effect=lines + ["0"]), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
            main.main(path, os.path.join(tmp.name, "lab"))
        return "\n".join(out), path

    def test_create_assign_start_is_saved_automatically_and_survives_restart(self):
        out, path = self.drive(["ana", "1", "Wifi down", "Network", "high", "12",
                                "2", "T001", "Sam", "3", "T001", "1"])
        self.assertIn("Created T001 with priority 'critical'", out)
        self.assertIn("T001 is now in_progress", out)
        out2, _ = self.drive(["ana", "11"], path)
        self.assertIn("Wifi down", out2)
        self.assertIn("in_progress", out2)

    def test_bad_input_is_reasked_and_unknown_id_reported(self):
        out, _ = self.drive(["ana", "1", "x", "cloud", "Other", "low", "0", "2", "2", "T404"])
        self.assertIn("Invalid category 'cloud'", out)
        self.assertIn("positive whole number", out)
        self.assertIn("Unknown ticket ID 'T404'", out)

    def test_damaged_file_stops_the_program_and_is_untouched(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "tickets.json")
        with open(path, "w") as f:
            f.write("{broken")
        out, _ = self.drive(["ana", "1"], path)
        self.assertIn("not valid JSON", out)
        with open(path) as f:
            self.assertEqual(f.read(), "{broken")


if __name__ == "__main__":
    unittest.main()
