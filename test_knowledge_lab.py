import glob
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import knowledge_lab as lab

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
CORRECT = {q[0]: q[4] for q in lab.QUESTIONS}


def run(answers, explain="I checked this with a small experiment.", participant="B",
        sessions_dir=None):
    """Drive run_lab with scripted input. answers: list of 10 letters."""
    script = [participant]
    for letter in answers:
        script += [letter, explain]
    feed, out = iter(script), []
    record = lab.run_lab(input_fn=lambda _p: next(feed), output_fn=out.append,
                         sessions_dir=sessions_dir, now=NOW)
    return record, out


class ScoringTests(unittest.TestCase):
    def test_bank_has_ten_questions_with_valid_keys(self):
        self.assertEqual(len(lab.QUESTIONS), 10)
        for _id, _t, _s, options, correct, _e, _r in lab.QUESTIONS:
            self.assertEqual(len(options), 4)
            self.assertIn(correct, "ABCD")

    def test_score_and_revision_topics(self):
        self.assertEqual(lab.score_answers(CORRECT), (10, []))
        wrong = dict(CORRECT, Q5="A", Q10="A")
        score, topics = lab.score_answers(wrong)
        self.assertEqual(score, 8)
        self.assertEqual(topics, ["Idempotent escalation", "Audit log integrity"])
        self.assertEqual(lab.score_answers({})[0], 0)           # unanswered = 0

    def test_quiz_rejects_e_blank_and_lowercase(self):         # must-test 15
        for bad in ("E", "", " ", "a", "AB", "1"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                lab.validate_choice(bad)
        for good in "ABCD":
            self.assertEqual(lab.validate_choice(good), good)
        with self.assertRaises(ValueError):
            lab.validate_participant("C")

    def test_explanation_rules_force_at_least_three(self):
        total = 10
        required = [lab.explanation_required(0, i, total) for i in range(1, 11)]
        self.assertEqual(required, [False] * 7 + [True] * 3)    # skipping all -> last 3 forced
        self.assertTrue(lab.explanation_required(2, 10, total))
        self.assertFalse(lab.explanation_required(3, 10, total))
        with self.assertRaises(ValueError):
            lab.clean_explanation("ok", required=True)
        self.assertEqual(lab.clean_explanation("", required=False), "")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.sessions = os.path.join(self.dir.name, "sessions")

    def tearDown(self):
        self.dir.cleanup()

    def test_session_record_saved_with_required_fields(self):
        answers = [CORRECT[f"Q{i}"] for i in range(1, 11)]
        answers[3] = "A"                                        # one wrong (Q4)
        record, out = run(answers, sessions_dir=self.sessions)
        files = glob.glob(os.path.join(self.sessions, "*.json"))
        self.assertEqual(len(files), 1)
        with open(files[0]) as f:
            saved = json.load(f)
        self.assertEqual(saved, record)
        self.assertEqual((saved["participant"], saved["score"]), ("B", 9))
        self.assertEqual(saved["timestamp"], NOW.isoformat())
        self.assertEqual(len(saved["choices"]), 10)
        self.assertGreaterEqual(len(saved["explanations"]), 3)
        self.assertEqual(saved["revision_topics"], ["SLA cycles and reopening"])
        text = "\n".join(out)
        self.assertIn("Score: 9/10", text)
        self.assertIn("Your explanation:", text)

    def test_invalid_input_reprompts_and_skips_are_limited(self):
        script = ["X", "A"]                                     # bad participant, then A
        for i in range(1, 11):
            script += ["E", "", CORRECT[f"Q{i}"]]               # bad choices, then valid
            script += ["" if i <= 7 else "short", "" if i <= 7 else
                       "A proper explanation here."]            # skip allowed only early
        feed, out = iter(script), []
        record = lab.run_lab(lambda _p: next(feed), out.append, self.sessions, NOW)
        self.assertEqual(record["score"], 10)
        self.assertEqual(sorted(record["explanations"]), ["Q10", "Q8", "Q9"])
        self.assertGreaterEqual(sum("Error" in line for line in out), 20)

    def test_quiz_leaves_ticket_state_untouched(self):          # must-test 16
        from workflow import create_ticket_logged
        tickets, events = [], []
        create_ticket_logged(tickets, events, "Printer", "Hardware", "low", 1, "ada", now=NOW)
        before = json.dumps([tickets, events], sort_keys=True)
        run([CORRECT[f"Q{i}"] for i in range(1, 11)], sessions_dir=self.sessions)
        self.assertEqual(json.dumps([tickets, events], sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
