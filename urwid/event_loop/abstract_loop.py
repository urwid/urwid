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

"""Abstract shared code for urwid EventLoop implementation."""

from __future__ import annotations

import abc
import logging
import signal
import typing

if typing.TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable
    from concurrent.futures import Executor, Future
    from types import FrameType

    from typing_extensions import ParamSpec

    _T = typing.TypeVar("_T")
    _Spec = ParamSpec("_Spec")

__all__ = ("EventLoop", "ExitMainLoop")


class ExitMainLoop(Exception):
    """
    When this exception is raised within a main loop the main loop
    will exit cleanly.
    """


class EventLoop(abc.ABC):
    """
    Abstract class representing an event loop to be used by :class:`MainLoop`.
    """

    __slots__ = ("logger",)

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> Future[_T] | asyncio.Future[_T]:
        """Run callable in executor if supported.

        :param executor: Executor to use for running the function
        :type executor: concurrent.futures.Executor
        :param func: function to call
        :type func: Callable
        :param args: arguments to function (positional only)
        :type args: object
        :param kwargs: keyword arguments to function (keyword only)
        :type kwargs: object
        :return: future object for the function call outcome.
                 (exact future type depends on the event loop type)
        :rtype: concurrent.futures.Future | asyncio.Future
        """
        raise NotImplementedError

    @abc.abstractmethod
    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> typing.Any:
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        This method has no default implementation.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """

    @abc.abstractmethod
    def enter_idle(self, callback):
        """
        Add a callback for entering idle.

        This method has no default implementation.

        Returns a handle that may be passed to remove_idle()
        """

    @abc.abstractmethod
    def remove_alarm(self, handle) -> bool:
        """
        Remove an alarm.

        This method has no default implementation.

        Returns True if the alarm exists, False otherwise
        """

    @abc.abstractmethod
    def remove_enter_idle(self, handle) -> bool:
        """
        Remove an idle callback.

        This method has no default implementation.

        Returns True if the handle was removed.
        """

    @abc.abstractmethod
    def remove_watch_file(self, handle) -> bool:
        """
        Remove an input file.

        This method has no default implementation.

        Returns True if the input file exists, False otherwise
        """

    @abc.abstractmethod
    def run(self) -> None:
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.

        This method has no default implementation.
        """

    @abc.abstractmethod
    def watch_file(self, fd: int, callback: Callable[[], typing.Any]):
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        This method has no default implementation.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """

    def set_signal_handler(
        self,
        signum: int,
        handler: Callable[[int, FrameType | None], typing.Any] | int | signal.Handlers,
    ) -> Callable[[int, FrameType | None], typing.Any] | int | signal.Handlers | None:
        """
        Sets the signal handler for signal signum.

        The default implementation of :meth:`set_signal_handler`
        is simply a proxy function that calls :func:`signal.signal()`
        and returns the resulting value.

        signum -- signal number
        handler -- function (taking signum as its single argument),
        or `signal.SIG_IGN`, or `signal.SIG_DFL`
        """
        return signal.signal(signum, handler)
