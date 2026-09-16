# Urwid main loop code
#    Copyright (C) 2004-2012  Ian Ward
#    Copyright (C) 2008 Walter Mundt
#    Copyright (C) 2009 Andrew Psaltis
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

"""Tornado IOLoop based urwid EventLoop implementation.

Tornado library is required.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import typing
from contextlib import suppress

from tornado import ioloop

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor

    from typing_extensions import Literal, ParamSpec

    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("TornadoEventLoop",)


class TornadoEventLoop(EventLoop):
    """This is an Urwid-specific event loop to plug into its MainLoop.
    It acts as an adaptor for Tornado's IOLoop which does all
    heavy lifting except idle-callbacks.

    .. note::
        :meth:`alarm`, :meth:`watch_file` and :meth:`enter_idle` accept an ``async def``
        callback in addition to a plain callable. A coroutine function is scheduled as
        an ``asyncio.Task`` on the IOLoop's underlying asyncio loop instead of being
        called directly.
    """

    def __init__(self, loop: ioloop.IOLoop | None = None) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        if loop:
            self._loop: ioloop.IOLoop = loop
        else:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self._loop = ioloop.IOLoop.current()

        self._pending_alarms: dict[object, int] = {}
        self._watch_handles: dict[int, int] = {}  # {<watch_handle> : <file_descriptor>}
        self._max_watch_handle: int = 0
        self._exc: BaseException | None = None

        self._idle_asyncio_handle: object | None = None
        self._idle_handle: int = 0
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._background_tasks: set[asyncio.Task[typing.Any]] = set()

    def _also_call_idle(self, callback: Callable[_Spec, _T]) -> Callable[_Spec, _T | None]:
        """
        Wrap the callback to also call _entering_idle.
        """

        @functools.wraps(callback)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | None:
            if not self._idle_asyncio_handle:
                self._idle_asyncio_handle = self._loop.call_later(0, self._entering_idle)
            return self._run_callback(callback, *args, **kwargs)

        return wrapper

    def _run_callback(self, callback: Callable[_Spec, _T], *args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | None:
        """Call callback, scheduling it as a task instead if it is a coroutine function.

        :param callback: function or coroutine function to call
        :type callback: Callable
        :param args: positional arguments to pass to callback
        :type args: Any
        :param kwargs: keyword arguments to pass to callback
        :type kwargs: Any
        :return: callback return value, or None if it was scheduled as a background task
        :rtype: Any
        """
        if inspect.iscoroutinefunction(callback):
            task = asyncio.get_running_loop().create_task(callback(*args, **kwargs))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            task.add_done_callback(self._handle_task_exception)
            return None
        return callback(*args, **kwargs)

    def _entering_idle(self) -> None:
        """
        Call all the registered idle callbacks.
        """
        try:
            for callback in self._idle_callbacks.values():
                self._run_callback(callback)
        finally:
            self._idle_asyncio_handle = None

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> asyncio.Future[_T]:
        """Run callable in executor.

        :param executor: Executor to use for running the function
        :type executor: concurrent.futures.Executor
        :param func: function to call
        :type func: Callable
        :param args: arguments to function (positional only)
        :type args: object
        :param kwargs: keyword arguments to function (keyword only)
        :type kwargs: object
        :return: future object for the function call outcome.
        :rtype: asyncio.Future
        """
        return typing.cast(
            "asyncio.Future[_T]",
            self._loop.run_in_executor(executor, functools.partial(func, *args, **kwargs)),
        )

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> object:
        @self._also_call_idle
        @functools.wraps(callback)
        def wrapped() -> None:
            with suppress(KeyError):
                del self._pending_alarms[handle]

            self.handle_exit(callback)()

        handle = self._loop.add_timeout(self._loop.time() + seconds, wrapped)
        self._pending_alarms[handle] = 1
        return handle

    def remove_alarm(self, handle: object) -> bool:
        self._loop.remove_timeout(handle)
        try:
            del self._pending_alarms[handle]
        except KeyError:
            return False

        return True

    def watch_file(self, fd: int, callback: Callable[[], _T]) -> int:
        @self._also_call_idle
        def handler(_fd: int, _events: int) -> None:
            self.handle_exit(callback)()

        self._loop.add_handler(fd, handler, ioloop.IOLoop.READ)
        self._max_watch_handle += 1
        handle = self._max_watch_handle
        self._watch_handles[handle] = fd
        return handle

    def remove_watch_file(self, handle: int) -> bool:
        if (fd := self._watch_handles.pop(handle, None)) is not None:
            self._loop.remove_handler(fd)
            return True

        return False

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
        # XXX there's no such thing as "idle" in most event loops; this fakes
        # it by adding extra callback to the timer and file watch callbacks.
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_enter_idle(self, handle: int) -> bool:
        """
        Remove an idle callback.

        Returns True if the handle was removed.
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False
        return True

    def _stop_after_error(self, exc: BaseException | None) -> None:
        """Stop the IOLoop after a callback failed, the same way a synchronous callback's would.

        :param exc: exception the callback raised; recorded unless it is an :exc:`ExitMainLoop`,
            or ``None`` for a clean :exc:`ExitMainLoop`
        :type exc: BaseException | None
        """
        if exc is not None and not isinstance(exc, ExitMainLoop):
            self._exc = exc

        if self._idle_asyncio_handle:
            # clean it up to prevent old callbacks
            # from messing things up if loop is restarted
            self._loop.remove_timeout(self._idle_asyncio_handle)
            self._idle_asyncio_handle = None

        self._loop.stop()

    def _handle_task_exception(self, task: asyncio.Task[typing.Any]) -> None:
        """Stop the loop if a background task scheduled from an ``async def`` callback failed.

        :param task: finished background task scheduled by :meth:`_run_callback`
        :type task: asyncio.Task
        """
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            self._stop_after_error(exc)

    def handle_exit(self, f: Callable[_Spec, _T]) -> Callable[_Spec, _T | Literal[False] | None]:
        @functools.wraps(f)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | Literal[False] | None:
            try:
                return self._run_callback(f, *args, **kwargs)
            except ExitMainLoop as exc:
                self._stop_after_error(exc)
            except Exception as exc:  # noqa: BLE001  # special case
                self._stop_after_error(exc)

            return False

        return wrapper

    def run(self) -> None:
        """
        Start the event loop and run it until :exc:`ExitMainLoop` is raised.

        :raises BaseException: the exception that stopped the loop, once the loop has been left.
        """
        self._loop.start()
        if self._exc:
            exc, self._exc = self._exc, None
            raise exc.with_traceback(exc.__traceback__)
