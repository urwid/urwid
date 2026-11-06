"""Tests for GuardedEventLoop, through a loop that runs its callbacks only when the test asks."""

from __future__ import annotations

import asyncio
import inspect
import typing
import unittest
from unittest import mock

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable


class RecordingEventLoop(urwid.EventLoop):  # pylint: disable=abstract-method  # run_in_executor is not supported
    """Keeps the callbacks registered on it, by handle, for the test to call."""

    def __init__(self) -> None:
        """Start with no callbacks."""
        super().__init__()
        self.callbacks: dict[int, Callable[[], typing.Any]] = {}
        self.removed: list[int] = []

    def _add(self, callback: Callable[[], typing.Any]) -> int:
        handle = len(self.callbacks) + 1
        self.callbacks[handle] = callback
        return handle

    def _remove(self, handle: int) -> bool:
        self.removed.append(handle)
        return handle in self.callbacks

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> int:
        """Keep *callback*."""
        return self._add(callback)

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """Keep *callback*."""
        return self._add(callback)

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> int:
        """Keep *callback*."""
        return self._add(callback)

    def remove_alarm(self, handle: int) -> bool:
        """Record the removal."""
        return self._remove(handle)

    def remove_enter_idle(self, handle: int) -> bool:
        """Record the removal."""
        return self._remove(handle)

    def remove_watch_file(self, handle: int) -> bool:
        """Record the removal."""
        return self._remove(handle)

    def run(self) -> None:
        """Do nothing."""


class GuardedEventLoopTest(unittest.TestCase):
    """Callbacks registered through the wrapper report their exceptions to its handler."""

    def setUp(self) -> None:
        """Wrap a recording loop with a handler that records the exceptions."""
        self.inner = RecordingEventLoop()
        self.errors: list[Exception] = []
        self.loop = urwid.GuardedEventLoop(self.inner, self.errors.append)

    def test_every_kind_of_callback_reports_its_exception(self) -> None:
        """Alarms, idle callbacks and file watches all go through the handler."""
        registrations = {
            "alarm": lambda callback: self.loop.alarm(1, callback),
            "enter_idle": self.loop.enter_idle,
            "watch_file": lambda callback: self.loop.watch_file(3, callback),
        }
        for name, register in registrations.items():
            with self.subTest(name):
                error = RuntimeError(name)

                def fail(error: Exception = error) -> None:
                    raise error

                handle = register(fail)
                self.assertIsNone(self.inner.callbacks[handle]())
                self.assertIs(error, self.errors[-1])

    def test_exit_main_loop_goes_to_the_handler(self) -> None:
        """ExitMainLoop is reported like any other exception, so the shared loop does not stop."""

        def stop() -> None:
            raise urwid.ExitMainLoop

        handle = self.loop.alarm(0, stop)
        self.inner.callbacks[handle]()
        self.assertIsInstance(self.errors[0], urwid.ExitMainLoop)

    def test_callback_without_error_returns_its_value(self) -> None:
        """A callback that does not raise behaves as if it were registered directly."""
        handle = self.loop.alarm(0, lambda: 42)
        self.assertEqual(42, self.inner.callbacks[handle]())
        self.assertEqual([], self.errors)

    def test_exceptions_that_are_not_errors_are_not_caught(self) -> None:
        """KeyboardInterrupt still reaches the wrapped loop."""

        def interrupt() -> None:
            raise KeyboardInterrupt

        handle = self.loop.alarm(0, interrupt)
        with self.assertRaises(KeyboardInterrupt):
            self.inner.callbacks[handle]()
        self.assertEqual([], self.errors)

    def test_an_exception_from_the_handler_reaches_the_wrapped_loop(self) -> None:
        """A handler that raises is not guarded itself."""

        def handler(exc: Exception) -> None:
            raise ValueError("from the handler") from exc

        loop = urwid.GuardedEventLoop(self.inner, handler)
        handle = loop.alarm(0, lambda: 1 / 0)
        with self.assertRaisesRegex(ValueError, "from the handler"):
            self.inner.callbacks[handle]()

    def test_async_callback_stays_async(self) -> None:
        """An async def callback is wrapped as one, so the wrapped loop still schedules it as a task."""

        async def fail() -> None:
            await asyncio.sleep(0)
            raise RuntimeError("async")

        handle = self.loop.alarm(0, fail)
        guarded = self.inner.callbacks[handle]
        self.assertTrue(inspect.iscoroutinefunction(guarded))
        self.assertIsNone(asyncio.run(guarded()))
        self.assertEqual(["async"], [str(error) for error in self.errors])

    def test_removal_and_other_calls_go_to_the_wrapped_loop(self) -> None:
        """Handles are the wrapped loop's own, and the remaining methods delegate."""
        handles = [self.loop.alarm(0, print), self.loop.enter_idle(print), self.loop.watch_file(3, print)]
        self.assertTrue(self.loop.remove_alarm(handles[0]))
        self.assertTrue(self.loop.remove_enter_idle(handles[1]))
        self.assertTrue(self.loop.remove_watch_file(handles[2]))
        self.assertEqual(handles, self.inner.removed)
        self.assertIs(self.inner, self.loop.loop)

        with mock.patch.object(self.inner, "set_signal_handler") as set_signal_handler:
            self.loop.set_signal_handler(2, print)
        set_signal_handler.assert_called_once_with(2, print)
        with mock.patch.object(self.inner, "run") as run:
            self.loop.run()
        run.assert_called_once_with()
        with self.assertRaises(NotImplementedError):
            self.loop.run_in_executor(mock.Mock(), print)


class GuardedAsyncioEventLoopTest(unittest.TestCase):
    """Callbacks on a real event loop, run as the loop runs them."""

    def test_errors_go_to_the_handler_and_the_loop_goes_on(self) -> None:
        """A sync ExitMainLoop and an async error reach the handler, and the loop runs until it is stopped."""
        inner = urwid.AsyncioEventLoop(loop=asyncio.new_event_loop())
        self.addCleanup(inner._loop.close)
        errors: list[str] = []
        loop = urwid.GuardedEventLoop(inner, lambda exc: errors.append(type(exc).__name__))
        ran_after: list[bool] = []

        def stop() -> None:
            raise urwid.ExitMainLoop

        async def fail() -> None:
            await asyncio.sleep(0)
            raise RuntimeError("async")

        def stop_inner() -> None:
            raise urwid.ExitMainLoop

        loop.alarm(0, stop)
        loop.alarm(0, fail)
        loop.alarm(0.05, lambda: ran_after.append(True))
        # registered on the wrapped loop, so it stops the run; it also ends the test if the guard lets an error through
        inner.alarm(0.1, stop_inner)
        inner.run()

        self.assertEqual(["ExitMainLoop", "RuntimeError"], sorted(errors))
        self.assertEqual([True], ran_after)
