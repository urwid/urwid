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

"""GLib based urwid EventLoop implementation.

PyGObject library is required.
"""

from __future__ import annotations

import functools
import logging
import signal
import typing

from gi.repository import GLib

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor, Future
    from types import FrameType

    from typing_extensions import Literal, ParamSpec

    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("GLibEventLoop",)


def _ignore_handler(_sig: int, _frame: FrameType | None = None) -> None:
    return None


class GLibEventLoop(EventLoop):
    """
    Event loop based on GLib.MainLoop
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self._alarms: list[int] = []
        self._watch_files: dict[int, int] = {}
        self._idle_handle: int = 0
        self._glib_idle_enabled = False  # have we called glib.idle_add?
        self._idle_callbacks: dict[int, Callable[[], typing.Any]] = {}
        self._loop = GLib.MainLoop()
        self._exc: BaseException | None = None
        self._enable_glib_idle()
        self._signal_handlers: dict[int, int] = {}

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
    ) -> tuple[int, Callable[[], typing.Any]]:
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """

        @self.handle_exit
        def ret_false() -> Literal[False]:
            callback()
            self._enable_glib_idle()
            return False

        fd = GLib.timeout_add(int(seconds * 1000), ret_false)
        self._alarms.append(fd)
        return (fd, callback)

    def set_signal_handler(
        self,
        signum: int,
        handler: Callable[[int, FrameType | None], typing.Any] | int | signal.Handlers,
    ) -> None:
        """
        Sets the signal handler for signal signum.

        .. WARNING::
            Because this method uses the `GLib`-specific `unix_signal_add`
            function, its behaviour is different than `signal.signal().`

            If `signum` is not `SIGHUP`, `SIGINT`, `SIGTERM`, `SIGUSR1`,
            `SIGUSR2` or `SIGWINCH`, this method performs no actions and
            immediately returns None.

            Returns None in all cases (unlike :func:`signal.signal()`).
        ..

        signum -- signal number
        handler -- function (taking signum as its single argument),
        or `signal.SIG_IGN`, or `signal.SIG_DFL`
        """
        glib_signals = [
            signal.SIGHUP,
            signal.SIGINT,
            signal.SIGTERM,
            signal.SIGUSR1,
            signal.SIGUSR2,
        ]

        # GLib supports SIGWINCH as of version 2.54.
        if not GLib.check_version(2, 54, 0):
            glib_signals.append(signal.SIGWINCH)

        if signum not in glib_signals:
            # The GLib event loop supports only the signals listed above
            return

        if signum in self._signal_handlers:
            GLib.source_remove(self._signal_handlers.pop(signum))

        if handler == signal.Handlers.SIG_IGN:
            handler = _ignore_handler
        elif handler == signal.Handlers.SIG_DFL:
            return

        def final_handler(signal_number: int):
            # MyPy False-negative: signal.Handlers casted
            handler(signal_number, None)  # type: ignore[operator]
            return GLib.SOURCE_CONTINUE

        source = GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, final_handler, signum)
        self._signal_handlers[signum] = source

    def remove_alarm(self, handle) -> bool:
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        try:
            self._alarms.remove(handle[0])
            GLib.source_remove(handle[0])

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

        @self.handle_exit
        def io_callback(source, cb_condition) -> Literal[True]:
            callback()
            self._enable_glib_idle()
            return True

        self._watch_files[fd] = GLib.io_add_watch(fd, GLib.IO_IN, io_callback)
        return fd

    def remove_watch_file(self, handle: int) -> bool:
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        if handle in self._watch_files:
            GLib.source_remove(self._watch_files[handle])
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

    def _enable_glib_idle(self) -> None:
        if self._glib_idle_enabled:
            return
        GLib.idle_add(self._glib_idle_callback)
        self._glib_idle_enabled = True

    def _glib_idle_callback(self):
        for callback in self._idle_callbacks.values():
            callback()
        self._glib_idle_enabled = False
        return False  # ask glib not to call again (or we would be called

    def remove_enter_idle(self, handle) -> bool:
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
        try:
            self._loop.run()
        finally:
            if self._loop.is_running():
                self._loop.quit()
        if self._exc:
            # An exception caused us to exit, raise it now
            exc = self._exc
            self._exc = None
            raise exc.with_traceback(exc.__traceback__)

    def handle_exit(self, f: Callable[_Spec, _T]) -> Callable[_Spec, _T | Literal[False]]:
        """
        Decorator that cleanly exits the :class:`GLibEventLoop` if
        :exc:`ExitMainLoop` is thrown inside of the wrapped function. Store the
        exception info if some other exception occurs, it will be reraised after
        the loop quits.

        *f* -- function to be wrapped
        """

        @functools.wraps(f)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | Literal[False]:
            try:
                return f(*args, **kwargs)
            except ExitMainLoop:
                self._loop.quit()
            except BaseException as exc:
                self._exc = exc
                if self._loop.is_running():
                    self._loop.quit()
            return False

        return wrapper
