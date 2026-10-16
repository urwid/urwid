"""Tests of the command descriptions and the key check of CommandMap."""

from __future__ import annotations

import pickle
import unittest

from urwid.command_map import Command, CommandInfo, CommandMap


class CommandMapHelpTest(unittest.TestCase):
    """Help text, categories and key binding through CommandMap.register."""

    def test_every_standard_command_is_described(self) -> None:
        """Describe every standard command, and list the keys bound to it."""
        cm = CommandMap()
        self.assertEqual(set(Command), set(cm.command_info))
        self.assertEqual(CommandInfo("Activate the focused widget", "Actions"), cm.command_info[Command.ACTIVATE])
        self.assertEqual((" ", "enter"), cm.keys_for(Command.ACTIVATE))

    def test_register_describes_and_binds(self) -> None:
        """Record the description of a new command and bind its keys in order."""
        cm = CommandMap()
        cm.register("quit", "q", "ctrl c", help_text="Quit the program", category="Application")
        self.assertEqual(CommandInfo("Quit the program", "Application"), cm.command_info["quit"])
        self.assertEqual(("q", "ctrl c"), cm.keys_for("quit"))
        self.assertEqual("quit", cm["q"])

    def test_register_without_keys_only_describes(self) -> None:
        """Describe a command without binding any key to it."""
        cm = CommandMap()
        cm.register("quit", help_text="Quit the program", category="Application")
        self.assertEqual(CommandInfo("Quit the program", "Application"), cm.command_info["quit"])
        self.assertEqual((), cm.keys_for("quit"))

    def test_register_accepts_a_key_already_bound_to_the_same_command(self) -> None:
        """Accept a key bound to the same command, and replace its description."""
        cm = CommandMap()
        cm.register("cursor up", "up", "k", help_text="Move up a row", category="Movement")
        self.assertEqual(("up", "k"), cm.keys_for(Command.UP))
        self.assertEqual(CommandInfo("Move up a row", "Movement"), cm.command_info[Command.UP])

    def test_register_rejects_a_key_bound_to_another_command(self) -> None:
        """Reject a key bound to a different command and leave the map unchanged."""
        cm = CommandMap()
        with self.assertRaisesRegex(ValueError, "'ctrl l' is already bound to 'redraw screen'"):
            cm.register("quit", "q", "ctrl l", help_text="Quit the program", category="Application")
        self.assertNotIn("quit", cm.command_info)
        self.assertIsNone(cm["q"])
        self.assertEqual(Command.REDRAW_SCREEN, cm["ctrl l"])

    def test_command_info_is_read_only(self) -> None:
        """Refuse a description added through the read-only view."""
        cm = CommandMap()
        with self.assertRaises(TypeError):
            cm.command_info["quit"] = CommandInfo("Quit the program", "Application")  # type: ignore[index]

    def test_description_survives_unbinding(self) -> None:
        """Keep a description when the command's keys are cleared or the defaults restored."""
        cm = CommandMap()
        cm.register("quit", "q", help_text="Quit the program", category="Application")
        cm.clear_command("quit")
        cm.restore_defaults()
        self.assertEqual((), cm.keys_for("quit"))
        self.assertIn("quit", cm.command_info)

    def test_copy_has_its_own_descriptions(self) -> None:
        """Keep descriptions registered on a copy out of the original and the class defaults."""
        cm = CommandMap()
        copied = cm.copy()
        copied.register("quit", "q", help_text="Quit the program", category="Application")
        self.assertIn("quit", copied.command_info)
        self.assertNotIn("quit", cm.command_info)
        self.assertNotIn("quit", CommandMap().command_info)

    def test_pickle_round_trip(self) -> None:
        """Keep bindings and descriptions through pickling."""
        cm = CommandMap()
        cm.register("quit", "q", help_text="Quit the program", category="Application")
        restored = pickle.loads(pickle.dumps(cm))
        self.assertEqual(("q",), restored.keys_for("quit"))
        self.assertEqual(dict(cm.command_info), dict(restored.command_info))

    def test_state_without_descriptions_gets_the_defaults(self) -> None:
        """Give a command map pickled before descriptions existed the default descriptions."""
        cm = CommandMap.__new__(CommandMap)
        cm.__setstate__({"_command": {"q": "quit"}})
        self.assertEqual(dict(CommandMap().command_info), dict(cm.command_info))
        self.assertEqual("quit", cm.copy()["q"])
