# Urwid main loop code using ZeroMQ queues
#    Copyright (C) 2019 Dave Jones
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

"""ZeroMQ based urwid EventLoop implementation.

`ZeroMQ <https://zeromq.org>`_ library is required.
"""

from __future__ import annotations

import contextlib
import errno
import heapq
import logging
import os
import time
import typing
from itertools import count

import zmq

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    import io
    from collections.abc import Callable
    from concurrent.futures import Executor, Future

    from typing_extensions import ParamSpec

    ZMQAlarmHandle = typing.TypeVar("ZMQAlarmHandle")
    _T = typing.TypeVar("_T")
    _Spec = ParamSpec("_Spec")


class ZMQEventLoop(EventLoop):
    """
    This class is an urwid event loop for `ZeroMQ`_ applications. It is very
    similar to :class:`SelectEventLoop`, supporting the usual :meth:`alarm`
    events and file watching (:meth:`watch_file`) capabilities, but also
    incorporates the ability to watch zmq queues for events
    (:meth:`watch_queue`).

    .. _ZeroMQ: https://zeromq.org/
    """

    _alarm_break = count()

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self._did_something = True
        self._alarms: list[tuple[float, int, Callable[[], typing.Any]]] = []
        self._poller = zmq.Poller()
        self._queue_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._idle_handle = 0
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}

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

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> ZMQAlarmHandle:
        """
        Call *callback* a given time from now. No parameters are passed to
        callback. Returns a handle that may be passed to :meth:`remove_alarm`.

        :param float seconds:
            floating point time to wait before calling callback.

        :param callback:
            function to call from event loop.
        """
        handle = (time.time() + seconds, next(self._alarm_break), callback)
        heapq.heappush(self._alarms, handle)
        return handle

    def remove_alarm(self, handle: ZMQAlarmHandle) -> bool:
        """
        Remove an alarm. Returns ``True`` if the alarm exists, ``False``
        otherwise.
        """
        try:
            self._alarms.remove(handle)
            heapq.heapify(self._alarms)

        except ValueError:
            return False

        return True

    def watch_queue(
        self,
        queue: zmq.Socket,
        callback: Callable[[], typing.Any],
        flags: int = zmq.POLLIN,
    ) -> zmq.Socket:
        """
        Call *callback* when zmq *queue* has something to read (when *flags* is
        set to ``POLLIN``, the default) or is available to write (when *flags*
        is set to ``POLLOUT``). No parameters are passed to the callback.
        Returns a handle that may be passed to :meth:`remove_watch_queue`.

        :param queue:
            The zmq queue to poll.

        :param callback:
            The function to call when the poll is successful.

        :param int flags:
            The condition to monitor on the queue (defaults to ``POLLIN``).
        """
        if queue in self._queue_callbacks:
            raise ValueError(f"already watching {queue!r}")
        self._poller.register(queue, flags)
        self._queue_callbacks[queue] = callback
        return queue

    def watch_file(
        self,
        fd: int | io.TextIOWrapper,
        callback: Callable[[], typing.Any],
        flags: int = zmq.POLLIN,
    ) -> io.TextIOWrapper:
        """
        Call *callback* when *fd* has some data to read. No parameters are
        passed to the callback. The *flags* are as for :meth:`watch_queue`.
        Returns a handle that may be passed to :meth:`remove_watch_file`.

        :param fd:
            The file-like object, or fileno to monitor.

        :param callback:
            The function to call when the file has data available.

        :param int flags:
            The condition to monitor on the file (defaults to ``POLLIN``).
        """
        if isinstance(fd, int):
            fd = os.fdopen(fd)
        self._poller.register(fd, flags)
        self._queue_callbacks[fd.fileno()] = callback
        return fd

    def remove_watch_queue(self, handle: zmq.Socket) -> bool:
        """
        Remove a queue from background polling. Returns ``True`` if the queue
        was being monitored, ``False`` otherwise.
        """
        try:
            try:
                self._poller.unregister(handle)
            finally:
                self._queue_callbacks.pop(handle, None)

        except KeyError:
            return False

        return True

    def remove_watch_file(self, handle: io.TextIOWrapper) -> bool:
        """
        Remove a file from background polling. Returns ``True`` if the file was
        being monitored, ``False`` otherwise.
        """
        try:
            try:
                self._poller.unregister(handle)
            finally:
                self._queue_callbacks.pop(handle.fileno(), None)

        except KeyError:
            return False

        return True

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """
        Add a *callback* to be executed when the event loop detects it is idle.
        Returns a handle that may be passed to :meth:`remove_enter_idle`.
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_enter_idle(self, handle: int) -> bool:
        """
        Remove an idle callback. Returns ``True`` if *handle* was removed,
        ``False`` otherwise.
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False

        return True

    def _entering_idle(self) -> None:
        for callback in list(self._idle_callbacks.values()):
            callback()

    def run(self) -> None:
        """
        Start the event loop. Exit the loop when any callback raises an
        exception. If :exc:`ExitMainLoop` is raised, exit cleanly.
        """
        with contextlib.suppress(ExitMainLoop):
            while True:
                try:
                    self._loop()
                except zmq.error.ZMQError as exc:  # noqa: PERF203
                    if exc.errno != errno.EINTR:
                        raise

    def _loop(self) -> None:
        """
        A single iteration of the event loop.
        """
        state = "wait"  # default state not expecting any action
        if self._alarms or self._did_something:
            timeout = 0
            if self._alarms:
                state = "alarm"
                timeout = max(0.0, self._alarms[0][0] - time.time())
            if self._did_something and (not self._alarms or (self._alarms and timeout > 0)):
                state = "idle"
                timeout = 0
            ready = dict(self._poller.poll(timeout * 1000))
        else:
            ready = dict(self._poller.poll())

        if not ready:
            if state == "idle":
                self._entering_idle()
                self._did_something = False
            elif state == "alarm":
                _due, _tie_break, callback = heapq.heappop(self._alarms)
                callback()
                self._did_something = True

        for queue in ready:
            self._queue_callbacks[queue]()
            self._did_something = True
