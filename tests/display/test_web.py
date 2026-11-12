from __future__ import annotations

import io
import itertools
import os
import pathlib
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

import urwid
from urwid.display import _web_common, web
from urwid.display.common import AttrSpec, ScreenError

IS_WINDOWS = sys.platform == "win32"
IS_GRAALPY = sys.implementation.name == "graalpy"


def _use_temporary_pipe_dir(test: unittest.TestCase) -> str:
    """Point the web display at a fresh temporary pipe_dir until `test` ends, and return its path."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    patcher = mock.patch.object(web._prefs, "pipe_dir", tmp.name)
    patcher.start()
    test.addCleanup(patcher.stop)
    return tmp.name


@unittest.skipIf(IS_WINDOWS, "The session directory check needs POSIX file ownership (os.geteuid)")
class SessionDirTest(unittest.TestCase):
    """Tests for the private per-user directory that holds the session files."""

    def setUp(self) -> None:
        """Use a temporary pipe_dir and compute the session directory expected in it."""
        self.pipe_dir = _use_temporary_pipe_dir(self)
        self.expected = os.path.join(self.pipe_dir, f"urwid-web-{os.geteuid()}")

    def test_creates_private_directory(self) -> None:
        """A missing session directory is created without group or other access."""
        self.assertEqual(self.expected, web._session_dir())
        st = os.lstat(self.expected)
        self.assertTrue(stat.S_ISDIR(st.st_mode))
        self.assertEqual(0, stat.S_IMODE(st.st_mode) & 0o077)

    def test_reuses_existing_private_directory(self) -> None:
        """An existing private session directory is accepted."""
        os.mkdir(self.expected, 0o700)
        self.assertEqual(self.expected, web._session_dir())

    def test_refuses_directory_open_to_other_users(self) -> None:
        """A session directory that the group can read is refused."""
        os.mkdir(self.expected, 0o700)
        os.chmod(self.expected, 0o740)
        with self.assertRaises(PermissionError):
            web._session_dir()

    def test_refuses_symlink(self) -> None:
        """A symbolic link planted at the session directory path is refused, not followed."""
        target = os.path.join(self.pipe_dir, "elsewhere")
        os.mkdir(target, 0o700)
        os.symlink(target, self.expected)
        with self.assertRaises(PermissionError):
            web._session_dir()

    def test_refuses_regular_file(self) -> None:
        """A regular file planted at the session directory path is refused."""
        with open(self.expected, "w", encoding="ascii"):
            pass
        with self.assertRaises(PermissionError):
            web._session_dir()

    def test_refuses_directory_of_another_user(self) -> None:
        """A session directory owned by another user is refused."""
        other_uid = os.geteuid() + 1
        other = os.path.join(self.pipe_dir, f"urwid-web-{other_uid}")
        # a directory created by this process stands in for one another user planted at that user's path
        os.mkdir(other, 0o700)
        with mock.patch.object(web.os, "geteuid", return_value=other_uid), self.assertRaises(PermissionError):
            web._session_dir()

    def test_session_path_does_not_contain_the_session_id(self) -> None:
        """Session file names are a stable hash of the id, inside the session directory."""
        urwid_id = "8Hq3_secret-token-value"
        path = web._session_path(urwid_id)
        self.assertEqual(self.expected, os.path.dirname(path))
        self.assertNotIn(urwid_id, path)
        self.assertEqual(path, web._session_path(urwid_id))


class HandleShortRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        # the session directory checks have their own tests and need POSIX ownership, which Windows does not have
        patcher = mock.patch.object(web, "_session_dir", return_value=_use_temporary_pipe_dir(self))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.environ = {
            "REQUEST_METHOD": "POST",
            "HTTP_X_URWID_ID": "valid-id",
        }

    def test_keyboard_input_uses_request_charset(self) -> None:
        """The request body is decoded with its own charset and written to the pipe as UTF-8."""
        stdin = io.TextIOWrapper(io.BytesIO(b"\xe9\n"), encoding="ascii")
        stdout = io.StringIO()
        environ = {**self.environ, "CONTENT_TYPE": 'text/plain; charset="iso-8859-1"'}

        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(web.sys, "stdin", stdin),
            mock.patch.object(web.sys, "stdout", stdout),
            mock.patch.object(web.os, "open", return_value=42) as pipe_open,
            mock.patch.object(web.os, "write") as write,
            mock.patch.object(web.os, "close") as close,
        ):
            self.assertTrue(web.handle_short_request())
            pipe_open.assert_called_once_with(f"{web._session_path('valid-id')}.in", os.O_WRONLY)

        write.assert_called_once_with(42, b"\xc3\xa9\n")
        close.assert_called_once_with(42)
        self.assertEqual("Content-type: text/plain\r\n\r\n", stdout.getvalue())

    def test_keyboard_encoding_error_closes_pipe(self) -> None:
        stdin = io.TextIOWrapper(io.BytesIO(b"\xe9\n"), encoding="ascii")
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

        sock.connect.assert_called_once_with(f"{web._session_path('valid-id')}.update")
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
        keydata = "a\nwindow resize 120 40\nb\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["a", "b", "window resize"])
        self.assertEqual(self.screen.screen_size, (120, 40))

    def test_get_input_drops_lines_that_are_not_key_names(self) -> None:
        """A line the page script never sends is neither a key nor a resize."""
        for line in (
            "",
            "a\r",
            "ab",
            "f0",
            "ctrl shift a",
            "\x01",
            "window resize",
            "window resize 80",
            "window resize 80 24 extra",
            "window resize -80 24",
            "window resize 80.5 24",
            "window resize abc 24",
        ):
            with self.subTest(line=line):
                self.assertEqual([["b"]], self._read_each(f"{line}\nb\n"))
                self.assertIsNone(self.screen.screen_size)

    def test_get_input_passes_every_key_name_the_page_script_sends(self) -> None:
        """Each named key and a sample of characters, alone and with each modifier combination, is a key."""
        script = pathlib.Path(_web_common.__file__).with_name("_web_common.js").read_text("utf-8")
        table = re.search(r"const key_names = \{(.*?)\};", script, re.DOTALL)
        self.assertIsNotNone(table)
        named = re.findall(r'"[^"]+": "([^"]+)"', table.group(1))
        names = [*named, *(f"f{number}" for number in range(1, 13)), "a", " ", "\u00e9", "\u4e2d", "\U0001f600"]
        modifiers = [
            "".join(combination)
            for count in range(len(_web_common._MODIFIERS) + 1)
            for combination in itertools.combinations(_web_common._MODIFIERS, count)
        ]
        keys = [prefix + name for prefix in modifiers for name in names]

        self.assertEqual([keys], self._read_each("".join(f"{key}\n" for key in keys)))

    def test_get_input_input_tail_buffering(self) -> None:
        """Properly buffers incomplete lines at the end of input."""
        selector_mock = self._make_selector_mock(has_input=True)
        self.screen.input_tail = "page "
        keydata = "up\nb\n"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["page up", "b"])
        self.assertEqual(self.screen.input_tail, "")

    def test_get_input_input_tail_carried_forward(self) -> None:
        """Incomplete last line is carried to next read."""
        selector_mock = self._make_selector_mock(has_input=True)
        keydata = "a\npage d"

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", return_value=keydata.encode("utf-8")),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            result = self.screen.get_input(raw_keys=False)

        self.assertEqual(result, ["a"])
        self.assertEqual(self.screen.input_tail, "page d")

    def test_get_input_decodes_the_pipe_as_utf8_across_reads(self) -> None:
        """The pipe carries UTF-8 whatever the screen's encoding, and a character may be split between two reads."""
        old_encoding = urwid.util.get_encoding()
        self.addCleanup(urwid.set_encoding, old_encoding)
        urwid.set_encoding("iso-8859-1")
        selector_mock = self._make_selector_mock(has_input=True)

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", side_effect=[b"a\n\xc3", b"\xa9\n"]),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            first = self.screen.get_input(raw_keys=False)
            second = self.screen.get_input(raw_keys=False)

        self.assertEqual(["a"], first)
        self.assertEqual(["é"], second)

    def _read_each(self, *chunks: str) -> list[list[str]]:
        """Return the keys of one get_input call per chunk, with each chunk the data of one read of the pipe."""
        selector_mock = self._make_selector_mock(has_input=True)

        with (
            mock.patch("urwid.display.web.selectors.DefaultSelector", return_value=selector_mock),
            mock.patch("urwid.display.web.os.read", side_effect=[chunk.encode("utf-8") for chunk in chunks]),
            mock.patch("urwid.display.web.os.close"),
            mock.patch("urwid.display.web.os.open", return_value=10),
        ):
            return [self.screen.get_input(raw_keys=False) for _ in chunks]

    @staticmethod
    def _resize_request(length: int) -> str:
        """Return a valid request to resize to 80x24, zero-padded to `length` characters."""
        return "window resize " + "80".zfill(length - len("window resize  24")) + " 24"

    def test_get_input_drops_a_complete_line_over_the_limit(self) -> None:
        """A line of the limit is applied, a longer one is dropped, and the lines around it are kept."""
        for length, expected, size in (
            (web.MAX_LINE_LENGTH, ["a", "b", "window resize"], (80, 24)),
            (web.MAX_LINE_LENGTH + 1, ["a", "b"], None),
        ):
            with self.subTest(length=length):
                self.screen.screen_size = None

                self.assertEqual([expected], self._read_each(f"a\n{self._resize_request(length)}\nb\n"))
                self.assertEqual(size, self.screen.screen_size)
                self.assertEqual("", self.screen.input_tail)

    def test_get_input_logs_the_length_of_a_dropped_line_not_its_content(self) -> None:
        """The debug log names how long a dropped line was, and never carries the untrusted text."""
        complete = "x" * (web.MAX_LINE_LENGTH + 1)
        unfinished = "y" * (web.MAX_LINE_LENGTH + 1)

        with self.assertLogs(self.screen.logger, "DEBUG") as logs:
            self._read_each(f"{complete}\nzzzz\nwindow resize qqqq 24\n{unfinished}")

        output = "\n".join(logs.output)
        self.assertIn(str(web.MAX_LINE_LENGTH + 1), output)
        self.assertNotIn("x" * 10, output)
        self.assertNotIn("y" * 10, output)
        self.assertNotIn("zzzz", output)
        self.assertNotIn("qqqq", output)
        self.assertIn("Dropped 2 input lines that are not key names", output)

    def test_get_input_joins_a_line_of_the_limit_split_between_reads(self) -> None:
        """The limit applies to the joined line, not to each read."""
        request = self._resize_request(web.MAX_LINE_LENGTH)
        half = web.MAX_LINE_LENGTH // 2

        self.assertEqual([[], ["window resize"]], self._read_each(request[:half], f"{request[half:]}\n"))
        self.assertEqual((80, 24), self.screen.screen_size)

    def test_get_input_drops_an_unfinished_line_over_the_limit_up_to_its_newline(self) -> None:
        """The rest of an over-long line arriving in later reads is dropped, and the next line is a key."""
        results = self._read_each("a\n" + "x" * (web.MAX_LINE_LENGTH + 1), "x" * 10, "x\nb\n")

        self.assertEqual([["a"], [], ["b"]], results)
        self.assertEqual("", self.screen.input_tail)

    def test_get_input_keeps_no_more_than_the_limit_of_a_line_without_newline(self) -> None:
        """Input that never ends its line does not accumulate."""
        for _ in range(8):
            self.assertEqual([[]], self._read_each("x" * web.MAX_READ))
            self.assertLessEqual(len(self.screen.input_tail), web.MAX_LINE_LENGTH)

        self.assertEqual([["b"]], self._read_each("x\nb\n"))


class ScreenStartTest(unittest.TestCase):
    """Tests for the request validation in Screen.start."""

    def setUp(self) -> None:
        self.pipe_dir = _use_temporary_pipe_dir(self)
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
                with self.assertRaises(SystemExit) as ctx, self.assertLogs(self.screen.logger, "DEBUG") as logs:
                    self.screen.start()

                self.assertEqual(ctx.exception.code, 0)
                self.assertEqual("Status: 400 Bad Request\r\n\r\n", stdout.getvalue())
                self.assertFalse(self.screen.started)
                # the request body is untrusted, so only its length is logged
                if client_init:
                    self.assertNotIn(client_init.strip(), "\n".join(logs.output))

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
            with self.assertRaises(SystemExit) as ctx, self.assertLogs(self.screen.logger, "DEBUG") as logs:
                self.screen.start()

            self.assertEqual(ctx.exception.code, 0)
            self.assertEqual("Status: 400 Bad Request\r\n\r\n", stdout.getvalue())
            self.assertNotIn("polling child", "\n".join(logs.output))
            # the request body is left untouched: validation happens before reading it
            self.assertEqual(0, stdin.tell())

    @unittest.skipIf(IS_WINDOWS, "Creating the client pipe requires the POSIX-only os.mkfifo and signal.alarm")
    @unittest.skipIf(IS_GRAALPY, "os.mkfifo is missing on GraalPy")
    def test_start_accepts_valid_resize_request(self) -> None:
        # left over from an earlier session of the same screen
        self.screen.input_tail = "page "
        self.screen._dropping_line = True

        with (
            mock.patch.object(web.sys, "stdin", io.StringIO("window resize 80 24\n")),
            mock.patch.dict(os.environ, {"HTTP_X_URWID_METHOD": "multipart"}, clear=True),
            mock.patch.object(web.os, "mkfifo") as mkfifo,
            mock.patch.object(web.os, "open", return_value=42),
            mock.patch.object(web.signal, "signal"),
            mock.patch.object(web.signal, "alarm"),
        ):
            self.screen.start()

        self.assertTrue(self.screen.started)
        # the pipe lives in the private session directory and its name does not reveal the session id
        urwid_id = self.screen.content_head.split("X-Urwid-ID: ", 1)[1].split("\r\n", 1)[0]
        self.assertNotIn(urwid_id, self.screen.pipe_name)
        self.assertEqual(web._session_path(urwid_id), self.screen.pipe_name)
        mkfifo.assert_called_once_with(f"{self.screen.pipe_name}.in", 0o600)
        self.assertEqual(self.screen.screen_size, (80, 24))
        self.assertEqual(self.screen.last_screen, {})
        self.assertEqual(self.screen.last_screen_width, 0)
        self.assertEqual("", self.screen.input_tail)
        self.assertFalse(self.screen._dropping_line)


class SpanStyleTest(unittest.TestCase):
    """Tests for web.code_span, which wraps common.attr_spec_to_css's inline CSS into the wire
    format sent to the browser. The colour/attribute-to-CSS logic itself is covered by
    tests/display/test_common.py, since web and html_fragment now share it.
    """

    def test_code_span_wraps_style_and_text(self) -> None:
        span = web.code_span("hi", AttrSpec("white", "black"))

        self.assertEqual("color:#ffffff;background-color:#000000\x01hi\n", span)

    def test_code_span_sends_the_hyperlink_as_a_third_field(self) -> None:
        for uri, expected in (
            ("https://urwid.org", "color:#ffffff;background-color:#000000\x01https://urwid.org\x01hi\n"),
            (" javascript:alert(1)", "color:#ffffff;background-color:#000000\x01hi\n"),
        ):
            with self.subTest(uri):
                self.assertEqual(expected, web.code_span("hi", AttrSpec("white", "black", hyperlink=uri)))

    def test_code_span_cursor_splits_into_three_pieces_with_swapped_colours(self) -> None:
        span = web.code_span("abc", AttrSpec("white", "black"), cursor=1)

        self.assertEqual(
            "color:#ffffff;background-color:#000000\x01a\n"
            "color:#000000;background-color:#ffffff\x01b\n"
            "color:#ffffff;background-color:#000000\x01c\n",
            span,
        )


class ScreenPollingChildDrawTest(unittest.TestCase):
    """The polling child answers the browser over its update socket, which takes bytes."""

    def test_draw_screen_sends_utf8_update_and_closes_the_connection(self) -> None:
        self.addCleanup(urwid.set_encoding, urwid.util.get_encoding())
        # the canvas is in the configured encoding, the transport is always UTF-8
        for encoding in ("utf-8", "latin-1"):
            with self.subTest(encoding=encoding):
                urwid.set_encoding(encoding)
                screen = web.Screen()
                screen.update_method = "polling child"
                client = mock.Mock()
                # a real socket rejects str the same way
                client.sendall.side_effect = memoryview
                screen.server_socket = mock.Mock(accept=mock.Mock(return_value=(client, None)))
                canvas = urwid.Text("h\u00e9").render((5,))

                with mock.patch.object(web.signal, "alarm", create=True):
                    screen.draw_screen((canvas.cols(), canvas.rows()), canvas)

                client.sendall.assert_called_once()
                (data,) = client.sendall.call_args.args
                self.assertIsInstance(data, bytes)
                self.assertIn("h\u00e9".encode("utf-8"), data)
                client.close.assert_called_once_with()


class ScreenPaletteTest(unittest.TestCase):
    """Tests for Screen palette registration and draw_screen's attribute/colour resolution,
    which must honour the full AttrSpec feature set the way raw_display does.
    """

    def setUp(self) -> None:
        self.screen = web.Screen()
        self.screen.update_method = "multipart"

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

    def test_fg_only_attribute_inherits_the_container_background(self) -> None:
        self.screen.register_palette([("red_fg", "dark red", "inherit"), ("blue_bg", "inherit", "dark blue")])
        canvas = urwid.AttrMap(urwid.Text(("red_fg", "a")), "blue_bg").render((2,))

        output = self._draw(canvas)

        for label, span in (
            ("fg-only run", "color:#cd0000;background-color:#0000ee\x01a"),
            ("padding", "color:#000000;background-color:#0000ee\x01 "),
        ):
            with self.subTest(label):
                self.assertIn(span, output)

    def test_palette_change_resends_only_changed_lines(self) -> None:
        self.screen.register_palette_entry("focus", "white", "black")
        canvas = urwid.Pile([urwid.AttrMap(urwid.Text("hi"), "focus"), urwid.Text("other")]).render((5,))
        self._draw(canvas)
        self.assertNotIn("hi", self._draw(canvas))

        self.screen.register_palette_entry("focus", "white", "dark blue")
        output = self._draw(canvas)
        self.assertIn("hi", output)
        self.assertNotIn("other", output)

        self.screen.register_palette([], replace=True)
        output = self._draw(canvas)
        self.assertIn("color:#000000;background-color:#e5e5e5\x01hi", output)
        self.assertNotIn("other", output)

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
