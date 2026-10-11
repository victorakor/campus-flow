import unittest

from config import CATEGORIES
from validation import clean_choice, clean_title, clean_users


class CleanChoiceTests(unittest.TestCase):
    def test_ignores_case_and_spaces(self):
        self.assertEqual(clean_choice("  network ", CATEGORIES, "category"), "Network")
        self.assertEqual(clean_choice("HARDWARE", CATEGORIES, "category"), "Hardware")

    def test_rejects_unknown_value(self):
        with self.assertRaises(ValueError):
            clean_choice("Printers", CATEGORIES, "category")


class CleanTitleTests(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(clean_title("  Wi-Fi down  "), "Wi-Fi down")

    def test_rejects_blank(self):
        for bad in ("", "   "):
            with self.assertRaises(ValueError):
                clean_title(bad)


class CleanUsersTests(unittest.TestCase):
    def test_accepts_positive_integers(self):
        self.assertEqual(clean_users(" 15 "), 15)
        self.assertEqual(clean_users(1), 1)

    def test_rejects_bad_values(self):
        for bad in ("0", "-3", "2.5", "many", "", "٣"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                clean_users(bad)


if __name__ == "__main__":
    unittest.main()
