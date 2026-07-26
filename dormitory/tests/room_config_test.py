#!/usr/bin/env python3
"""Regression tests for room_config.py without modifying room files."""

from pathlib import Path
import sys
import unittest


DORMITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DORMITORY_ROOT))

from room_config import (  # noqa: E402
    add_letter,
    get_light_status,
    update_description,
    update_quote,
)


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

    def test_codex_desk_lamp_uses_the_shared_room_light(self):
        source = (DORMITORY_ROOT / "rooms" / "codex" / "index.html").read_text()

        self.assertIn('href="room.css"', source)
        self.assertGreaterEqual(source.count('data-agent-light="codex"'), 2)

    def test_codex_keeper_description_is_outside_hidden_scene(self):
        source = (DORMITORY_ROOT / "rooms" / "codex" / "index.html").read_text()
        scene_start = source.index('<div class="desk-scene" aria-hidden="true">')
        scene_end = source.index(
            '        </div>\n        <p class="keeper-description">',
            scene_start,
        )
        keeper = source.index('<div class="clock-keeper"', scene_start)
        description = source.index(
            '<p class="keeper-description">'
            "A small keeper rests beside an unreadable clock.</p>"
        )

        self.assertLess(keeper, scene_end)
        self.assertGreater(description, scene_end)

    def test_personalized_codex_note_remains_configurable(self):
        source = (DORMITORY_ROOT / "rooms" / "codex" / "index.html").read_text()

        updated = update_quote(source, "A newly indexed thought.")
        updated = update_description(updated, "A newly indexed description.")

        self.assertIn('<p><em>"A newly indexed thought."</em></p>', updated)
        self.assertIn("<p>A newly indexed description.</p>", updated)


if __name__ == "__main__":
    unittest.main()
