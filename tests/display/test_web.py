from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

import urwid
from urwid.display import web
from urwid.display.common import AttrSpec, ScreenError

IS_WINDOWS = sys.platform == "win32"


class HandleShortRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environ = {
            "REQUEST_METHOD": "POST",
            "HTTP_X_URWID_ID": "valid-id",
        }

    def test_keyboard_input_uses_request_charset(self) -> None:
        stdin = io.StringIO("é\n")
        stdout = io.StringIO()
        environ = {**self.environ, "CONTENT_TYPE": 'text/plain; charset="iso-8859-1"'}

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdin", stdin),
            mock.patch.object(web.sys, "stdout", stdout),
            mock.patch.object(web.os, "open", return_value=42),
            mock.patch.object(web.os, "write") as write,
            mock.patch.object(web.os, "close") as close,
        ):
            self.assertTrue(web.handle_short_request())

        write.assert_called_once_with(42, b"\xe9\n")
        close.assert_called_once_with(42)
        self.assertEqual("Content-type: text/plain\r\n\r\n", stdout.getvalue())

    def test_keyboard_encoding_error_closes_pipe(self) -> None:
        stdin = io.StringIO("é\n")
        stdout = io.StringIO()
        environ = {**self.environ, "CONTENT_TYPE": "text/plain; charset=ascii"}

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdin", stdin),
            mock.patch.object(web.sys, "stdout", stdout),
            mock.patch.object(web.os, "open", return_value=42),
            mock.patch.object(web.os, "write") as write,
            mock.patch.object(web.os, "close") as close,
        ):
            self.assertTrue(web.handle_short_request())

        write.assert_not_called()
        close.assert_called_once_with(42)
        self.assertEqual("Status: 400 Bad Request\r\n\r\n", stdout.getvalue())

    @unittest.skipIf(IS_WINDOWS, "The polling update channel is a POSIX-only socket.AF_UNIX socket")
    def test_polling_decodes_after_receiving_complete_utf8_payload(self) -> None:
        stdout = io.StringIO()
        environ = {**self.environ, "HTTP_X_URWID_METHOD": "polling"}
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.side_effect = [b"\xc3", b"\xa9", b""]

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdout", stdout),
            mock.patch.object(web.socket, "socket", return_value=sock),
        ):
            self.assertTrue(web.handle_short_request())

        sock.__exit__.assert_called_once()
        self.assertEqual("Content-type: text/plain; charset=utf-8\r\n\r\né", stdout.getvalue())

    @unittest.skipIf(IS_WINDOWS, "The polling update channel is a POSIX-only socket.AF_UNIX socket")
    def test_polling_invalid_utf8_closes_socket(self) -> None:
        stdout = io.StringIO()
        environ = {**self.environ, "HTTP_X_URWID_METHOD": "polling"}
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.side_effect = [b"\xff", b""]

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdout", stdout),
            mock.patch.object(web.socket, "socket", return_value=sock),
        ):
            self.assertTrue(web.handle_short_request())

        sock.__exit__.assert_called_once()
        self.assertEqual("Status: 502 Bad Gateway\r\n\r\n", stdout.getvalue())


@unittest.skipIf(IS_WINDOWS, "Reading the client pipe requires the POSIX-only os.O_NONBLOCK flag")
class ScreenGetInputTest(unittest.TestCase):
    """Tests for Screen.get_input method with improved validation."""

    def setUp(self) -> None:
        self.screen = web.Screen()
        self.screen.input_fd = 10
        self.screen.pipe_name = "/tmp/test_pipe"
        self.screen.update_method = "multipart"
        self.screen.input_tail = ""  # Initialize input_tail attribute

    def _make_selector_mock(self, has_input: bool):
        """Create a mock selector that optionally returns file descriptor events."""
        selector = mock.MagicMock()
        if has_input:
            event = mock.MagicMock()
            event.fd = 10
            selector.__enter__.return_value = selector
            selector.__exit__.return_value = None
            selector.select.return_value = [(event, None)]
        else:
            selector.__enter__.return_value = selector
            selector.__exit__.return_value = None
            selector.select.return_value = []
        return selector

    def test_get_input_no_input_available_raw_false(self) -> None:
        """When no input available and raw_keys=False, returns empty list."""
        selector_mock = self._make_selector_mock(has_input=False)

        with mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, [])

    def test_get_input_no_input_available_raw_true(self) -> None:
        """When no input available and raw_keys=True, returns tuple of empty lists."""
        selector_mock = self._make_selector_mock(has_input=False)

        with mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock):
            result = self.screen.get_input(raw_keys=True)

        self.assertEqual(result, ([], []))

    def test_get_input_regular_keys(self) -> None:
        """Returns regular keyboard input."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "a\nb\nc\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["a", "b", "c"])

    def test_get_input_valid_window_resize(self) -> None:
        """Handles valid window resize commands correctly."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize 80 24\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["window resize"])
        self.assertEqual(self.screen.screen_size, (80, 24))

    def test_get_input_window_resize_with_regular_keys(self) -> None:
        """Handles window resize mixed with regular input."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "key1\nwindow resize 120 40\nkey2\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["key1", "key2", "window resize"])
        self.assertEqual(self.screen.screen_size, (120, 40))

    def test_get_input_invalid_resize_wrong_param_count_too_few(self) -> None:
        """Rejects window resize with too few parameters."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize 80\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        # Invalid resize should be treated as regular input, not as resize command
        self.assertEqual(result, ["window resize 80"])

    def test_get_input_invalid_resize_wrong_param_count_too_many(self) -> None:
        """Rejects window resize with too many parameters."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize 80 24 extra\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["window resize 80 24 extra"])

    def test_get_input_invalid_resize_non_decimal_negative(self) -> None:
        """Rejects window resize with negative dimensions."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize -80 24\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["window resize -80 24"])

    def test_get_input_invalid_resize_non_decimal_float(self) -> None:
        """Rejects window resize with floating point dimensions."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize 80.5 24\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["window resize 80.5 24"])

    def test_get_input_invalid_resize_non_decimal_alpha(self) -> None:
        """Rejects window resize with non-numeric dimensions."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "window resize abc 24\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["window resize abc 24"])

    def test_get_input_input_tail_buffering(self) -> None:
        """Properly buffers incomplete lines at the end of input."""
        selector_mock = self._make_selector_mock(has_input=True)
        self.screen.input_tail = "incom"
        keydata = "plete\nkey2\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["incomplete", "key2"])
        self.assertEqual(self.screen.input_tail, "")

    def test_get_input_input_tail_carried_forward(self) -> None:
        """Incomplete last line is carried to next read."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "key1\nincompl"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["key1"])
        self.assertEqual(self.screen.input_tail, "incompl")


class ScreenStartTest(unittest.TestCase):
    """Tests for the request validation in Screen.start."""

    def setUp(self) -> None:
        self.screen = web.Screen()

    def test_start_rejects_invalid_resize_request(self) -> None:
        for client_init in (
            "",
            "hello\n",
            "window resize\n",
            "window resize 80\n",
            "window resize 80 24 extra\n",
            "window resize -80 24\n",
            "window resize 80.5 24\n",
            "window resize abc 24\n",
        ):
            stdout = io.StringIO()

            with (
                self.subTest(client_init=client_init),
                mock.patch.dict(os.environ, {"HTTP_X_URWID_METHOD": "multipart"}, clear=True),
                mock.patch.object(web.sys, "stdin", io.StringIO(client_init)),
                mock.patch.object(web.sys, "stdout", stdout),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    self.screen.start()

                self.assertEqual(ctx.exception.code, 0)
                self.assertEqual("Status: 400 Bad Request\r\n\r\n", stdout.getvalue())
                self.assertFalse(self.screen.started)

    def test_start_rejects_not_set_update_method(self) -> None:
        stdout = io.StringIO()
        stdin = io.StringIO("window resize 80 24\n")

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(web.sys, "stdin", stdin),
            mock.patch.object(web.sys, "stdout", stdout),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.screen.start()

            self.assertEqual("'HTTP_X_URWID_METHOD' environment vairable is not set", str(ctx.exception))

    def test_start_rejects_unsupported_update_method(self) -> None:
        environ = {"HTTP_X_URWID_METHOD": "polling child"}
        stdout = io.StringIO()
        stdin = io.StringIO("window resize 80 24\n")

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdin", stdin),
            mock.patch.object(web.sys, "stdout", stdout),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.screen.start()

            self.assertEqual(ctx.exception.code, 0)
            self.assertEqual("Status: 400 Bad Request\r\n\r\n", stdout.getvalue())
            # the request body is left untouched: validation happens before reading it
            self.assertEqual(0, stdin.tell())

    @unittest.skipIf(IS_WINDOWS, "Creating the client pipe requires the POSIX-only os.mkfifo and signal.alarm")
    def test_start_accepts_valid_resize_request(self) -> None:
        with (
            mock.patch.object(web.sys, "stdin", io.StringIO("window resize 80 24\n")),
            mock.patch.dict(os.environ, {"HTTP_X_URWID_METHOD": "multipart"}, clear=True),
            mock.patch.object(web.glob, "glob", return_value=[]),
            mock.patch.object(web.os, "mkfifo"),
            mock.patch.object(web.os, "open", return_value=42),
            mock.patch.object(web.signal, "signal"),
            mock.patch.object(web.signal, "alarm"),
        ):
            self.screen.start()

        self.assertTrue(self.screen.started)
        self.assertEqual(self.screen.screen_size, (80, 24))
        self.assertEqual(self.screen.last_screen, {})
        self.assertEqual(self.screen.last_screen_width, 0)


class SpanStyleTest(unittest.TestCase):
    """Tests for web._span_style and web.code_span, which translate an AttrSpec into the
    inline CSS sent to the browser -- the web equivalent of raw_display's _attrspec_to_escape.
    """

    def test_default_colours_fall_back_to_the_page_palette(self) -> None:
        fg, bg, extra = web._span_style(AttrSpec("default", "default"))

        self.assertEqual("#000000", fg)
        self.assertEqual("#e5e5e5", bg)
        self.assertEqual("", extra)

    def test_named_colours_render_as_hex(self) -> None:
        fg, bg, extra = web._span_style(AttrSpec("white", "black"))

        self.assertEqual("#ffffff", fg)
        self.assertEqual("#000000", bg)
        self.assertEqual("", extra)

    def test_high_colour_renders_exact_rgb(self) -> None:
        fg, bg, _extra = web._span_style(AttrSpec("#76b900", "#000000", colors=16777216))

        self.assertEqual("#76b900", fg)
        self.assertEqual("#000000", bg)

    def test_standout_swaps_foreground_and_background(self) -> None:
        fg, bg, _extra = web._span_style(AttrSpec("white,standout", "black"))

        self.assertEqual("#000000", fg)
        self.assertEqual("#ffffff", bg)

    def test_all_attributes_combine_into_one_style(self) -> None:
        aspec = AttrSpec("white,bold,italics,underline,blink,strikethrough,faint", "black")
        _fg, _bg, extra = web._span_style(aspec)

        self.assertIn(";text-decoration:underline line-through", extra)
        self.assertIn(";font-weight:bold", extra)
        self.assertIn(";font-style:italic", extra)
        self.assertIn(";animation:urwid-blink 1s step-start infinite", extra)
        self.assertIn(";opacity:0.5", extra)

    def test_underline_alone_has_no_line_through(self) -> None:
        _fg, _bg, extra = web._span_style(AttrSpec("white,underline", "black"))

        self.assertEqual(";text-decoration:underline", extra)

    def test_no_attributes_gives_empty_extra(self) -> None:
        _fg, _bg, extra = web._span_style(AttrSpec("white", "black"))

        self.assertEqual("", extra)

    def test_code_span_wraps_style_and_text(self) -> None:
        span = web.code_span("hi", AttrSpec("white", "black"))

        self.assertEqual("color:#ffffff;background-color:#000000\x01hi\n", span)

    def test_code_span_cursor_splits_into_three_pieces_with_swapped_colours(self) -> None:
        span = web.code_span("abc", AttrSpec("white", "black"), cursor=1)

        self.assertEqual(
            "color:#ffffff;background-color:#000000\x01a\n"
            "color:#000000;background-color:#ffffff\x01b\n"
            "color:#ffffff;background-color:#000000\x01c\n",
            span,
        )


class ScreenPaletteTest(unittest.TestCase):
    """Tests for Screen palette registration and draw_screen's attribute/colour resolution,
    which must honour the full AttrSpec feature set the way raw_display does.
    """

    def setUp(self) -> None:
        self.screen = web.Screen()
        self.screen.content_head = ""
        self.screen.update_method = "multipart"
        self.screen.last_screen = {}
        self.screen.last_screen_width = 0

    def _draw(self, canvas: urwid.Canvas) -> str:
        stdout = io.StringIO()
        with (
            mock.patch.object(web.sys, "stdout", stdout),
            # signal.alarm() doesn't exist on Windows; create=True lets draw_screen's
            # unconditional signal.alarm(...) calls hit the mock there too
            mock.patch.object(web.signal, "alarm", create=True),
        ):
            self.screen.draw_screen((canvas.cols(), canvas.rows()), canvas)
        return stdout.getvalue()

    def test_default_palette_entry_is_registered_on_construction(self) -> None:
        self.assertIn(None, self.screen._palette)

    def test_named_palette_entry_renders_registered_attributes(self) -> None:
        self.screen.register_palette_entry("focus", "light red,bold,underline,standout", "dark blue")
        canvas = urwid.AttrMap(urwid.Text("hi"), "focus").render((5,))

        output = self._draw(canvas)

        # standout swaps light red (#ff0000) and dark blue (#0000ee)
        self.assertIn("color:#0000ee;background-color:#ff0000;text-decoration:underline;font-weight:bold\x01hi", output)

    def test_attrspec_on_canvas_bypasses_the_palette(self) -> None:
        canvas = urwid.AttrMap(urwid.Text("hi"), AttrSpec("white", "black")).render((5,))

        output = self._draw(canvas)

        self.assertIn("color:#ffffff;background-color:#000000\x01hi", output)

    def test_register_palette_copies_an_existing_entry(self) -> None:
        self.screen.register_palette_entry("focus", "white", "black")
        self.screen.register_palette([("alias", "focus")])

        self.assertEqual(self.screen._palette["focus"], self.screen._palette["alias"])

    def test_register_palette_rejects_unknown_alias_target(self) -> None:
        with self.assertRaises(ScreenError):
            self.screen.register_palette([("alias", "missing")])

    def test_set_terminal_properties_switches_to_mono_rendering(self) -> None:
        self.screen.register_palette_entry("focus", "white,bold", "black", mono="underline")
        self.screen.set_terminal_properties(colors=1)
        canvas = urwid.AttrMap(urwid.Text("hi"), "focus").render((5,))

        output = self._draw(canvas)

        # mono mode drops the colour choice (falls back to the page default) but keeps 'underline'
        self.assertIn("color:#000000;background-color:#e5e5e5;text-decoration:underline\x01hi", output)

    def test_set_terminal_properties_rejects_unsupported_colour_count(self) -> None:
        with self.assertRaises(KeyError):
            self.screen.set_terminal_properties(colors=42)
