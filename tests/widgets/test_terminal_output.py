from __future__ import annotations

import contextlib
import importlib
import itertools
import sys
import typing
import unittest
from unittest import mock

import urwid
import urwid.term_canvas
import urwid.widget.terminal_output
from urwid.util import set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

_SIGNALS = ("beep", "leds", "title", "resize")


def _recording(size: tuple[int, int] = (20, 4), **kwargs: typing.Any) -> tuple[urwid.TerminalOutput, list[tuple]]:
    """Return a widget and the list its signals are recorded in, as ``(name, *arguments)``."""
    output = urwid.TerminalOutput(size=size, **kwargs)
    events: list[tuple] = []
    for name in _SIGNALS:
        urwid.connect_signal(output, name, lambda _widget, *args, name=name: events.append((name, *args)))
    return output, events


def _state(output: urwid.TerminalOutput, events: list[tuple], size: tuple[int, int] = (20, 4)) -> tuple:
    """Return the cells, the cursor position and the signals of *output*, to compare two ways of writing."""
    canvas = output.render(size)
    return list(canvas.content()), output._term.term_cursor, list(events)


def _text(output: urwid.TerminalOutput, size: tuple[int, int]) -> list[bytes]:
    """Return the screen lines of *output* rendered at *size*, without trailing blanks."""
    return [line.rstrip() for line in output.render(size).text]


@contextlib.contextmanager
def _imported_without_posix_modules() -> Iterator[tuple[ModuleType, ModuleType]]:
    """Import fresh copies of the canvas and widget modules while the POSIX-only modules cannot be imported.

    Everything the import changes is restored afterwards, also when the body fails.
    """
    parents = ((urwid, "term_canvas"), (urwid.widget, "terminal_output"))
    saved = [(parent, name, getattr(parent, name)) for parent, name in parents]
    try:
        with mock.patch.dict(sys.modules):
            for name in ("urwid.term_canvas", "urwid.widget.terminal_output"):
                del sys.modules[name]
            for name in ("pty", "fcntl", "termios", "urwid.vterm"):
                sys.modules[name] = None  # type: ignore[assignment]  # makes `import name` raise ImportError
            yield importlib.import_module("urwid.term_canvas"), importlib.import_module("urwid.widget.terminal_output")
    finally:
        for parent, name, module in saved:
            setattr(parent, name, module)


class TerminalOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(urwid.set_encoding, urwid.util.get_encoding())
        urwid.set_encoding("utf-8")

    def test_output_reaches_the_screen(self) -> None:
        """Show text, SGR colors and cursor movement, and emit the bell, LED and title signals."""
        output, events = _recording()
        output.write("\x1b[31mA\x1b[38;5;100mB\x1b[38;2;1;2;3mC\x1b[0m\x1b[2;3Hx\a\x1b[1q\x1b]2;title\a")
        first, second = itertools.islice(output.render((20, 4)).content(), 2)

        self.assertEqual(
            [
                (urwid.AttrSpec("dark red", "default"), None, b"A"),
                (urwid.AttrSpec("#880", "default"), None, b"B"),
                (urwid.AttrSpec("#010203", "default", colors=2**24), None, b"C"),
            ],
            first[:3],
        )
        self.assertEqual((None, None, b"x"), second[2])
        self.assertEqual([("beep",), ("leds", "scroll_lock"), ("title", "title")], events)

    def test_queries_are_not_answered(self) -> None:
        """Discard the replies to a status report and a device attributes query."""
        output, _events = _recording()
        output.write("\x1b[6n\x1b[c\x1b[5nok")

        self.assertEqual([b"ok", b"", b"", b""], _text(output, (20, 4)))

    def test_size_must_be_positive(self) -> None:
        for size in ((0, 4), (20, 0), (-1, 4)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                urwid.TerminalOutput(size=size)

    def test_text_and_its_utf8_bytes_give_the_same_cells(self) -> None:
        """Under UTF-8, write a character as text or as its UTF-8 bytes with the same result."""
        for char in ("\xe9", "€", "\U0001f600", "漢", "─"):
            with self.subTest(char=char):
                from_text, text_events = _recording()
                from_text.write(f"a{char}b")
                from_bytes, bytes_events = _recording()
                from_bytes.write(f"a{char}b".encode())

                self.assertEqual(_state(from_bytes, bytes_events), _state(from_text, text_events))

    def test_bytes_in_another_encoding_are_decoded_by_the_caller(self) -> None:
        """Show Latin-1 bytes under UTF-8 only once the caller decodes them.

        Under UTF-8 a byte that cannot start a character, such as a lone continuation byte, shows nothing,
        also one in the C1 control range that is no control the terminal acts on.
        """
        for data in (b"caf\xe9", b"caf\xa9", b"caf\x81"):
            with self.subTest(data=data):
                as_bytes, _events = _recording()
                as_bytes.write(data)
                decoded, _events = _recording()
                decoded.write(data.decode("latin-1"))

                self.assertEqual([b"caf", b"", b"", b""], _text(as_bytes, (20, 4)))
                self.assertEqual(
                    [data.decode("latin-1").encode(), b"", b"", b""],
                    _text(decoded, (20, 4)),
                )

    def test_character_pending_when_the_encoding_changes_is_dropped(self) -> None:
        """Do not complete a UTF-8 character with bytes written after the encoding stopped being UTF-8 and came back."""
        output, _events = _recording()
        output.write(b"\xc3")
        with set_temporary_encoding("iso8859-1"):
            output.write(b"x")
        output.write(b"\xa9")

        self.assertEqual([b"x", b"", b"", b""], _text(output, (20, 4)))

    def test_single_byte_encoding(self) -> None:
        """Under ISO 8859-1, show text and the encoding's bytes, and fall back for a character it lacks."""
        with set_temporary_encoding("iso8859-1"):
            for data, expected in (("caf\xe9", b"caf\xe9"), (b"caf\xe9", b"caf\xe9"), ("€!", b"?!")):
                with self.subTest(data=data):
                    output, _events = _recording()
                    output.write(data)

                    self.assertEqual([expected, b"", b"", b""], _text(output, (20, 4)))

    def test_text_in_any_encoding_shows_its_characters(self) -> None:
        """Show text as the characters given, also where a character's bytes in the encoding hold a C1 control."""
        # U+4EC3 holds 0x9B (CSI) in gbk, U+2500 is a DEC line-drawing character
        for encoding, text in (("gbk", "a\u4ec31mX"), ("iso8859-1", "a\u25001mX")):
            with self.subTest(encoding=encoding), set_temporary_encoding(encoding):
                output, events = _recording()
                output.write(text)
                utf8_mode, utf8_events = _recording()
                utf8_mode.write(f"\x1b%G{text}")

                self.assertEqual(_state(utf8_mode, utf8_events), _state(output, events))
                self.assertEqual(b"1mX", _text(output, (20, 4))[0][-3:])

    def test_bytes_like_data(self) -> None:
        for data in (b"ok", bytearray(b"ok"), memoryview(b"ok")):
            with self.subTest(data=type(data).__name__):
                output, _events = _recording()
                output.write(data)

                self.assertEqual([b"ok", b"", b"", b""], _text(output, (20, 4)))

    def test_zero_size_render_keeps_the_terminal(self) -> None:
        """Show nothing at a size with a zero dimension, and keep the screen and what is written meanwhile."""
        for size in ((0, 3), (8, 0)):
            with self.subTest(size=size):
                output, events = _recording(size=(8, 3))
                output.write("one\ntwo\n")
                canvas = output.render(size)
                output.write("three")

                self.assertEqual(size, (canvas.cols(), canvas.rows()))
                self.assertEqual([b"one", b"two", b"three"], _text(output, (8, 3)))
                self.assertEqual([], events)

    def test_mode_change_inside_one_string(self) -> None:
        """Encode each character for the mode the text before it selected, wherever the string is split."""
        texts = (
            "\x1b%G\xe9",
            "\xe9\x1b%G\xe9",
            "\x1b%G\xe9\x1b%@\xe9",
            "\x1b%G\xe9\x1bc\xe9",
            "\x1b%G漢\x1b%@\xe9",
        )
        for encoding, text in itertools.product(("iso8859-1", "utf-8"), texts):
            with self.subTest(encoding=encoding, text=text), set_temporary_encoding(encoding):
                whole, whole_events = _recording()
                whole.write(text)
                expected = _state(whole, whole_events)
                for split in range(1, len(text)):
                    output, events = _recording()
                    output.write(text[:split])
                    output.write(text[split:])

                    self.assertEqual(expected, _state(output, events), f"split at {split}")

    def test_split_writes_give_the_same_result(self) -> None:
        """Give the same cells, cursor and signals however the data is split between writes."""
        corpus = (
            b"one\r\ntwo\nthree\r",
            b"\r\nafter",
            b"\xc3\xa9\xe2\x82\xac\xf0\x9f\x98\x80",
            b"\x1b[1;31mred\x1b[0m\x1b[2;5Hx\x1b[1\n0Gy",
            b"\x1b]2;a title\a\x1b]2;another\x1b\\\x1b]8;;https://urwid.org\alink\x1b]8;;\a\x1b]2;li\nne\a",
            b"before\x1bcab\ncd",
        )
        for data, lf_to_crlf in itertools.product(corpus, (True, False)):
            with self.subTest(data=data, lf_to_crlf=lf_to_crlf):
                whole, whole_events = _recording(lf_to_crlf=lf_to_crlf)
                whole.write(data)
                expected = _state(whole, whole_events)

                bytewise, bytewise_events = _recording(lf_to_crlf=lf_to_crlf)
                for byte in data:
                    bytewise.write(bytes((byte,)))
                self.assertEqual(expected, _state(bytewise, bytewise_events), "one byte at a time")

                for split in range(1, len(data)):
                    output, events = _recording(lf_to_crlf=lf_to_crlf)
                    output.write(data[:split])
                    output.write(data[split:])
                    self.assertEqual(expected, _state(output, events), f"split at {split}")

                text = data.decode()
                for split in range(1, len(text)):
                    output, events = _recording(lf_to_crlf=lf_to_crlf)
                    output.write(text[:split])
                    output.write(text[split:])
                    self.assertEqual(expected, _state(output, events), f"text split at {split}")

    def test_line_feed(self) -> None:
        """Start a new line at a line feed by default, and only move down without the conversion."""
        for data, lf_to_crlf, expected in (
            ("ab\r\ncd", True, [b"ab", b"cd"]),
            ("ab\r\ncd", False, [b"ab", b"cd"]),
            ("ab\ncd", True, [b"ab", b"cd"]),
            ("ab\ncd", False, [b"ab", b"  cd"]),
            # a reset in the data turns off any line feed mode, and the conversion still applies after it
            ("x\x1b[20h\x1bcab\ncd", True, [b"ab", b"cd"]),
        ):
            with self.subTest(data=data, lf_to_crlf=lf_to_crlf):
                output, _events = _recording(size=(10, 2), lf_to_crlf=lf_to_crlf)
                output.write(data)

                self.assertEqual(expected, _text(output, (10, 2)))

    def test_cursor_follows_focus(self) -> None:
        """Draw the cursor only with focus, while get_cursor_coords() reports it either way."""
        output, _events = _recording(size=(10, 3))
        output.write("ab\ncd")
        for focus, drawn in ((True, (2, 1)), (False, None), (True, (2, 1))):
            with self.subTest(focus=focus):
                canvas = output.render((10, 3), focus=focus)

                self.assertEqual(drawn, canvas.cursor)
                self.assertEqual((2, 1), output.get_cursor_coords((10, 3)))

    def test_cursor_coords(self) -> None:
        """Report no cursor when the data hides it or the view is scrolled past its row, as a render draws it."""
        output, _events = _recording(size=(10, 3))
        output.write("\n".join("0123456") + "\x1b[1;3H")
        for data, wheel_ups, expected in (
            ("", 0, (2, 0)),
            ("\x1b[?25l", 0, None),
            ("\x1b[?25h", 0, (2, 0)),
            ("", 1, (2, 1)),
            ("", 2, (2, 2)),
            ("", 3, None),
            # a move past an edge stops at the edge, and the cursor is drawn there
            ("\x1b[1;200H", 0, (9, 0)),
            ("\x1b[H\x1b[200C", 0, (9, 0)),
            ("\x1b[3;1H\x1b[5B", 0, (0, 2)),
            ("\x1b[H\x1b[5A", 0, (0, 0)),
        ):
            with self.subTest(data=data, wheel_ups=wheel_ups):
                output.write(data)
                for _ in range(wheel_ups):
                    output.mouse_event((10, 3), "mouse press", urwid.MouseButton.WHEEL_UP, 0, 0, focus=True)

                self.assertEqual(expected, output.get_cursor_coords((10, 3)))
                self.assertEqual(expected, output.render((10, 3), focus=True).cursor)
                for _ in range(wheel_ups):
                    output.mouse_event((10, 3), "mouse press", urwid.MouseButton.WHEEL_DOWN, 0, 0, focus=True)

    def test_cursor_coords_at_another_size(self) -> None:
        """Keep the cursor inside a size other than the one last rendered."""
        output, _events = _recording(size=(10, 3))
        output.write("\x1b[2;8H")

        self.assertEqual((7, 1), output.get_cursor_coords((10, 3)))
        self.assertEqual((4, 1), output.get_cursor_coords((5, 2)))
        self.assertEqual((4, 0), output.get_cursor_coords((5, 1)))

    def test_first_render_at_another_size(self) -> None:
        """Resize to the first rendered size when it differs from the constructor's, and emit "resize" once."""
        for size in ((3, 4), (30, 4), (20, 2), (20, 6)):
            with self.subTest(size=size):
                output, events = _recording()
                output.write("hello\nworld")
                output.render(size)
                output.render(size)

                self.assertEqual([("resize", size)], events)
                canvas = output.render(size)
                self.assertEqual(size, (canvas.cols(), canvas.rows()))

    def test_narrow_then_widen(self) -> None:
        """Cut the lines when narrowing; widening again adds blank cells, not the cut ones."""
        output, events = _recording(size=(6, 2))
        output.write("abcdef")

        self.assertEqual([b"abc", b""], _text(output, (3, 2)))
        self.assertEqual([b"abc", b""], _text(output, (6, 2)))
        self.assertEqual([("resize", (3, 2)), ("resize", (6, 2))], events)

    def test_shorten_then_heighten(self) -> None:
        """Move the top rows into the scrollback when shortening, and take them back in order when heightening."""
        output, _events = _recording(size=(4, 3))
        output.write("1\n2\n3")

        self.assertEqual([b"3"], _text(output, (4, 1)))
        self.assertEqual((1, 0), output._term.term_cursor)
        self.assertEqual([b"1", b"2", b"3"], _text(output, (4, 3)))
        self.assertEqual((1, 2), output._term.term_cursor)

    def test_resize_handler_draws_for_the_new_size(self) -> None:
        """Show what a "resize" handler writes in the same render."""
        output = urwid.TerminalOutput(size=(10, 2))
        urwid.connect_signal(
            output,
            "resize",
            lambda widget, size: widget.write(f"\x1b[2J\x1b[H{size[0]}x{size[1]}"),
        )

        self.assertEqual([b"8x1"], _text(output, (8, 1)))

    def test_resize_handler_renders_the_widget_again(self) -> None:
        """A "resize" handler that renders the widget at another size gets the terminal cut or padded to it.

        The terminal keeps the size being reported, and the render that resized it returns that size.
        A later render at the handler's size still resizes the terminal, also while the handler's canvas is alive.
        """
        output, events = _recording(size=(10, 2))
        nested: list[urwid.Canvas] = []

        def render_again(widget: urwid.TerminalOutput, size: tuple[int, int]) -> None:
            widget.write(f"\x1b[2J\x1b[H{size[0]}x{size[1]}")
            if not nested:
                nested.append(widget.render((3, 3)))

        urwid.connect_signal(output, "resize", render_again)

        self.assertEqual([b"6x2", b""], _text(output, (6, 2)))
        self.assertEqual([b"6x2", b"", b""], [line.rstrip() for line in nested[0].text])
        self.assertEqual([("resize", (6, 2))], events)

        output.render((3, 3))
        self.assertEqual((3, 3), (output._term.width, output._term.height))
        self.assertEqual([("resize", (6, 2)), ("resize", (3, 3))], events)

    def test_scrolling(self) -> None:
        """Scroll on the page keys and the mouse wheel, and leave other input to the parent."""
        output, _events = _recording(size=(4, 2))
        output.write("\n".join("123456"))

        self.assertIsNone(output.keypress((4, 2), "page up"))
        self.assertEqual([b"4", b"5"], _text(output, (4, 2)))
        self.assertIsNone(output.keypress((4, 2), "page down"))
        self.assertEqual([b"5", b"6"], _text(output, (4, 2)))
        self.assertTrue(output.mouse_event((4, 2), "mouse press", urwid.MouseButton.WHEEL_UP, 0, 0, focus=True))
        self.assertEqual([b"4", b"5"], _text(output, (4, 2)))
        self.assertTrue(output.mouse_event((4, 2), "mouse press", urwid.MouseButton.WHEEL_DOWN, 0, 0, focus=True))
        self.assertEqual([b"5", b"6"], _text(output, (4, 2)))

        self.assertEqual("x", output.keypress((4, 2), "x"))
        self.assertFalse(output.mouse_event((4, 2), "mouse press", urwid.MouseButton.LEFT, 0, 0, focus=True))
        self.assertFalse(output.mouse_event((4, 2), "mouse release", urwid.MouseButton.WHEEL_UP, 0, 0, focus=True))

    def test_write_while_scrolled_back(self) -> None:
        """Return the view to the bottom on a write, or keep it on the lines shown with scroll_on_output off."""
        for scroll_on_output, view in ((True, [b"6", b"7", b"8"]), (False, [b"1", b"2", b"3"])):
            with self.subTest(scroll_on_output=scroll_on_output):
                output, _events = _recording(size=(4, 3), scroll_on_output=scroll_on_output)
                output.write("\n".join("12345"))
                output.mouse_event((4, 3), "mouse press", urwid.MouseButton.WHEEL_UP, 0, 0, focus=True)
                output.mouse_event((4, 3), "mouse press", urwid.MouseButton.WHEEL_UP, 0, 0, focus=True)
                output.write("\n6\n7\n8")

                self.assertEqual(view, _text(output, (4, 3)))

    def test_exported_on_every_platform(self) -> None:
        for name, module in (
            ("TerminalOutput", "urwid.widget.terminal_output"),
            ("TermCanvas", "urwid.term_canvas"),
            ("TermCharset", "urwid.term_canvas"),
            ("TermModes", "urwid.term_canvas"),
        ):
            with self.subTest(name=name):
                self.assertIn(name, urwid.__all__)
                self.assertEqual(module, getattr(urwid, name).__module__)

    def test_imports_without_posix_modules(self) -> None:
        """Import the canvas and the widget without pty, fcntl, termios and urwid.vterm.

        This simulates Windows on the platform the test runs on.
        The windows-latest CI job runs this module for real.
        """
        old_term_canvas, old_terminal_output = urwid.term_canvas, urwid.widget.terminal_output
        with _imported_without_posix_modules() as (term_canvas, terminal_output):
            self.assertIsNot(old_term_canvas, term_canvas)
            self.assertIsNot(old_terminal_output, terminal_output)
            output = terminal_output.TerminalOutput(size=(5, 1))
            output.write("ok")
            self.assertIsInstance(output.render((5, 1)), term_canvas.TermCanvas)

        self.assertIs(sys.modules["urwid.term_canvas"], urwid.term_canvas)
        self.assertIs(sys.modules["urwid.widget.terminal_output"], urwid.widget.terminal_output)
        self.assertIs(urwid.term_canvas.TermCanvas, urwid.TermCanvas)
        self.assertIs(urwid.widget.terminal_output.TerminalOutput, urwid.TerminalOutput)
        if sys.platform != "win32":
            self.assertIs(urwid.term_canvas.TermCanvas, sys.modules["urwid.vterm"].TermCanvas)
