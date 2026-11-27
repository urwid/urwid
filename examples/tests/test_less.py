"""Tests of the examples/less.py pager: lazy reading, going to a line and its keys."""

from __future__ import annotations

import importlib.util
import io
import pathlib
import sys
import typing
import unittest

import urwid

if typing.TYPE_CHECKING:
    import types

EXAMPLE: typing.Final = pathlib.Path(__file__).resolve().parent.parent / "less.py"
SIZE: typing.Final = (40, 5)


def load_example() -> types.ModuleType:
    """Import examples/less.py by its path, without running it."""
    spec = importlib.util.spec_from_file_location("less_example", EXAMPLE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {EXAMPLE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


less = load_example()


def pager(text: str) -> typing.Any:
    """Return a pager over *text*."""
    return less.Pager(less.LineWalker(io.StringIO(text)), "sample.txt")


def screen(shown: typing.Any) -> list[str]:
    """Return the rows of the pager as drawn at SIZE, the status line included."""
    return [row.decode() for row in shown.frame.render(SIZE).text]


def press(shown: typing.Any, *keys: str) -> None:
    """Send *keys* to the pager as the main loop does, the list box first."""
    for key in keys:
        if shown.frame.keypress(SIZE, key) is not None:
            shown.unhandled_input(key)


class TestLineWalker(unittest.TestCase):
    """The walker reads the file lazily and finds a line by its number."""

    def test_reads_only_the_lines_shown(self) -> None:
        """Read at most the focus line before the first render, and about as many lines as a render shows.

        On Python 3.11 an ``isinstance`` check against a protocol reads ``ListBox.focus``, which reads the first line.
        """
        shown = pager("".join(f"line {number}\n" for number in range(1, 1001)))
        self.assertLessEqual(len(shown.walker.lines), 1)
        self.assertEqual(["line 1", "line 2", "line 3", "line 4"], [row.rstrip() for row in screen(shown)[:4]])
        self.assertLessEqual(len(shown.walker.lines), 5)

    def test_lines_have_tabs_expanded_and_no_newline(self) -> None:
        """Tabs are expanded, and the last line needs no newline."""
        shown = pager("a\tb\nlast line without newline")
        self.assertEqual(["a       b", "last line without newline"], [row.rstrip() for row in screen(shown)[:2]])

    def test_position_of(self) -> None:
        """A line number maps to its position, capped at the last line."""
        for name, text, number, expected in (
            ("first line", "a\nb\nc\n", 1, 0),
            ("a middle line", "a\nb\nc\n", 2, 1),
            ("past the end", "a\nb\nc\n", 10, 2),
            ("zero", "a\nb\n", 0, 0),
            ("empty file", "", 5, None),
        ):
            with self.subTest(name):
                self.assertEqual(expected, less.LineWalker(io.StringIO(text)).position_of(number))

    def test_position_of_reads_up_to_the_line(self) -> None:
        """Going to a line reads the file up to it and no further."""
        walker = less.LineWalker(io.StringIO("".join(f"{number}\n" for number in range(100))))
        walker.position_of(10)
        self.assertEqual(10, len(walker.lines))


class TestPagerKeys(unittest.TestCase):
    """Keys the list box leaves to the pager."""

    def setUp(self) -> None:
        """Make a pager over 100 numbered lines."""
        self.shown = pager("".join(f"line {number}\n" for number in range(1, 101)))

    def test_number_and_g_show_the_line_at_the_top(self) -> None:
        """The typed number shows in the status line, and g puts that line at the top."""
        press(self.shown, "4", "2")
        self.assertIn("42g", screen(self.shown)[-1])
        press(self.shown, "g")
        self.assertEqual("line 42", screen(self.shown)[0].rstrip())
        self.assertNotIn("42g", screen(self.shown)[-1])

    def test_g_alone_goes_to_the_first_line(self) -> None:
        """Without a number, g goes to the first line."""
        press(self.shown, "5", "0", "g", "g")
        self.assertEqual("line 1", screen(self.shown)[0].rstrip())

    def test_esc_forgets_the_number(self) -> None:
        """Esc drops the typed number, so a later g goes to the first line."""
        press(self.shown, "5", "0", "g", "7", "esc", "g")
        self.assertEqual("line 1", screen(self.shown)[0].rstrip())

    def test_number_is_capped(self) -> None:
        """Digits past the cap are ignored, so a long paste still goes to a line: here past the end, to the last one."""
        press(self.shown, *"9" * 5000)
        self.assertEqual("9" * less.MAX_DIGITS, self.shown.number)
        press(self.shown, "g")
        self.assertEqual("line 100", screen(self.shown)[-2].rstrip())

    def test_g_on_an_empty_file(self) -> None:
        """G on an empty file leaves the empty screen as it is."""
        shown = pager("")
        press(shown, "5", "g")
        self.assertEqual("", screen(shown)[0].strip())
        self.assertEqual("", shown.number)

    def test_q_quits(self) -> None:
        """The q key leaves the main loop."""
        with self.assertRaises(urwid.ExitMainLoop):
            self.shown.unhandled_input("q")

    def test_other_input_is_left_alone(self) -> None:
        """Other keys and mouse events are not handled and leave the number alone."""
        for key in ("x", "meta 5", "\N{SUPERSCRIPT TWO}", ("mouse press", 1, 0, 0)):
            with self.subTest(key):
                self.assertIsNone(self.shown.unhandled_input(key))
                self.assertEqual("", self.shown.number)


if __name__ == "__main__":
    unittest.main()
