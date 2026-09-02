from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

from urwid.display import web

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
