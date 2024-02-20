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

"""Twisted Reactor based urwid EventLoop implementation.

Twisted library is required.
"""

from __future__ import annotations

import functools
import logging
import sys
import typing

from twisted.internet.abstract import FileDescriptor
from twisted.internet.error import AlreadyCalled, AlreadyCancelled

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor, Future

    from twisted.internet.base import DelayedCall, ReactorBase
    from typing_extensions import ParamSpec

    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("TwistedEventLoop",)


class _TwistedInputDescriptor(FileDescriptor):
    def __init__(self, reactor: ReactorBase, fd: int, cb: Callable[[], typing.Any]) -> None:
        self._fileno = fd
        self.cb = cb
        super().__init__(reactor)  # ReactorBase implement full API as required in interfaces

    def fileno(self) -> int:
        return self._fileno

    def doRead(self):
        return self.cb()

    def getHost(self):
        raise NotImplementedError("No network operation expected")

    def getPeer(self):
        raise NotImplementedError("No network operation expected")

    def writeSomeData(self, data: bytes) -> None:
        raise NotImplementedError("Reduced functionality: read-only")


class TwistedEventLoop(EventLoop):
    """
    Event loop based on Twisted_
    """

    _idle_emulation_delay = 1.0 / 256  # a short time (in seconds)

    def __init__(self, reactor: ReactorBase | None = None, manage_reactor: bool = True) -> None:
        """
        :param reactor: reactor to use
        :type reactor: :class:`twisted.internet.reactor`.
        :param: manage_reactor: `True` if you want this event loop to run
                                and stop the reactor.
        :type manage_reactor: boolean

        .. WARNING::
           Twisted's reactor doesn't like to be stopped and run again.  If you
           need to stop and run your :class:`MainLoop`, consider setting
           ``manage_reactor=False`` and take care of running/stopping the reactor
           at the beginning/ending of your program yourself.

           You can also forego using :class:`MainLoop`'s run() entirely, and
           instead call start() and stop() before and after starting the
           reactor.

        .. _Twisted: https://twisted.org/
        """
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        if reactor is None:
            import twisted.internet.reactor

            reactor = twisted.internet.reactor
        self.reactor: ReactorBase = reactor
        self._watch_files: dict[int, _TwistedInputDescriptor] = {}
        self._idle_handle: int = 0
        self._twisted_idle_enabled = False
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._exc: BaseException | None = None
        self.manage_reactor = manage_reactor
        self._enable_twisted_idle()

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[..., _T],
        *args: object,
        **kwargs: object,
    ) -> Future[_T]:
        raise NotImplementedError(
            "Twisted implement it's own ThreadPool executor. Please use native API for call:\n"
            "'threads.deferToThread(Callable[..., Any], *args, **kwargs)'\n"
            "And use 'addCallback' api for callbacks:\n"
            "'threads.deferToThread(Callable[..., T], *args, **kwargs).addCallback(Callable[[T], None])'"
        )

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> DelayedCall:
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """
        handle = self.reactor.callLater(seconds, self.handle_exit(callback))
        return handle

    def remove_alarm(self, handle: DelayedCall) -> bool:
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        try:
            handle.cancel()

        except (AlreadyCancelled, AlreadyCalled):
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
        ind = _TwistedInputDescriptor(self.reactor, fd, self.handle_exit(callback))
        self._watch_files[fd] = ind
        self.reactor.addReader(ind)
        return fd

    def remove_watch_file(self, handle: int) -> bool:
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        if handle in self._watch_files:
            self.reactor.removeReader(self._watch_files[handle])
            del self._watch_files[handle]
            return True
        return False

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_enter_idle()
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def _enable_twisted_idle(self) -> None:
        """
        Twisted's reactors don't have an idle or enter-idle callback
        so the best we can do for now is to set a timer event in a very
        short time to approximate an enter-idle callback.

        .. WARNING::
           This will perform worse than the other event loops until we can find a
           fix or workaround
        """
        if self._twisted_idle_enabled:
            return
        self.reactor.callLater(
            self._idle_emulation_delay,
            self.handle_exit(self._twisted_idle_callback, enable_idle=False),
        )
        self._twisted_idle_enabled = True

    def _twisted_idle_callback(self) -> None:
        for callback in self._idle_callbacks.values():
            callback()
        self._twisted_idle_enabled = False

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

    def run(self) -> None:
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """
        if not self.manage_reactor:
            return
        self.reactor.run()
        if self._exc:
            # An exception caused us to exit, raise it now
            exc = self._exc
            self._exc = None
            raise exc.with_traceback(exc.__traceback__)

    def handle_exit(self, f: Callable[_Spec, _T], enable_idle: bool = True) -> Callable[_Spec, _T | None]:
        """
        Decorator that cleanly exits the :class:`TwistedEventLoop` if
        :class:`ExitMainLoop` is thrown inside of the wrapped function. Store the
        exception info if some other exception occurs, it will be reraised after
        the loop quits.

        *f* -- function to be wrapped
        """

        @functools.wraps(f)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | None:
            rval = None
            try:
                rval = f(*args, **kwargs)
            except ExitMainLoop:
                if self.manage_reactor:
                    self.reactor.stop()
            except BaseException as exc:
                print(sys.exc_info())
                self._exc = exc
                if self.manage_reactor:
                    self.reactor.crash()
            if enable_idle:
                self._enable_twisted_idle()
            return rval

        return wrapper
