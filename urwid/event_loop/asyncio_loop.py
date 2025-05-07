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

"""Asyncio based urwid EventLoop implementation."""

from __future__ import annotations

import asyncio
import functools
import logging
import sys
import typing

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor

    from typing_extensions import ParamSpec

    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("AsyncioEventLoop",)


class AsyncioEventLoop(EventLoop):
    """
    Event loop based on the standard library ``asyncio`` module.

    .. warning::
        Under Windows, AsyncioEventLoop globally enforces WindowsSelectorEventLoopPolicy
        as a side-effect of creating a class instance.
        Original event loop policy is restored in destructor method.

    .. note::
        If you make any changes to the urwid state outside of it
        handling input or responding to alarms (for example, from asyncio.Task
        running in background), and wish the screen to be
        redrawn, you must call :meth:`MainLoop.draw_screen` method of the
        main loop manually.

        A good way to do this:
            asyncio.get_event_loop().call_soon(main_loop.draw_screen)
    """

    def __init__(self, *, loop: asyncio.AbstractEventLoop | None = None, **kwargs) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)

        if sys.version_info[:2] < (3, 11):
            self._event_loop_policy_altered: bool = False
            self._original_event_loop_policy: asyncio.AbstractEventLoopPolicy | None = None

            if loop:
                self._loop: asyncio.AbstractEventLoop = loop
            else:
                self._original_event_loop_policy = asyncio.get_event_loop_policy()
                if sys.platform == "win32" and not isinstance(
                    self._original_event_loop_policy, asyncio.WindowsSelectorEventLoopPolicy
                ):
                    self.logger.debug("Set WindowsSelectorEventLoopPolicy as asyncio event loop policy")
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                    self._event_loop_policy_altered = True
                else:
                    self._event_loop_policy_altered = False

                self._loop = asyncio.get_event_loop()

        else:
            self._runner: asyncio.Runner | None = None

            if loop:
                self._loop: asyncio.AbstractEventLoop = loop
            else:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    self._runner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
                    self._loop = self._runner.get_loop()

        self._exc: BaseException | None = None

        self._idle_asyncio_handle: asyncio.TimerHandle | None = None
        self._idle_handle: int = 0
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}

    def __del__(self) -> None:
        if sys.version_info[:2] < (3, 11):
            if self._event_loop_policy_altered:
                asyncio.set_event_loop_policy(self._original_event_loop_policy)  # Restore default event loop policy
        elif self._runner is not None:
            self._runner.close()

    def _also_call_idle(self, callback: Callable[_Spec, _T]) -> Callable[_Spec, _T]:
        """
        Wrap the callback to also call _entering_idle.
        """

        @functools.wraps(callback)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T:
            if not self._idle_asyncio_handle:
                self._idle_asyncio_handle = self._loop.call_later(0, self._entering_idle)
            return callback(*args, **kwargs)

        return wrapper

    def _entering_idle(self) -> None:
        """
        Call all the registered idle callbacks.
        """
        try:
            for callback in self._idle_callbacks.values():
                callback()
        finally:
            self._idle_asyncio_handle = None

    def run_in_executor(
        self,
        executor: Executor | None,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> asyncio.Future[_T]:
        """Run callable in executor.

        :param executor: Executor to use for running the function. Default asyncio executor is used if None.
        :type executor: concurrent.futures.Executor | None
        :param func: function to call
        :type func: Callable
        :param args: arguments to function (positional only)
        :type args: object
        :param kwargs: keyword arguments to function (keyword only)
        :type kwargs: object
        :return: future object for the function call outcome.
        :rtype: asyncio.Future
        """
        return self._loop.run_in_executor(executor, functools.partial(func, *args, **kwargs))

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> asyncio.TimerHandle:
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- time in seconds to wait before calling callback
        callback -- function to call from event loop
        """
        return self._loop.call_later(seconds, self._also_call_idle(callback))

    def remove_alarm(self, handle) -> bool:
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        existed = not handle.cancelled()
        handle.cancel()
        return existed

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> int:
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        self._loop.add_reader(fd, self._also_call_idle(callback))
        return fd

    def remove_watch_file(self, handle: int) -> bool:
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        return self._loop.remove_reader(handle)

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_enter_idle()
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

    def _exception_handler(self, loop: asyncio.AbstractEventLoop, context):
        if exc := context.get("exception"):
            loop.stop()

            if self._idle_asyncio_handle:
                # clean it up to prevent old callbacks
                # from messing things up if loop is restarted
                self._idle_asyncio_handle.cancel()
                self._idle_asyncio_handle = None

            if not isinstance(exc, ExitMainLoop):
                # Store the exc_info so we can re-raise after the loop stops
                self._exc = exc
        else:
            loop.default_exception_handler(context)

    def run(self) -> None:
        """Start the event loop.

        Exit the loop when any callback raises an exception.
        If ExitMainLoop is raised, exit cleanly.
        """
        self._loop.set_exception_handler(self._exception_handler)
        self._loop.run_forever()
        if self._exc:
            exc = self._exc
            self._exc = None
            raise exc.with_traceback(exc.__traceback__)
