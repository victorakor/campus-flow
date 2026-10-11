import os
import tempfile
import unittest

from storage import load_tickets, save_tickets
from ticket_service import create_ticket


def new_ticket(tickets, urgency="low", users=1):
    return create_ticket(tickets, "Test", "Network", urgency, users)


class SaveLoadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "tickets.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_gives_empty_list(self):
        self.assertEqual(load_tickets(self.path), [])

    def test_round_trip_and_unique_ids_after_reload(self):
        tickets = []
        new_ticket(tickets)
        new_ticket(tickets)
        save_tickets(tickets, self.path)
        loaded = load_tickets(self.path)
        self.assertEqual(loaded, tickets)
        self.assertEqual(new_ticket(loaded)["id"], "T003")

    def test_malformed_json_raises_and_file_is_kept(self):
        with open(self.path, "w") as f:
            f.write("{bad json")
        with self.assertRaises(ValueError):
            load_tickets(self.path)
        with open(self.path) as f:
            self.assertEqual(f.read(), "{bad json")

    def test_wrong_structure_raises(self):
        with open(self.path, "w") as f:
            f.write('{"tickets": []}')
        with self.assertRaises(ValueError):
            load_tickets(self.path)


if __name__ == "__main__":
    unittest.main()
