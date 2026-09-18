from __future__ import annotations

import concurrent.futures
import contextlib
import doctest
import io
import os
import socket
import sys
import threading
import time
import typing
import unittest.mock

import urwid
from urwid.display.common import BaseScreen
from urwid.event_loop import main_loop as main_loop_module

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


class NonExternalLoopScreen(BaseScreen):
    """Screen with no ``hook_event_loop`` support, forcing :meth:`MainLoop._run_screen_event_loop`."""

    def __init__(self, cols_rows: tuple[int, int] = (10, 5)) -> None:
        super().__init__()
        self._cols_rows = cols_rows
        self.input_calls = 0

    def get_cols_rows(self) -> tuple[int, int]:
        return self._cols_rows

    def draw_screen(self, size: tuple[int, int], canvas: typing.Any) -> None:
        pass

    def get_input(self, raw_keys: bool = False) -> tuple[list[typing.Any], list[int]]:
        self.input_calls += 1
        return [], []

    def set_input_timeouts(self, max_wait: float | None = None) -> None:
        pass


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
        self.mouse_calls: list[tuple[str, int, int, int]] = []

    def selectable(self) -> bool:
        return self._selectable

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        self.keypress_calls.append(key)
        return self._keypress_return

    def mouse_event(self, size: tuple[int, int], event: str, button: int, col: int, row: int, focus: bool) -> bool:
        self.mouse_calls.append((event, button, col, row))
        return self._mouse_return


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
    def test_remove_watch_pipe_missing_fd(self):
        """Removing a watch pipe that was never created returns False."""
        with dummy_raw_main_loop() as evl:
            self.assertFalse(evl.remove_watch_pipe(999999))

    @unittest.skipIf(IS_WINDOWS, "selectors for pipe are not supported on Windows")
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

    def test_run_screen_event_loop_clears_next_alarm_when_queue_empty(self):
        """_run_screen_event_loop resets next_alarm to None once the alarm queue drains."""
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

    def test_run_reraises_unexpected_event_loop_error(self):
        """run() stops the screen and lets an unexpected event loop error propagate."""
        with dummy_raw_main_loop() as evl:
            with unittest.mock.patch.object(evl.event_loop, "run", side_effect=RuntimeError("boom")):
                self.assertRaises(RuntimeError, evl.run)
            self.assertFalse(evl.screen.started)

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
