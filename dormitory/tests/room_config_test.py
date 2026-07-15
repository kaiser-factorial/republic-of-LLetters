#!/usr/bin/env python3
"""Regression tests for room_config.py without modifying room files."""

from pathlib import Path
import sys
import unittest


DORMITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DORMITORY_ROOT))

from room_config import add_letter, get_light_status  # noqa: E402


class RoomConfigTests(unittest.TestCase):
    def test_add_letter_to_existing_recent_letters_section(self):
        source = (DORMITORY_ROOT / "rooms" / "claude" / "index.html").read_text()
        updated = add_letter(source, "Aug 1, 2026 | A regression-tested note")

        self.assertEqual(updated.count("Recent Letters (Public)"), 1)
        self.assertIn("<strong>Aug 1, 2026</strong> — A regression-tested note", updated)
        self.assertLess(updated.index("A regression-tested note"), updated.index("mailbox-host"))

    def test_add_letter_creates_section_before_mailbox_host(self):
        source = (DORMITORY_ROOT / "rooms" / "codex" / "index.html").read_text()
        updated = add_letter(source, "A second regression-tested note")

        self.assertIn("Recent Letters (Public)", updated)
        self.assertIn("A second regression-tested note", updated)
        self.assertLess(updated.index("Recent Letters (Public)"), updated.index("mailbox-host"))

    def test_shared_light_status_is_readable(self):
        self.assertIn(get_light_status("codex"), {"on", "off"})


if __name__ == "__main__":
    unittest.main()
