from __future__ import annotations

import asyncio
import concurrent.futures
import errno
import gc
import selectors
import signal
import socket
import sys
import time
import typing
import unittest
from unittest import mock

import urwid
from tests.util import TtyRefusingSelector

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future
    from types import TracebackType

try:
    import gi.repository
except ImportError:
    GLIB_AVAILABLE = False
else:
    GLIB_AVAILABLE = True

try:
    import tornado
except ImportError:
    TORNADO_AVAILABLE = False
else:
    TORNADO_AVAILABLE = True

try:
    import twisted
except ImportError:
    TWISTED_AVAILABLE = False
else:
    TWISTED_AVAILABLE = True

try:
    import trio
except ImportError:
    TRIO_AVAILABLE = False
else:
    TRIO_AVAILABLE = True

try:
    import zmq
except ImportError:
    ZMQ_AVAILABLE = False
else:
    ZMQ_AVAILABLE = True

IS_WINDOWS = sys.platform == "win32"


class ClosingSocketPair(typing.ContextManager[tuple[socket.socket, socket.socket]]):
    __slots__ = ("rd_s", "wr_s")

    def __init__(self) -> None:
        self.rd_s: socket.socket | None = None
        self.wr_s: socket.socket | None = None

    def __enter__(self) -> tuple[socket.socket, socket.socket]:
        self.rd_s, self.wr_s = socket.socketpair()
        return self.rd_s, self.wr_s

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.rd_s is not None:
            self.rd_s.close()
        if self.wr_s is not None:
            self.wr_s.close()


class EventLoopTestMixin:
    evl: urwid.EventLoop

    def _exit_once_seen(self, out: list[str], exit_clean: Callable[[], typing.NoReturn], *expected: str) -> None:
        """Call *exit_clean* from an alarm once every string in *expected* is in *out*.

        Work the test waits for can finish after any fixed delay on a loaded machine, and alarms that are due
        together run in one pass, so a loop started late can stop before it was ever idle. The check repeats on
        a short alarm and calls *exit_clean* anyway after a generous deadline, so work that never happens fails
        the test instead of hanging it.
        """
        deadline = time.monotonic() + 10

        def exit_once_seen() -> None:
            if not set(expected).issubset(out) and time.monotonic() < deadline:
                self.evl.alarm(0.005, exit_once_seen)
                return
            exit_clean()

        self.evl.alarm(0.01, exit_once_seen)

    def test_event_loop(self):
        evl: urwid.EventLoop = self.evl
        out = []
        rd: socket.socket
        wr: socket.socket

        def step1():
            out.append("writing")
            wr.send(b"hi")

        def step2():
            out.append(rd.recv(2).decode("ascii"))
            raise urwid.ExitMainLoop

        with ClosingSocketPair() as (rd, wr):
            _handle = evl.alarm(0, step1)
            _handle = evl.watch_file(rd.fileno(), step2)

            evl.run()

        self.assertEqual(out, ["writing", "hi"])

    def test_remove_alarm(self):
        evl: urwid.EventLoop = self.evl
        handle = evl.alarm(50, lambda: None)

        def step1():
            self.assertTrue(evl.remove_alarm(handle))
            self.assertFalse(evl.remove_alarm(handle))
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()

    def test_remove_watch_file(self):
        evl: urwid.EventLoop = self.evl

        with ClosingSocketPair() as (rd, _wr):
            handle = evl.watch_file(rd.fileno(), lambda: None)

            def step1():
                self.assertTrue(evl.remove_watch_file(handle))
                self.assertFalse(evl.remove_watch_file(handle))
                raise urwid.ExitMainLoop

            evl.alarm(0, step1)
            evl.run()

    def test_remove_enter_idle(self):
        evl: urwid.EventLoop = self.evl
        out: list[str] = []

        handle = evl.enter_idle(lambda: out.append("idle"))
        self.assertTrue(evl.remove_enter_idle(handle))
        self.assertFalse(evl.remove_enter_idle(handle))

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.alarm(0.01, exit_clean)
        evl.run()
        self.assertEqual([], out)

    def test_alarm_reschedule(self):
        """Reschedule a short alarm until work completes, then exit the loop."""
        evl: urwid.EventLoop = self.evl
        ticks: list[int] = []
        remaining = 3

        def tick() -> None:
            nonlocal remaining
            remaining -= 1
            ticks.append(remaining)
            if remaining:
                evl.alarm(0.01, tick)
            else:
                raise urwid.ExitMainLoop

        evl.alarm(0.01, tick)
        evl.run()
        self.assertEqual([2, 1, 0], ticks)

    def test_idle_callback_exit_main_loop_stops_the_loop(self) -> None:
        """ExitMainLoop raised by an idle callback stops the loop cleanly, as from an alarm callback."""
        evl = self.evl
        out: list[str] = []

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def guard_exit() -> typing.NoReturn:
            out.append("guard exit")
            raise urwid.ExitMainLoop

        evl.enter_idle(exit_clean)
        self._exit_once_seen(out, guard_exit, "clean exit")
        evl.run()
        self.assertEqual(["clean exit"], out)

    def test_idle_callback_may_change_the_idle_callbacks(self) -> None:
        """An idle callback that removes itself and adds another does not break the loop."""
        evl = self.evl
        out: list[str] = []
        handles: list[int] = []

        def once() -> None:
            out.append("once")
            evl.remove_enter_idle(handles[0])
            handles.append(evl.enter_idle(lambda: out.append("waiting")))

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        handles.append(evl.enter_idle(once))
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()
        self.assertEqual("once", out[0])
        self.assertIn("waiting", out)
        self.assertEqual("clean exit", out[-1])

    def test_idle_callback_error_is_raised_from_run(self) -> None:
        """An exception raised by an idle callback stops the loop and is raised from run()."""
        evl = self.evl
        out: list[str] = []

        def exit_error() -> typing.NoReturn:
            out.append("error")
            raise ZeroDivisionError

        def guard_exit() -> typing.NoReturn:
            out.append("guard exit")
            raise urwid.ExitMainLoop

        evl.enter_idle(exit_error)
        self._exit_once_seen(out, guard_exit, "error")
        self.assertRaises(ZeroDivisionError, evl.run)
        self.assertEqual(["error"], out)

    def test_alarm_set_by_idle_callback_runs_on_time(self) -> None:
        """An alarm set by an idle callback fires when due, without waiting for another event."""
        evl = self.evl
        out: list[str] = []

        def set_exit_alarm() -> None:
            # Set once the loop has nothing due before the guard alarm.
            if "ready" in out and "alarm set" not in out:
                out.append("alarm set")
                evl.alarm(0.01, exit_clean)

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def guard_exit() -> typing.NoReturn:
            out.append("guard exit")
            raise urwid.ExitMainLoop

        evl.enter_idle(set_exit_alarm)
        evl.alarm(0.005, lambda: out.append("ready"))
        evl.alarm(5, guard_exit)
        evl.run()
        self.assertEqual(["ready", "alarm set", "clean exit"], out)

    def test_idle_callback_setting_an_alarm_does_not_repeat_idle(self) -> None:
        """An idle callback that sets an alarm on each pass does not cause another idle pass by that alone."""
        evl = self.evl
        idle_passes: list[None] = []

        def set_alarm() -> None:
            idle_passes.append(None)
            evl.alarm(10, lambda: None)

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(set_alarm)
        evl.alarm(0.2, exit_clean)
        evl.run()
        self.assertLess(len(idle_passes), 10)

    def test_remove_alarm_after_it_fired(self) -> None:
        """Removing an alarm that has already fired reports that it was not pending."""
        evl = self.evl
        out: list[bool] = []
        fired = evl.alarm(0, lambda: None)

        def check() -> typing.NoReturn:
            out.append(evl.remove_alarm(fired))
            raise urwid.ExitMainLoop

        evl.alarm(0.01, check)
        evl.run()
        self.assertEqual([False], out)

    def test_watch_file_twice_replaces_the_watch(self) -> None:
        """A second watch on one descriptor replaces the first one."""
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):

            def first() -> None:
                out.append("first")

            def second() -> typing.NoReturn:
                out.append(rd.recv(2).decode("ascii"))
                raise urwid.ExitMainLoop

            def guard_exit() -> typing.NoReturn:
                out.append("guard exit")
                raise urwid.ExitMainLoop

            evl.watch_file(rd.fileno(), first)
            handle = evl.watch_file(rd.fileno(), second)
            evl.alarm(5, guard_exit)
            wr.send(b"hi")
            evl.run()
            evl.remove_watch_file(handle)

        self.assertEqual(["hi"], out)

    _expected_idle_handle = 1

    def test_run(self):
        evl: urwid.EventLoop = self.evl
        out = []
        wr: socket.socket
        rd: socket.socket

        def say_hello():
            out.append("hello")

        def say_waiting():
            out.append("waiting")

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def exit_error() -> typing.NoReturn:
            1 / 0

        with ClosingSocketPair() as (rd, wr):
            self.assertEqual(wr.send(b"data"), 4)

            self._exit_once_seen(out, exit_clean, "waiting", "hello")
            _handle = evl.alarm(0.005, say_hello)
            idle_handle = evl.enter_idle(say_waiting)
            if self._expected_idle_handle is not None:
                self.assertEqual(idle_handle, 1)

            evl.run()
            self.assertTrue("waiting" in out, out)
            self.assertTrue("hello" in out, out)
            self.assertTrue("clean exit" in out, out)
            handle = evl.watch_file(rd.fileno(), exit_clean)
            del out[:]

            evl.run()
            self.assertEqual(["clean exit"], out)
            self.assertTrue(evl.remove_watch_file(handle))
            _handle = evl.alarm(0, exit_error)
            self.assertRaises(ZeroDivisionError, evl.run)
            _handle = evl.watch_file(rd.fileno(), exit_error)
            self.assertRaises(ZeroDivisionError, evl.run)

    def test_run_in_executor(self):
        out: list[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:

            def start():
                out.append("started")
                self.evl.run_in_executor(executor, func).add_done_callback(callback)

            def func() -> bool:
                out.append("future called")
                return True

            def callback(fut: Future) -> None:
                out.append(f"callback called with future outcome: {fut.result()}")

            def exit_clean() -> typing.NoReturn:
                out.append("clean exit")
                raise urwid.ExitMainLoop

            self._exit_once_seen(out, exit_clean, "callback called with future outcome: True")
            _handle = self.evl.alarm(0.005, start)
            self.evl.run()

        self.assertEqual(
            [
                "started",
                "future called",
                "callback called with future outcome: True",
                "clean exit",
            ],
            out,
        )


class StaleReadyWatchTestMixin:
    """Descriptors reported ready together, where an earlier callback changes the watch of a later one."""

    def _poll_once(self) -> None:
        """Run one iteration of the loop."""
        raise NotImplementedError

    def test_watch_removed_by_earlier_callback_is_skipped(self):
        """A descriptor that was ready but lost its watch earlier in the same pass is not called back."""
        evl = self.evl
        called = []
        with ClosingSocketPair() as (rd_1, wr_1), ClosingSocketPair() as (rd_2, wr_2):

            def first() -> None:
                called.append("first")
                evl.remove_watch_file(rd_2.fileno())

            def second() -> None:
                called.append("second")
                evl.remove_watch_file(rd_1.fileno())

            evl.watch_file(rd_1.fileno(), first)
            evl.watch_file(rd_2.fileno(), second)
            wr_1.send(b"x")
            wr_2.send(b"x")

            self._poll_once()

        # Both descriptors were ready; whichever callback ran first removed the other one's watch.
        self.assertEqual(1, len(called))

    def test_watch_replaced_by_earlier_callback_is_skipped(self):
        """A watch replaced earlier in the same pass is not called with the readiness seen for the old one."""
        evl = self.evl
        called = []
        with ClosingSocketPair() as (rd_1, wr_1), ClosingSocketPair() as (rd_2, wr_2):

            def replacement() -> None:
                called.append("replacement")

            def first() -> None:
                called.append("first")
                evl.remove_watch_file(rd_2.fileno())
                evl.watch_file(rd_2.fileno(), replacement)

            def second() -> None:
                called.append("second")
                evl.remove_watch_file(rd_1.fileno())
                evl.watch_file(rd_1.fileno(), replacement)

            evl.watch_file(rd_1.fileno(), first)
            evl.watch_file(rd_2.fileno(), second)
            wr_1.send(b"x")
            wr_2.send(b"x")

            self._poll_once()

        self.assertEqual(1, len(called))
        self.assertNotIn("replacement", called)


class AlarmFairnessTestMixin:
    def test_alarm_ignores_a_wall_clock_step(self):
        """An alarm does not run early when the wall clock is set forward after it was scheduled."""
        called = []
        self.evl._did_something = True  # pylint: disable=protected-access  # poll without waiting for the alarm
        self.evl.alarm(10, lambda: called.append("alarm"))
        with mock.patch("time.time", return_value=time.time() + 3600):
            self._poll_once()

        self.assertEqual([], called)

    def test_expired_alarm_runs_while_a_descriptor_stays_readable(self):
        """A due alarm runs in the first poll even if input remains readable."""
        called = []
        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: called.append("ready"))
            wr.send(b"x")
            self.evl.alarm(0, lambda: called.append("alarm"))

            self._poll_once()

        self.assertEqual(["ready", "alarm"], called)

    def test_future_alarm_waits_while_a_descriptor_is_readable(self):
        """Readable input does not fire an alarm before its deadline."""
        called = []
        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: called.append("ready"))
            wr.send(b"x")
            self.evl.alarm(60, lambda: called.append("alarm"))

            self._poll_once()

        self.assertEqual(["ready"], called)

    def test_ready_callback_can_cancel_an_expired_alarm(self):
        """Use the current alarm heap after an input callback cancels an alarm."""
        called = []
        handle = self.evl.alarm(0, lambda: called.append("cancelled"))
        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: self.evl.remove_alarm(handle))
            wr.send(b"x")

            self._poll_once()

        self.assertEqual([], called)
        self.assertFalse(self.evl.remove_alarm(handle))

    def test_only_one_expired_alarm_runs_per_poll_with_readable_input(self):
        """Keep input processing between callbacks when several alarms are due."""
        called = []
        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: called.append("ready"))
            wr.send(b"x")
            self.evl.alarm(0, lambda: called.append("first"))
            self.evl.alarm(0, lambda: called.append("second"))

            self._poll_once()
            self.assertEqual(["ready", "first"], called)
            self._poll_once()

        self.assertEqual(["ready", "first", "ready", "second"], called)


class MainLoopPausedTestMixin:
    """MainLoop.paused() run on the event loop of the test case."""

    evl: urwid.EventLoop

    def _paused_event_loop(self) -> urwid.EventLoop:
        """Return the event loop to run a :class:`urwid.MainLoop` on."""
        return self.evl

    def test_main_loop_paused_watches_the_input_again(self) -> None:
        """Input written while MainLoop.paused() runs is read from the restarted screen once the block ends."""
        out: list[tuple[str, bool]] = []
        rd: socket.socket
        wr: socket.socket

        def pause() -> None:
            with loop.paused():
                out.append(("paused", loop.screen.started))
                wr.send(b"x")

        def give_up() -> typing.NoReturn:
            out.append(("timeout", loop.screen.started))
            raise urwid.ExitMainLoop

        def unhandled(key: str | tuple[str, int, int, int]) -> typing.NoReturn:
            out.append((str(key), loop.screen.started))
            raise urwid.ExitMainLoop

        with (
            ClosingSocketPair() as (rd, wr),
            ClosingSocketPair() as (_output_rd, output_wr),
            output_wr.makefile("w", encoding="utf-8") as output,
        ):
            screen = urwid.display.raw.Screen(input=rd, output=output)
            loop = urwid.MainLoop(
                urwid.SolidFill(),
                screen=screen,
                event_loop=self._paused_event_loop(),
                handle_mouse=False,
                unhandled_input=unhandled,
            )
            loop.set_alarm_in(0, lambda *_args: pause())
            loop.set_alarm_in(10, lambda *_args: give_up())
            loop.run()

        self.assertEqual([("paused", False), ("x", True)], out)


class SelectEventLoopTest(
    unittest.TestCase,
    EventLoopTestMixin,
    StaleReadyWatchTestMixin,
    AlarmFairnessTestMixin,
    MainLoopPausedTestMixin,
):
    def setUp(self):
        self.evl = urwid.SelectEventLoop()

    def _poll_once(self) -> None:
        """Run one iteration of the loop."""
        self.evl._loop()

    def test_watch_registered_with_a_file_object_is_called(self):
        """A watch registered with an object that has fileno() is found again when its descriptor is ready."""
        called = []
        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: called.append("ready"))
            wr.send(b"x")

            self._poll_once()

        self.assertEqual(["ready"], called)

    def test_watch_refused_by_the_default_selector_is_called(self):
        """A watch the default selector refuses with EINVAL, as kqueue on macOS refuses /dev/tty, is still called.

        The refused selector is closed, so the fallback on every pass leaks no descriptor.
        """
        called = []
        with (
            ClosingSocketPair() as (rd, wr),
            mock.patch.object(selectors, "DefaultSelector", TtyRefusingSelector),
            mock.patch.object(
                TtyRefusingSelector,
                "close",
                autospec=True,
                side_effect=selectors.SelectSelector.close,
            ) as refused_close,
        ):
            self.evl.watch_file(rd.fileno(), lambda: called.append("ready"))
            wr.send(b"x")

            self._poll_once()

        self.assertEqual(["ready"], called)
        refused_close.assert_called_once()

    def test_watch_refused_with_another_error_is_raised(self):
        """Only EINVAL selects the fallback: any other error from registering a watch propagates."""
        refused = mock.Mock(side_effect=OSError(errno.EBADF, "Bad file descriptor"))
        with ClosingSocketPair() as (rd, _wr), mock.patch.object(selectors.DefaultSelector, "register", refused):
            self.evl.watch_file(rd.fileno(), lambda: None)

            with self.assertRaises(OSError) as ctx:
                self._poll_once()

        self.assertEqual(errno.EBADF, ctx.exception.errno)


@unittest.skipIf(IS_WINDOWS, "Windows is temporary not supported by AsyncioEventLoop.")
class AsyncioEventLoopTest(unittest.TestCase, EventLoopTestMixin, MainLoopPausedTestMixin):
    def setUp(self):
        self.evl_runner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        self.loop = self.evl_runner.get_loop()
        self.evl = urwid.AsyncioEventLoop(loop=self.loop)

    def tearDown(self):
        self.evl_runner.close()

    _expected_idle_handle = None

    def test_finalizer_tolerates_an_already_closed_owned_loop(self):
        """The finalizer does not fail when the owned loop was closed first, as a cycle collection can do."""
        evl = urwid.AsyncioEventLoop()
        # The loop's own finalizer closes it when it runs first; no public API exposes the owned loop.
        evl._loop.close()  # pylint: disable=protected-access
        # A direct call fixes the finalizer order a cycle collection is free to pick.
        evl.__del__()  # pylint: disable=unnecessary-dunder-call

    def test_finalizer_tolerates_a_failed_loop_creation(self):
        """The finalizer of an instance whose loop could not be created reports nothing."""
        with (
            mock.patch.object(asyncio, "SelectorEventLoop", side_effect=OSError(errno.EMFILE, "Too many open files")),
            mock.patch.object(sys, "unraisablehook") as unraisablehook,
        ):
            with self.assertRaises(OSError):
                urwid.AsyncioEventLoop()
            gc.collect()

        unraisablehook.assert_not_called()

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    def test_run_restores_the_previous_exception_handler(self):
        """After run() returns or raises, the loop's own exception handler is back in place."""

        def previous_handler(_loop: asyncio.AbstractEventLoop, _context: dict[str, typing.Any]) -> None:
            """Stand in for an exception handler the application installed."""

        def stop() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        self.loop.set_exception_handler(previous_handler)
        self.addCleanup(self.loop.set_exception_handler, None)
        self.evl.alarm(0, stop)
        self.evl.run()
        self.assertIs(previous_handler, self.loop.get_exception_handler())

        self.evl.alarm(0, lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            self.evl.run()
        self.assertIs(previous_handler, self.loop.get_exception_handler())

    @unittest.skipIf(
        sys.implementation.name in ("pypy", "graalpy"),
        "Relies on CPython's refcounting GC to promptly finalize the task and trigger "
        "asyncio's 'Task exception was never retrieved' handler; PyPy and GraalPy use a "
        "tracing GC, so that finalizer may never run before the process exits and evl.run() "
        "hangs forever.",
    )
    def test_coroutine_error(self):
        evl = self.evl

        async def error_coro():
            result = 1 / 0  # Simulate error in coroutine
            return result

        asyncio.ensure_future(error_coro(), loop=self.loop)
        self.assertRaises(ZeroDivisionError, evl.run)

    def test_async_alarm_callback(self):
        evl = self.evl
        out: list[str] = []

        async def step1() -> typing.NoReturn:
            out.append("async alarm")
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()
        self.assertEqual(["async alarm"], out)

    # test_event_loop() and test_run() (EventLoopTestMixin) watch a pipe and close it as part of
    # the test body; on GraalPy, tearDown()'s evl_runner.close() -> shutdown_asyncgens() then
    # tries to select() on that already-closed fd and raises "OSError: [Errno 9] Bad file
    # descriptor" -- after the test body itself has already passed. This is GraalPy's asyncio
    # SelectorEventLoop failing to deregister a closed fd during Runner shutdown, not an urwid
    # issue, so the test as a whole is skipped rather than weakening the assertions to work around
    # a teardown-only failure.
    _skip_graalpy_runner_close = unittest.skipIf(
        sys.implementation.name == "graalpy",
        "GraalPy's asyncio.Runner.close() raises OSError: Bad file descriptor tearing down a closed watched pipe",
    )

    @_skip_graalpy_runner_close
    def test_event_loop(self):
        super().test_event_loop()

    @_skip_graalpy_runner_close
    def test_run(self):
        super().test_run()

    def test_async_watch_file_callback(self):
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):
            # Non-blocking: the fd stays readable for one extra event loop
            # tick after the async callback is scheduled, so it may fire
            # again with no data left to read.
            rd.setblocking(False)

            async def step2() -> None:
                try:
                    data = rd.recv(2)
                except BlockingIOError:
                    return
                out.append(data.decode("ascii"))
                raise urwid.ExitMainLoop

            evl.watch_file(rd.fileno(), step2)
            wr.send(b"hi")
            evl.run()
            # De-register before the fd is closed and its number possibly reused by a later test.
            evl.remove_watch_file(rd.fileno())

        self.assertEqual(["hi"], out)

    def test_async_enter_idle_callback(self):
        evl = self.evl
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def say_hello() -> None:
            out.append("hello")

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(say_waiting)
        evl.alarm(0.005, say_hello)
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()
        self.assertIn("waiting", out)

    @unittest.skipIf(
        sys.implementation.name == "pypy",
        "Well known dead wait (lock?) on pypy.",
    )
    def test_async_alarm_callback_error(self):
        evl = self.evl

        async def error_coro() -> typing.NoReturn:
            1 / 0  # Simulate error in coroutine

        evl.alarm(0, error_coro)
        self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skip("Unstable test: race conditions happens")
@unittest.skipUnless(GLIB_AVAILABLE, "GLIB unavailable")
class GLibEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.GLibEventLoop()

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skipUnless(GLIB_AVAILABLE, "GLIB unavailable")
class GLibWithoutRunningLoopTest(unittest.TestCase):
    """Idle callback and watch handling, exercised without running the GLib main loop."""

    # pylint: disable=protected-access  # the loop's state is read and driven directly instead of by a running loop

    def setUp(self) -> None:
        """Create the event loop under test."""
        self.evl = urwid.GLibEventLoop()

    def test_idle_callback_may_change_the_idle_callbacks(self) -> None:
        """An idle callback that removes itself and adds another does not break the idle pass."""
        evl = self.evl
        out: list[str] = []
        handles: list[int] = []

        def once() -> None:
            out.append("once")
            evl.remove_enter_idle(handles[0])
            handles.append(evl.enter_idle(lambda: out.append("waiting")))

        handles.append(evl.enter_idle(once))
        evl._glib_idle_callback()
        evl._glib_idle_callback()
        self.assertEqual(["once", "waiting"], out)

    def test_watch_file_twice_replaces_the_watch(self) -> None:
        """A second watch on one descriptor removes the first watch's GLib source."""
        from gi.repository import GLib

        with ClosingSocketPair() as (rd, _wr):
            self.evl.watch_file(rd.fileno(), lambda: None)
            first_source = self.evl._watch_files[rd.fileno()]
            handle = self.evl.watch_file(rd.fileno(), lambda: None)
            try:
                self.assertIsNone(GLib.MainContext.default().find_source_by_id(first_source))
            finally:
                self.evl.remove_watch_file(handle)

    def test_idle_callback_error_keeps_idle_scheduling(self) -> None:
        """An idle callback that raises does not leave idle scheduling switched off."""
        evl = self.evl
        evl.enter_idle(lambda: 1 / 0)
        self.assertRaises(ZeroDivisionError, evl._glib_idle_callback)
        self.assertFalse(evl._glib_idle_enabled)


@unittest.skipUnless(GLIB_AVAILABLE, "GLIB unavailable")
@unittest.skipIf(IS_WINDOWS, "GLib.unix_signal_add is POSIX-only")
class GLibSignalHandlerTest(unittest.TestCase):
    def test_invalid_handler_is_rejected_and_keeps_the_previous_one(self) -> None:
        """Reject a handler that is neither callable nor SIG_IGN/SIG_DFL at once, as `signal.signal()` does."""
        evl = urwid.GLibEventLoop()
        evl.set_signal_handler(signal.SIGUSR1, signal.SIG_IGN)
        self.addCleanup(evl.set_signal_handler, signal.SIGUSR1, signal.SIG_DFL)
        source = evl._signal_handlers[signal.SIGUSR1]

        with self.assertRaises(TypeError):
            evl.set_signal_handler(signal.SIGUSR1, 5)

        self.assertEqual(source, evl._signal_handlers[signal.SIGUSR1])


@unittest.skipUnless(TORNADO_AVAILABLE, "Tornado not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TornadoEventLoop due to race conditions.",
)
class TornadoEventLoopTest(unittest.TestCase, EventLoopTestMixin, MainLoopPausedTestMixin):
    def setUp(self):
        from tornado.ioloop import IOLoop

        self.evl = urwid.TornadoEventLoop(IOLoop())

    _expected_idle_handle = None

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    def test_async_alarm_callback(self):
        evl = self.evl
        out: list[str] = []

        async def step1() -> typing.NoReturn:
            out.append("async alarm")
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()
        self.assertEqual(["async alarm"], out)

    def test_async_watch_file_callback(self):
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):
            # Non-blocking: the fd stays readable for one extra event loop
            # tick after the async callback is scheduled, so it may fire
            # again with no data left to read.
            rd.setblocking(False)

            async def step2() -> None:
                try:
                    data = rd.recv(2)
                except BlockingIOError:
                    return
                out.append(data.decode("ascii"))
                raise urwid.ExitMainLoop

            evl.watch_file(rd.fileno(), step2)
            wr.send(b"hi")
            evl.run()
            evl.remove_watch_file(rd.fileno())

        self.assertEqual(["hi"], out)

    def test_async_enter_idle_callback(self):
        evl = self.evl
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def say_hello() -> None:
            out.append("hello")

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(say_waiting)
        evl.alarm(0.005, say_hello)
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()
        self.assertIn("waiting", out)

    def test_async_alarm_callback_error(self):
        evl = self.evl

        async def error_coro() -> typing.NoReturn:
            1 / 0  # Simulate error in coroutine

        evl.alarm(0, error_coro)
        self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skipUnless(TWISTED_AVAILABLE, "Twisted is not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TwistedEventLoop due to race conditions.",
)
class TwistedEventLoopTest(unittest.TestCase, EventLoopTestMixin, MainLoopPausedTestMixin):
    def setUp(self):
        self.evl = urwid.TwistedEventLoop()

    # can't restart twisted reactor, so use shortened tests
    def test_event_loop(self):
        pass

    def test_remove_alarm(self):
        pass

    def test_remove_watch_file(self):
        pass

    def test_remove_enter_idle(self):
        pass

    def test_alarm_reschedule(self):
        pass

    def test_idle_callback_exit_main_loop_stops_the_loop(self) -> None:
        """Skipped: the shared test stops the reactor, which cannot be started again."""

    def test_idle_callback_error_is_raised_from_run(self) -> None:
        """Skipped: the shared test stops the reactor, which cannot be started again."""

    def test_alarm_set_by_idle_callback_runs_on_time(self) -> None:
        """Skipped: the shared test stops the reactor, which cannot be started again."""

    def test_idle_callback_setting_an_alarm_does_not_repeat_idle(self) -> None:
        """Skipped: the shared test stops the reactor, which cannot be started again."""

    def test_remove_alarm_after_it_fired(self) -> None:
        """Skipped: the shared test stops the reactor, which cannot be started again."""

    def _paused_event_loop(self) -> urwid.EventLoop:
        """Return a loop on a reactor of its own: the shared reactor cannot be started again."""
        from twisted.internet.selectreactor import SelectReactor

        reactor = SelectReactor()
        self.addCleanup(reactor.waker.connectionLost, None)
        # reactor.run() points SIGINT and SIGTERM at this reactor and never restores them
        for signum in (signal.SIGINT, signal.SIGTERM):
            self.addCleanup(signal.signal, signum, signal.getsignal(signum))
        return urwid.TwistedEventLoop(reactor=reactor)

    def test_watch_file_twice_replaces_the_watch(self) -> None:
        """A second watch on one descriptor replaces the first one in the reactor."""
        from twisted.internet.selectreactor import SelectReactor

        # The epoll reactor keeps one reader per descriptor by itself; the select reactor keeps every one added.
        reactor = SelectReactor()
        self.addCleanup(reactor.waker.connectionLost, None)
        evl = urwid.TwistedEventLoop(reactor=reactor, manage_reactor=False)
        with ClosingSocketPair() as (rd, _wr):
            evl.watch_file(rd.fileno(), lambda: None)
            handle = evl.watch_file(rd.fileno(), lambda: None)
            try:
                watching = [reader for reader in reactor.getReaders() if reader.fileno() == rd.fileno()]
                self.assertEqual(1, len(watching))
            finally:
                evl.remove_watch_file(handle)

    def test_idle_callback_may_change_the_idle_callbacks(self) -> None:
        """An idle callback that removes itself and adds another does not break idle handling."""
        from twisted.internet.task import Clock

        clock = Clock()
        evl = urwid.TwistedEventLoop(reactor=clock, manage_reactor=False)
        out: list[str] = []
        handles: list[int] = []

        def once() -> None:
            out.append("once")
            evl.remove_enter_idle(handles[0])
            handles.append(evl.enter_idle(lambda: out.append("waiting")))

        handles.append(evl.enter_idle(once))
        with self.assertNoLogs(evl.logger):
            clock.advance(1)
            evl.alarm(0, lambda: None)
            clock.advance(1)
            clock.advance(1)
        self.assertEqual(["once", "waiting"], out)

    def test_idle_callback_error_keeps_idle_callbacks_running(self) -> None:
        """An idle callback that raises is logged and does not stop later idle passes."""
        from twisted.internet.task import Clock

        clock = Clock()
        evl = urwid.TwistedEventLoop(reactor=clock, manage_reactor=False)
        out: list[str] = []

        def fail_once() -> None:
            out.append("idle")
            if len(out) == 1:
                raise ZeroDivisionError

        evl.enter_idle(fail_once)
        with self.assertLogs(evl.logger, "ERROR"):
            clock.advance(1)
        evl.alarm(0, lambda: None)
        clock.advance(1)
        clock.advance(1)
        self.assertEqual(["idle", "idle"], out)

    def test_run(self):
        from twisted.internet import threads

        evl = self.evl
        out = []
        wr: socket.socket
        rd: socket.socket

        def step2() -> str:
            data = rd.recv(2).decode("ascii")
            out.append(data)
            return data  # the watch must stay: Twisted stops watching when the descriptor's doRead() returns this

        def say_hello():
            out.append("hello")

        def say_waiting():
            out.append("waiting")

        def test_remove_alarm():
            handle = evl.alarm(50, lambda: None)
            self.assertTrue(evl.remove_alarm(handle))
            self.assertFalse(evl.remove_alarm(handle))
            out.append("remove_alarm ok")

        def test_remove_watch_file():
            with ClosingSocketPair() as (rd_, _wr):
                handle = evl.watch_file(rd_.fileno(), lambda: None)
                self.assertTrue(evl.remove_watch_file(handle))
                self.assertFalse(evl.remove_watch_file(handle))

            out.append("remove_watch_file ok")

        def test_threaded():
            out.append("schedule to thread")
            threads.deferToThread(func).addCallback(callback)

        def func() -> bool:
            out.append("future called")
            return True

        def callback(result: bool) -> None:
            out.append(f"callback called with future outcome: {result}")

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def exit_error() -> typing.NoReturn:
            1 / 0

        with ClosingSocketPair() as (rd, wr):
            self.assertEqual(wr.send(b"data"), 4)

            _handle = evl.watch_file(rd.fileno(), step2)
            self._exit_once_seen(out, exit_clean, "callback called with future outcome: True")
            _handle = evl.alarm(0.05, say_hello)
            _handle = evl.alarm(0.06, test_remove_alarm)
            _handle = evl.alarm(0.07, test_remove_watch_file)
            _handle = evl.alarm(0.08, test_threaded)
            self.assertEqual(evl.enter_idle(say_waiting), 1)
            evl.run()

        self.assertIn("da", out)
        self.assertIn("ta", out)
        self.assertIn("hello", out)
        self.assertIn("remove_alarm ok", out)
        self.assertIn("clean exit", out)
        self.assertIn("schedule to thread", out)
        self.assertIn("future called", out)
        self.assertIn("callback called with future outcome: True", out)

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    @unittest.skip("not implemented for twisted event loop")
    def test_run_in_executor(self):
        """Not implemented for twisted event loop."""


@unittest.skipUnless(TRIO_AVAILABLE, "Trio not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TrioEventLoop due to race conditions.",
)
class TrioEventLoopTest(unittest.TestCase, EventLoopTestMixin, MainLoopPausedTestMixin):
    def setUp(self):
        self.evl = urwid.TrioEventLoop()

    _expected_idle_handle = None

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    @unittest.skip("not implemented for trio event loop")
    def test_run_in_executor(self):
        """Not implemented for trio event loop."""

    def test_async_alarm_callback(self):
        evl = self.evl
        out: list[str] = []

        async def step1() -> typing.NoReturn:
            out.append("async alarm")
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()
        self.assertEqual(["async alarm"], out)

    def test_async_watch_file_callback(self):
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):
            # Non-blocking: the fd stays readable for one extra event loop
            # tick after the async callback is scheduled, so it may fire
            # again with no data left to read.
            rd.setblocking(False)

            async def step2() -> None:
                try:
                    data = rd.recv(2)
                except BlockingIOError:
                    return
                out.append(data.decode("ascii"))
                raise urwid.ExitMainLoop

            handle = evl.watch_file(rd.fileno(), step2)
            wr.send(b"hi")
            evl.run()
            evl.remove_watch_file(handle)

        self.assertEqual(["hi"], out)

    def test_async_enter_idle_callback(self):
        evl = self.evl
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def say_hello() -> None:
            out.append("hello")

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(say_waiting)
        evl.alarm(0.005, say_hello)
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()
        self.assertIn("waiting", out)

    def test_idle_pass_follows_later_work_of_a_task_an_idle_callback_started(self) -> None:
        """A task started by an idle callback causes an idle pass once it does work after waiting."""
        evl = typing.cast("urwid.TrioEventLoop", self.evl)
        out: list[str] = []

        async def worker() -> None:
            await trio.sleep(0.05)
            out.append("updated")

        def idle() -> None:
            out.append("idle")
            if out == ["idle"]:
                evl._nursery.start_soon(worker)  # pylint: disable=protected-access  # as user code holding it

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(idle)
        # The only other event: an idle pass after "updated" can only come from the worker's own step.
        evl.alarm(0.5, exit_clean)
        evl.run()
        self.assertEqual(["idle", "updated", "idle"], out)

    def _replace_watch_in_one_batch(self) -> list[str]:
        """Make two descriptors ready at once, and replace the second one's watch from the first one's callback.

        :returns: the events in order: "replaced", and "old" or "new" for each call of the second descriptor's watch.
        """
        evl = self.evl = urwid.TrioEventLoop()
        out: list[str] = []
        with ClosingSocketPair() as (rd1, wr1), ClosingSocketPair() as (rd2, wr2):

            def replace() -> None:
                rd1.recv(1)
                if "replaced" not in out:
                    out.append("replaced")
                    evl.watch_file(rd2.fileno(), new)

            def old() -> None:
                out.append("old")
                rd2.recv(1)

            def new() -> None:
                out.append("new")
                rd2.recv(1)

            def exit_clean() -> typing.NoReturn:
                raise urwid.ExitMainLoop

            evl.watch_file(rd1.fileno(), replace)
            evl.watch_file(rd2.fileno(), old)
            wr1.send(b"x")
            wr2.send(b"x")
            self._exit_once_seen(out, exit_clean, "replaced")
            evl.run()
        return out

    def test_replaced_watch_does_not_run_after_replacement(self) -> None:
        """A watch replaced by a callback woken in the same batch does not run its old callback afterwards."""
        # Trio runs the tasks of one batch in random order, so the race is repeated to meet both orders.
        for _ in range(20):
            out = self._replace_watch_in_one_batch()
            self.assertNotIn("old", out[out.index("replaced") :], out)

    def test_job_posted_during_an_idle_pass_causes_an_idle_pass(self) -> None:
        """A run_sync_soon job, as posted from another thread, is work even when the idle pass wakes the loop."""
        evl = typing.cast("urwid.TrioEventLoop", self.evl)
        out: list[str] = []

        async def started_by_idle() -> None:
            await trio.sleep(10)

        def idle() -> None:
            out.append("idle")
            if out == ["idle", "ready", "idle"]:
                trio.lowlevel.current_trio_token().run_sync_soon(out.append, "updated")
                evl._nursery.start_soon(started_by_idle)  # pylint: disable=protected-access  # as user code holding it

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(idle)
        evl.alarm(0.05, lambda: out.append("ready"))
        # The only other event: an idle pass after "updated" can only come from the posted job.
        evl.alarm(0.5, exit_clean)
        evl.run()
        self.assertEqual(["idle", "ready", "idle", "updated", "idle"], out)

    def test_work_started_or_woken_by_idle_callbacks_does_not_repeat_idle(self) -> None:
        """Tasks that idle callbacks start or wake, directly or through other idle work, cause no idle pass."""
        cases: dict[str, Callable[[urwid.TrioEventLoop, list[None]], None]] = {
            "nursery in an async idle callback": self._idle_starts_a_nursery,
            "alarm from an async idle callback": self._idle_sets_an_alarm_from_a_task,
            "task woken by a sync idle callback": self._idle_wakes_a_task,
        }
        for name, set_up in cases.items():
            with self.subTest(name):
                evl = urwid.TrioEventLoop()
                idle_passes: list[None] = []
                set_up(evl, idle_passes)
                evl.alarm(0.2, self._exit_clean)
                evl.run()
                self.assertLess(len(idle_passes), 10)

    def test_embedded_loops_do_not_repeat_each_others_idle(self) -> None:
        """Two loops embedded in one Trio run do not count each other's idle work as work."""
        idle_passes: list[list[None]] = [[], []]
        loops = [urwid.TrioEventLoop(), urwid.TrioEventLoop()]
        for evl, passes in zip(loops, idle_passes, strict=True):
            self._idle_starts_a_nursery(evl, passes)
            evl.alarm(0.2, self._exit_clean)

        async def body() -> None:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(loops[1].run_async)
                await loops[0].run_async()

        trio.run(body)
        self.assertLess(len(idle_passes[0]), 10)
        self.assertLess(len(idle_passes[1]), 10)

    @staticmethod
    def _exit_clean() -> typing.NoReturn:
        raise urwid.ExitMainLoop

    @staticmethod
    def _idle_starts_a_nursery(evl: urwid.TrioEventLoop, idle_passes: list[None]) -> None:
        async def idle() -> None:
            idle_passes.append(None)
            async with trio.open_nursery() as nursery:
                nursery.start_soon(trio.lowlevel.checkpoint)

        evl.enter_idle(idle)

    @staticmethod
    def _idle_sets_an_alarm_from_a_task(evl: urwid.TrioEventLoop, idle_passes: list[None]) -> None:
        async def idle() -> None:
            idle_passes.append(None)
            evl.alarm(10, lambda: None)

        evl.enter_idle(idle)

    @staticmethod
    def _idle_wakes_a_task(evl: urwid.TrioEventLoop, idle_passes: list[None]) -> None:
        events = [trio.Event()]

        async def worker() -> typing.NoReturn:
            while True:
                await events[0].wait()
                events[0] = trio.Event()

        def idle() -> None:
            idle_passes.append(None)
            events[0].set()

        evl.enter_idle(idle)
        evl.alarm(0, worker)

    def test_async_idle_callback_does_not_repeat_idle(self) -> None:
        """An async idle callback runs at once, and its task does not cause another idle pass by that alone."""
        evl = self.evl
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        evl.enter_idle(say_waiting)
        evl.alarm(0.2, exit_clean)
        evl.run()
        self.assertEqual("clean exit", out[-1])
        self.assertLess(out.count("waiting"), 10)

    def test_idle_callbacks_run_only_while_the_nursery_is_open(self) -> None:
        """Idle callbacks, which need the nursery when async, are not run while Trio polls after it closed."""
        evl = typing.cast("urwid.TrioEventLoop", self.evl)
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(lambda: out.append("idle" if evl._nursery else "idle after exit"))
        evl.enter_idle(say_waiting)
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()

        self.assertIn("waiting", out)
        self.assertNotIn("idle after exit", out)

    def test_async_alarm_callback_error(self):
        evl = self.evl

        async def error_coro() -> typing.NoReturn:
            1 / 0  # Simulate error in coroutine

        evl.alarm(0, error_coro)
        self.assertRaises(ZeroDivisionError, evl.run)

    def test_watch_file_callback_self_cancel_exits_cleanly(self):
        # A callback that cancels its own watch (rather than raising ExitMainLoop)
        # has to leave the watching task's loop, not have it call wait_readable
        # again on an fd it just gave up watching.
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):

            def step() -> None:
                out.append(rd.recv(2).decode("ascii"))
                evl.remove_watch_file(handle)

            handle = evl.watch_file(rd.fileno(), step)
            wr.send(b"hi")

            def exit_clean() -> typing.NoReturn:
                raise urwid.ExitMainLoop

            self._exit_once_seen(out, exit_clean, "hi")
            evl.run()

        self.assertEqual(["hi"], out)

    def test_run_async_embeds_in_an_existing_trio_run(self):
        evl = self.evl
        out: list[str] = []

        async def body() -> None:
            async with trio.open_nursery() as nursery:

                def exit_clean() -> typing.NoReturn:
                    out.append("clean exit")
                    raise urwid.ExitMainLoop

                evl.alarm(0.01, exit_clean)
                await evl.run_async()
                nursery.cancel_scope.cancel()

        trio.run(body)
        self.assertEqual(["clean exit"], out)

    def test_run_async_reraises_a_callback_error(self):
        # No outer nursery here (unlike the embedding example above): wrapping the
        # await in one more nursery would let *its* __aexit__ re-wrap the already
        # unwrapped error in a fresh single-exception ExceptionGroup of its own.
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)

        async def body() -> None:
            await evl.run_async()

        self.assertRaises(ZeroDivisionError, trio.run, body)

    def test_multi_exception_group_is_not_unwrapped(self):
        # A single failing task's exception is unwrapped from its ExceptionGroup
        # (see test_error above), but a group of more than one exception has to
        # be raised as-is so neither exception is silently dropped. Triggering
        # two *simultaneous* task failures through evl.run() is inherently racy
        # (trio cancels not-yet-started sibling tasks before they can raise
        # their own exception), so the group is built directly instead.
        evl = self.evl
        group = BaseExceptionGroup("multiple failures", [ZeroDivisionError(), RuntimeError("boom")])

        with self.assertRaises(BaseExceptionGroup) as ctx:
            evl._handle_main_loop_exception(group)
        self.assertIs(group, ctx.exception)


@unittest.skipUnless(ZMQ_AVAILABLE, "ZMQ is not available")
@unittest.skipIf(IS_WINDOWS, "ZMQEventLoop is not supported under windows")
class ZMQEventLoopTest(
    unittest.TestCase,
    EventLoopTestMixin,
    StaleReadyWatchTestMixin,
    AlarmFairnessTestMixin,
    MainLoopPausedTestMixin,
):
    def setUp(self):
        self.evl = urwid.ZMQEventLoop()

    def _poll_once(self) -> None:
        """Run one iteration of the loop."""
        asyncio.run(self.evl._loop())

    def test_fractional_poll_timeout_does_not_busy_spin(self):
        called = []
        self.evl._did_something = False
        with (
            mock.patch("urwid.event_loop.zmq_loop.time.monotonic", return_value=100.0),
            mock.patch.object(self.evl._poller, "poll", new_callable=mock.AsyncMock, return_value=[]) as poll,
        ):
            self.evl.alarm(0.0005, lambda: called.append("alarm"))
            self._poll_once()

        poll.assert_awaited_once_with(1)
        self.assertEqual([], called)

    def test_expired_alarm_runs_while_a_queue_stays_readable(self):
        called = []
        ctx = zmq.Context.instance()
        pull = ctx.socket(zmq.PULL)
        push = ctx.socket(zmq.PUSH)
        try:
            address = f"inproc://{self.id()}"
            pull.bind(address)
            push.connect(address)
            push.send(b"x")
            self.assertTrue(pull.poll(1000, zmq.POLLIN))
            self.evl.watch_queue(pull, lambda: called.append("ready"))
            self.evl.alarm(0, lambda: called.append("alarm"))

            self._poll_once()

            self.assertEqual(["ready", "alarm"], called)
        finally:
            self.evl.remove_watch_queue(pull)
            pull.close(linger=0)
            push.close(linger=0)

    def test_async_expired_alarm_runs_while_a_descriptor_stays_readable(self):
        called = []

        async def on_alarm() -> None:
            called.append("alarm")

        with ClosingSocketPair() as (rd, wr):
            self.evl.watch_file(rd, lambda: called.append("ready"))
            wr.send(b"x")
            self.evl.alarm(0, on_alarm)

            self._poll_once()

        self.assertEqual(["ready", "alarm"], called)

    def test_async_callback_error_stops_the_loop_while_its_task_is_referenced(self):
        """A failing async callback stops the loop without waiting for its task to be garbage collected."""
        evl = self.evl
        tasks: list[asyncio.Task[typing.Any] | None] = []
        out: list[str] = []

        async def error_coro() -> typing.NoReturn:
            tasks.append(asyncio.current_task())
            raise ZeroDivisionError

        def guard_exit() -> typing.NoReturn:
            out.append("guard exit")
            raise urwid.ExitMainLoop

        evl.alarm(0, error_coro)
        evl.alarm(5, guard_exit)
        self.assertRaises(ZeroDivisionError, evl.run)
        self.assertEqual([], out)

    def test_watch_queue_and_remove_watch_queue(self):
        evl = self.evl
        out: list[bytes] = []
        ctx = zmq.Context.instance()
        pull = ctx.socket(zmq.PULL)
        push = ctx.socket(zmq.PUSH)
        try:
            address = f"inproc://{self.id()}"
            pull.bind(address)
            push.connect(address)

            def on_ready() -> typing.NoReturn:
                out.append(pull.recv())
                raise urwid.ExitMainLoop

            handle = evl.watch_queue(pull, on_ready)
            push.send(b"hi")
            evl.run()

            self.assertEqual([b"hi"], out)
            self.assertTrue(evl.remove_watch_queue(handle))
            self.assertFalse(evl.remove_watch_queue(handle))
        finally:
            pull.close()
            push.close()

    def test_watch_file_with_a_zmq_socket(self):
        """A zmq socket given to watch_file() is called back when it has a message."""
        evl = self.evl
        out: list[bytes] = []
        ctx = zmq.Context.instance()
        pull = ctx.socket(zmq.PULL)
        push = ctx.socket(zmq.PUSH)
        try:
            address = f"inproc://{self.id()}"
            pull.bind(address)
            push.connect(address)

            def on_ready() -> typing.NoReturn:
                out.append(pull.recv())
                raise urwid.ExitMainLoop

            def give_up() -> typing.NoReturn:
                raise urwid.ExitMainLoop

            evl.watch_file(pull, on_ready)
            evl.alarm(5, give_up)  # a missed event fails the assertion below instead of hanging the run
            push.send(b"hi")
            evl.run()

            self.assertEqual([b"hi"], out)
            self.assertTrue(evl.remove_watch_file(pull))
        finally:
            pull.close()
            push.close()

    def test_zmq_socket_has_one_watch_for_file_and_queue(self):
        """watch_file() and watch_queue() set the same watch on a zmq socket, and either remove call clears it."""
        evl = self.evl
        pull = zmq.Context.instance().socket(zmq.PULL)
        try:
            evl.watch_file(pull, lambda: None)
            with self.assertRaises(ValueError):
                evl.watch_queue(pull, lambda: None)
            self.assertTrue(evl.remove_watch_queue(pull))
            self.assertFalse(evl.remove_watch_file(pull))

            evl.watch_queue(pull, lambda: None)
            self.assertTrue(evl.remove_watch_file(pull))
            self.assertFalse(evl.remove_watch_queue(pull))
        finally:
            pull.close()

    def test_remove_watch_file_by_object_or_descriptor(self):
        """A watch is removed from the poller whether it is named by the object or by its descriptor number."""
        evl = self.evl
        called = []
        with ClosingSocketPair() as (rd_1, wr_1), ClosingSocketPair() as (rd_2, wr_2):
            evl.watch_file(rd_1, lambda: called.append("by object"))
            evl.watch_file(rd_2.fileno(), lambda: called.append("by descriptor"))

            self.assertTrue(evl.remove_watch_file(rd_1.fileno()))
            self.assertTrue(evl.remove_watch_file(rd_2))
            self.assertFalse(evl.remove_watch_file(rd_1))
            wr_1.send(b"x")
            wr_2.send(b"x")

            def stop() -> typing.NoReturn:
                raise urwid.ExitMainLoop

            evl.alarm(0, stop)
            evl.run()

        self.assertEqual([], called)

    def test_watch_queue_rejects_a_queue_already_being_watched(self):
        evl = self.evl
        pull = zmq.Context.instance().socket(zmq.PULL)
        try:
            evl.watch_queue(pull, lambda: None)
            with self.assertRaises(ValueError):
                evl.watch_queue(pull, lambda: None)
        finally:
            evl.remove_watch_queue(pull)
            pull.close()

    def test_remove_watch_queue_missing_handle(self):
        evl = self.evl
        pull = zmq.Context.instance().socket(zmq.PULL)
        try:
            self.assertFalse(evl.remove_watch_queue(pull))
        finally:
            pull.close()

    def test_async_alarm_callback(self):
        evl = self.evl
        out: list[str] = []

        async def step1() -> typing.NoReturn:
            out.append("async alarm")
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()
        self.assertEqual(["async alarm"], out)

    def test_async_watch_file_callback(self):
        evl = self.evl
        out: list[str] = []

        with ClosingSocketPair() as (rd, wr):
            # Non-blocking: the fd stays readable for one extra event loop
            # tick after the async callback is scheduled, so it may fire
            # again with no data left to read.
            rd.setblocking(False)

            async def step2() -> None:
                try:
                    data = rd.recv(2)
                except BlockingIOError:
                    return
                out.append(data.decode("ascii"))
                raise urwid.ExitMainLoop

            handle = evl.watch_file(rd.fileno(), step2)
            wr.send(b"hi")
            evl.run()
            evl.remove_watch_file(handle)

        self.assertEqual(["hi"], out)

    def test_async_enter_idle_callback(self):
        evl = self.evl
        out: list[str] = []

        async def say_waiting() -> None:
            out.append("waiting")

        def say_hello() -> None:
            out.append("hello")

        def exit_clean() -> typing.NoReturn:
            raise urwid.ExitMainLoop

        evl.enter_idle(say_waiting)
        evl.alarm(0.005, say_hello)
        self._exit_once_seen(out, exit_clean, "waiting")
        evl.run()
        self.assertIn("waiting", out)

    def test_async_alarm_callback_error(self):
        evl = self.evl

        async def error_coro() -> typing.NoReturn:
            1 / 0  # Simulate error in coroutine

        evl.alarm(0, error_coro)
        self.assertRaises(ZeroDivisionError, evl.run)

    def test_async_callback_runs_concurrently_as_a_background_task(self):
        # ZMQEventLoop runs on top of an asyncio loop (via zmq.asyncio.Poller), so an
        # async def callback is scheduled as a background task there just like on
        # AsyncioEventLoop/TornadoEventLoop: the rest of the loop keeps running rather
        # than waiting for the callback's own internal awaits to resolve.
        evl = self.evl
        out: list[str] = []

        async def slow() -> None:
            out.append("start")
            await asyncio.sleep(10)  # long enough to still be pending when the loop exits
            out.append("end")

        def exit_clean() -> typing.NoReturn:
            out.append("exit")
            raise urwid.ExitMainLoop

        evl.alarm(0, slow)
        evl.alarm(0, exit_clean)
        evl.run()
        self.assertEqual(["start", "exit"], out)

    def test_exception_handler_is_a_no_op_once_the_main_task_is_gone(self):
        # _run_async() clears _main_task in its finally block once the loop stops, so a
        # background task's exception that only surfaces during interpreter/loop shutdown
        # (after _run_async() itself has already returned) must not crash trying to
        # cancel a task that no longer exists.
        evl = self.evl
        self.assertIsNone(evl._main_task)

        evl._exception_handler(typing.cast("typing.Any", None), {"exception": RuntimeError("boom")})

        self.assertIsInstance(evl._exc, RuntimeError)
