from __future__ import annotations

import io
import os
import unittest
from unittest import mock

from urwid.display import web


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
