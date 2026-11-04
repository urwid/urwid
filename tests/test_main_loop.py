from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import contextlib
import contextvars
import doctest
import gc
import inspect
import io
import math
import os
import select
import socket
import sys
import threading
import time
import typing
import unittest.mock
import weakref

import urwid
import urwid.testing
from tests.util import NonExternalLoopScreen, external_loop
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED
from urwid.event_loop import main_loop as main_loop_module

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

IS_WINDOWS = sys.platform == "win32"
IS_GRAALPY = sys.implementation.name == "graalpy"
IS_CPYTHON = sys.implementation.name == "cpython"


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


class ScriptedInputScreen(NonExternalLoopScreen):
    """Screen returning a scripted sequence of get_input() results, then empty."""

    def __init__(
        self,
        responses: list[tuple[list[typing.Any], list[int]]],
        cols_rows: tuple[int, int] = (10, 5),
    ) -> None:
        super().__init__(cols_rows)
        self._responses = list(responses)

    def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
        self.input_calls += 1
        if self._responses:
            return self._responses.pop(0)
        return [], []


class LimitedInputScreen(ScriptedInputScreen):
    """Scripted screen that fails a test reading input after the script, instead of letting it wait forever."""

    def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
        """Return the next scripted input, or empty input up to a limit.

        :raises AssertionError: input was read 20 times and the script is used up.
        """
        if not self._responses and self.input_calls >= 20:
            raise AssertionError("still waiting for input")
        return super().get_input(raw_keys)


class RecordingWidget:
    """Duck-typed widget recording keypress/mouse calls with a scripted response."""

    def __init__(
        self,
        selectable: bool = True,
        keypress_return: str | None = None,
        mouse_return: bool = True,
    ) -> None:
        self._selectable = selectable
        self._keypress_return = keypress_return
        self._mouse_return = mouse_return
        self.keypress_calls: list[str] = []
        self.keypress_sizes: list[tuple[int, int]] = []
        self.mouse_calls: list[tuple[str, int, int, int]] = []

    def selectable(self) -> bool:
        return self._selectable

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        self.keypress_calls.append(key)
        self.keypress_sizes.append(size)
        return self._keypress_return

    def mouse_event(self, size: tuple[int, int], event: str, button: int, col: int, row: int, focus: bool) -> bool:
        self.mouse_calls.append((event, button, col, row))
        return self._mouse_return


class TestMainLoop(unittest.TestCase):
    def test_run_stops_the_screen_when_start_fails(self):
        """A failure in start() after the screen started leaves the terminal restored."""
        screen = unittest.mock.Mock(spec=urwid.display.raw.Screen)
        screen.set_mouse_tracking.side_effect = OSError
        event_loop = unittest.mock.Mock(spec=urwid.SelectEventLoop)
        loop = urwid.MainLoop(urwid.SolidFill(), screen=screen, event_loop=event_loop)

        with self.assertRaises(OSError):
            loop.run()

        screen.start.assert_called_once_with()
        screen.stop.assert_called_once_with()
        event_loop.run.assert_not_called()

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_watch_pipe_removed_at_end_of_file(self):
        """Once every write end is closed, the callback gets b"" once and the watch is gone."""
        loop = urwid.MainLoop(
            urwid.SolidFill(),
            screen=unittest.mock.Mock(spec=urwid.display.raw.Screen),
            event_loop=urwid.SelectEventLoop(),
        )
        received: list[bytes] = []

        def stop() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        def on_data(data: bytes) -> None:
            received.append(data)
            if len(received) > 2:
                stop()  # a watch left on the closed pipe keeps it ready and starves the alarm below

        pipe_wr = loop.watch_pipe(on_data)
        os.write(pipe_wr, b"data")
        os.close(pipe_wr)
        loop.event_loop.alarm(0.1, stop)
        loop.event_loop.run()

        self.assertEqual([b"data", b""], received)
        self.assertFalse(loop.remove_watch_pipe(pipe_wr))

    @unittest.skipIf(IS_WINDOWS, "AsyncioEventLoop is not supported on Windows here")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_watch_pipe_async_callback_reads_each_write_once(self):
        """Wake-ups queued before the first task read the pipe do not fail on the drained descriptor."""
        asyncio_loop = asyncio.new_event_loop()
        self.addCleanup(asyncio_loop.close)
        loop = urwid.MainLoop(
            urwid.SolidFill(),
            screen=unittest.mock.Mock(spec=urwid.display.raw.Screen),
            event_loop=urwid.AsyncioEventLoop(loop=asyncio_loop),
        )
        received: list[bytes] = []

        async def on_data(data: bytes) -> bool:
            received.append(data)
            return data != b"last"

        def stop() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        pipe_wr = loop.watch_pipe(on_data)
        self.addCleanup(os.close, pipe_wr)
        os.write(pipe_wr, b"first")
        loop.event_loop.alarm(0.1, lambda: os.write(pipe_wr, b"last"))
        loop.event_loop.alarm(0.2, stop)
        loop.event_loop.run()

        self.assertEqual([b"first", b"last"], received)
        self.assertFalse(loop.remove_watch_pipe(pipe_wr))

    @unittest.skipIf(IS_WINDOWS, "AsyncioEventLoop is not supported on Windows here")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_watch_pipe_async_callback_gets_end_of_file_once(self):
        """An async callback still running at the end of the pipe does not get b"" again on later passes."""
        asyncio_loop = asyncio.new_event_loop()
        self.addCleanup(asyncio_loop.close)
        loop = urwid.MainLoop(
            urwid.SolidFill(),
            screen=unittest.mock.Mock(spec=urwid.display.raw.Screen),
            event_loop=urwid.AsyncioEventLoop(loop=asyncio_loop),
        )
        received: list[bytes] = []

        async def on_data(data: bytes) -> None:
            received.append(data)
            await asyncio.sleep(0.05)

        def stop() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        pipe_wr = loop.watch_pipe(on_data)
        os.close(pipe_wr)
        loop.event_loop.alarm(0.2, stop)
        loop.event_loop.run()

        self.assertEqual([b""], received)
        self.assertFalse(loop.remove_watch_pipe(pipe_wr))

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
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

    def test_set_alarm_in_async_callback(self):
        """An async def callback is awaited, not silently dropped, on a loop that supports it."""
        seen: list[tuple[urwid.MainLoop, object]] = []

        async def on_alarm(loop: urwid.MainLoop, user_data: object) -> typing.NoReturn:
            seen.append((loop, user_data))
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop(event_loop=urwid.AsyncioEventLoop()) as evl:
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

    def test_set_alarm_in_callback_error_logged(self):
        """A mis-shaped alarm callback logs its traceback and does not kill the loop."""
        calls: list[str] = []

        def mis_shaped(rect: object) -> None:
            raise AssertionError("must not run: set_alarm_in passes (loop, user_data)")

        def healthy(loop: urwid.MainLoop, _user_data: object) -> typing.NoReturn:
            calls.append("healthy")
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop() as evl, self.assertLogs(evl.logger, level="ERROR") as logs:
            evl.set_alarm_in(0.01, typing.cast("typing.Callable[..., None]", mis_shaped))
            evl.set_alarm_in(0.02, healthy)
            evl.run()

        self.assertEqual(["healthy"], calls)
        self.assertTrue(any("mis_shaped" in output for output in logs.output))
        self.assertTrue(any("TypeError" in output for output in logs.output))

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

    def test_default_screen_created(self):
        """No screen given: MainLoop constructs its own raw display Screen."""
        evl = urwid.MainLoop(urwid.SolidFill())
        self.assertIsInstance(evl.screen, urwid.display.raw.Screen)

    def test_register_palette_via_constructor(self):
        """A non-empty palette passed to the constructor is registered on the screen."""
        with ClosingScreenIO() as (screen_input, screen_output):
            screen = urwid.display.raw.Screen(input=screen_input, output=screen_output)
            urwid.MainLoop(urwid.SolidFill(), palette=[("body", "black", "white")], screen=screen)
        self.assertIn("body", screen._palette)

    def test_explicit_event_loop_used_directly(self):
        """An explicit event_loop is stored as-is, without constructing a default SelectEventLoop."""
        with ClosingScreenIO() as (screen_input, screen_output):
            screen = urwid.display.raw.Screen(input=screen_input, output=screen_output)
            loop = urwid.SelectEventLoop()
            evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, event_loop=loop)
        self.assertIs(loop, evl.event_loop)

    def test_widget_setter_updates_pop_up_target(self):
        """Replacing widget while pop_ups is enabled updates the PopUpTarget's original_widget."""
        first = urwid.SolidFill(".")
        second = urwid.SolidFill("#")
        with dummy_raw_main_loop(first, pop_ups=True) as evl:
            self.assertIs(first, evl._topmost_widget.original_widget)
            evl.widget = second
            self.assertIs(second, evl._topmost_widget.original_widget)

    def test_set_alarm_at(self):
        """set_alarm_at schedules a callback at an absolute time."""
        seen: list[object] = []

        def on_alarm(loop: urwid.MainLoop, user_data: object) -> typing.NoReturn:
            seen.append(user_data)
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop() as evl:
            evl.set_alarm_at(time.time() + 0.01, on_alarm, user_data="at")
            evl.run()

        self.assertEqual(["at"], seen)

    def test_set_alarm_at_async_callback(self):
        """An async def callback is awaited, not silently dropped, on a loop that supports it."""
        seen: list[object] = []

        async def on_alarm(loop: urwid.MainLoop, user_data: object) -> typing.NoReturn:
            seen.append(user_data)
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop(event_loop=urwid.AsyncioEventLoop()) as evl:
            evl.set_alarm_at(time.time() + 0.01, on_alarm, user_data="at")
            evl.run()

        self.assertEqual(["at"], seen)

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_watch_pipe_async_callback(self):
        """An async def watch_pipe callback is awaited, and its return value still controls removal."""
        outcome: list[bytes] = []

        async def pipe_cb(data: bytes) -> bool | None:
            outcome.append(data)
            return False

        with dummy_raw_main_loop(event_loop=urwid.AsyncioEventLoop()) as evl:
            pipe_fd = evl.watch_pipe(pipe_cb)
            os.write(pipe_fd, b"hi")
            evl.set_alarm_in(0.05, stop_screen_cb)
            evl.run()

        self.assertEqual([b"hi"], outcome)
        # already removed by the callback returning False, so a second removal fails
        self.assertFalse(evl.remove_watch_pipe(pipe_fd))

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_remove_watch_pipe_missing_fd(self):
        """Removing a watch pipe that was never created returns False."""
        with dummy_raw_main_loop() as evl:
            self.assertFalse(evl.remove_watch_pipe(999999))

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    def test_remove_watch_pipe_active(self):
        """Removing a still-active watch pipe succeeds once and fails on a second attempt."""
        with dummy_raw_main_loop() as evl:
            pipe_fd = evl.watch_pipe(lambda data: None)
            self.assertTrue(evl.remove_watch_pipe(pipe_fd))
            self.assertFalse(evl.remove_watch_pipe(pipe_fd))

    def test_watch_file_and_remove_watch_file(self):
        """watch_file and remove_watch_file delegate directly to the event loop."""
        with dummy_raw_main_loop() as evl:
            pipe_rd, pipe_wr = os.pipe()
            try:
                handle = evl.watch_file(pipe_rd, lambda: None)
                self.assertTrue(evl.remove_watch_file(handle))
                self.assertFalse(evl.remove_watch_file(handle))
            finally:
                os.close(pipe_rd)
                os.close(pipe_wr)

    def test_start_sets_mouse_tracking_when_handled(self):
        """start() enables mouse tracking on the screen when handle_mouse is True."""
        with ClosingScreenIO() as (screen_input, screen_output):
            screen = urwid.display.raw.Screen(input=screen_input, output=screen_output)
            calls: list[bool] = []
            screen.set_mouse_tracking = lambda enable=True: calls.append(enable)
            evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=True)
            with evl.start():
                pass
        self.assertEqual([True], calls)

    def test_screen_stop_removes_its_input_from_the_event_loop(self):
        """Stopping the screen of a started loop stops watching its input, also after a later re-notification."""
        event_loop = urwid.SelectEventLoop()
        with dummy_raw_main_loop(event_loop=event_loop) as evl, evl.start():
            self.assertTrue(event_loop._watch_files)

            # The one watch left is the loop's own, for call_from_thread().
            thread_calls = {evl._thread_calls.reader.fileno()}
            evl.screen.stop()
            self.assertEqual(thread_calls, set(event_loop._watch_files))

            urwid.emit_signal(evl.screen, INPUT_DESCRIPTORS_CHANGED)
            self.assertEqual(thread_calls, set(event_loop._watch_files))

    def test_paused_stops_and_restarts_the_screen(self) -> None:
        """paused() stops the screen and its input for the block and restarts them for a full redraw."""
        with dummy_raw_main_loop() as evl, evl.start():
            screen = typing.cast("urwid.display.raw.Screen", evl.screen)
            evl.screen_size = (10, 5)
            with evl.paused():
                self.assertFalse(screen.started)
                self.assertEqual([], screen.get_input_descriptors())
                screen.screen_buf = [[]]

            self.assertTrue(screen.started)
            self.assertTrue(screen.get_input_descriptors())
            self.assertIsNone(evl.screen_size)
            self.assertIsNone(screen.screen_buf)

    def test_paused_restores_mouse_tracking_when_handled(self) -> None:
        """paused() enables mouse tracking again on resume when handle_mouse is True."""
        with ClosingScreenIO() as (screen_input, screen_output):
            screen = urwid.display.raw.Screen(input=screen_input, output=screen_output)
            evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=True)
            with (
                unittest.mock.patch.object(screen, "set_mouse_tracking") as set_mouse_tracking,
                evl.start(),
                evl.paused(),
            ):
                pass
        self.assertEqual([unittest.mock.call(), unittest.mock.call()], set_mouse_tracking.call_args_list)

    def test_paused_restarts_the_screen_when_the_block_raises(self) -> None:
        """An exception in the paused block propagates and the screen is started again."""
        with dummy_raw_main_loop() as evl, evl.start():
            with self.assertRaises(RuntimeError), evl.paused():
                raise RuntimeError("editor failed")
            self.assertTrue(evl.screen.started)

    def test_paused_leaves_a_stopped_screen_alone(self) -> None:
        """paused() on a screen that was not started runs the block and starts nothing."""
        with dummy_raw_main_loop() as evl:
            ran: list[bool] = []
            with evl.paused():
                ran.append(evl.screen.started)
            self.assertEqual([False], ran)
            self.assertFalse(evl.screen.started)

    def test_paused_redraws_after_resume(self) -> None:
        """A change made while paused is drawn once the block ends."""
        text = urwid.Text("before")

        def unhandled(key: str | tuple[str, int, int, int]) -> bool:
            with evl.paused():
                text.set_text("after")
            return True

        screen = urwid.testing.ScriptedScreen(size=(6, 1), inputs=[["e"]])
        evl = urwid.MainLoop(urwid.Filler(text), screen=screen, unhandled_input=unhandled)
        evl.run()
        self.assertEqual(["after "], screen.last_text)

    def test_paused_in_screen_event_loop_restarts_before_the_next_read(self) -> None:
        """With a screen that drives its own loop, input after a pause is read from a started screen."""

        class StartedRecordingScreen(LimitedInputScreen):
            """Scripted screen recording whether it was started at each read."""

            def __init__(self, responses: list[tuple[list[typing.Any], list[int]]]) -> None:
                super().__init__(responses)
                self.started_at_read: list[bool] = []

            def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
                self.started_at_read.append(self.started)
                return super().get_input(raw_keys)

        def unhandled(key: str | tuple[str, int, int, int]) -> bool:
            if key == "q":
                raise urwid.ExitMainLoop
            with evl.paused():
                pass
            return True

        screen = StartedRecordingScreen([(["e"], []), (["q"], [])])
        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False, unhandled_input=unhandled)
        evl.run()
        self.assertEqual([True, True], screen.started_at_read)

    def test_process_input_gives_a_size_to_keys_after_a_pause(self) -> None:
        """A key after a pausing handler in the same batch is given the screen size, not None."""
        widget = RecordingWidget(selectable=True, keypress_return="z")
        paused: list[bool] = []

        def unhandled(key: str | tuple[str, int, int, int]) -> bool:
            if not paused:
                paused.append(True)
                with evl.paused():
                    pass
            return True

        with dummy_raw_main_loop(typing.cast("urwid.Widget", widget), unhandled_input=unhandled) as evl, evl.start():
            evl.process_input(["e", "x"])
        self.assertEqual(["e", "x"], widget.keypress_calls)
        self.assertIsInstance(widget.keypress_sizes[1], tuple)
        self.assertEqual(2, len(widget.keypress_sizes[1]))

    def test_start_raises_when_screen_lacks_external_loop_support(self):
        """start() raises CantUseExternalLoop for a screen without hook_event_loop."""
        evl = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen())
        with self.assertRaises(main_loop_module.CantUseExternalLoop):
            evl.start()

    def test_run_uses_screen_event_loop_when_unsupported(self):
        """run() falls back to _run_screen_event_loop for a screen without external loop support."""
        screen = NonExternalLoopScreen()
        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False)
        evl.set_alarm_in(0, stop_screen_cb)
        evl.run()
        self.assertGreaterEqual(screen.input_calls, 1)
        self.assertEqual([0.0], screen.timeouts)
        self.assertFalse(screen.started)

    def test_run_screen_event_loop_processes_keys_without_alarms(self):
        """_run_screen_event_loop handles real keys and a resize with no alarms scheduled."""
        screen = ScriptedInputScreen([([], []), (["window resize"], []), (["quit"], [])])

        def unhandled(data: str) -> bool | None:
            if data == "quit":
                raise urwid.ExitMainLoop
            return False

        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False, unhandled_input=unhandled)
        evl.run()
        self.assertGreaterEqual(screen.input_calls, 3)
        self.assertEqual({None}, set(screen.timeouts))

    def test_run_screen_event_loop_processes_multiple_alarms(self):
        """_run_screen_event_loop pops and fires alarms one at a time across outer iterations."""
        order: list[str] = []

        def cb_a(loop: urwid.MainLoop, data: object) -> None:
            order.append("a")

        def cb_b(loop: urwid.MainLoop, data: object) -> typing.NoReturn:
            order.append("b")
            raise urwid.ExitMainLoop

        screen = NonExternalLoopScreen()
        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False)
        evl.set_alarm_in(0, cb_a)
        evl.set_alarm_in(0.03, cb_b)
        evl.run()
        self.assertEqual(["a", "b"], order)

    def test_run_screen_event_loop_input_changes_pending_alarms(self):
        """Input handled while an alarm is pending can remove that alarm and add an earlier one."""
        removed: list[bool] = []

        def late(loop: urwid.MainLoop, data: object) -> None:
            raise AssertionError("removed alarm fired")

        def exit_clean(loop: urwid.MainLoop, data: object) -> typing.NoReturn:
            raise urwid.ExitMainLoop

        def unhandled(data: str) -> bool:
            removed.append(evl.remove_alarm(late_handle))
            evl.set_alarm_in(0, exit_clean)
            return True

        screen = LimitedInputScreen([(["x"], [])])
        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False, unhandled_input=unhandled)
        late_handle = evl.set_alarm_in(60, late)
        evl.run()
        self.assertEqual([True], removed)

    def test_run_screen_event_loop_keeps_reading_input_once_the_alarm_queue_drains(self):
        """_run_screen_event_loop keeps reading input once the alarm queue drains."""
        order: list[str] = []

        def cb_a(loop: urwid.MainLoop, data: object) -> None:
            order.append("a")

        screen = ScriptedInputScreen([([], []), (["quit"], [])])

        def unhandled(data: str) -> bool | None:
            if data == "quit":
                raise urwid.ExitMainLoop
            return False

        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False, unhandled_input=unhandled)
        evl.set_alarm_in(0, cb_a)
        evl.run()
        self.assertEqual(["a"], order)

    def test_run_screen_event_loop_runs_a_watched_file_and_redraws(self) -> None:
        """With a poll interval, a readable watched file is handled within one poll, and the screen is redrawn."""
        received: list[bytes] = []
        rd, wr = socket.socketpair()
        self.addCleanup(rd.close)
        self.addCleanup(wr.close)

        class ExitOnRedraw(urwid.SolidFill):
            """Fill that leaves the loop when it is drawn after being told to."""

            exit_next = False

            def render(self, size: tuple[int, int], focus: bool = False) -> urwid.SolidCanvas:
                """Render the fill, or leave the loop once told to.

                :raises ExitMainLoop: :attr:`exit_next` is set.
                """
                if self.exit_next:
                    raise urwid.ExitMainLoop
                return super().render(size, focus)

        def on_ready() -> None:
            received.append(rd.recv(1))
            widget.exit_next = True
            widget._invalidate()

        def give_up(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            received.append(b"timeout")
            raise urwid.ExitMainLoop

        widget = ExitOnRedraw()
        screen = NonExternalLoopScreen()
        evl = urwid.MainLoop(widget, screen=screen, handle_mouse=False, poll_interval=0.25)
        evl.watch_file(rd.fileno(), on_ready)
        evl.set_alarm_in(0, lambda *_args: wr.send(b"x"))
        evl.set_alarm_in(10, give_up)
        evl.run()

        self.assertEqual([b"x"], received)
        # Windows has no poll: the curses screen there cannot stop waiting before a key arrives.
        self.assertEqual(not IS_WINDOWS, 0.25 in screen.timeouts)

    def test_poll_interval_is_none_or_at_least_a_tenth_of_a_second(self) -> None:
        """A poll interval shorter than the curses screen can wait, or not finite, is refused, also when assigned."""
        loop = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), poll_interval=0.1)
        for poll_interval in (0, -0.1, 0.05, math.inf, math.nan):
            with self.subTest(poll_interval=poll_interval):
                with self.assertRaises(ValueError):
                    urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), poll_interval=poll_interval)
                with self.assertRaises(ValueError):
                    loop.poll_interval = poll_interval
                self.assertEqual(0.1, loop.poll_interval)

        loop.poll_interval = None
        self.assertIsNone(loop.poll_interval)

    def test_run_screen_event_loop_stops_calling_a_removed_watch(self) -> None:
        """A watch that removes itself is not called again, although its descriptor stays readable."""
        calls: list[str] = []
        rd, wr = socket.socketpair()
        self.addCleanup(rd.close)
        self.addCleanup(wr.close)

        def on_ready() -> None:
            calls.append("ready")
            evl.remove_watch_file(handle)

        screen = NonExternalLoopScreen()
        evl = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False)
        handle = evl.watch_file(rd.fileno(), on_ready)
        wr.send(b"x")
        evl.set_alarm_in(0.05, stop_screen_cb)
        evl.run()

        self.assertEqual(["ready"], calls)

    def test_run_screen_event_loop_skips_a_watch_changed_earlier_in_the_pass(self) -> None:
        """A ready watch removed or replaced by an earlier callback of the same pass is not called."""

        class OneReadScreen(NonExternalLoopScreen):
            """Screen that leaves the loop on its second read, so a single pass of watches runs."""

            def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
                """Return no input on the first read.

                :raises ExitMainLoop: this is the second read.
                """
                if self.input_calls:
                    raise urwid.ExitMainLoop
                return super().get_input(raw_keys)

        for replace in (False, True):
            with self.subTest(replace=replace):
                called: list[str] = []
                rd_1, wr_1 = socket.socketpair()
                rd_2, wr_2 = socket.socketpair()
                for sock in (rd_1, wr_1, rd_2, wr_2):
                    self.addCleanup(sock.close)
                evl = urwid.MainLoop(urwid.SolidFill(), screen=OneReadScreen(), handle_mouse=False)

                def change(other: socket.socket, name: str, *, replace: bool = replace) -> None:
                    called.append(name)
                    evl.remove_watch_file(other.fileno())
                    if replace:
                        evl.watch_file(other.fileno(), lambda: called.append("replacement"))

                evl.watch_file(rd_1.fileno(), lambda: change(rd_2, "first"))
                evl.watch_file(rd_2.fileno(), lambda: change(rd_1, "second"))
                wr_1.send(b"x")
                wr_2.send(b"x")
                evl.run()

                self.assertEqual(1, len(called))
                self.assertNotIn("replacement", called)

    def test_run_screen_event_loop_without_polls_checks_watches_after_input(self) -> None:
        """Without a poll interval, or on Windows, a watched file does not shorten the wait for input.

        It is checked once the input returned.
        Windows is simulated by patching the platform check; the curses screen's blocking read there is not run.
        """
        for windows, poll_interval in ((False, None), (True, 0.1)):
            with self.subTest(windows=windows, poll_interval=poll_interval):
                calls: list[str] = []
                rd, wr = socket.socketpair()
                self.addCleanup(rd.close)
                self.addCleanup(wr.close)

                def unhandled(
                    key: str | tuple[str, int, int, int],
                    *,
                    record: Callable[[str], None] = calls.append,
                ) -> typing.NoReturn:
                    record(str(key))
                    raise urwid.ExitMainLoop

                screen = ScriptedInputScreen([(["k"], [])])
                evl = urwid.MainLoop(
                    urwid.SolidFill(),
                    screen=screen,
                    handle_mouse=False,
                    unhandled_input=unhandled,
                    poll_interval=poll_interval,
                )
                evl.watch_file(rd.fileno(), lambda rd=rd, calls=calls: calls.append(rd.recv(1).decode()))
                wr.send(b"w")
                with unittest.mock.patch.object(main_loop_module, "IS_WINDOWS", windows):
                    evl.run()

                self.assertEqual([None], screen.timeouts)
                self.assertEqual(["w", "k"], calls)

    def test_run_reraises_unexpected_event_loop_error(self):
        """run() removes its event loop hooks, stops the screen and lets an unexpected event loop error propagate."""
        with dummy_raw_main_loop() as evl:
            with unittest.mock.patch.object(evl.event_loop, "run", side_effect=RuntimeError("boom")):
                self.assertRaises(RuntimeError, evl.run)
            self.assertFalse(evl.screen.started)
            self.assertIsNone(evl.idle_handle)

    def test_update_processes_keys_and_resets_screen_size_on_resize(self):
        """_update runs process_input and clears screen_size on a window resize event."""
        with dummy_raw_main_loop() as evl:
            evl.screen_size = (10, 5)
            evl._update(["window resize"], [])
            self.assertIsNone(evl.screen_size)

    def test_process_input_computes_screen_size(self):
        """process_input queries the screen size when none is cached yet."""
        with dummy_raw_main_loop() as evl:
            self.assertIsNone(evl.screen_size)
            evl.process_input([])
            self.assertIsNotNone(evl.screen_size)

    def test_process_input_window_resize(self):
        """A 'window resize' key is skipped without being treated as handled."""
        with dummy_raw_main_loop() as evl:
            evl.screen_size = (10, 5)
            self.assertFalse(evl.process_input(["window resize"]))

    def test_process_input_keypress_handled_by_widget(self):
        """A key fully consumed by the widget's keypress marks input as handled."""
        widget = RecordingWidget(selectable=True, keypress_return=None)
        with dummy_raw_main_loop(widget) as evl:
            evl.screen_size = (10, 5)
            self.assertTrue(evl.process_input(["a"]))
        self.assertEqual(["a"], widget.keypress_calls)

    def test_process_input_redraw_screen_command(self):
        """An unhandled key mapped to REDRAW_SCREEN clears the screen."""
        widget = RecordingWidget(selectable=True, keypress_return="ctrl l")
        cleared: list[bool] = []
        with dummy_raw_main_loop(widget) as evl:
            evl.screen_size = (10, 5)
            evl.screen.clear = lambda: cleared.append(True)
            self.assertTrue(evl.process_input(["ctrl l"]))
        self.assertEqual([True], cleared)

    def test_process_input_mouse_event(self):
        """A mouse event handled by the widget marks input as handled."""
        widget = RecordingWidget(selectable=False, mouse_return=True)
        with dummy_raw_main_loop(widget) as evl:
            evl.screen_size = (10, 5)
            self.assertTrue(evl.process_input([("mouse press", 1, 5, 4)]))
        self.assertEqual([("mouse press", 1, 5, 4)], widget.mouse_calls)

    def test_process_input_invalid_key_raises_type_error(self):
        """A key that is neither a string nor a mouse event tuple raises TypeError."""
        with dummy_raw_main_loop() as evl:
            evl.screen_size = (10, 5)
            with self.assertRaises(TypeError):
                evl.process_input([123])

    def test_process_input_empty_key(self):
        """A falsy key value is still counted as handled."""
        with dummy_raw_main_loop() as evl:
            evl.screen_size = (10, 5)
            self.assertTrue(evl.process_input([""]))

    def test_input_filter_uses_constructor_callback(self):
        """input_filter delegates to the function passed to the constructor."""
        calls: list[tuple[list[str], list[int]]] = []

        def custom_filter(keys: list[str], raw: list[int]) -> list[str]:
            calls.append((keys, raw))
            return keys[:1]

        with dummy_raw_main_loop(input_filter=custom_filter) as evl:
            result = evl.input_filter(["a", "b"], [1, 2])

        self.assertEqual(["a"], result)
        self.assertEqual([(["a", "b"], [1, 2])], calls)

    def test_unhandled_input_default_returns_false(self):
        """unhandled_input returns False when no callback was passed to the constructor."""
        with dummy_raw_main_loop() as evl:
            self.assertFalse(evl.unhandled_input("x"))

    def test_entering_idle_skips_draw_when_screen_not_started(self):
        """entering_idle does not draw the screen before it has been started."""
        with dummy_raw_main_loop() as evl:
            self.assertFalse(evl.screen.started)
            evl.entering_idle()
            self.assertIsNone(evl.screen_size)

    def test_refl_loop_exit_raises_exit_main_loop(self):
        """_refl(..., loop_exit=True) raises ExitMainLoop when called."""
        reflected = main_loop_module._refl("scr", loop_exit=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(urwid.ExitMainLoop):
            reflected()

    def test_module_doctests_pass(self):
        """The module's own doctests (covering the _refl test helper) run cleanly."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            results = doctest.testmod(main_loop_module, verbose=False)
        self.assertEqual(0, results.failed)

    def test_test_function_runs_doctests(self):
        """main_loop._test() runs the module doctests via doctest.testmod()."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main_loop_module._test()


class LoopRecordingWidget(urwid.Widget):
    """Box widget recording the running loop at each render and keypress, leaving the loop on ``q``."""

    _sizing = frozenset((urwid.BOX,))
    _selectable = True

    def __init__(self) -> None:
        """Start with nothing recorded."""
        super().__init__()
        self.seen: list[tuple[str, urwid.MainLoop | None]] = []

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.SolidCanvas:
        """Record the running loop and return a blank canvas."""
        self.seen.append(("render", urwid.get_running_loop_or_none()))
        return urwid.SolidCanvas(" ", *size)

    def keypress(self, size: tuple[int, int], key: str) -> None:
        """Record the running loop and handle *key*.

        :raises ExitMainLoop: *key* is ``q``.
        """
        self.seen.append((key, urwid.get_running_loop_or_none()))
        if key == "q":
            raise urwid.ExitMainLoop


def input_callback(loop: urwid.MainLoop) -> typing.Callable[[list[typing.Any], list[int]], None]:
    """Return the input callback a started *loop* hooked into its mock screen."""
    return typing.cast("unittest.mock.Mock", loop.screen).hook_event_loop.call_args.args[1]


class TestRunningLoop(unittest.TestCase):
    """get_running_loop() and get_running_loop_or_none()."""

    def run(self, result: unittest.TestResult | None = None) -> unittest.TestResult | None:
        """Run each test in an empty context, so a loop a failed test left running cannot reach the next one."""
        return contextvars.Context().run(super().run, result)

    def test_no_loop_outside_any_run(self) -> None:
        """Without a running loop, get_running_loop() raises and get_running_loop_or_none() returns None."""
        with self.assertRaises(RuntimeError):
            urwid.get_running_loop()
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_screen_event_loop_renders_and_dispatches_with_the_loop(self) -> None:
        """On the screen-driven loop, rendering and key handling see the loop, which is gone after run()."""
        widget = LoopRecordingWidget()
        loop = urwid.MainLoop(widget, screen=LimitedInputScreen([(["x"], []), (["q"], [])]), handle_mouse=False)
        loop.run()

        self.assertEqual({"render", "x", "q"}, {name for name, _ in widget.seen})
        self.assertEqual([loop], list({id(seen): seen for _, seen in widget.seen}.values()))
        with self.assertRaises(RuntimeError):
            urwid.get_running_loop()

    def test_alarm_set_before_start_sees_the_loop(self) -> None:
        """An alarm scheduled before run() runs with the loop current."""
        seen: list[urwid.MainLoop | None] = []

        def record(loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen.append(urwid.get_running_loop())
            raise urwid.ExitMainLoop

        with dummy_raw_main_loop() as evl:
            evl.set_alarm_in(0, record)
            evl.run()

        self.assertEqual([evl], seen)

    def test_nested_run_of_another_loop(self) -> None:
        """A loop run from a callback of another is current inside, and the outer loop is current again after."""
        seen: dict[str, urwid.MainLoop | None] = {}

        def inner_alarm(loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen["inner"] = urwid.get_running_loop_or_none()
            raise urwid.ExitMainLoop

        def outer_alarm(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            inner.set_alarm_in(0, inner_alarm)
            inner.run()
            seen["after"] = urwid.get_running_loop_or_none()
            raise urwid.ExitMainLoop

        inner = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        outer = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        outer.set_alarm_in(0, outer_alarm)
        outer.run()

        self.assertEqual({"inner": inner, "after": outer}, seen)
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_nested_run_of_the_same_loop(self) -> None:
        """A loop run again from its own callback keeps its outer run current once the inner run returns."""
        seen: list[object] = []

        def outer_alarm(loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            outer_activation = loop._activation
            loop.set_alarm_in(0, stop_screen_cb)
            loop.run()
            seen.extend((urwid.get_running_loop_or_none(), loop._activation is outer_activation))
            raise urwid.ExitMainLoop

        loop = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        loop.set_alarm_in(0, outer_alarm)
        loop.run()

        self.assertEqual([loop, True], seen)
        self.assertIsNone(loop._activation)

    def test_stop_from_another_context(self) -> None:
        """stop() ends the loop both where start() ran and in a context copied from it, whichever runs stop()."""
        loop = external_loop()
        loop.start()
        contextvars.copy_context().run(loop.stop)
        self.assertIsNone(urwid.get_running_loop_or_none())
        self.assertIsNone(contextvars.copy_context().run(urwid.get_running_loop_or_none))

        started_in = contextvars.copy_context()
        started_in.run(loop.start)
        self.assertIs(loop, started_in.run(urwid.get_running_loop_or_none))
        loop.stop()
        self.assertIsNone(started_in.run(urwid.get_running_loop_or_none))

    def test_stopped_entries_do_not_accumulate(self) -> None:
        """Entries ended from another context are dropped when the context holding them starts a loop again."""
        loop = external_loop()
        for _ in range(10):
            loop.start()
            contextvars.copy_context().run(loop.stop)
        self.assertLessEqual(len(main_loop_module._running.get()), 1)

    @unittest.skipUnless(IS_CPYTHON, "relies on reference counting to free the loop at once")
    def test_copied_context_does_not_keep_the_loop_alive(self) -> None:
        """A context copied during a run holds no reference to the loop once the run ended."""
        copied: list[contextvars.Context] = []

        def capture(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            copied.append(contextvars.copy_context())
            raise urwid.ExitMainLoop

        loop = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        loop.set_alarm_in(0, capture)
        loop.run()
        ref = weakref.ref(loop)
        del loop
        gc.collect()

        self.assertIsNone(ref())
        self.assertIsNone(copied[0].run(urwid.get_running_loop_or_none))

    def test_failed_start_leaves_no_loop(self) -> None:
        """A start() that fails after starting the screen leaves no loop current."""
        loop = external_loop()
        typing.cast("unittest.mock.Mock", loop.screen).hook_event_loop.side_effect = OSError
        with self.assertRaises(OSError):
            loop.run()
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_failed_nested_start_keeps_the_outer_run(self) -> None:
        """A run of the loop from its own callback that fails to start leaves the outer run current."""
        seen: list[urwid.MainLoop | None] = []
        loop = external_loop()
        typing.cast("unittest.mock.Mock", loop.screen).hook_event_loop.side_effect = [None, OSError]

        def nested(_loop: urwid.MainLoop, _data: object) -> None:
            with self.assertRaises(OSError):
                loop.run()

        def last(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen.append(urwid.get_running_loop_or_none())
            raise urwid.ExitMainLoop

        loop.set_alarm_in(0, nested)
        loop.set_alarm_in(0.01, last)
        loop.run()

        self.assertEqual([loop], seen)
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_failed_stop_leaves_no_loop(self) -> None:
        """A stop() whose screen fails to stop still ends the loop."""
        loop = external_loop()
        loop.start()
        typing.cast("unittest.mock.Mock", loop.screen).stop.side_effect = OSError
        with self.assertRaises(OSError):
            loop.stop()
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_callbacks_after_stop_see_no_loop(self) -> None:
        """Alarms, watches and input left behind by a stopped loop see no loop; hand-driven calls still do."""
        seen: list[tuple[str, urwid.MainLoop | None]] = []
        widget = LoopRecordingWidget()
        loop = external_loop(widget)
        event_loop = typing.cast("urwid.SelectEventLoop", loop.event_loop)
        rd, wr = socket.socketpair()
        self.addCleanup(rd.close)
        self.addCleanup(wr.close)

        loop.start()
        loop.set_alarm_in(0, lambda *_args: seen.append(("alarm", urwid.get_running_loop_or_none())))
        loop.watch_file(rd.fileno(), lambda: seen.append(("watch", urwid.get_running_loop_or_none())))
        update = input_callback(loop)
        loop.stop()
        wr.send(b"x")
        for _ in range(5):
            event_loop._loop()
        update(["k"], [])

        self.assertIn(("alarm", None), seen)
        self.assertIn(("watch", None), seen)
        self.assertEqual({None}, {seen_loop for _, seen_loop in seen + widget.seen})
        self.assertIn(("k", None), widget.seen)

        widget.seen.clear()
        widget._invalidate()
        loop.draw_screen()
        loop.process_input(["k"])
        self.assertEqual([("render", loop), ("k", loop)], widget.seen)
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_stop_during_input_ends_the_loop_for_the_rest_of_it(self) -> None:
        """Keys an input filter returns after stopping the loop are handled with no loop current."""
        widget = LoopRecordingWidget()

        def stop_and_pass(keys: list[typing.Any], _raw: list[int]) -> list[typing.Any]:
            loop.stop()
            return keys

        loop = external_loop(widget, input_filter=stop_and_pass)
        loop.start()
        input_callback(loop)(["k"], [])

        self.assertEqual([("k", None)], widget.seen)
        self.assertIsNone(urwid.get_running_loop_or_none())

    def test_stopped_loop_callback_does_not_see_another_running_loop(self) -> None:
        """A callback a stopped loop left on a shared event loop sees no loop, not the loop running there now."""
        event_loop = urwid.SelectEventLoop()
        widget_a = LoopRecordingWidget()
        widget_b = LoopRecordingWidget()
        loop_a = external_loop(widget_a, event_loop)
        loop_b = external_loop(widget_b, event_loop)
        seen: dict[str, urwid.MainLoop | None] = {}
        copied: list[contextvars.Context] = []

        def leftover(_loop: urwid.MainLoop, _data: object) -> None:
            seen["callback"] = urwid.get_running_loop_or_none()
            copied.append(contextvars.copy_context())
            seen["copied during"] = copied[0].run(urwid.get_running_loop_or_none)
            loop_b.draw_screen()

        loop_a.start()
        loop_a.set_alarm_in(0, leftover)
        loop_a.stop()
        with loop_b.start():
            # Until both alarms ran and the loop went idle: then it waits for input, which never comes.
            for _ in range(5):
                if not (event_loop._alarms or event_loop._did_something):
                    break
                event_loop._loop()
            seen["copied after"] = copied[0].run(urwid.get_running_loop_or_none)

        self.assertEqual({"callback": None, "copied during": None, "copied after": loop_b}, seen)
        self.assertIn(("render", loop_b), widget_b.seen)
        self.assertEqual([("render", None)], widget_a.seen)

    def test_restarted_loop_is_not_visible_to_a_context_of_the_first_run(self) -> None:
        """A context copied during one run does not see the loop during or after the next run."""
        copied: list[contextvars.Context] = []
        seen: list[urwid.MainLoop | None] = []

        def capture(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            copied.append(contextvars.copy_context())
            raise urwid.ExitMainLoop

        def check(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen.append(copied[0].run(urwid.get_running_loop_or_none))
            raise urwid.ExitMainLoop

        loop = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        loop.set_alarm_in(0, capture)
        loop.run()
        loop.set_alarm_in(0, check)
        loop.run()

        self.assertEqual([None, None], [*seen, copied[0].run(urwid.get_running_loop_or_none)])

    def test_threads_see_the_loop_only_with_a_copied_context(self) -> None:
        """A thread started with an empty context sees no loop; one running a copied context sees it."""
        seen: dict[str, urwid.MainLoop | None] = {}

        def record(name: str, context: contextvars.Context) -> None:
            seen[name] = context.run(urwid.get_running_loop_or_none)

        def start_threads(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            threads = [
                threading.Thread(target=record, args=("empty", contextvars.Context())),
                threading.Thread(target=record, args=("copied", contextvars.copy_context())),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            raise urwid.ExitMainLoop

        loop = urwid.MainLoop(urwid.SolidFill(), screen=NonExternalLoopScreen(), handle_mouse=False)
        loop.set_alarm_in(0, start_threads)
        loop.run()

        self.assertEqual({"empty": None, "copied": loop}, seen)

    def test_raising_callback_restores_the_running_loops(self) -> None:
        """An alarm callback that raises, logged or leaving the loop, leaves the running loops as they were."""

        def fail(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            raise ValueError

        loop = external_loop()
        with loop.start():
            before = main_loop_module._running.get()
            with self.assertLogs(loop.logger, "ERROR"):
                loop._make_alarm_callback(fail, None)()
            self.assertIs(before, main_loop_module._running.get())
            with self.assertRaises(urwid.ExitMainLoop):
                loop._make_alarm_callback(stop_screen_cb, None)()
            self.assertIs(before, main_loop_module._running.get())
            self.assertIs(loop, urwid.get_running_loop_or_none())

    def test_async_callback_closed_from_another_context_ends_its_entry(self) -> None:
        """An async callback closed outside the context it ran in, as the garbage collector does, ends its entry."""
        entries: list[tuple[main_loop_module._Activation, ...]] = []

        class Suspend:
            """Awaitable that suspends its coroutine once, without an event loop."""

            def __await__(self) -> typing.Generator[None]:
                yield

        async def suspended(_loop: urwid.MainLoop, _data: object) -> None:
            entries.append(main_loop_module._running.get())
            await Suspend()

        loop = external_loop()
        with loop.start():
            coroutine = loop._make_alarm_callback(suspended, None)()
            contextvars.copy_context().run(coroutine.send, None)
            coroutine.close()

        self.assertEqual([None], list({entry.loop for entry in entries[0]}))

    def test_watch_file_wraps_the_callback(self) -> None:
        """watch_file() hands the event loop a wrapper that runs the callback with the loop current."""
        seen: list[urwid.MainLoop | None] = []
        event_loop = unittest.mock.Mock(spec=urwid.SelectEventLoop)
        loop = external_loop(event_loop=event_loop)

        def callback() -> str:
            seen.append(urwid.get_running_loop_or_none())
            return "result"

        async def async_callback() -> None:
            seen.append(urwid.get_running_loop_or_none())

        with loop.start():
            loop.watch_file(1, callback)
            wrapper = event_loop.watch_file.call_args.args[1]
            loop.watch_file(1, async_callback)
            async_wrapper = event_loop.watch_file.call_args.args[1]

            self.assertIsNot(callback, wrapper)
            self.assertFalse(inspect.iscoroutinefunction(wrapper))
            self.assertTrue(inspect.iscoroutinefunction(async_wrapper))
            self.assertEqual("result", wrapper())
            asyncio.run(async_wrapper())

        self.assertEqual([loop, loop], seen)


class TestCallFromThread(unittest.TestCase):
    """MainLoop.call_from_thread()."""

    def _started(self, event_loop: urwid.EventLoop | None = None) -> tuple[urwid.MainLoop, urwid.SelectEventLoop]:
        """Return a started loop over a mock screen with its select loop, past the draw that start() schedules.

        The loop is stopped at the end of the test.
        """
        event_loop = event_loop if event_loop is not None else urwid.SelectEventLoop()
        loop = external_loop(event_loop=event_loop)
        loop.start()
        self.addCleanup(loop.stop)
        self._settle(typing.cast("urwid.SelectEventLoop", event_loop))
        return loop, typing.cast("urwid.SelectEventLoop", event_loop)

    @staticmethod
    def _settle(event_loop: urwid.SelectEventLoop) -> None:
        """Run *event_loop* until its due alarms ran and it went idle."""
        for _ in range(10):
            if not (event_loop._alarms or event_loop._did_something):
                return
            event_loop._loop()
        msg = "the event loop does not settle"
        raise AssertionError(msg)

    @staticmethod
    def _wake_up_pending(loop: urwid.MainLoop) -> bool:
        """Return whether the socket call_from_thread() wakes *loop* through is readable."""
        state = loop._thread_calls
        return state is not None and bool(select.select([state.reader], [], [], 0)[0])

    def _step(self, loop: urwid.MainLoop, event_loop: urwid.SelectEventLoop) -> None:
        """Run one iteration of *event_loop*, failing instead of waiting when nothing is due or ready."""
        self.assertTrue(
            event_loop._alarms or event_loop._did_something or self._wake_up_pending(loop),
            "the iteration would wait for input",
        )
        event_loop._loop()

    def test_calls_run_in_order_on_the_loop_thread(self) -> None:
        """Calls from a worker thread run in order, with their arguments, on the loop thread with the loop current."""
        seen: list[tuple[object, ...]] = []

        def record(*args: object, **kwargs: object) -> None:
            seen.append((args, kwargs, threading.get_ident(), urwid.get_running_loop_or_none() is loop))

        def work() -> None:
            loop.call_from_thread(record, 1)
            # pylint: disable-next=kwarg-superseded-by-positional-arg  # a keyword of the callback named like the parameter
            loop.call_from_thread(record, 2, callback="keyword named callback")
            loop.call_from_thread(record)
            loop.call_from_thread(stop_screen_cb)

        loop = external_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            loop.set_alarm_in(0, lambda *_args: executor.submit(work))
            loop.set_alarm_in(1, stop_screen_cb)
            loop.run()

        loop_thread = threading.get_ident()
        self.assertEqual(
            [
                ((1,), {}, loop_thread, True),
                ((2,), {"callback": "keyword named callback"}, loop_thread, True),
                ((), {}, loop_thread, True),
            ],
            seen,
        )

    def test_burst_of_calls_runs_in_order(self) -> None:
        """A thousand calls from a worker all run, in the order they were made."""
        seen: list[int] = []

        def work() -> None:
            for number in range(1000):
                loop.call_from_thread(seen.append, number)
            loop.call_from_thread(stop_screen_cb)

        loop = external_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            loop.set_alarm_in(0, lambda *_args: executor.submit(work))
            loop.set_alarm_in(5, stop_screen_cb)
            loop.run()

        self.assertEqual(list(range(1000)), seen)

    def test_call_on_the_loop_thread_is_deferred(self) -> None:
        """A call made on the loop thread runs after the code that made it returned."""
        seen: list[str] = []

        def alarm(_loop: urwid.MainLoop, _data: object) -> None:
            loop.call_from_thread(seen.append, "call")
            seen.append("alarm end")

        loop, event_loop = self._started()
        loop.set_alarm_in(0, alarm)
        self._settle(event_loop)

        self.assertEqual(["alarm end", "call"], seen)

    def test_rejects_an_async_callback(self) -> None:
        """An ``async def`` callback, which nothing would await, is refused."""

        async def callback() -> None:
            pass

        loop, _event_loop = self._started()
        with self.assertRaises(TypeError):
            loop.call_from_thread(callback)
        self.assertEqual(0, len(typing.cast("main_loop_module._ThreadCalls", loop._thread_calls).calls))

    def test_calls_after_an_exit_get_a_wake_up(self) -> None:
        """Calls queued behind one that raised ExitMainLoop run on the next pass, for an event loop that goes on."""
        seen: list[str] = []
        loop, event_loop = self._started()
        loop.call_from_thread(stop_screen_cb)
        loop.call_from_thread(seen.append, "after the exit")
        with self.assertRaises(urwid.ExitMainLoop):
            self._step(loop, event_loop)
        self.assertEqual([], seen)

        self._step(loop, event_loop)
        self.assertEqual(["after the exit"], seen)

    def test_raises_when_the_loop_is_not_running(self) -> None:
        """Before the loop starts and after it stopped, a call raises and nothing is queued."""
        loop = external_loop()
        with self.assertRaises(RuntimeError):
            loop.call_from_thread(print)

        loop.set_alarm_in(0, stop_screen_cb)
        loop.run()
        with self.assertRaises(RuntimeError):
            loop.call_from_thread(print)

    def test_descriptors_are_released_when_the_run_ends(self) -> None:
        """Both ends of the wake-up socket pair are closed once the run ended and nothing holds its state."""
        states: list[main_loop_module._ThreadCalls | None] = []
        loop = external_loop()
        loop.set_alarm_in(0, lambda *_args: states.append(loop._thread_calls))
        loop.set_alarm_in(0, stop_screen_cb)
        loop.run()

        state = states.pop()
        assert state is not None
        reader, writer = state.reader, state.writer
        del state
        gc.collect()
        self.assertEqual((-1, -1), (reader.fileno(), writer.fileno()))

    def test_raising_callback_is_logged_and_the_next_call_runs(self) -> None:
        """A call that raises is logged, the calls after it still run, and the running loops are as they were."""
        seen: list[str] = []

        def fail() -> typing.NoReturn:
            raise ValueError

        loop, event_loop = self._started()
        before = main_loop_module._running.get()
        loop.call_from_thread(fail)
        loop.call_from_thread(seen.append, "next")
        with self.assertLogs(loop.logger, "ERROR"):
            self._step(loop, event_loop)

        self.assertEqual(["next"], seen)
        self.assertIs(before, main_loop_module._running.get())
        self.assertIsNotNone(loop._thread_calls)

    def test_full_wake_up_buffer_does_not_fail_the_call(self) -> None:
        """A call made while the wake-up socket is full is queued, and runs."""
        seen: list[str] = []
        loop, event_loop = self._started()
        state = loop._thread_calls
        assert state is not None
        with contextlib.suppress(BlockingIOError):
            for _ in range(100_000):
                state.writer.send(b"x" * 4096)

        loop.call_from_thread(seen.append, "call")
        self._step(loop, event_loop)

        self.assertEqual(["call"], seen)

    def test_pass_is_bounded_and_wakes_the_loop_for_the_rest(self) -> None:
        """One pass runs a bounded number of calls, wakes the loop for the rest, and passes in a row draw between."""
        per_pass = main_loop_module._THREAD_CALLS_PER_PASS
        seen: list[int] = []
        loop, event_loop = self._started()
        draw_screen = typing.cast("unittest.mock.Mock", loop.screen).draw_screen
        for number in range(3 * per_pass):
            loop.call_from_thread(seen.append, number)

        self._step(loop, event_loop)
        self.assertEqual(list(range(per_pass)), seen)
        self.assertTrue(self._wake_up_pending(loop))
        self.assertEqual([], event_loop._alarms)

        draws = draw_screen.call_count
        self._step(loop, event_loop)
        self.assertEqual(list(range(2 * per_pass)), seen)
        self.assertGreater(draw_screen.call_count, draws)

        draws = draw_screen.call_count
        self._step(loop, event_loop)
        self.assertEqual(list(range(3 * per_pass)), seen)
        self.assertGreater(draw_screen.call_count, draws)
        self.assertFalse(self._wake_up_pending(loop))

    def test_alarm_and_redraw_are_served_during_a_flood(self) -> None:
        """While calls keep the wake-up socket readable, a due alarm runs and the screen is still drawn."""
        alarms: list[str] = []
        floods: list[None] = []

        def flood() -> None:
            floods.append(None)
            loop.call_from_thread(flood)

        loop, event_loop = self._started()
        draw_screen = typing.cast("unittest.mock.Mock", loop.screen).draw_screen
        draws = draw_screen.call_count
        loop.set_alarm_in(0, lambda *_args: alarms.append("alarm"))
        loop.call_from_thread(flood)

        for _ in range(2):
            self._step(loop, event_loop)
        self.assertEqual(["alarm"], alarms)
        for _ in range(2):
            self._step(loop, event_loop)
        self.assertGreater(draw_screen.call_count, draws)
        # A call queued during a pass runs in that pass while the pass has room: the deque is what a pass reads.
        self.assertEqual(4 * main_loop_module._THREAD_CALLS_PER_PASS, len(floods))

    def test_fallback_loop_reads_input_and_draws_during_a_flood(self) -> None:
        """On a screen without event loop support, input and draws go on while calls keep arriving."""
        processed: list[str] = []
        floods: list[None] = []

        class CountingScreen(LimitedInputScreen):
            """Scripted screen counting its draws."""

            draws = 0

            def draw_screen(self, size: tuple[int, int], canvas: typing.Any) -> None:
                CountingScreen.draws += 1

        def flood() -> None:
            floods.append(None)
            loop.call_from_thread(flood)

        def unhandled(key: str | tuple[str, int, int, int]) -> typing.NoReturn:
            processed.append(typing.cast("str", key))
            raise urwid.ExitMainLoop

        screen = CountingScreen([([], []), ([], []), ([], []), (["x"], [])])
        loop = urwid.MainLoop(
            urwid.SolidFill(),
            screen=screen,
            handle_mouse=False,
            unhandled_input=unhandled,
            poll_interval=0.1,
        )
        loop.set_alarm_in(0, lambda *_args: loop.call_from_thread(flood))
        loop.run()

        self.assertEqual(["x"], processed)
        self.assertEqual(4, screen.input_calls)
        self.assertEqual(4, CountingScreen.draws)
        self.assertEqual(3 * main_loop_module._THREAD_CALLS_PER_PASS, len(floods))

    def test_fallback_loop_runs_a_call_from_a_worker(self) -> None:
        """On a screen without event loop support and a poll interval, a worker's call runs while the loop waits.

        On Windows the loop does not poll, so the screen waits for the call instead of a key.
        """
        seen: list[bool] = []
        posted = threading.Event()

        def done() -> typing.NoReturn:
            seen.append(urwid.get_running_loop_or_none() is loop)
            raise urwid.ExitMainLoop

        def post() -> None:
            loop.call_from_thread(done)
            posted.set()

        class WaitingScreen(LimitedInputScreen):
            """Scripted screen that waits out its input timeout, as a terminal does."""

            def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
                if (timeout := self.timeouts[-1]) is None:
                    # a key ends an endless wait; the test sends none, so the posted call stands in for one
                    if not posted.wait(5):
                        raise AssertionError("the worker never posted its call")
                    # on Windows the wake-up socket pair is TCP loopback, which can deliver after send() returns
                    time.sleep(0.05)
                else:
                    time.sleep(timeout)
                return super().get_input(raw_keys)

        screen = WaitingScreen([])
        loop = urwid.MainLoop(urwid.SolidFill(), screen=screen, handle_mouse=False, poll_interval=0.1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            loop.set_alarm_in(0, lambda *_args: executor.submit(post))
            loop.run()

        self.assertEqual([True], seen)
        self.assertIsNone(loop._thread_calls)
        self.assertEqual(not main_loop_module.IS_WINDOWS, 0.1 in screen.timeouts)

    def test_stop_from_a_call_drops_the_calls_after_it(self) -> None:
        """A call that stops the loop ends the pass, and the calls queued after it never run, also after a restart."""
        seen: list[str] = []
        loop, event_loop = self._started()
        loop.call_from_thread(seen.append, "first")
        loop.call_from_thread(loop.stop)
        loop.call_from_thread(seen.append, "third")
        self._step(loop, event_loop)
        self.assertEqual(["first"], seen)
        self.assertIsNone(loop._thread_calls)

        loop.start()
        self._settle(event_loop)
        self.assertFalse(self._wake_up_pending(loop))
        self.assertEqual(["first"], seen)

    def test_sender_racing_a_restart_reaches_no_later_run(self) -> None:
        """A call that read the state before stop() and queues after the next start() raises and never runs."""
        seen: list[str] = []
        outcome: list[BaseException | None] = []
        captured = threading.Event()
        go = threading.Event()

        class PausingDeque(collections.deque):
            """Deque whose append() waits until the test lets it go on."""

            def append(self, x: typing.Any, /) -> None:
                captured.set()
                go.wait(5)
                super().append(x)

        def send() -> None:
            try:
                loop.call_from_thread(seen.append, "late")
            except RuntimeError as exc:
                outcome.append(exc)
            else:
                outcome.append(None)

        loop, event_loop = self._started()
        state = loop._thread_calls
        assert state is not None
        state.calls = PausingDeque()
        worker = threading.Thread(target=send)
        worker.start()
        self.assertTrue(captured.wait(5))
        loop.stop()
        loop.start()
        go.set()
        worker.join(5)

        self.assertEqual(1, len(outcome))
        self.assertIsInstance(outcome[0], RuntimeError)
        self._settle(event_loop)
        self.assertFalse(self._wake_up_pending(loop))
        self.assertEqual([], seen)

    def test_nested_run_from_a_call_ends_the_outer_calls(self) -> None:
        """A call that runs the same loop again ends cleanly, and its inner stop() ends the calls of the outer run."""
        seen: list[str] = []
        loop, event_loop = self._started()

        def nested() -> None:
            loop.set_alarm_in(0, stop_screen_cb)
            loop.run()
            seen.append("nested run returned")

        loop.call_from_thread(nested)
        loop.call_from_thread(seen.append, "after nested")
        self._step(loop, event_loop)

        self.assertEqual(["nested run returned"], seen)
        with self.assertRaises(RuntimeError):
            loop.call_from_thread(print)

    def test_failed_watch_leaves_no_socket_open(self) -> None:
        """A start() whose event loop refuses the wake-up watch closes both ends of the socket pair."""
        pairs: list[tuple[socket.socket, socket.socket]] = []
        real_socketpair = socket.socketpair

        def recording_socketpair() -> tuple[socket.socket, socket.socket]:
            pairs.append(real_socketpair())
            return pairs[-1]

        event_loop = unittest.mock.Mock(spec=urwid.SelectEventLoop)
        event_loop.watch_file.side_effect = OSError
        loop = external_loop(event_loop=event_loop)
        with (
            unittest.mock.patch.object(main_loop_module.socket, "socketpair", recording_socketpair),
            self.assertRaises(OSError),
        ):
            loop.run()

        self.assertEqual([(-1, -1)], [(reader.fileno(), writer.fileno()) for reader, writer in pairs])
        event_loop.remove_watch_file.assert_not_called()
        typing.cast("unittest.mock.Mock", loop.screen).stop.assert_called_once_with()

    def test_event_loop_that_cannot_watch_files_runs_without_calls(self) -> None:
        """An event loop without file watches, as asyncio's ProactorEventLoop, runs; a call says why it cannot work."""
        pairs: list[tuple[socket.socket, socket.socket]] = []
        real_socketpair = socket.socketpair

        def recording_socketpair() -> tuple[socket.socket, socket.socket]:
            pairs.append(real_socketpair())
            return pairs[-1]

        event_loop = unittest.mock.Mock(spec=urwid.SelectEventLoop)
        event_loop.watch_file.side_effect = NotImplementedError
        loop = external_loop(event_loop=event_loop)
        with unittest.mock.patch.object(main_loop_module.socket, "socketpair", recording_socketpair):
            loop.start()

        with self.assertRaisesRegex(RuntimeError, "cannot watch files"):
            loop.call_from_thread(print)
        self.assertEqual([(-1, -1)], [(reader.fileno(), writer.fileno()) for reader, writer in pairs])
        loop.stop()
        event_loop.remove_watch_file.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "not running"):
            loop.call_from_thread(print)

    def test_failed_watch_removal_still_drops_the_calls_and_stops(self) -> None:
        """A stop() whose event loop fails to remove the wake-up watch still drops the calls and stops the screen."""
        event_loop = unittest.mock.Mock(spec=urwid.SelectEventLoop)
        event_loop.remove_watch_file.side_effect = OSError
        loop = external_loop(event_loop=event_loop)
        screen = typing.cast("unittest.mock.Mock", loop.screen)
        loop.start()
        state = loop._thread_calls
        assert state is not None
        state.calls.append(print)

        with self.assertRaises(OSError):
            loop.stop()

        self.assertIsNone(loop._thread_calls)
        with self.assertRaises(RuntimeError):
            loop.call_from_thread(print)
        self.assertEqual(0, len(state.calls))
        event_loop.remove_enter_idle.assert_called_once()
        screen.unhook_event_loop.assert_called()
        screen.stop.assert_called_once_with()
        self.assertIsNone(urwid.get_running_loop_or_none())
