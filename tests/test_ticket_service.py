import unittest

from campusflow.ticket_service import (assign_ticket, calculate_priority, change_status,
                            create_ticket, find_ticket, report, work_queue)


def new_ticket(tickets, urgency="low", users=1):
    return create_ticket(tickets, "Test", "Network", urgency, users)


class PriorityTests(unittest.TestCase):
    def test_rules(self):
        cases = [("high", 10, "critical"), ("high", 9, "high"),
                 ("medium", 10, "high"), ("low", 10, "high"),
                 ("medium", 1, "medium"), ("low", 3, "medium"),
                 ("low", 2, "low"), ("low", 1, "low")]
        for urgency, users, expected in cases:
            self.assertEqual(calculate_priority(urgency, users), expected)


class CreateTests(unittest.TestCase):
    def test_create_normalizes_input_and_generates_ids(self):
        tickets = []
        t = create_ticket(tickets, " Wi-Fi down ", "network", "HIGH", "15")
        self.assertEqual((t["id"], t["title"], t["category"], t["urgency"],
                          t["affected_users"], t["priority"], t["status"],
                          t["assigned_to"]),
                         ("T001", "Wi-Fi down", "Network", "high", 15,
                          "critical", "open", None))
        self.assertEqual(new_ticket(tickets)["id"], "T002")

    def test_invalid_input_is_rejected(self):
        bad = [("", "Network", "low", 1), ("a", "Printers", "low", 1),
               ("a", "Network", "urgent", 1), ("a", "Network", "low", 0),
               ("a", "Network", "low", -3), ("a", "Network", "low", 2.5),
               ("a", "Network", "low", "many")]
        tickets = []
        for args in bad:
            with self.assertRaises(ValueError, msg=str(args)):
                create_ticket(tickets, *args)
        self.assertEqual(tickets, [])


class WorkflowTests(unittest.TestCase):
    def test_assign_and_unknown_id(self):
        tickets = []
        new_ticket(tickets)
        self.assertEqual(assign_ticket(tickets, "t001", "Ada")["assigned_to"], "Ada")
        with self.assertRaises(ValueError):
            assign_ticket(tickets, "T001", "  ")
        with self.assertRaises(ValueError):
            find_ticket(tickets, "T099")

    def test_status_rules(self):
        tickets = []
        new_ticket(tickets)
        with self.assertRaises(ValueError):                 # unassigned
            change_status(tickets, "T001", "in_progress")
        assign_ticket(tickets, "T001", "Ada")
        with self.assertRaises(ValueError):                 # cannot skip
            change_status(tickets, "T001", "resolved")
        change_status(tickets, "T001", "in_progress")
        change_status(tickets, "T001", "resolved")
        with self.assertRaises(ValueError):                 # resolved is locked
            assign_ticket(tickets, "T001", "Bob")
        change_status(tickets, "T001", "open")              # explicit reopen
        assign_ticket(tickets, "T001", "Bob")

    def test_queue_order_and_tiebreak(self):
        tickets = []
        for _ in range(10):
            new_ticket(tickets, "low", 1)                   # T001-T010 low
        new_ticket(tickets, "high", 10)                     # T011 critical
        new_ticket(tickets, "high", 1)                      # T012 high
        order = [t["id"] for t in work_queue(tickets)]
        self.assertEqual(order, ["T011", "T012"] + [f"T{n:03d}" for n in range(1, 11)])

    def test_queue_excludes_resolved(self):
        tickets = []
        new_ticket(tickets)
        assign_ticket(tickets, "T001", "Ada")
        change_status(tickets, "T001", "in_progress")
        change_status(tickets, "T001", "resolved")
        self.assertEqual(work_queue(tickets), [])


class ReportTests(unittest.TestCase):
    def test_zero_tickets(self):
        r = report([])
        self.assertEqual(r["total"], 0)
        self.assertEqual(sum(r["status"].values()) + sum(r["priority"].values()), 0)

    def test_counts(self):
        tickets = []
        new_ticket(tickets, "high", 10)
        new_ticket(tickets, "low", 1)
        r = report(tickets)
        self.assertEqual((r["total"], r["priority"]["critical"], r["status"]["open"]),
                         (2, 1, 2))


if __name__ == "__main__":
    unittest.main()
