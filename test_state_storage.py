"""Engineer A: schema-version-2 persistence, corruption safety, migration
(checkpoints A5, A6). All files live in temporary directories."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from sla import escalate_overdue
from storage import (is_legacy_format, load_state, migrate_legacy, save_state,
                     validate_state)
from workflow import (assign_ticket_logged, change_status_logged,
                      create_ticket_logged)

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def sample_state():
    tickets, events = [], []
    create_ticket_logged(tickets, events, "Wi-Fi down", "Network", "high", 12, "ada", now=T0)
    assign_ticket_logged(tickets, events, "T001", "Bob", "ada", now=at(1))
    change_status_logged(tickets, events, "T001", "in_progress", "bob", now=at(2))
    escalate_overdue(tickets, events, at(61), "ada")
    create_ticket_logged(tickets, events, "Projector", "Hardware", "low", 1, "ada", now=at(5))
    return tickets, events


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "tickets.json")

    def write(self, text, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, path=None):
        with open(path or self.path, encoding="utf-8") as f:
            return f.read()


class SaveLoadV2Tests(TempDirCase):
    def test_missing_file_is_a_fresh_start(self):
        self.assertEqual(load_state(self.path), ([], []))

    def test_round_trip_keeps_tickets_and_event_history(self):          # must-test 14
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        self.assertEqual(load_state(self.path), (tickets, events))
        data = json.loads(self.read())
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual([e["event_type"] for e in data["events"]],
                         ["CREATE", "ASSIGN", "START", "ESCALATE", "CREATE"])

    def test_ids_continue_after_restart(self):
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        tickets, events = load_state(self.path)
        t = create_ticket_logged(tickets, events, "New", "Other", "low", 1, "ada", now=at(9))
        self.assertEqual(t["id"], "T003")
        self.assertEqual(events[-1]["event_id"], "E006")

    def test_escalation_stays_idempotent_across_restart(self):
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        tickets, events = load_state(self.path)
        r = escalate_overdue(tickets, events, at(300), "ada")
        self.assertNotIn("T001", r["new_ids"])                            # already escalated


class CorruptionTests(TempDirCase):
    def test_a5_corrupt_json_raises_and_file_is_untouched(self):         # must-test 13
        self.write("{ this is not json")
        with self.assertRaises(ValueError):
            load_state(self.path)
        self.assertEqual(self.read(), "{ this is not json")

    def test_corrupt_reload_preserves_valid_in_memory_state(self):
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        snapshot = copy.deepcopy((tickets, events))
        self.write('{"schema_version": 2, "tickets": "oops"')              # truncated file
        try:                                                                # same pattern as the CLI
            new_t, new_e = load_state(self.path)
            tickets[:], events[:] = new_t, new_e
        except ValueError:
            pass
        self.assertEqual((tickets, events), snapshot)

    def test_inconsistent_data_is_rejected(self):
        tickets, events = sample_state()
        good = {"schema_version": 2, "tickets": tickets, "events": events}
        mutations = {
            "wrong version": lambda d: d.update(schema_version=1),
            "missing field": lambda d: d["tickets"][0].pop("due_at"),
            "duplicate ticket id": lambda d: d["tickets"][1].update(id="T001"),
            "bad status": lambda d: d["tickets"][0].update(status="done"),
            "naive timestamp": lambda d: d["tickets"][0].update(created_at="2026-10-14T10:00:00"),
            "priority mismatch": lambda d: d["tickets"][0].update(priority="low"),
            "in_progress unassigned": lambda d: d["tickets"][0].update(assigned_to=None),
            "due before SLA": lambda d: d["tickets"][0].update(due_at=d["tickets"][0]["created_at"]),
            "negative cycle": lambda d: d["tickets"][0].update(escalation_cycle=-1),
            "event for unknown ticket": lambda d: d["events"][0].update(ticket_id="T999"),
            "duplicate event id": lambda d: d["events"][1].update(event_id="E001"),
            "unknown event type": lambda d: d["events"][0].update(event_type="DELETE"),
            "non-CREATE without before": lambda d: d["events"][1].update(before_status=None),
        }
        for name, mutate in mutations.items():
            bad = copy.deepcopy(good)
            mutate(bad)
            with self.subTest(name), self.assertRaises(ValueError):
                validate_state(bad)
        validate_state(copy.deepcopy(good))                                # control: good passes

    def test_non_object_and_binary_files_rejected(self):
        for content in ("[]", "42", '"text"', "null"):
            self.write(content)
            with self.subTest(content), self.assertRaises(ValueError):
                load_state(self.path)
        with open(self.path, "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        with self.assertRaises(ValueError):
            load_state(self.path)


class AtomicWriteTests(TempDirCase):
    def test_a6_invalid_data_is_never_written(self):
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        before = self.read()
        broken = copy.deepcopy(tickets)
        broken[0]["status"] = "nonsense"
        with self.assertRaises(ValueError):
            save_state(broken, events, self.path)
        self.assertEqual(self.read(), before)
        self.assertEqual(os.listdir(self.dir.name), ["tickets.json"])      # no temp litter

    def test_crash_during_write_keeps_old_file_and_cleans_temp(self):
        tickets, events = sample_state()
        save_state(tickets, events, self.path)
        before = self.read()
        tickets.append(dict(copy.deepcopy(tickets[0]), id="T003"))
        with mock.patch("storage.os.replace", side_effect=OSError("power cut")):
            with self.assertRaises(OSError):
                save_state(tickets, events, self.path)
        self.assertEqual(self.read(), before)
        self.assertEqual(os.listdir(self.dir.name), ["tickets.json"])

    def test_first_save_creates_the_file(self):
        save_state([], [], self.path)
        self.assertEqual(load_state(self.path), ([], []))


class LegacyMigrationTests(TempDirCase):
    LEGACY = [{"id": "T001", "title": "goat", "category": "Network", "urgency": "low",
               "affected_users": 2, "priority": "low", "status": "in_progress",
               "assigned_to": "gabriel"}]

    def test_old_list_file_is_rejected_not_overwritten(self):
        self.write(json.dumps(self.LEGACY))
        self.assertTrue(is_legacy_format(self.path))
        with self.assertRaises(ValueError):
            load_state(self.path)
        self.assertEqual(json.loads(self.read()), self.LEGACY)

    def test_migration_backs_up_original_and_invents_no_history(self):
        self.write(json.dumps(self.LEGACY))
        original = self.read()
        r = migrate_legacy(self.path, now=T0)
        self.assertEqual(self.read(r["backup"]), original)                 # byte-identical backup
        tickets, events = load_state(self.path)
        self.assertEqual(events, [])                                       # nothing fabricated
        self.assertEqual(tickets[0]["created_at"], "2026-10-14T10:00:00+00:00")
        self.assertEqual(tickets[0]["due_at"], "2026-10-16T10:00:00+00:00")  # low = 2880 min
        self.assertEqual((tickets[0]["status"], tickets[0]["assigned_to"]),
                         ("in_progress", "gabriel"))

    def test_migration_refuses_to_overwrite_existing_backup_or_missing_source(self):
        with self.assertRaises(ValueError):
            migrate_legacy(self.path)                                      # no file
        self.write(json.dumps(self.LEGACY))
        self.write("keep me", self.path + ".legacy-backup")
        with self.assertRaises(ValueError):
            migrate_legacy(self.path)
        self.assertEqual(json.loads(self.read()), self.LEGACY)             # untouched

    def test_migration_rejects_bad_legacy_data_without_writing(self):
        bad = [dict(self.LEGACY[0], priority="critical")]                  # inconsistent
        self.write(json.dumps(bad))
        with self.assertRaises(ValueError):
            migrate_legacy(self.path)
        self.assertEqual(os.listdir(self.dir.name), ["tickets.json"])


if __name__ == "__main__":
    unittest.main()
