"""Tests of the key check of CommandMap.bind."""

from __future__ import annotations

import unittest

from urwid.command_map import Command, CommandMap


class CommandMapBindTest(unittest.TestCase):
    """Binding keys through CommandMap.bind."""

    def test_bind_new_command(self) -> None:
        """Bind every key given to a new command."""
        cm = CommandMap()
        cm.bind("quit", "q", "ctrl c")
        self.assertEqual("quit", cm["q"])
        self.assertEqual("quit", cm["ctrl c"])

    def test_bind_accepts_a_key_already_bound_to_the_same_command(self) -> None:
        """Accept a key bound to the same command, given as a string or as a Command."""
        cm = CommandMap()
        cm.bind("cursor up", "up", "k")
        cm.bind(Command.UP, "up")
        self.assertEqual(Command.UP, cm["up"])
        self.assertEqual("cursor up", cm["k"])

    def test_bind_rejects_a_key_bound_to_another_command(self) -> None:
        """Reject a key bound to a different command and leave the map unchanged."""
        cm = CommandMap()
        with self.assertRaisesRegex(ValueError, "'ctrl l' is already bound to 'redraw screen'"):
            cm.bind("quit", "q", "ctrl l")
        self.assertIsNone(cm["q"])
        self.assertEqual(Command.REDRAW_SCREEN, cm["ctrl l"])


class CommandMapBindReadlineTest(unittest.TestCase):
    """Binding the readline keys through CommandMap.bind_readline."""

    def test_bind_readline_on_default_map(self) -> None:
        """Bind every readline key and keep the defaults."""
        cm = CommandMap()
        cm.bind_readline()
        expected = {
            "ctrl a": Command.LINE_START,
            "ctrl e": Command.LINE_END,
            "meta b": Command.WORD_LEFT,
            "meta f": Command.WORD_RIGHT,
            "meta backspace": Command.DELETE_WORD_LEFT,
            "meta d": Command.DELETE_WORD_RIGHT,
            "ctrl u": Command.DELETE_TO_LINE_START,
            "ctrl k": Command.DELETE_TO_LINE_END,
            "ctrl w": Command.DELETE_SPACE_WORD_LEFT,
            "ctrl d": Command.DELETE_RIGHT,
        }
        self.assertEqual({key: cm[key] for key in expected}, expected)
        self.assertEqual(dict(cm), {**CommandMap(), **expected})

    def test_bind_readline_conflict_leaves_map_unchanged(self) -> None:
        """Refuse a key taken by another command, early or late in the preset, and bind none of the keys."""
        for taken in ("ctrl a", "ctrl d"):
            with self.subTest(taken=taken):
                cm = CommandMap()
                cm[taken] = "quit"
                before = dict(cm)
                with self.assertRaisesRegex(ValueError, f"'{taken}' is already bound to 'quit'"):
                    cm.bind_readline()
                self.assertEqual(dict(cm), before)
