"""Engineer A: UTC time helpers (Lesson A)."""
import unittest
from datetime import datetime, timedelta, timezone

from clock import parse_iso, to_iso


class ClockTests(unittest.TestCase):
    def test_round_trip_is_explicit_utc(self):
        moment = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
        text = to_iso(moment)
        self.assertTrue(text.endswith("+00:00"))
        self.assertEqual(parse_iso(text), moment)

    def test_z_suffix_and_other_offsets_normalise_to_utc(self):
        self.assertEqual(parse_iso("2026-10-14T10:00:00Z"),
                         datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc))
        lagos = timezone(timedelta(hours=1))
        self.assertEqual(to_iso(datetime(2026, 10, 14, 11, 0, tzinfo=lagos)),
                         "2026-10-14T10:00:00+00:00")

    def test_naive_and_garbage_are_rejected(self):
        with self.assertRaises(ValueError):
            to_iso(datetime(2026, 10, 14, 10, 0))          # naive
        for bad in ("2026-10-14T10:00:00", "not a date", "", None):
            with self.assertRaises(ValueError):
                parse_iso(bad)


if __name__ == "__main__":
    unittest.main()
