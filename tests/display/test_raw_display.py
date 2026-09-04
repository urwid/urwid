from __future__ import annotations

import os
import unittest

import urwid
from urwid import escape, signals
from urwid.display._raw_display_base import detect_terminal_properties
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED
from urwid.util import set_temporary_encoding


class TestRawDisplay(unittest.TestCase):
    def test_attrspec_to_escape(self):
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        a2e = s._attrspec_to_escape
        self.assertEqual("\x1b[0;33;42m", a2e(s.AttrSpec("brown", "dark green")))
        self.assertEqual("\x1b[0;38;5;229;4;48;5;164m", a2e(s.AttrSpec("#fea,underline", "#d0d")))
        self.assertEqual("\x1b[0;33;2;42m", a2e(s.AttrSpec("brown,faint", "dark green")))

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

    def test_last_row_without_preceding_segment(self):
        """A last row holding a single grapheme has no character to slide back."""
        s = urwid.display.raw.Screen()
        row = [(None, None, "日".encode())]

        self.assertEqual((row, 0, None), s._last_row(row))

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

    def test_restart_after_stop_reconnects_input(self):
        """stop() followed by start() must leave the screen's input descriptors
        watchable again (regression test for urwid/urwid#285).

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
        """Palette entries modified with modify_terminal_palette() must be reset when the
        screen stops, so urwid doesn't leave the user's terminal with a custom palette after
        the process exits (urwid/urwid#458).
        """
        s = urwid.display.raw.Screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s._started = True

        s.modify_terminal_palette([(1, 255, 0, 0), (2, 0, 255, 0)])
        self.assertEqual({1, 2}, s._modified_palette_entries)

        s._stop_restore_palette()

        self.assertIn("\x1b]104;1;2\x1b\\", "".join(written))
        self.assertEqual(set(), s._modified_palette_entries)

    def test_stop_restore_palette_noop_when_untouched(self):
        """No reset escape should be sent if the palette was never modified."""
        s = urwid.display.raw.Screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s._started = True

        s._stop_restore_palette()

        self.assertEqual([], written)


class TestTerminalProperties(unittest.TestCase):
    def test_term_families(self) -> None:
        cases = (
            ("", 16, True, True, False, True),
            ("xterm", 16, True, False, False, True),
            ("xterm-256color", 256, True, False, False, True),
            ("xterm-direct", 16777216, True, False, False, True),
            ("linux", 16, True, True, True, True),
            ("linux-16color", 16, True, True, True, True),
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
            return detect_terminal_properties(term, environ, windows_version=(0, 0, 0)).colors

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
