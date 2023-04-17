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

"""Tornado IOLoop based urwid IOLoop implementation.

Tornado library is required.
"""

from __future__ import annotations

import functools
import typing
from collections.abc import Callable

from tornado import ioloop

from .abstract_loop import EventLoop, ExitMainLoop

if typing.TYPE_CHECKING:

    from typing_extensions import Literal, ParamSpec
    _Spec = ParamSpec("_Spec")
    _T = typing.TypeVar("_T")

__all__ = ("TornadoEventLoop",)


class TornadoEventLoop(EventLoop):
    """ This is an Urwid-specific event loop to plug into its MainLoop.
        It acts as an adaptor for Tornado's IOLoop which does all
        heavy lifting except idle-callbacks.

        Notice, since Tornado has no concept of idle callbacks we
        monkey patch ioloop._impl.poll() function to be able to detect
        potential idle periods.
    """
    _idle_emulation_delay = 1.0 / 30  # a short time (in seconds)

    def __init__(self, loop: ioloop.IOLoop | None = None) -> None:
        if loop:
            self._loop: ioloop.IOLoop = loop
        else:
            self._loop = ioloop.IOLoop.instance()

        self._pending_alarms: dict[object, int] = {}
        self._watch_handles: dict[int, int] = {}  # {<watch_handle> : <file_descriptor>}
        self._max_watch_handle: int = 0
        self._exc: BaseException | None = None

    def alarm(self, seconds: float | int, callback:  Callable[[], typing.Any]):
        def wrapped() -> None:
            try:
                del self._pending_alarms[handle]
            except KeyError:
                pass
            self.handle_exit(callback)()

        handle = self._loop.add_timeout(self._loop.time() + seconds, wrapped)
        self._pending_alarms[handle] = 1
        return handle

    def remove_alarm(self, handle) -> bool:
        self._loop.remove_timeout(handle)
        try:
            del self._pending_alarms[handle]
        except KeyError:
            return False
        else:
            return True

    def watch_file(self, fd: int, callback: Callable[[], _T]) -> int:
        def handler(_fd: int, _events: int) -> None:
            self.handle_exit(callback)()

        self._loop.add_handler(fd, handler, ioloop.IOLoop.READ)
        self._max_watch_handle += 1
        handle = self._max_watch_handle
        self._watch_handles[handle] = fd
        return handle

    def remove_watch_file(self, handle: int) -> bool:
        fd = self._watch_handles.pop(handle, None)
        if fd is None:
            return False
        else:
            self._loop.remove_handler(fd)
            return True

    def enter_idle(self, callback: Callable[[], typing.Any]) -> list[object]:
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
        # XXX there's no such thing as "idle" in most event loops; this fakes
        # it the same way as Twisted, by scheduling the callback to be called
        # repeatedly
        mutable_handle: list[object] = []

        def faux_idle_callback():
            callback()
            mutable_handle[0] = self._loop.call_later(self._idle_emulation_delay, faux_idle_callback)

        mutable_handle.append(self._loop.call_later(self._idle_emulation_delay, faux_idle_callback))

        # asyncio used as backend, real type comes from asyncio_loop.call_later
        return mutable_handle

    def remove_enter_idle(self, handle) -> bool:
        """
        Remove an idle callback.

        Returns True if the handle was removed.
        """
        # `handle` is just a list containing the current actual handle
        return self.remove_alarm(handle[0])

    def handle_exit(self, f: Callable[_Spec, _T]) -> Callable[_Spec, _T | Literal[False]]:
        @functools.wraps(f)
        def wrapper(*args: _Spec.args, **kwargs: _Spec.kwargs) -> _T | Literal[False]:
            try:
                return f(*args, **kwargs)
            except ExitMainLoop:
                self._loop.stop()
            except Exception as exc:
                self._exc = exc
                self._loop.stop()
            return False
        return wrapper

    def run(self) -> None:
        self._loop.start()
        if self._exc:
            exc, self._exc = self._exc, None
            raise exc.with_traceback(exc.__traceback__)
