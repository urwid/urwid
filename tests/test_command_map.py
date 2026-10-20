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
