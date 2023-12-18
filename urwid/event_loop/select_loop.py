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

"""Select based urwid EventLoop implementation."""

from __future__ import annotations

import contextlib
import heapq
import logging
import selectors
import time
import typing
from contextlib import suppress
from itertools import count

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from concurrent.futures import Executor, Future

    from typing_extensions import Literal, ParamSpec

    _T = typing.TypeVar("_T")
    _Spec = ParamSpec("_Spec")

__all__ = ("SelectEventLoop",)


class SelectEventLoop(EventLoop):
    """
    Event loop based on :func:`selectors.DefaultSelector.select`
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self._alarms: list[tuple[float, int, Callable[[], typing.Any]]] = []
        self._watch_files: dict[int, Callable[[], typing.Any]] = {}
        self._idle_handle: int = 0
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._tie_break: Iterator[int] = count()
        self._did_something: bool = False

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> Future[_T]:
        """Run callable in executor.

        :param executor: Executor to use for running the function
        :type executor: concurrent.futures.Executor
        :param func: function to call
        :type func: Callable
        :param args: positional arguments to function
        :type args: object
        :param kwargs: keyword arguments to function
        :type kwargs: object
        :return: future object for the function call outcome.
        :rtype: concurrent.futures.Future
        """
        return executor.submit(func, *args, **kwargs)

    def alarm(
        self,
        seconds: float,
        callback: Callable[[], typing.Any],
    ) -> tuple[float, int, Callable[[], typing.Any]]:
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """
        tm = time.time() + seconds
        handle = (tm, next(self._tie_break), callback)
        heapq.heappush(self._alarms, handle)
        return handle

    def remove_alarm(self, handle: tuple[float, int, Callable[[], typing.Any]]) -> bool:
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        try:
            self._alarms.remove(handle)
            heapq.heapify(self._alarms)

        except ValueError:
            return False

        return True

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> int:
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        self._watch_files[fd] = callback
        return fd

    def remove_watch_file(self, handle: int) -> bool:
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        if handle in self._watch_files:
            del self._watch_files[handle]
            return True
        return False

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
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

    def _entering_idle(self) -> None:
        """
        Call all the registered idle callbacks.
        """
        for callback in self._idle_callbacks.values():
            callback()

    def run(self) -> None:
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """
        with contextlib.suppress(ExitMainLoop):
            self._did_something = True
            while True:
                with suppress(InterruptedError):
                    self._loop()

    def _loop(self) -> None:
        """
        A single iteration of the event loop
        """
        tm: float | Literal["idle"] | None = None

        with selectors.DefaultSelector() as selector:
            for fd, callback in self._watch_files.items():
                selector.register(fd, selectors.EVENT_READ, callback)

            if self._alarms or self._did_something:
                timeout = 0.0

                if self._alarms:
                    timeout_ = self._alarms[0][0]
                    tm = timeout_
                    timeout = max(timeout, timeout_ - time.time())

                if self._did_something and (not self._alarms or (self._alarms and timeout > 0)):
                    timeout = 0.0
                    tm = "idle"

                self.logger.debug(f"Waiting for input: timeout={timeout!r}")
                ready = [event for event, _ in selector.select(timeout)]

            elif self._watch_files:
                self.logger.debug("Waiting for input: timeout")
                ready = [event for event, _ in selector.select()]
            else:
                ready = []

        if not ready:
            if tm == "idle":
                self.logger.debug("No input, entering IDLE")
                self._entering_idle()
                self._did_something = False
            elif tm is not None:
                # must have been a timeout
                tm, _tie_break, alarm_callback = heapq.heappop(self._alarms)
                self.logger.debug(f"No input in timeout, calling scheduled {alarm_callback!r}")
                alarm_callback()
                self._did_something = True

        self.logger.debug("Processing input")
        for record in ready:
            record.data()
            self._did_something = True
