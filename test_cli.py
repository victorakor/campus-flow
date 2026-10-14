import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import helpdesk
import knowledge_lab as lab

CORRECT = [q[4] for q in lab.QUESTIONS]


def run_cli(lines, data_file, sessions_dir):
    out = io.StringIO()
    with mock.patch("builtins.input", side_effect=lines), contextlib.redirect_stdout(out):
        helpdesk.main(data_file=data_file, sessions_dir=sessions_dir)
    return out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.dir.name, "tickets.json")
        self.sessions = os.path.join(self.dir.name, "lab")

    def tearDown(self):
        self.dir.cleanup()

    def state(self):
        with open(self.data) as f:
            return json.load(f)

    def test_invalid_input_reprompts_and_bad_menu_choice(self):
        out = run_cli(["ada", "99", "abc", "1", "  ", "Printer", "Printers", "Hardware",
                       "urgent", "low", "0", "-2", "2", "0"], self.data, self.sessions)
        self.assertIn("Invalid choice", out)
        for msg in ("Title must not be blank", "Invalid category", "Invalid urgency",
                    "positive whole number"):
            self.assertIn(msg, out)
        self.assertIn("Created T001", out)
        self.assertEqual(len(self.state()["events"]), 1)

    def test_duplicate_decline_and_confirm_via_cli(self):
        base = ["ada", "1", " Wi-Fi   Down ", "network", "low", "1"]
        out = run_cli(base + ["1", "wi-fi down", "network", "low", "1", "no",
                              "1", "wi-fi down", "network", "low", "1", "yes", "0"],
                      self.data, self.sessions)
        self.assertIn("same title and category: T001", out)
        self.assertIn("Cancelled: no ticket or event was created.", out)
        state = self.state()
        self.assertEqual([t["id"] for t in state["tickets"]], ["T001", "T002"])
        self.assertEqual(len(state["events"]), 2)               # declined one added nothing

    def test_rejected_transition_adds_no_event_and_history_shows(self):
        out = run_cli(["ada", "1", "Printer", "Hardware", "low", "1",
                       "3", "T001", "1",                        # unassigned start: rejected
                       "6", "T001", "0"], self.data, self.sessions)
        self.assertIn("unassigned", out)
        self.assertEqual(len(self.state()["events"]), 1)
        self.assertIn("E001", out)

    def test_original_queue_and_old_operations_still_reachable(self):
        out = run_cli(["ada", "1", "Printer", "Hardware", "low", "1", "11", "12", "T001",
                       "4", "0"], self.data, self.sessions)
        self.assertIn("(unassigned)", out)
        self.assertIn("Printer", out)

    def test_knowledge_lab_via_menu_does_not_change_saved_tickets(self):
        run_cli(["ada", "1", "Printer", "Hardware", "low", "1", "0"],
                self.data, self.sessions)
        with open(self.data, "rb") as f:
            before = f.read()
        script = ["ada", "10", "B"]
        for letter in CORRECT:
            script += [letter, "I reasoned this through carefully."]
        out = run_cli(script + ["0"], self.data, self.sessions)
        self.assertIn("Score: 10/10", out)
        with open(self.data, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(len(os.listdir(self.sessions)), 1)

    def test_corrupt_file_is_rejected_and_not_overwritten(self):
        with open(self.data, "w") as f:
            f.write("{bad json")
        out = run_cli(["ada", "0"], self.data, self.sessions)
        self.assertIn("not valid JSON", out)
        with open(self.data) as f:
            self.assertEqual(f.read(), "{bad json")


if __name__ == "__main__":
    unittest.main()
