from __future__ import annotations

import concurrent.futures
import os
import socket
import sys
import threading
import typing
import unittest.mock

import urwid

if typing.TYPE_CHECKING:
    from types import TracebackType

IS_WINDOWS = sys.platform == "win32"


class ClosingTemporaryFilesPair(typing.ContextManager[tuple[typing.TextIO, typing.TextIO]]):
    """File pair context manager that closes temporary files on exit.

    Since `sys.stdout` is TextIO, tests have to use compatible api for the proper behavior imitation.
    """

    __slots__ = ("rd_s", "wr_s", "rd_f", "wr_f")

    def __init__(self) -> None:
        self.rd_s: socket.socket | None = None
        self.wr_s: socket.socket | None = None
        self.rd_f: typing.TextIO | None = None
        self.wr_f: typing.TextIO | None = None

    def __enter__(self) -> tuple[typing.TextIO, typing.TextIO]:
        self.rd_s, self.wr_s = socket.socketpair()
        self.rd_f = os.fdopen(self.rd_s.fileno(), "r", encoding="utf-8", closefd=False)
        self.wr_f = os.fdopen(self.wr_s.fileno(), "w", encoding="utf-8", closefd=False)
        return self.rd_f, self.wr_f

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close everything explicit without waiting for garbage collected."""
        if self.rd_f is not None and not self.rd_f.closed:
            self.rd_f.close()
        if self.rd_s is not None:
            self.rd_s.close()
        if self.wr_f is not None and not self.wr_f.closed:
            self.wr_f.close()
        if self.wr_s is not None:
            self.wr_s.close()


def stop_screen_cb(*_args, **_kwargs) -> typing.NoReturn:
    raise urwid.ExitMainLoop


class TestMainLoop(unittest.TestCase):
    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    def test_watch_pipe(self):
        """Test watching pipe is stopped on explicit False only."""
        evt = threading.Event()  # We need thread synchronization
        outcome: list[bytes] = []

        def pipe_cb(data: bytes) -> typing.Any:
            outcome.append(data)

            if not evt.is_set():
                evt.set()

            if data == b"false":
                return False
            if data == b"true":
                return True
            if data == b"null":
                return None
            return object()

        def pipe_writer(fd: int) -> None:
            os.write(fd, b"something")
            if evt.wait(0.1):
                evt.clear()
                os.write(fd, b"true")
            if evt.wait(0.1):
                evt.clear()
                os.write(fd, b"null")
            if evt.wait(0.1):
                evt.clear()
                os.write(fd, b"false")

        with (
            ClosingTemporaryFilesPair() as (
                rd_r,
                wr_r,
            ),
            ClosingTemporaryFilesPair() as (
                rd_w,
                wr_w,
            ),
            concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
            ) as executor,
            unittest.mock.patch(
                "subprocess.Popen",  # we want to be sure that nothing outside is called
                autospec=True,
            ),
        ):
            evl = urwid.MainLoop(
                urwid.SolidFill(),
                screen=urwid.display.raw.Screen(input=rd_r, output=wr_w),  # We need screen which support mocked IO
                handle_mouse=False,  # Less external calls - better
            )
            evl.set_alarm_in(1, stop_screen_cb)
            pipe_fd = evl.watch_pipe(pipe_cb)
            executor.submit(pipe_writer, pipe_fd)

            evl.run()
            self.assertEqual([b"something", b"true", b"null", b"false"], outcome)
            not_removed = evl.remove_watch_pipe(pipe_fd)
            self.assertFalse(not_removed)
