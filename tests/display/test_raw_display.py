from __future__ import annotations

import errno
import gc
import io
import itertools
import os
import pathlib
import selectors
import shutil
import signal
import socket
import stat
import struct
import sys
import tempfile
import typing
import unittest
import weakref
from unittest import mock

import urwid
from tests.util import TtyRefusingSelector
from urwid import signals
from urwid.display import _raw_display_base, escape
from urwid.display._raw_display_base import TermModes, detect_term_colors, detect_terminal_properties
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED, NO_HYPERLINK, AttrSpec
from urwid.util import set_temporary_encoding


def draw(screen: urwid.display.raw.Screen, canvas: urwid.Canvas, *, windows: bool = False) -> str:
    """Draw *canvas* on the started *screen* and return what is written to the terminal.

    The output depends on the platform only in how the last cell of the screen is inserted,
    so *windows* selects that form and the result is the same on every operating system.
    """
    written: list[str] = []
    screen.write = written.append
    screen.flush = lambda: None
    screen._started = True
    with mock.patch.object(_raw_display_base, "IS_WINDOWS", windows):
        screen.draw_screen((canvas.cols(), canvas.rows()), canvas)
    return "".join(written)


def insert(text: str, *, windows: bool) -> str:
    """Return how the raw display inserts *text*, one column wide, into the last cell of the screen."""
    return f"\x1b[1@{text}" if windows else f"\x1b[4h{text}\x1b[4l"


def raw_link_canvas() -> urwid.TextCanvas:
    """Return a canvas carrying OSC 8 bytes in zero-width charset "U" runs, as applications inject them."""
    raw_open = b"\x1b]8;;https://a.example\x1b\\"
    raw_close = b"\x1b]8;;\x1b\\"
    return urwid.TextCanvas(
        [b"ab" + raw_open + b"cd" + raw_close + b"  ", b"xy  ", b"pqrstu"],
        [
            [("plain", 2), (None, len(raw_open)), ("plain", 2), (None, len(raw_close)), (None, 2)],
            [("plain", 4)],
            [("plain", 6)],
        ],
        [[(None, 2), ("U", len(raw_open)), (None, 2), ("U", len(raw_close)), (None, 2)], [(None, 4)], [(None, 6)]],
        maxcol=6,
        check_width=False,
    )


def link_screen(hyperlinks: bool = True) -> urwid.display.raw.Screen:
    """Return a 16-color screen drawing OSC 8 hyperlinks when *hyperlinks* is set, with a "plain" palette entry."""
    screen = urwid.display.raw.Screen()
    screen.set_terminal_properties(colors=16, bright_is_bold=False, hyperlinks=hyperlinks)
    screen.back_color_erase = True
    screen.register_palette([("plain", "dark red", "default")])
    return screen


def runs_canvas(
    rows: list[list[tuple[typing.Hashable, typing.Literal["0", "U"] | None, bytes]]],
    cols: int,
) -> urwid.TextCanvas:
    """Return a canvas of *cols* columns made of (attribute, charset, bytes) runs, without measuring their width."""
    return urwid.TextCanvas(
        [b"".join(run for _attr, _cs, run in row) for row in rows],
        [[(attr, len(run)) for attr, _cs, run in row] for row in rows],
        [[(cs, len(run)) for _attr, cs, run in row] for row in rows],
        maxcol=cols,
        check_width=False,
    )


LINK_A = AttrSpec("dark red", "default", hyperlink="https://a.example")
LINK_B = AttrSpec("dark red", "default", hyperlink="https://b.example")
OPEN_A = "\x1b]8;;https://a.example\x1b\\"
OPEN_B = "\x1b]8;;https://b.example\x1b\\"
CLOSE = "\x1b]8;;\x1b\\"
RED = "\x1b[0;31;49m"
DEFAULT = "\x1b[0;39;49m"
# written before the first row of every draw
DRAW_START = "\x1b)0\x1b[?25l\x1b[0;39;49m\x1b[H\x1b[1;1H"


class TestRawDisplay(unittest.TestCase):
    def test_attrspec_to_escape(self):
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        a2e = s._attrspec_to_escape
        self.assertEqual("\x1b[0;33;42m", a2e(s.AttrSpec("brown", "dark green")))
        self.assertEqual("\x1b[0;38;5;229;4;48;5;164m", a2e(s.AttrSpec("#fea,underline", "#d0d")))
        self.assertEqual("\x1b[0;33;2;42m", a2e(s.AttrSpec("brown,faint", "dark green")))

    @unittest.skipUnless(
        sys.implementation.name == "cpython",
        "relies on reference counting freeing the screen as soon as it is dropped",
    )
    def test_dropped_screen_is_freed_without_the_cyclic_collector(self):
        """Nothing in a new screen refers back to it, so dropping it releases its sockets at once."""
        gc.disable()
        self.addCleanup(gc.enable)
        s = urwid.display.raw.Screen()
        screen_ref = weakref.ref(s)
        del s

        self.assertIsNone(screen_ref())

    def test_attrspec_faint(self):
        a = urwid.AttrSpec("dark red,faint", "")
        self.assertTrue(a.faint)
        self.assertEqual("dark red,faint", a.foreground)
        # faint can be combined with other settings and is kept on round-trip
        self.assertEqual(
            "AttrSpec('yellow,bold,faint', 'dark blue')",
            repr(urwid.AttrSpec("yellow,faint,bold", "dark blue")),
        )
        self.assertFalse(urwid.AttrSpec("dark red", "").faint)

    def test_last_row_drawn_untouched(self):
        """A last row with nothing of any width before Z, or raw sequence bytes after Y or in Y or Z, is untouched."""
        s = urwid.display.raw.Screen()
        wide, rlm = "\u65e5".encode(), "\u200f".encode()
        osc_open, osc_close = b"\x1b]8;;https://a.example\x1b\\", b"\x1b]8;;\x1b\\"
        for row in (
            [(None, None, wide)],
            [(None, None, wide), ("b", None, rlm)],
            [(None, None, b"x"), (None, "U", osc_open), (None, None, b"abc"), (None, "U", osc_close)],
            [(None, None, b"xab"), (None, "U", osc_open), (None, None, b"c"), (None, "U", osc_close)],
            [(None, "U", osc_open), (None, None, b"abc"), (None, "U", osc_close), (None, None, b"d")],
            [(None, "U", b"xa" + osc_open + b"b")],
            [(None, "U", b"ab" + osc_close)],
            [(None, "U", osc_open + b"a"), (None, None, b"b")],
            [(None, "U", b"ab\xc2\x9b31m")],  # a C1 CSI, as UTF-8
            [(None, "U", b"ab\xc2\x9d0;t\xc2\x9c")],  # a C1 OSC, as UTF-8
        ):
            with self.subTest(row=row), set_temporary_encoding("utf-8"):
                self.assertEqual((row, 0, []), s._last_row(row))

        row = [(None, "U", b"ab\x1b[1m")]
        with self.subTest(row=row), set_temporary_encoding("iso8859-1"):
            self.assertEqual((row, 0, []), s._last_row(row))

    def test_last_row_moves_back_over_the_last_character(self):
        """Z is drawn where Y starts, so the cursor moves back as many columns as Z is wide, not Y.

        Runs of no width are neither Y nor Z: those after Z are drawn after it, and those between Y and Z follow Y.
        """
        s = urwid.display.raw.Screen()
        wide = "\u65e5".encode()
        # the Hebrew word "shalom": "shin lamed", then Y "vav" and Z "final mem"
        head, y, z = "\u05e9\u05dc".encode(), "\u05d5".encode(), "\u05dd".encode()
        rli, pdi, rlm, acute = "\u2067".encode(), "\u2069".encode(), "\u200f".encode(), "\u0301".encode()
        for row, expected in (
            ([(None, None, b"a" + wide + b"c")], ([(None, None, b"a"), (None, None, b"c")], 1, [(None, None, wide)])),
            (
                [("x", None, b"ab "), ("y", None, wide)],
                ([("x", None, b"ab"), ("y", None, wide)], 2, [("x", None, b" ")]),
            ),
            (
                [("a", None, head + y + z), ("b", None, rlm)],
                ([("a", None, head), ("a", None, z), ("b", None, rlm)], 1, [("a", None, y)]),
            ),
            (
                [("a", None, b"x " + rli + head + y + z), ("b", None, pdi)],
                ([("a", None, b"x " + rli + head), ("a", None, z), ("b", None, pdi)], 1, [("a", None, y)]),
            ),
            (
                [("a", None, b"abce"), ("b", None, acute)],
                ([("a", None, b"ab"), ("a", None, b"e"), ("b", None, acute)], 1, [("a", None, b"c")]),
            ),
            (
                [("x", None, b"ab"), ("y", None, b"c"), ("b", None, rlm)],
                ([("x", None, b"a"), ("y", None, b"c"), ("b", None, rlm)], 1, [("x", None, b"b")]),
            ),
            (
                [("a", None, b"xy"), ("b", None, rlm), ("a", None, b"z"), ("b", None, rlm)],
                ([("a", None, b"x"), ("a", None, b"z"), ("b", None, rlm)], 1, [("a", None, b"y"), ("b", None, rlm)]),
            ),
            (
                [("a", None, b"abc"), ("b", None, acute), ("a", None, b"d")],
                ([("a", None, b"ab"), ("a", None, b"d")], 1, [("a", None, b"c"), ("b", None, acute)]),
            ),
            # a C1 byte inside a UTF-8 character is not a control
            (
                [(None, "U", "ab\u011b".encode())],
                ([(None, "U", b"a"), (None, "U", "\u011b".encode())], 1, [(None, "U", b"b")]),
            ),
            # a raw escape sequence in a run that neither Y nor Z is taken from does not matter
            (
                [(None, "U", b"\x1b[1ma"), (None, None, b"bc")],
                ([(None, "U", b"\x1b[1ma"), (None, None, b"c")], 1, [(None, None, b"b")]),
            ),
        ):
            with self.subTest(row=row), set_temporary_encoding("utf-8"):
                self.assertEqual(expected, s._last_row(row))

        # bytes 0x80-0x9f in an IBM PC character set run are glyphs, not controls
        row = [(None, "U", b"ab\x82")]
        with self.subTest(row=row), set_temporary_encoding("iso8859-1"):
            self.assertEqual(([(None, "U", b"a"), (None, "U", b"\x82")], 1, [(None, "U", b"b")]), s._last_row(row))

    def test_draw_screen_last_row_inserts_y_in_front_of_z(self):
        """Draw the last row without Y, move back over Z and insert Y in front of it.

        A narrow character before a wide last one is inserted in front of it, not into its second column,
        and a mark in a run of its own between Y and Z is written after Y is inserted, so it stays on Y.
        """
        mark, red = "\u0301", AttrSpec("dark red", "default")
        for windows in (False, True):
            with set_temporary_encoding("utf-8"):
                cases = (
                    (urwid.Text("ab 日").render((5,)), f"ab日\x08\x08{insert(' ', windows=windows)}"),
                    (
                        runs_canvas([[(None, None, b"abc"), (red, None, mark.encode()), (None, None, b"d")]], 4),
                        f"abd\x08{insert('c', windows=windows)}{RED}{mark}",
                    ),
                )
                for canvas, expected in cases:
                    with self.subTest(windows=windows, expected=expected):
                        s = urwid.display.raw.Screen()
                        s.set_terminal_properties(colors=16)

                        self.assertEqual(f"{DRAW_START}{expected}", draw(s, canvas, windows=windows))

    def test_attrspec_to_escape_fbterm(self) -> None:
        """Write the default colors and then the settings as SGR on fbterm, and only a set color as a palette entry.

        fbterm's SGR 39 also ends underline, so the settings come after it.
        """
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        s.term = "fbterm"
        a2e = s._attrspec_to_escape  # pylint: disable=protected-access  # the encoder has no public entry point
        for fg, bg, expected in (
            ("default", "default", "\x1b[0;39;49m"),
            ("black", "default", "\x1b[0;39;49m\x1b[1;0}"),
            ("brown,bold,underline", "dark green", "\x1b[0;39;49;1;4m\x1b[1;3}\x1b[2;2}"),
            ("default,underline", "default", "\x1b[0;39;49;4m"),
            ("default,standout", "#d0d", "\x1b[0;39;49;7m\x1b[2;164}"),
            ("#fea", "light blue", "\x1b[0;39;49m\x1b[1;229}\x1b[2;12}"),
        ):
            with self.subTest(fg=fg, bg=bg):
                self.assertEqual(expected, a2e(s.AttrSpec(fg, bg)))

    def test_attrspec_truecolor_to_escape(self):
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=16777216)
        a2e = s._attrspec_to_escape

        self.assertEqual(
            "\x1b[0;38;2;118;185;0;48;2;0;0;0m",
            a2e(s.AttrSpec("#76b900", "#000000")),
        )

    def test_named_palette_attr_to_escape(self):
        # Bright foreground colors render either as bold or as a 90-series color depending on the
        # terminal, so bright_is_bold is pinned instead of inherited from the ambient TERM.
        for bright_is_bold, expected in ((True, "\x1b[0;1;32;1;44m"), (False, "\x1b[0;92;1;44m")):
            with self.subTest(bright_is_bold=bright_is_bold):
                s = urwid.display.raw.Screen()
                s.set_terminal_properties(colors=256, bright_is_bold=bright_is_bold)
                s.register_palette_entry("focus", "light green,bold", "dark blue")

                self.assertEqual(expected, s._attr_to_escape("focus"))

    def test_draw_screen_two_columns_wide_characters(self):
        """Drawing double width text on a two column screen used to raise IndexError."""
        s = urwid.display.raw.Screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s._started = True

        with set_temporary_encoding("utf-8"):
            canvas = urwid.Text("日本語").render((2,))
            s.draw_screen((2, canvas.rows()), canvas)

        self.assertEqual(3, canvas.rows())
        self.assertIn("語", "".join(written))

    def test_draw_screen_shows_cursor_when_set(self):
        s = urwid.display.raw.Screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s._started = True

        canvas = urwid.Edit("x").render((10,), focus=True)
        s.draw_screen((10, canvas.rows()), canvas)

        output = "".join(written)
        self.assertEqual((1, 0), canvas.cursor)
        self.assertIn(escape.SHOW_CURSOR, output)
        self.assertIn(escape.HIDE_CURSOR, output)

    def test_draw_screen_replaces_control_characters(self):
        """Displayed text must not reach the terminal as C0 or C1 control sequences (e.g. OSC 52, CSI)."""
        for encoding in ("utf-8", "latin-1"):
            with self.subTest(encoding=encoding), set_temporary_encoding(encoding):
                s = urwid.display.raw.Screen()
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None

                # a canvas built directly, as Text leaves control characters out of the canvas it renders
                text = "a\x1b]0;t\x07 \x9d52;c;SGVsbG8=\x9c \x9b2J \x85é".encode(encoding)
                canvas = urwid.TextCanvas([text], maxcol=40)
                with mock.patch.object(s, "_started", True):
                    s.draw_screen((40, canvas.rows()), canvas)

                output = "".join(written)
                self.assertIn("a?]0;t? ?52;c;SGVsbG8=? ?2J ?é", output)
                self.assertFalse(any("\x80" <= char <= "\x9f" for char in output))

    def test_draw_screen_output_of_plain_and_raw_runs(self):
        """Pin the bytes written for plain attributes and application-injected charset "U" runs."""
        for windows in (False, True):
            with self.subTest(windows=windows), set_temporary_encoding("utf-8"):
                s = urwid.display.raw.Screen()
                s.set_terminal_properties(colors=16, bright_is_bold=False)
                s.back_color_erase = True
                s.register_palette([("plain", "dark red", "default")])

                self.assertEqual(
                    "\x1b)0\x1b[?25l\x1b[0;39;49m\x1b[H\x1b[1;1H"
                    "\x1b[0;31;49mab\x1b[0;39;49m\x1b]8;;https://a.example\x1b\\\x1b[0;31;49mcd\x1b[0;39;49m\x1b]8;;\x1b\\\x1b[K"
                    "\x1b[2;1H\x1b[0;31;49mxy\x1b[K"
                    f"\x1b[3;1Hpqrsu\x08{insert('t', windows=windows)}",
                    draw(s, raw_link_canvas(), windows=windows),
                )

    def test_hyperlinks_off_write_no_osc_8(self):
        """Adjacent runs that differ only by their hyperlink repeat their SGR once, and no OSC 8 is written."""
        plain = AttrSpec("dark red", "default")
        for windows in (False, True):
            with self.subTest(windows=windows), set_temporary_encoding("utf-8"):
                expected = draw(
                    link_screen(False),
                    runs_canvas([[("plain", None, b"ab"), (plain, None, b"cdef")]], 6),
                    windows=windows,
                )
                output = draw(
                    link_screen(False),
                    runs_canvas([[("plain", None, b"ab"), (LINK_A, None, b"cd"), (LINK_B, None, b"ef")]], 6),
                    windows=windows,
                )

                self.assertEqual(f"{DRAW_START}{RED}ab{RED}cdf\x08{insert('e', windows=windows)}", expected)
                self.assertEqual(f"{DRAW_START}{RED}ab{RED}cd{RED}f\x08{insert('e', windows=windows)}", output)

    def test_hyperlink_open_and_close(self):
        cursor_canvas = runs_canvas([[(LINK_A, None, b"ab")], [(None, None, b"cd")]], 2)
        cursor_canvas.cursor = (0, 1)
        cases = (
            (
                "attribute change and row end",
                runs_canvas(
                    [[("plain", None, b"ab"), (LINK_A, None, b"cd"), (LINK_B, None, b"ef")], [(None, None, b"      ")]],
                    6,
                ),
                f"{RED}ab{RED}{OPEN_A}cd{RED}{OPEN_B}ef{CLOSE}\x1b[2;1H{DEFAULT}\x1b[K",
            ),
            (
                "linked trailing spaces keep their cells",
                runs_canvas([[("plain", None, b"ab"), (LINK_A, None, b"  ")], [(None, None, b"    ")]], 4),
                f"{RED}ab{RED}{OPEN_A}  {CLOSE}\x1b[2;1H{DEFAULT}\x1b[K",
            ),
            (
                "each row reopens",
                runs_canvas([[(LINK_A, None, b"ab")], [(LINK_A, None, b"cd")], [(None, None, b"  ")]], 2),
                f"{RED}{OPEN_A}ab{CLOSE}\x1b[2;1H{RED}{OPEN_A}cd{CLOSE}\x1b[3;1H{DEFAULT}\x1b[K",
            ),
            (
                "explicit no link closes once",
                runs_canvas(
                    [
                        [
                            (LINK_A, None, b"ab"),
                            (AttrSpec(hyperlink=NO_HYPERLINK), None, b"cd"),
                            ("plain", None, b"ef"),
                        ],
                        [(None, None, b"  ")],
                    ],
                    6,
                ),
                f"{RED}{OPEN_A}ab{CLOSE}{DEFAULT}cd{RED}ef\x1b[2;1H{DEFAULT}\x1b[K",
            ),
            (
                "last row insert",
                runs_canvas([[(None, None, b"abc")], [("plain", None, b"x"), (LINK_A, None, b"yz")]], 3),
                f"abc\x1b[2;1H{RED}x{RED}{OPEN_A}z\x08{{y}}{CLOSE}",
            ),
            (
                "cursor",
                cursor_canvas,
                f"{RED}{OPEN_A}ab{CLOSE}\x1b[2;1H{DEFAULT}d\x08{{c}}\x1b[2;1H\x1b[?25h",
            ),
        )
        # {c} and {y} stand for the last cell of the screen, inserted as the platform does it
        for (name, canvas, expected), windows in itertools.product(cases, (False, True)):
            inserts = {cell: insert(cell, windows=windows) for cell in "cy"}
            with self.subTest(name, windows=windows), set_temporary_encoding("utf-8"):
                self.assertEqual(
                    f"{DRAW_START}{expected.format_map(inserts)}",
                    draw(link_screen(), canvas, windows=windows),
                )

    def test_hyperlinks_and_raw_runs(self):
        """OSC 8 bytes of charset "U" runs are written unchanged, and urwid's own link is reopened after them."""
        raw_open = OPEN_B.encode()
        raw_close = CLOSE.encode()
        cases = (
            (
                "raw link before an attribute link",
                runs_canvas(
                    [
                        [
                            (None, "U", raw_open),
                            ("plain", None, b"ab"),
                            (None, "U", raw_close),
                            (LINK_A, None, b"cd"),
                        ],
                        [(None, None, b"    ")],
                    ],
                    4,
                ),
                f"{OPEN_B}{RED}ab{DEFAULT}{CLOSE}{RED}{OPEN_A}cd{CLOSE}\x1b[2;1H{DEFAULT}\x1b[K",
            ),
            (
                "raw link across rows",
                runs_canvas(
                    [[("plain", None, b"ab"), (None, "U", raw_open)], [(None, "U", raw_close), ("plain", None, b"cd")]],
                    2,
                ),
                f"{RED}ab{DEFAULT}{OPEN_B}\x1b[2;1H{DEFAULT}{CLOSE}{RED}d\x08{{c}}",
            ),
            (
                "raw run inside an attribute link",
                runs_canvas(
                    [[(LINK_A, None, b"ab"), (LINK_A, "U", raw_open), (LINK_A, None, b"cd")], [(None, None, b"    ")]],
                    4,
                ),
                f"{RED}{OPEN_A}ab{OPEN_B}{RED}{OPEN_A}cd{CLOSE}\x1b[2;1H{DEFAULT}\x1b[K",
            ),
        )
        # {c} and {y} stand for the last cell of the screen, inserted as the platform does it
        for (name, canvas, expected), windows in itertools.product(cases, (False, True)):
            inserts = {cell: insert(cell, windows=windows) for cell in "cy"}
            with self.subTest(name, windows=windows), set_temporary_encoding("utf-8"):
                self.assertEqual(
                    f"{DRAW_START}{expected.format_map(inserts)}",
                    draw(link_screen(), canvas, windows=windows),
                )

    def test_linked_trailing_spaces_are_erased_with_hyperlinks_off(self):
        output = draw(
            link_screen(False),
            runs_canvas([[("plain", None, b"ab"), (LINK_A, None, b"  ")], [(None, None, b"    ")]], 4),
        )

        self.assertEqual(f"{DRAW_START}{RED}ab{RED}\x1b[K\x1b[2;1H{DEFAULT}\x1b[K", output)

    def test_screen_attrspec_shortcut_passes_the_hyperlink(self):
        screen = link_screen()

        self.assertEqual(
            AttrSpec("dark red", "default", 16, hyperlink="https://a.example"),
            screen.AttrSpec("dark red", "default", hyperlink="https://a.example"),
        )

    def test_hyperlink_change_redraws_only_its_row(self):
        screen = link_screen()
        draw(screen, runs_canvas([[(LINK_A, None, b"ab")], [("plain", None, b"cd")]], 2))

        output = draw(screen, runs_canvas([[(LINK_B, None, b"ab")], [("plain", None, b"cd")]], 2))

        self.assertEqual(f"\x1b[?25l{DEFAULT}\x1b[H\x1b[1;1H{RED}{OPEN_B}ab{CLOSE}", output)

    def test_set_hyperlinks_alone_clears_the_caches(self):
        screen = link_screen(False)
        screen.screen_buf = []
        self.assertEqual(RED, screen._attr_to_escape(LINK_A))

        screen.set_terminal_properties(hyperlinks=True)

        self.assertTrue(screen.hyperlinks)
        self.assertIsNone(screen.screen_buf)
        self.assertEqual(f"{RED}{OPEN_A}", screen._attr_to_escape(LINK_A))

    def test_stop_closes_a_hyperlink_when_hyperlinks_are_on(self):
        for hyperlinks in (False, True):
            with self.subTest(hyperlinks=hyperlinks):
                screen = link_screen(hyperlinks)
                written: list[str] = []
                screen.write = written.append
                screen.flush = lambda: None

                with mock.patch.object(screen, "_mouse_tracking"):
                    screen._stop_mouse_restore_buffer()

                output = "".join(written)
                self.assertEqual(hyperlinks, output.startswith(CLOSE))
                self.assertEqual(int(hyperlinks), output.count("\x1b]8"))

    def test_restart_after_stop_reconnects_input(self):
        """stop() followed by start() must leave the screen's input descriptors watchable again
        (regression test for urwid/urwid#285).

        MainLoop reacts to INPUT_DESCRIPTORS_CHANGED by re-hooking the event loop
        with whatever ``get_input_descriptors()`` currently returns, so that list
        must be non-empty again once ``start()`` finishes -- otherwise stopping the
        screen to run an external program and then restarting it silently stops
        delivering keypresses.
        """
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = urwid.display.raw.Screen(input=os.fdopen(read_fd, "rb", buffering=0), output=open(os.devnull, "w"))

        watched = {}

        class FakeEventLoop:
            def watch_file(self, fd, callback):
                fd = fd if isinstance(fd, int) else fd.fileno()
                watched[fd] = callback
                return fd

            def remove_watch_file(self, handle):
                watched.pop(handle, None)
                return True

        event_loop = FakeEventLoop()

        def reset_input_descriptors():
            s.unhook_event_loop(event_loop)
            s.hook_event_loop(event_loop, lambda keys, raw: None)

        s.start()
        signals.connect_signal(s, INPUT_DESCRIPTORS_CHANGED, reset_input_descriptors)
        reset_input_descriptors()
        self.assertTrue(watched, "expected watched descriptors after the initial start()")

        s.stop()
        s.start()

        self.assertTrue(watched, "no descriptors are watched after restart -- regression of urwid/urwid#285")
        s.stop()

    def test_modify_terminal_palette_restored_on_stop(self):
        """Palette entries modified with modify_terminal_palette() must be reset when the screen stops,
        so urwid doesn't leave the user's terminal with a custom palette after the process exits
        (urwid/urwid#458).

        The Linux console has neither OSC 4 nor OSC 104, and fbterm has no reset sequence.
        """
        osc4 = ("\x1b]4;1;rgb:ff/00/00;2;rgb:00/ff/00\x1b\\", "\x1b]104;1;2\x1b\\")
        linux = ("\x1b]P1ff0000\x1b]P200ff00", "\x1b]R")
        for term, (expected_set, expected_restore) in {
            "xterm-256color": osc4,
            # GNU screen interprets the sequences itself, whatever terminal it runs in
            "screen.linux": osc4,
            "fbterm": ("\x1b[3;1;255;0;0;2;0;255;0}", ""),
            "linux": linux,
            "linux-16color": linux,
            "linux.utf8": linux,
            # versioned terminfo names of the Linux console
            "linux2.6.26": linux,
            "linux3.0": linux,
            "linuxfoo": osc4,
        }.items():
            with self.subTest(term=term):
                s = urwid.display.raw.Screen()
                s.term = term
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s._started = True

                s.modify_terminal_palette([(1, 255, 0, 0), (2, 0, 255, 0)])
                self.assertEqual(expected_set, "".join(written))
                self.assertEqual({1, 2}, s._modified_palette_entries)

                written.clear()
                s._stop_restore_palette()

                self.assertEqual(expected_restore, "".join(written))
                self.assertEqual(set(), s._modified_palette_entries)

    def test_modify_terminal_palette_rejects_unrepresentable_entries(self) -> None:
        """An entry the terminal's sequence cannot carry raises before anything is written.

        A value that is not an integer is rejected by every terminal. The Linux console sequence has one hex digit
        for the index and two per component, so a wider value would end the sequence early.
        """
        for term, entry, error in (
            ("xterm-256color", (1, None, 0, 0), TypeError),
            ("xterm-256color", (1, 0.5, 0, 0), TypeError),
            ("xterm-256color", ("1", 0, 0, 0), TypeError),
            ("fbterm", (1, 0, None, 0), TypeError),
            ("fbterm", (1, 0, "0", 0), TypeError),
            ("linux", (1, 0, 0, None), TypeError),
            ("linux", (1.0, 0, 0, 0), TypeError),
            ("linux", (256, 0, 0, 0), ValueError),
            ("linux", (-1, 0, 0, 0), ValueError),
            ("linux", (1, 256, 0, 0), ValueError),
            ("linux", (1, 0, -1, 0), ValueError),
        ):
            with self.subTest(term=term, entry=entry):
                s = urwid.display.raw.Screen()
                s.term = term
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s._started = True

                with self.assertRaises(error):
                    s.modify_terminal_palette([(0, 0, 0, 0), entry])

                self.assertEqual([], written)
                self.assertEqual(set(), s._modified_palette_entries)

    def test_modify_terminal_palette_linux_console_skips_missing_entries(self) -> None:
        """The Linux console has entries 0-15 only: the others are skipped, and not reset on stop."""
        for entries, expected, modified in (
            ([(1, 255, 0, 0), (16, 0, 255, 0), (255, 0, 0, 255)], "\x1b]P1ff0000", {1}),
            ([(16, 0, 255, 0), (255, 0, 0, 255)], "", set()),
        ):
            with self.subTest(entries=entries):
                s = urwid.display.raw.Screen()
                s.term = "linux"
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s._started = True

                s.modify_terminal_palette(entries)

                self.assertEqual(expected, "".join(written))
                self.assertEqual(modified, s._modified_palette_entries)

    def test_reset_default_terminal_palette_linux_console(self) -> None:
        """The Linux console gets the same 16 basic colors whatever the color mode, since its palette has no more."""
        outputs: set[str] = set()
        for colors in (16, 88, 256, 2**24):
            with self.subTest(colors=colors):
                s = urwid.display.raw.Screen()
                s.term = "linux"
                s.set_terminal_properties(colors=colors)
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s._started = True

                s.reset_default_terminal_palette()

                output = "".join(written)
                self.assertEqual(16, output.count("\x1b]P"))
                self.assertTrue(output.startswith("\x1b]P0000000"))
                self.assertEqual(set(range(16)), s._modified_palette_entries)
                outputs.add(output)
        self.assertEqual(1, len(outputs))

    def test_stop_restore_palette_noop_when_untouched(self):
        """No reset escape should be sent if the palette was never modified."""
        for term in ("xterm-256color", "linux"):
            with self.subTest(term=term):
                s = urwid.display.raw.Screen()
                s.term = term
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s._started = True

                s._stop_restore_palette()

                self.assertEqual([], written)

    def test_linux_palette_reset_is_not_the_last_write_on_stop(self):
        """A terminal that only claims TERM=linux reads ESC ] R as an unterminated OSC string.

        The sequences written after it on stop end that string, so it cannot swallow the shell prompt.
        """
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = urwid.display.raw.Screen(input=os.fdopen(read_fd, "rb", buffering=0), output=open(os.devnull, "w"))
        self.addCleanup(s._term_input_file.close)
        self.addCleanup(s._term_output_file.close)
        s.start()
        s.term = "linux"
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s.modify_terminal_palette([(1, 255, 0, 0)])
        written.clear()

        s.stop()

        output = "".join(written)
        self.assertIn(escape.LINUX_RESET_PALETTE, output)
        self.assertIn(escape.ESC, output.partition(escape.LINUX_RESET_PALETTE)[2])

    def test_draw_screen_ignores_eintr(self):
        """An EINTR OSError from write() during draw_screen() is swallowed (interrupted syscall)."""
        s = urwid.display.raw.Screen()
        s._setup_G1_done = True  # skip the G1-setup write, so the error comes from the frame write under test
        s.write = mock.Mock(side_effect=OSError(errno.EINTR, "interrupted system call"))
        s.flush = lambda: None
        s._started = True

        canvas = urwid.Text("x").render((1,))
        s.draw_screen((1, canvas.rows()), canvas)  # must not raise

    def test_setup_g1_propagates_oserror(self):
        """A terminal that cannot be written to raises instead of retrying, and the setup is tried again later."""
        s = urwid.display.raw.Screen()
        s.write = mock.Mock(side_effect=OSError(errno.EIO, "I/O error"))
        s.flush = lambda: None

        canvas = urwid.Text("x").render((1,))
        with mock.patch.object(s, "_started", True):
            for _ in range(2):
                with self.assertRaises(OSError):
                    s.draw_screen((1, canvas.rows()), canvas)

        self.assertEqual([mock.call(escape.DESIGNATE_G1_SPECIAL)] * 2, s.write.call_args_list)

    def test_setup_g1_after_restart(self) -> None:
        """Designate G1 once while the screen runs, and again on the first draw after it is stopped and restarted."""
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        input_file = self.enterContext(os.fdopen(read_fd, "rb", buffering=0))
        s = urwid.display.raw.Screen(input=input_file, output=io.StringIO())
        written: list[str] = []
        with (
            mock.patch.object(s, "write", side_effect=written.append),
            mock.patch.object(s, "flush"),
        ):
            for _ in range(2):
                s.start()
                for text in ("x", "y"):
                    canvas = urwid.Text(text).render((1,))
                    s.draw_screen((1, canvas.rows()), canvas)
                s.stop()

        self.assertEqual(2, written.count(escape.DESIGNATE_G1_SPECIAL))
        # each run designates G1 in its first frame, before the stop that ends it
        stops = [i for i, data in enumerate(written) if escape.SI in data]
        designations = [i for i, data in enumerate(written) if data == escape.DESIGNATE_G1_SPECIAL]
        self.assertLess(designations[0], stops[0])
        self.assertLess(stops[0], designations[1])

    def test_draw_screen_reraises_other_oserror(self):
        """An OSError with an errno other than EINTR during draw_screen() must propagate."""
        s = urwid.display.raw.Screen()
        s._setup_G1_done = True  # skip the G1-setup write, so the error comes from the frame write under test
        s.write = mock.Mock(side_effect=OSError(errno.EIO, "I/O error"))
        s.flush = lambda: None
        s._started = True

        canvas = urwid.Text("x").render((1,))
        with self.assertRaises(OSError):
            s.draw_screen((1, canvas.rows()), canvas)

    def test_get_available_raw_input_drains_resize_pipe(self):
        """Every pending write on the resize pipe is drained in one call, however many arrived."""
        s = urwid.display.raw.Screen()
        # Only the resize-pipe drain is under test here: route around the keyboard-input side
        # (_wait_for_input_ready()'s select() over get_input_descriptors(), which is platform- and
        # terminal-state-sensitive -- e.g. it needs a started screen with a real selectable input,
        # and an empty descriptor list raises WSAEINVAL when select()ed on Windows) entirely.
        s._get_input_codes = list
        s._resize_pipe_wr.send(b"R")
        s._resize_pipe_wr.send(b"R")
        s._resize_pipe_wr.send(b"R")

        codes = s.get_available_raw_input()

        self.assertEqual([], codes)
        # The pipe is now empty: a second call must not find anything left to drain either.
        self.assertEqual([], s.get_available_raw_input())

    def test_input_refused_by_the_default_selector_is_reported_ready(self):
        """Input the default selector refuses with EINVAL, as kqueue on macOS refuses /dev/tty, is still waited for."""
        s = urwid.display.raw.Screen()
        rd, wr = socket.socketpair()
        self.addCleanup(rd.close)
        self.addCleanup(wr.close)
        s.get_input_descriptors = lambda: [rd.fileno()]
        wr.send(b"x")

        with mock.patch.object(selectors, "DefaultSelector", TtyRefusingSelector):
            ready = s._wait_for_input_ready(0)

        self.assertEqual([rd.fileno()], ready)

    def test_resize_drops_screen_buffer_in_parse_input(self):
        """The resize handler leaves the screen buffer to the drawing thread, which drops it with the report."""
        s = urwid.display.raw.Screen()
        s.screen_buf = [[]]

        s._sigwinch_handler()

        self.assertTrue(s._resized)
        self.assertEqual([[]], s.screen_buf)

        keys, _raw = s.parse_input(None, None, [])

        self.assertEqual(["window resize"], keys)
        self.assertFalse(s._resized)
        self.assertIsNone(s.screen_buf)

    def test_resize_wake_up_does_not_block_on_a_full_socket(self):
        """A wake-up already pending in a full socket is enough, so the handler returns instead of blocking."""
        s = urwid.display.raw.Screen()
        with mock.patch.object(s, "_resize_pipe_wr") as wake_socket:
            wake_socket.send.side_effect = BlockingIOError

            s._sigwinch_handler()

        wake_socket.send.assert_called_once_with(b"R")
        self.assertTrue(s._resized)

    def test_attrspec_hash_is_stable_and_matches_equal_instances(self):
        """AttrSpec caches its hash at construction time; equal instances must still hash equal,
        and the cached value must match what a fresh hash computation would give.
        """
        a = AttrSpec("yellow", "dark blue")
        b = AttrSpec("yellow", "dark blue")

        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(hash((a.__class__, a._value, a.hyperlink)), hash(a))

    def test_attr_to_escape_uses_attrspec_as_dict_key(self):
        """_pal_escape.get(a) is looked up with an AttrSpec instance directly (not just by
        palette name), which requires AttrSpec to hash and compare consistently.
        """
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        a = s.AttrSpec("brown", "dark green")
        s._pal_escape[a] = "sentinel escape"

        self.assertEqual("sentinel escape", s._attr_to_escape(a))
        self.assertEqual("sentinel escape", s._attr_to_escape(s.AttrSpec("brown", "dark green")))

    def test_legacy_get_input_nonblocking_warns_and_still_polls(self):
        class LegacyScreen(urwid.display.raw.Screen):
            def get_input_nonblocking(self):
                return None, ["a"], [97]

        s = LegacyScreen()
        received = []
        with self.assertWarns(DeprecationWarning) as ctx:
            wrapper = s._make_legacy_input_wrapper(mock.Mock(), lambda keys, raw: received.append((keys, raw)))
        self.assertEqual(__file__, ctx.filename)
        self.assertIn("will be removed in version 7.0", str(ctx.warning))

        wrapper()
        self.assertEqual([(["a"], [97])], received)


def terminfo_entry(colors: int, *, magic: int = 0o432, names: bytes = b"test|test terminal\0") -> bytes:
    """Return a compiled terminfo entry, as term(5) describes it, with one boolean and *colors* as its 14th number."""
    booleans = b"\x01"
    number_format = {0o432: "<h", 0o1036: "<i"}[magic]
    numbers = b"".join(struct.pack(number_format, number) for number in (*(-1,) * 13, colors))
    padding = b"\0" * ((len(names) + len(booleans)) % 2)
    return struct.pack("<6h", magic, len(names), len(booleans), 14, 0, 0) + names + booleans + padding + numbers


class TestTerminalProperties(unittest.TestCase):
    def setUp(self) -> None:
        """Keep the host terminfo database out of the results, and give each test its own database root."""
        self.enterContext(mock.patch.object(_raw_display_base, "_TERMINFO_SYSTEM_DIRS", ()))
        # Resolved, because the terminfo reader stats the realpath: on macOS the temporary directory is under /var,
        # a symlink to /private/var, and a test matching on the unresolved path never sees the reader's calls.
        self.root = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)

    def install_terminfo(self, path: str, data: bytes) -> str:
        """Write *data* as the entry at *path* under the temporary root and return the directory of its database."""
        entry = self.root / path
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_bytes(data)
        return str(entry.parent.parent)

    def test_term_families(self) -> None:
        cases = (
            ("", 16, True, True, False, True),
            ("xterm", 16, True, False, False, True),
            ("xterm-256color", 256, True, False, False, True),
            ("xterm-direct", 16777216, True, False, False, True),
            ("linux", 16, True, True, True, True),
            ("linux-16color", 16, True, True, True, True),
            ("linux2.6", 16, True, True, True, True),
            ("linux3.0", 16, True, True, True, True),
            ("gnome-256color", 256, True, False, False, True),
            ("konsole", 16, True, False, False, True),
            ("konsole-direct", 16777216, True, False, False, True),
            ("rxvt-unicode-256color", 256, True, False, False, True),
            ("vte-256color", 256, True, False, False, True),
            ("screen", 16, True, True, False, False),
            ("screen-256color", 256, True, True, False, False),
            ("screen-256color-bce", 256, True, True, False, True),
            ("screen.xterm-256color", 256, True, False, False, False),
            ("tmux-256color", 256, True, False, False, True),
            ("alacritty", 16777216, True, False, False, True),
            ("xterm-kitty", 16777216, True, False, False, True),
            ("dumb", 1, False, True, False, False),
            ("xterm-88color", 88, True, False, False, True),
        )
        for term, colors, underline, bright_bold, blink, bce in cases:
            with self.subTest(term=term):
                props = detect_terminal_properties(term, {}, windows_version=(0, 0, 0))
                self.assertEqual(colors, props.colors)
                self.assertEqual(underline, props.has_underline)
                self.assertEqual(bright_bold, props.fg_bright_is_bold)
                self.assertEqual(blink, props.bg_bright_is_blink)
                self.assertEqual(bce, props.back_color_erase)

    def test_color_environment_variables(self) -> None:
        xterm = "xterm-256color"

        def colors(term: str, environ: dict[str, str]) -> int:
            return detect_term_colors(term, environ, windows_version=(0, 0, 0))

        self.assertEqual(1, colors(xterm, {"NO_COLOR": "1"}))
        self.assertEqual(1, colors(xterm, {"CLICOLOR": "0"}))
        self.assertEqual(16, colors(xterm, {"FORCE_COLOR": "1"}))
        self.assertEqual(256, colors("xterm", {"FORCE_COLOR": "2"}))
        self.assertEqual(16777216, colors("linux", {"FORCE_COLOR": "3"}))
        self.assertEqual(256, colors("xterm", {"CLICOLOR_FORCE": "2"}))
        self.assertEqual(16777216, colors(xterm, {"COLORTERM": "truecolor"}))
        self.assertEqual(16777216, colors("xterm", {"COLORTERM": "24bit"}))
        self.assertEqual(256, colors("xterm", {"COLORTERM": "gnome-terminal"}))
        # NO_COLOR wins over COLORTERM / FORCE_COLOR
        self.assertEqual(1, colors(xterm, {"NO_COLOR": "1", "COLORTERM": "truecolor"}))
        self.assertEqual(1, colors(xterm, {"NO_COLOR": "1", "FORCE_COLOR": "3"}))
        # Empty NO_COLOR is unset per the spec
        self.assertEqual(256, colors(xterm, {"NO_COLOR": ""}))

    @unittest.skipIf(sys.platform == "win32", "native Windows has no terminfo lookup")
    def test_terminfo_colors(self) -> None:
        """Check that the ``colors`` of a terminfo entry raises the colour count the TERM name gives."""
        terminfo = self.install_terminfo("terminfo/f/fancy", terminfo_entry(256))
        self.install_terminfo("terminfo/f/fancy-direct32", terminfo_entry(16777216, magic=0o1036, names=b"fancy\0"))
        self.install_terminfo("terminfo/f/fancy-8", terminfo_entry(8))
        self.install_terminfo("terminfo/f/fancy-mono", terminfo_entry(-1))
        self.install_terminfo("terminfo/f/fancy-truncated", terminfo_entry(256)[:-2])
        self.install_terminfo("terminfo/f/fancy-bad-magic", terminfo_entry(256)[2:])
        bad_strings = struct.pack("<6h", 0o432, 0, 0, 14, -5, -5) + terminfo_entry(256)[12 + 20 :]
        self.install_terminfo("terminfo/f/fancy-bad-strings", bad_strings)
        self.install_terminfo("terminfo/a/alacritty", terminfo_entry(256))
        environ = {"TERMINFO": terminfo}
        cases: tuple[tuple[str, dict[str, str], int], ...] = (
            ("fancy", {}, 16),
            ("fancy", environ, 256),
            ("fancy-direct32", environ, 16777216),
            ("fancy-8", environ, 16),
            ("fancy-mono", environ, 16),
            ("fancy-truncated", environ, 16),
            ("fancy-bad-magic", environ, 16),
            ("fancy-bad-strings", environ, 16),
            # the entry raises the count the name gives and never lowers it
            ("alacritty", environ, 16777216),
            # the environment variables still decide over the entry
            ("fancy-direct32", {**environ, "NO_COLOR": "1"}, 1),
            ("fancy-8", {**environ, "COLORTERM": "yes"}, 256),
            # TERM never leaves the database directory, and only names a file the platform can encode
            ("../f/fancy", {"TERMINFO": f"{terminfo}/f"}, 16),
            ("f:fancy", environ, 16),
            ("fancy\udc80", environ, 16),
        )
        for term, case_environ, colors in cases:
            with self.subTest(term=term, environ=case_environ):
                self.assertEqual(colors, detect_term_colors(term, case_environ, windows_version=(0, 0, 0)))

    @unittest.skipIf(sys.platform == "win32", "native Windows has no terminfo lookup")
    def test_terminfo_search_order(self) -> None:
        """Check that terminfo entries are searched in ncurses' directory order."""
        terminfo = self.install_terminfo("terminfo/f/fancy", terminfo_entry(256))
        self.install_terminfo("home/.terminfo/66/fancy", terminfo_entry(88))  # hexadecimal subdirectory, as on macOS
        first = self.install_terminfo("first/f/fancy", terminfo_entry(16777216, magic=0o1036))
        # Malformed entries and directories named like an entry are passed over.
        broken = self.install_terminfo("broken/f/fancy", terminfo_entry(256)[:-2])
        (self.root / "broken/66/fancy").mkdir(parents=True)
        home = str(self.root / "home")
        cases = (
            ({"TERMINFO": terminfo, "HOME": home, "TERMINFO_DIRS": first}, 256),
            ({"HOME": home, "TERMINFO_DIRS": first}, 88),
            ({"TERMINFO_DIRS": os.pathsep.join(("", first))}, 16777216),
            ({"TERMINFO": broken, "TERMINFO_DIRS": first}, 16777216),
            ({"TERMINFO": "nul\0byte", "HOME": "lone\udc80surrogate", "TERMINFO_DIRS": first}, 16777216),
        )
        for environ, colors in cases:
            with self.subTest(environ=environ):
                self.assertEqual(colors, detect_term_colors("fancy", environ, windows_version=(0, 0, 0)))
        with mock.patch.object(_raw_display_base, "_TERMINFO_SYSTEM_DIRS", (first,)):
            self.assertEqual(16777216, detect_term_colors("fancy", {}, windows_version=(0, 0, 0)))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are POSIX only")
    def test_terminfo_fifo_is_not_opened(self) -> None:
        """Check that a FIFO named like a terminfo entry is passed over without being opened."""
        fifo = self.root / "terminfo/f/fancy"
        fifo.parent.mkdir(parents=True)
        os.mkfifo(fifo)
        terminfo = self.install_terminfo("first/f/fancy", terminfo_entry(256))
        environ = {"TERMINFO": str(fifo.parent.parent), "TERMINFO_DIRS": terminfo}

        def blocked(_signum: int, _frame: object) -> None:
            # Not an OSError such as TimeoutError, which the lookup would catch and pass over.
            self.fail("reading the FIFO blocked")

        self.addCleanup(signal.signal, signal.SIGALRM, signal.signal(signal.SIGALRM, blocked))
        self.addCleanup(signal.setitimer, signal.ITIMER_REAL, 0)
        signal.setitimer(signal.ITIMER_REAL, 5)
        with mock.patch.object(os, "open", wraps=os.open) as os_open:
            self.assertEqual(256, detect_term_colors("fancy", environ, windows_version=(0, 0, 0)))
        # Only the valid entry is opened, not the FIFO in front of it.
        self.assertEqual(1, sum(pathlib.PurePath(call.args[0]).name == "fancy" for call in os_open.call_args_list))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are POSIX only")
    def test_terminfo_entry_replaced_after_stat_is_not_opened(self) -> None:
        """Check that an entry swapped for a symlink after its stat() is not followed to what the link names."""
        terminfo = self.install_terminfo("terminfo/f/fancy", terminfo_entry(256))
        entry = self.root / "terminfo/f/fancy"
        device = self.root / "device"  # a FIFO stands in for a device, which a test cannot create
        os.mkfifo(device)
        real_stat = os.stat

        def stat_then_swap(path: str | os.PathLike[str], *, follow_symlinks: bool = True) -> os.stat_result:
            result = real_stat(path, follow_symlinks=follow_symlinks)
            if pathlib.Path(path) == entry:
                entry.unlink()
                entry.symlink_to(device)
            return result

        real_open = os.open
        opened_fifos = []

        def open_and_record(path: str | os.PathLike[str], flags: int, *, dir_fd: int | None = None) -> int:
            fd = real_open(path, flags, dir_fd=dir_fd)
            if stat.S_ISFIFO(os.fstat(fd).st_mode):
                opened_fifos.append(path)
            return fd

        with (
            mock.patch.object(os, "stat", side_effect=stat_then_swap),
            mock.patch.object(os, "open", side_effect=open_and_record),
        ):
            colors = detect_term_colors("fancy", {"TERMINFO": terminfo}, windows_version=(0, 0, 0))
        self.assertEqual(16, colors)
        self.assertTrue(entry.is_symlink())
        self.assertEqual([], opened_fifos)

    def test_terminfo_not_read_on_windows(self) -> None:
        """Check that nothing is opened on Windows, where a file name such as COM1 can name a device."""
        terminfo = self.install_terminfo("terminfo/f/fancy", terminfo_entry(256))
        with (
            mock.patch.object(_raw_display_base, "IS_WINDOWS", new=True),
            mock.patch.object(os, "stat", wraps=os.stat) as os_stat,
            mock.patch.object(os, "open", wraps=os.open) as os_open,
        ):
            colors = detect_term_colors("fancy", {"TERMINFO": terminfo}, windows_version=(0, 0, 0))
        self.assertEqual(16, colors)
        os_stat.assert_not_called()
        os_open.assert_not_called()

    def test_windows_console_vt(self) -> None:
        win7 = (6, 1, 7601)
        win10_rtm = (10, 0, 10240)
        win10_1511 = (10, 0, 10586)
        win10_1703 = (10, 0, 15063)
        win11 = (10, 0, 22621)

        props = detect_terminal_properties("", {}, windows_version=win7)
        self.assertEqual(16, props.colors)
        self.assertTrue(props.fg_bright_is_bold)

        props = detect_terminal_properties("", {}, windows_version=win10_rtm)
        self.assertEqual(16, props.colors)
        self.assertTrue(props.fg_bright_is_bold)

        props = detect_terminal_properties("", {}, windows_version=win10_1511)
        self.assertEqual(256, props.colors)
        self.assertFalse(props.fg_bright_is_bold)
        self.assertTrue(props.has_underline)
        self.assertTrue(props.back_color_erase)
        self.assertFalse(props.bg_bright_is_blink)

        for version in (win10_1703, win11):
            with self.subTest(windows_version=version):
                props = detect_terminal_properties("", {}, windows_version=version)
                self.assertEqual(16777216, props.colors)
                self.assertFalse(props.fg_bright_is_bold)
                self.assertTrue(props.has_underline)
                self.assertTrue(props.back_color_erase)
                self.assertFalse(props.bg_bright_is_blink)

        self.assertEqual(1, detect_terminal_properties("", {"NO_COLOR": "1"}, windows_version=win11).colors)
        self.assertEqual(1, detect_terminal_properties("dumb", {}, windows_version=win11).colors)

    def test_windows_terminal_hosts(self) -> None:
        # Windows Terminal / ConEmu / VS Code report xterm-256color but speak 24-bit SGR.
        for environ in (
            {"WT_SESSION": "deadbeef-0000-0000-0000-000000000000"},
            {"WT_PROFILE_ID": "{guid}"},
            {"ConEmuANSI": "ON"},
            {"ConEmuPID": "1234"},
            {"TERM_PROGRAM": "vscode"},
        ):
            with self.subTest(environ=environ):
                props = detect_terminal_properties("xterm-256color", environ, windows_version=(6, 1, 7601))
                self.assertEqual(16777216, props.colors)
                self.assertFalse(props.fg_bright_is_bold)
                self.assertTrue(props.has_underline)


class TestTermModesSetFromCodes(unittest.TestCase):
    def test_recognized_reply_resolves_sentinel(self) -> None:
        modes = TermModes()
        newly_supported = modes.set_from_codes((escape.PrivateMode.BRACKETED_PASTE, 1))
        self.assertTrue(modes.bracketed_paste)
        self.assertEqual({"bracketed_paste"}, newly_supported)

    def test_unrecognized_reply_resolves_sentinel_to_false(self) -> None:
        modes = TermModes()
        newly_supported = modes.set_from_codes((escape.PrivateMode.BRACKETED_PASTE, 0))
        self.assertFalse(modes.bracketed_paste)
        self.assertEqual(frozenset(), newly_supported)

    def test_permanently_reset_reply_resolves_sentinel_to_false(self) -> None:
        """A mode the terminal recognises but can never turn on is not supported."""
        modes = TermModes()
        newly_supported = modes.set_from_codes((escape.PrivateMode.BRACKETED_PASTE, 4))
        self.assertFalse(modes.bracketed_paste)
        self.assertEqual(frozenset(), newly_supported)

    def test_reply_for_an_already_resolved_field_is_not_reported_as_newly_supported(self) -> None:
        modes = TermModes(bracketed_paste=True)
        newly_supported = modes.set_from_codes((escape.PrivateMode.BRACKETED_PASTE, 1))
        self.assertTrue(modes.bracketed_paste)
        self.assertEqual(frozenset(), newly_supported)

    def test_unmapped_mode_is_ignored(self) -> None:
        modes = TermModes()
        newly_supported = modes.set_from_codes(("9999", 1))
        self.assertEqual(frozenset(), newly_supported)

    def test_multiple_reports_in_one_call(self) -> None:
        modes = TermModes()
        newly_supported = modes.set_from_codes(
            (escape.PrivateMode.BRACKETED_PASTE, 1),
            (escape.PrivateMode.FOCUS_REPORTING, 0),
            (escape.PrivateMode.SYNCHRONIZED_OUTPUT, 2),
        )
        self.assertTrue(modes.bracketed_paste)
        self.assertFalse(modes.focus_reporting)
        self.assertTrue(modes.synchronized_output)
        self.assertEqual({"bracketed_paste", "synchronized_output"}, newly_supported)


class TestInheritedColors(unittest.TestCase):
    """Render widgets whose attributes leave a color to 'inherit', and check the escapes each cell is drawn with."""

    def setUp(self) -> None:
        """Make a 16-color screen with fg-only, bg-only and opaque palette entries."""
        self.screen = urwid.display.raw.Screen()
        self.screen.set_terminal_properties(colors=16, bright_is_bold=False)
        self.screen.register_palette(
            [
                ("red_fg", "dark red", "inherit"),
                ("green_fg", "dark green", "inherit"),
                ("brown_fg", "brown", "inherit"),
                ("blue_bg", "inherit", "dark blue"),
                ("panel_bg", "inherit", "dark cyan"),
                ("focus_bg", "inherit", "light gray"),
                ("error", "black", "dark red"),
                ("opaque", "yellow", "default"),
            ]
        )

    def cells(self, widget: urwid.Widget, size: tuple[int] | tuple[int, int], focus: bool = False) -> list[str]:
        """Return each row of *widget* as the SGR parameters of every cell, joined by spaces."""
        rows = []
        for row in widget.render(size, focus).content():
            codes = []
            for attr, _cs, text in row:
                code = self.screen._attr_to_escape(attr).removeprefix("\x1b[0;").removesuffix("m")
                codes.extend([code] * len(text))
            rows.append(" ".join(codes))
        return rows

    def test_draw_output_and_palette_change_repaint(self) -> None:
        """Write the inherited colors, and after a palette change rewrite only the rows it gives other colors."""
        canvas = urwid.Pile([urwid.AttrMap(urwid.Text(("red_fg", "x")), "blue_bg"), urwid.Text("other")]).render((5,))

        self.assertIn("\x1b[0;31;44mx\x1b[0;39;44m", draw(self.screen, canvas))
        self.screen.register_palette_entry("blue_bg", "inherit", "dark green")
        output = draw(self.screen, canvas)
        self.assertIn("\x1b[0;31;42mx", output)
        self.assertNotIn("other", output)

    def test_monochrome_draw_output(self) -> None:
        """Combine monochrome settings of the layers in the drawn output."""
        self.screen.set_terminal_properties(colors=1)
        self.screen.register_palette(
            [("bold_fg", "dark red", "inherit", "bold"), ("ul_bg", "inherit", "dark blue", "underline")]
        )
        canvas = urwid.AttrMap(urwid.Text(("bold_fg", "x")), "ul_bg").render((1,))

        self.assertIn("\x1b[0;39;1;4;49mx", draw(self.screen, canvas))

    def test_cell_colors(self) -> None:
        focus_rows = [
            urwid.AttrMap(
                urwid.Columns(
                    [
                        urwid.Text(("green_fg", "G")),
                        urwid.Text(("error", "E")),
                        urwid.Text(("brown_fg", "s")),
                    ]
                ),
                None,
                focus_map="focus_bg",
            )
            for _ in range(2)
        ]
        cases = (
            (
                # every cell of a Pile has the AttrMap background, each child keeps its foreground (#329)
                "container background",
                urwid.AttrMap(
                    urwid.Pile(
                        [
                            urwid.Text(("red_fg", "a")),
                            urwid.Divider("-"),
                            urwid.Columns([urwid.Text("b"), urwid.Text(("green_fg", "c"))]),
                        ]
                    ),
                    "panel_bg",
                ),
                (4,),
                False,
                [],
                ["31;46 39;46 39;46 39;46", "39;46 39;46 39;46 39;46", "39;46 39;46 32;46 39;46"],
            ),
            (
                # the focused row is highlighted behind fg-only attributes; a run with its own background keeps it
                "focus highlight",
                urwid.ListBox(urwid.SimpleFocusListWalker(focus_rows)),
                (3, 2),
                True,
                [],
                ["32;47 30;41 33;47", "32;49 30;41 33;49"],
            ),
            (
                "nested markup returns to the outer background",
                urwid.AttrMap(urwid.Text(("red_fg", ["a", ("blue_bg", "b"), "c"])), "panel_bg"),
                (3,),
                False,
                [],
                ["31;46 31;44 31;46"],
            ),
            (
                "screen background from the None entry",
                urwid.Text([("red_fg", "a"), "b"]),
                (2,),
                False,
                [(None, "default", "dark magenta")],
                ["31;45 39;45"],
            ),
        )
        for name, widget, size, focus, palette, expected in cases:
            with self.subTest(name):
                self.screen.register_palette([(None, "default", "default"), *palette])
                self.assertEqual(expected, self.cells(widget, size, focus=focus))

    def test_redefined_alias_is_drawn_with_its_new_entry(self) -> None:
        self.screen.register_palette([("alias", "red_fg")])
        self.screen._attr_to_escape("alias")  # drawn once, so its escape is cached
        self.screen.register_palette([("alias", "blue_bg")])

        self.assertEqual("\x1b[0;39;44m", self.screen._attr_to_escape("alias"))

    def test_opaque_attributes_ignore_enclosing_layers(self) -> None:
        expected = self.screen._attrspec_to_escape(urwid.AttrSpec("yellow", "default", 16))

        for attr in ("opaque", urwid.LayeredAttr("opaque", "panel_bg")):
            with self.subTest(attr=attr):
                self.assertEqual(expected, self.screen._attr_to_escape(attr))
