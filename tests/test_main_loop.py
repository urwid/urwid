from __future__ import annotations

import concurrent.futures
import contextlib
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


class ClosingScreenIO(typing.ContextManager[tuple[socket.socket, typing.TextIO]]):
    """Socket backed input/output for a raw `Screen` detached from any real terminal.

    The raw display reads bytes from its input socket and writes text to its output stream,
    so the input end is handed over as a socket and the output end as a text stream.
    Both ends are sockets since a socket descriptor can not be wrapped by `os.fdopen` on Windows.
    """

    __slots__ = ("_closing",)

    def __init__(self) -> None:
        self._closing: list[typing.IO[typing.Any] | socket.socket] = []

    def __enter__(self) -> tuple[socket.socket, typing.TextIO]:
        screen_input, feed_input = socket.socketpair()
        collect_output, screen_output = socket.socketpair()
        output_stream = screen_output.makefile("w", encoding="utf-8")
        self._closing = [output_stream, screen_input, feed_input, collect_output, screen_output]
        return screen_input, output_stream

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close everything explicit without waiting for garbage collected."""
        for closing in self._closing:
            with contextlib.suppress(OSError):
                closing.close()
        self._closing = []


def stop_screen_cb(*_args, **_kwargs) -> typing.NoReturn:
    raise urwid.ExitMainLoop


@contextlib.contextmanager
def dummy_raw_main_loop(
    widget: urwid.Widget | None = None,
    **kwargs: typing.Any,
) -> typing.Iterator[urwid.MainLoop]:
    """MainLoop bound to socket-backed raw Screen IO (no real TTY)."""
    with ClosingScreenIO() as (screen_input, screen_output):
        yield urwid.MainLoop(
            widget if widget is not None else urwid.SolidFill(),
            screen=urwid.display.raw.Screen(input=screen_input, output=screen_output),
            handle_mouse=False,
            **kwargs,
        )


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
            ClosingScreenIO() as (screen_input, screen_output),
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
                # We need screen which support mocked IO
                screen=urwid.display.raw.Screen(input=screen_input, output=screen_output),
                handle_mouse=False,  # Less external calls - better
            )
            evl.set_alarm_in(1, stop_screen_cb)
            pipe_fd = evl.watch_pipe(pipe_cb)
            executor.submit(pipe_writer, pipe_fd)

            evl.run()
            self.assertEqual([b"something", b"true", b"null", b"false"], outcome)
            not_removed = evl.remove_watch_pipe(pipe_fd)
            self.assertFalse(not_removed)

    def test_set_alarm_in(self):
        """Loop_customizations schedules work with set_alarm_in and ExitMainLoop."""
        seen: list[tuple[urwid.MainLoop, object]] = []

        def on_alarm(loop: urwid.MainLoop, user_data: object) -> typing.NoReturn:
            seen.append((loop, user_data))
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop() as evl:
            evl.set_alarm_in(0.01, on_alarm, user_data="token")
            evl.run()

        self.assertEqual(1, len(seen))
        self.assertIs(seen[0][0], evl)
        self.assertEqual("token", seen[0][1])

    def test_set_alarm_in_reschedule(self):
        """Drain reschedules set_alarm_in until finished."""
        ticks: list[int] = []
        remaining = 3

        def drain(loop: urwid.MainLoop, _user_data: object) -> None:
            nonlocal remaining
            remaining -= 1
            ticks.append(remaining)
            if remaining:
                loop.set_alarm_in(0.01, drain)
            else:
                raise urwid.ExitMainLoop

        with dummy_raw_main_loop() as evl:
            evl.set_alarm_in(0.01, drain)
            evl.run()

        self.assertEqual([2, 1, 0], ticks)

    def test_draw_screen_from_alarm(self):
        """Update widgets then call draw_screen."""
        text = urwid.Text("wait")
        widget = urwid.Filler(text, valign="top")
        draws = 0
        original_draw: typing.Callable[..., None] | None = None

        def counting_draw(*args: typing.Any, **kwargs: typing.Any) -> None:
            nonlocal draws
            draws += 1
            typing.cast("typing.Callable[..., None]", original_draw)(*args, **kwargs)

        def on_alarm(loop: urwid.MainLoop, _user_data: object) -> typing.NoReturn:
            text.set_text("done")
            loop.draw_screen()
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop(widget) as evl:
            original_draw = evl.screen.draw_screen
            evl.screen.draw_screen = counting_draw  # type: ignore[method-assign]
            evl.set_alarm_in(0.01, on_alarm)
            evl.run()

        self.assertEqual("done", text.text)
        self.assertGreaterEqual(draws, 1)

    def test_widget_replace_and_draw_screen(self):
        """Replaces the top widget then redraw."""
        first = urwid.SolidFill(".")
        second = urwid.SolidFill("#")

        def on_alarm(loop: urwid.MainLoop, _user_data: object) -> typing.NoReturn:
            loop.widget = second
            loop.draw_screen()
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop(first) as evl:
            evl.set_alarm_in(0.01, on_alarm)
            evl.run()
            self.assertIs(second, evl.widget)

    def test_remove_alarm(self):
        fired = False

        def should_not_run(_loop: urwid.MainLoop, _user_data: object) -> None:
            nonlocal fired
            fired = True

        with dummy_raw_main_loop() as evl:
            handle = evl.set_alarm_in(50, should_not_run)
            self.assertTrue(evl.remove_alarm(handle))
            self.assertFalse(evl.remove_alarm(handle))
            evl.set_alarm_in(0.01, stop_screen_cb)
            evl.run()

        self.assertFalse(fired)

    def test_unhandled_input(self):
        """Pass unhandled_key as unhandled_input."""
        seen: list[str | tuple[str, int, int, int]] = []

        def unhandled(key: str | tuple[str, int, int, int]) -> bool:
            seen.append(key)
            return True

        with dummy_raw_main_loop(unhandled_input=unhandled) as evl:
            evl.screen_size = (80, 24)
            self.assertTrue(evl.process_input(["esc"]))

        self.assertEqual(["esc"], seen)

    def test_pop_ups(self):
        """Construct MainLoop with pop_ups enabled."""
        with dummy_raw_main_loop(pop_ups=True) as evl:
            self.assertTrue(evl.pop_ups)
            evl.set_alarm_in(0.01, stop_screen_cb)
            evl.run()
