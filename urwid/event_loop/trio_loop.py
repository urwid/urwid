# Urwid main loop code using Python-3.5 features (Trio, Curio, etc)
#    Copyright (C) 2018 Toshio Kuratomi
#    Copyright (C) 2019 Tamas Nepusz
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/

"""Trio Runner based urwid EventLoop implementation.

Trio library is required.
"""

from __future__ import annotations

import functools
import inspect
import logging
import sys
import typing

import trio

from .abstract_loop import EventLoop, ExitMainLoop, SupportsFileno

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup  # pylint: disable=redefined-builtin  # backport

if typing.TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable
    from concurrent.futures import Executor, Future

    from typing_extensions import ParamSpec

    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("TrioEventLoop",)


async def _reraise(exc: BaseException) -> typing.NoReturn:
    """Raise *exc* from a nursery task, so it stops the loop like a failing alarm or watch callback."""
    raise exc


class _TrioIdleCallbackInstrument(trio.abc.Instrument):
    """IDLE callbacks emulation helper."""

    __slots__ = ("_event_loop",)

    def __init__(self, event_loop: TrioEventLoop) -> None:
        self._event_loop = event_loop

    def before_io_wait(self, timeout: float) -> None:
        # pylint: disable=protected-access  # cooperating class
        # Trio keeps polling while the main task's nursery is cancelled and after it has closed: the loop is exiting.
        nursery = self._event_loop._nursery
        if timeout > 0 and nursery is not None and not nursery.cancel_scope.cancel_called:
            try:
                for idle_callback in list(self._event_loop._idle_callbacks.values()):
                    self._event_loop._run_callback(idle_callback)
            # Trio logs an exception raised by an instrument hook and then disables the instrument.
            except BaseException as exc:  # noqa: BLE001  # re-raised in the nursery
                nursery.start_soon(_reraise, exc)
                # The wait this hook precedes would otherwise run its full timeout before the new task.
                trio.lowlevel.current_trio_token().run_sync_soon(lambda: None)


class TrioEventLoop(EventLoop):
    """
    Event loop based on the ``trio`` module.

    ``trio`` is an async library for Python 3.5 and later.

    .. note::
        :meth:`alarm`, :meth:`watch_file` and :meth:`enter_idle` accept an ``async def``
        callback in addition to a plain callable. A coroutine function is scheduled as
        a task in the main loop's nursery instead of being called directly.
    """

    def __init__(self) -> None:
        """Initialize the Trio event loop."""
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)

        self._idle_handle = 0
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._pending_tasks: list[
            tuple[
                Callable[..., Awaitable[typing.Any]],
                trio.CancelScope,
                tuple[typing.Any, ...],
            ]
        ] = []

        self._nursery: trio.Nursery | None = None

        self._sleep = trio.sleep
        self._wait_readable = trio.lowlevel.wait_readable

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> Future[_T] | asyncio.Future[_T]:
        """Raise :exc:`NotImplementedError`: use Trio's own thread API.

        :raises NotImplementedError: Trio runs blocking calls in threads itself; use ``trio.to_thread.run_sync``.
        """
        raise NotImplementedError(
            "Trio implements its own worker threads. Please use native API for call:\n"
            "'await trio.to_thread.run_sync(Callable[..., T], *args)'"
        )

    def alarm(
        self,
        seconds: float,
        callback: Callable[[], typing.Any],
    ) -> trio.CancelScope:
        """Call `callback()` a given time from now.

        :param seconds: time in seconds to wait before calling the callback
        :param callback: function to call from the event loop
        :return: a handle that may be passed to `remove_alarm()`

        No parameters are passed to the callback.
        """
        return self._start_task(self._alarm_task, seconds, callback)

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """Call `callback()` when the event loop enters the idle state.

        There is no such thing as being idle in a Trio event loop so we
        simulate it by repeatedly calling `callback()` with a short delay.
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_alarm(self, handle: trio.CancelScope) -> bool:
        """Remove an alarm.

        :param handle: the handle of the alarm to remove
        """
        return self._cancel_scope(handle)

    def remove_enter_idle(self, handle: int) -> bool:
        """Remove an idle callback.

        :param handle: the handle of the idle callback to remove
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False
        return True

    def remove_watch_file(self, handle: trio.CancelScope) -> bool:
        """Remove a file descriptor being watched for input.

        :param handle: the handle of the file descriptor callback to remove
        :returns: True if the file descriptor was watched, False otherwise
        """
        return self._cancel_scope(handle)

    def _cancel_scope(self, scope: trio.CancelScope) -> bool:
        """Cancel the given Trio cancellation scope.

        :param scope: the Trio cancellation scope to cancel
        :returns: True if the scope was cancelled, False if it was cancelled already before invoking this function
        """
        existed = not scope.cancel_called
        scope.cancel()
        return existed

    def _run_callback(self, callback: Callable[_Spec, _T], *args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | None:
        """Call callback, scheduling it as a nursery task instead if it is a coroutine function.

        A coroutine function's exceptions propagate through the nursery like any other task's,
        so unlike the asyncio/Tornado event loops there is no separate bookkeeping to fail the
        main loop on error.

        :param callback: function or coroutine function to call
        :param args: positional arguments to pass to callback
        :param kwargs: keyword arguments to pass to callback
        :return: callback return value, or None if it was scheduled as a nursery task
        """
        if inspect.iscoroutinefunction(callback):
            # Callers run only while the nursery is open: its tasks, and the idle instrument, which checks.
            nursery = typing.cast("trio.Nursery", self._nursery)
            fn = functools.partial(callback, *args, **kwargs) if kwargs else callback
            nursery.start_soon(fn, *(() if kwargs else args))
            return None
        return callback(*args, **kwargs)

    def run(self) -> None:
        """Start the event loop.

        Exit the loop when any callback raises an exception. If ExitMainLoop is raised, exit cleanly.
        """
        emulate_idle_callbacks = _TrioIdleCallbackInstrument(self)

        try:
            trio.run(self._main_task, instruments=[emulate_idle_callbacks])
        except BaseException as exc:  # noqa: BLE001  # would be handled
            self._handle_main_loop_exception(exc)

    async def run_async(self) -> None:
        """Start the main loop and block asynchronously until the main loop exits.

        This allows one to embed an urwid app in a Trio app even if the Trio event loop is already running.
        Example::

            with trio.open_nursery() as nursery:
                event_loop = urwid.TrioEventLoop()

                # [...launch other async tasks in the nursery...]

                loop = urwid.MainLoop(widget, event_loop=event_loop)
                with loop.start():
                    await event_loop.run_async()

                nursery.cancel_scope.cancel()
        """
        emulate_idle_callbacks = _TrioIdleCallbackInstrument(self)

        try:
            trio.lowlevel.add_instrument(emulate_idle_callbacks)
            try:
                await self._main_task()
            finally:
                trio.lowlevel.remove_instrument(emulate_idle_callbacks)
        except BaseException as exc:  # noqa: BLE001  # would be handled
            self._handle_main_loop_exception(exc)

    def watch_file(
        self,
        fd: int | SupportsFileno,
        callback: Callable[[], typing.Any],
    ) -> trio.CancelScope:
        """Call `callback()` when the given file descriptor has some data to read.

        No parameters are passed to the callback.

        :param fd: file descriptor to watch for input
        :param callback: function to call when some input is available
        :returns: a handle that may be passed to `remove_watch_file()`
        """
        return self._start_task(self._watch_task, fd, callback)

    async def _alarm_task(
        self,
        scope: trio.CancelScope,
        seconds: float,
        callback: Callable[[], typing.Any],
    ) -> None:
        """Asynchronous task that sleeps for a given number of seconds and then calls the given callback.

        :param scope: the cancellation scope that can be used to cancel the task
        :param seconds: the number of seconds to wait
        :param callback: the callback to call
        """
        with scope:
            await self._sleep(seconds)
            self._run_callback(callback)

    def _handle_main_loop_exception(self, exc: BaseException) -> None:
        """Handle exceptions raised from the main loop, catching ExitMainLoop instead of letting it propagate.

        Note that since Trio may collect multiple exceptions from tasks into an ExceptionGroup, we cannot simply
        use a try..catch clause, we need a helper function like this.

        :raises BaseException: *exc* itself, unless it is :exc:`ExitMainLoop`.
        """
        self._idle_callbacks.clear()
        if isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
            exc = exc.exceptions[0]

        if isinstance(exc, ExitMainLoop):
            return

        raise exc.with_traceback(exc.__traceback__) from None

    async def _main_task(self) -> None:
        """Open a nursery and sleep until the user exits the app by raising ExitMainLoop."""
        try:
            async with trio.open_nursery() as self._nursery:
                self._schedule_pending_tasks()
                await trio.sleep_forever()
        finally:
            self._nursery = None

    def _schedule_pending_tasks(self) -> None:
        """Schedule pending tasks created before the nursery opened to run on it soon.

        Tasks queued via :meth:`_start_task` before the nursery existed are started here once it is open.
        """
        if self._nursery is None:
            return
        for task, scope, args in self._pending_tasks:
            self._nursery.start_soon(task, scope, *args)
        self._pending_tasks.clear()

    def _start_task(
        self,
        task: Callable[..., Awaitable[typing.Any]],
        *args: typing.Any,
    ) -> trio.CancelScope:
        """Start an asynchronous task in the Trio nursery managed by the main loop.

        If the nursery has not started yet, store a reference to the task and the arguments so we can start the
        task when the nursery is open.

        :param task: a Trio task to run
        :param args: extra positional arguments passed to the task after its cancellation scope
        :returns: a cancellation scope for the Trio task
        """
        scope = trio.CancelScope()
        if self._nursery:
            self._nursery.start_soon(task, scope, *args)
        else:
            self._pending_tasks.append((task, scope, args))
        return scope

    async def _watch_task(
        self,
        scope: trio.CancelScope,
        fd: int | SupportsFileno,
        callback: Callable[[], typing.Any],
    ) -> None:
        """Watch *fd* and call *callback* whenever it becomes readable.

        :param scope: the cancellation scope that can be used to cancel the task
        :param fd: the file descriptor to watch
        :param callback: the callback to call
        """
        with scope:
            # We check for the scope being cancelled before calling
            # wait_readable because if callback cancels the scope, fd might be
            # closed and calling wait_readable with a closed fd does not work.
            while not scope.cancel_called:
                await self._wait_readable(fd)
                self._run_callback(callback)
