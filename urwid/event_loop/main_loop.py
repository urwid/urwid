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


"""The main loop that connects a widget tree, a display module and an event loop."""

from __future__ import annotations

import contextvars
import functools
import heapq
import inspect
import logging
import os
import socket
import sys
import time
import typing
import weakref
from collections import deque
from contextlib import contextmanager, suppress

from urwid import _selectors, display, signals
from urwid.command_map import Command, command_map
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED
from urwid.util import StoppingContext, is_mouse_event
from urwid.widget import PopUpTarget

from .abstract_loop import ExitMainLoop
from .select_loop import SelectEventLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Iterator
    from typing import Literal, ParamSpec, Self

    from urwid.display import BaseScreen
    from urwid.display.common import PaletteEntry
    from urwid.widget import AbstractWidget

    from .abstract_loop import EventLoop

    _T = typing.TypeVar("_T")
    _Spec = ParamSpec("_Spec")

    class _ExternalLoopScreen(typing.Protocol):
        """Screen able to drive an external event loop (e.g. raw_display / curses screens).

        These members are not part of :class:`BaseScreen`;
        :class:`MainLoop` only uses them after guarding with ``hasattr``
        (or after :meth:`MainLoop.start` raised :exc:`CantUseExternalLoop`),
        so accessing them through this protocol via ``cast`` is safe.
        """

        signal_handler_setter: Callable[..., typing.Any]

        def hook_event_loop(
            self,
            event_loop: EventLoop,
            callback: Callable[[list[str | tuple[str, int, int, int]], list[int]], typing.Any],
        ) -> None:
            """Register `callback` with `event_loop` to be called when input is available."""

        def unhook_event_loop(self, event_loop: EventLoop) -> None:
            """Remove the input callback previously registered with `event_loop`."""

        def get_input(self, raw_keys: Literal[True]) -> tuple[list[str | tuple[str, int, int, int]], list[int]]:
            """Return the input received since the last call, alongside its raw key codes."""
            ...

        def set_input_timeouts(self, max_wait: float | None = ...) -> None:
            """Set the maximum time to wait for input before returning, in seconds."""

    class _EventLoopWithAlarmsStore(typing.Protocol):
        """Event loop that stores its alarms and watched files (like :class:`SelectEventLoop`).

        Not all event loops store them.
        """

        _alarms: list[tuple[float, int, Callable[[], typing.Any]]]
        _watch_files: dict[int, Callable[[], typing.Any]]


IS_WINDOWS = sys.platform == "win32"
PIPE_BUFFER_READ_SIZE = 4096  # can expect this much on Linux, so try for that
# Seconds between checks of watched files while a screen without event loop support waits for input:
# its get_input() cannot wait on other descriptors.
_SCREEN_LOOP_WATCH_POLL: typing.Final = 0.1
# Calls run by one pass of MainLoop.call_from_thread() work; the event loop serves input and alarms between passes.
_THREAD_CALLS_PER_PASS: typing.Final = 64
_NOT_RUNNING: typing.Final = "the urwid MainLoop is not running"

__all__ = ("CantUseExternalLoop", "MainLoop", "get_running_loop", "get_running_loop_or_none")


class _Activation:
    """One entry of the running-loop stack, shared by every context that copied the tuple holding it.

    Ending an entry clears :attr:`loop`, which ends it in all of those contexts at once and releases the loop.
    """

    __slots__ = ("__weakref__", "loop", "previous", "running")

    def __init__(self, loop: MainLoop, *, running: bool, previous: _Activation | None = None) -> None:
        self.loop: MainLoop | None = loop  # None once the entry ended: lookups skip it
        self.running: typing.Final = running  # False: a mask, which hides every entry below it
        self.previous = previous  # the start entry of the same loop that this one is nested in


class _ThreadCalls:
    """Calls handed to a running :class:`MainLoop` from other threads, for one run of the loop.

    A sender keeps the object it found, so a call made across :meth:`MainLoop.stop` lands in the deque of the ended
    run, which nothing reads any more, and never in the deque of a later run.
    """

    __slots__ = ("__weakref__", "active", "calls", "drawn", "handle", "reader", "writer")

    def __init__(self, reader: socket.socket, writer: socket.socket) -> None:
        # append() and popleft() of a deque are atomic, so neither a thread nor a signal handler takes a lock.
        self.calls: deque[Callable[[], object]] = deque()
        self.reader: typing.Final = reader  # watched by the event loop; one byte is sent per wake-up
        self.writer: typing.Final = writer
        self.handle: typing.Any = None  # the event loop's watch of reader
        self.active = True  # False once the run ended: a pass in progress stops after its current call
        self.drawn = True  # the screen was drawn since the last pass


# Immutable tuples: a mutable default would be shared by every context of the process.
_running: typing.Final[contextvars.ContextVar[tuple[_Activation, ...]]] = contextvars.ContextVar(
    "urwid_running_loops",
    default=(),
)


def get_running_loop_or_none() -> MainLoop | None:
    """Return the :class:`MainLoop` running in the current thread or task, or ``None`` when there is none.

    A loop is running between its :meth:`~MainLoop.start` (or :meth:`~MainLoop.run`) and its :meth:`~MainLoop.stop`.
    It is also the running loop inside every alarm, watch, input and render call it makes,
    and inside :meth:`~MainLoop.draw_screen` and :meth:`~MainLoop.process_input` called by hand.
    A context copied from one where the loop runs sees it too, until the loop stops.

    >>> print(get_running_loop_or_none())
    None
    """
    for entry in reversed(_running.get()):
        if (loop := entry.loop) is not None:
            return loop if entry.running else None
    return None


def get_running_loop() -> MainLoop:
    """Return the :class:`MainLoop` running in the current thread or task.

    It is the loop :func:`get_running_loop_or_none` finds.

    :raises RuntimeError: no loop is running in the current thread or task.
    """
    if (loop := get_running_loop_or_none()) is None:
        raise RuntimeError("no urwid MainLoop is running in this thread or task")
    return loop


class CantUseExternalLoop(Exception):
    """Raised when an event loop given to :class:`MainLoop` cannot be reused as an external loop."""


class MainLoop:
    """This is the standard main loop implementation for a single interactive session.

    :param widget: the topmost widget used for painting the screen, stored as
                   :attr:`widget` and may be modified. Must be a box widget.

    :param palette: initial palette for screen

    :param screen: screen to use, default is a new :class:`display.raw.Screen`
                   instance; stored as :attr:`screen`

    :param handle_mouse: ``True`` to ask :attr:`.screen` to process mouse events

    :param input_filter: a function to filter input before sending it to
                   :attr:`.widget`, called from :meth:`.input_filter`

    :param unhandled_input: a function called when input is not handled by
                            :attr:`.widget`, called from :meth:`.unhandled_input`

    :param event_loop: if :attr:`.screen` supports external an event loop it may be
                       given here, default is a new :class:`SelectEventLoop` instance;
                       stored as :attr:`.event_loop`

    :param pop_ups: `True` to wrap :attr:`.widget` with a :class:`PopUpTarget`
                    instance to allow any widget to open a pop-up anywhere on the screen;
                    required by :class:`DropDown` and other :class:`PopUpLauncher` widgets


    .. attribute:: screen

        The screen object this main loop uses for screen updates and reading input

    .. attribute:: event_loop

        The event loop object this main loop uses for waiting on alarms and IO

    .. note::
        Some :attr:`event_loop` implementations accept an ``async def`` callback in addition to a
        plain callable - see the specific implementation's own documentation for whether it does,
        and how it runs one. :meth:`set_alarm_in`, :meth:`set_alarm_at`, :meth:`watch_file` and
        :meth:`watch_pipe` all detect an ``async def`` callback and pass that detection through to
        :attr:`event_loop`; whether it actually does anything still depends on :attr:`event_loop`.
    """

    __slots__ = (
        "__dict__",
        "__weakref__",
        "_activation",
        "_input_filter",
        "_pop_ups",
        "_thread_calls",
        "_topmost_widget",
        "_unhandled_input",
        "_watch_pipes",
        "_widget",
        "event_loop",
        "handle_mouse",
        "idle_handle",
        "logger",
        "screen",
        "screen_size",
    )

    def __init__(
        self,
        widget: AbstractWidget,
        palette: Iterable[PaletteEntry] = (),
        screen: BaseScreen | None = None,
        handle_mouse: bool = True,
        input_filter: (
            Callable[[list[str | tuple[str, int, int, int]], list[int]], list[str | tuple[str, int, int, int]]] | None
        ) = None,
        unhandled_input: Callable[[str | tuple[str, int, int, int]], bool | None] | None = None,
        event_loop: EventLoop | None = None,
        pop_ups: bool = False,
    ) -> None:
        """
        Set up the main loop around a top-level widget, a screen and an event loop.

        :raises NotImplementedError: an *event_loop* is given but *screen* does not support external event loops.
        """
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self._widget = widget
        self._topmost_widget = widget
        self.handle_mouse = handle_mouse
        self._pop_ups = False  # only initialize placeholder
        self.pop_ups = pop_ups  # triggers property setting side-effect

        if not screen:
            screen = display.raw.Screen()

        if palette:
            screen.register_palette(palette)

        self.screen: BaseScreen = screen
        self.screen_size: tuple[int, int] | None = None

        self._unhandled_input = unhandled_input
        self._input_filter = input_filter

        if not hasattr(screen, "hook_event_loop") and event_loop is not None:
            raise NotImplementedError(f"screen object passed {screen!r} does not support external event loops")
        if event_loop is None:
            event_loop = SelectEventLoop()
        self.event_loop: EventLoop = event_loop
        self.idle_handle: typing.Any = None

        if hasattr(self.screen, "signal_handler_setter"):
            # Tell the screen what function it must use to set
            # signal handlers
            typing.cast("_ExternalLoopScreen", self.screen).signal_handler_setter = self.event_loop.set_signal_handler

        # write end -> (event loop watch handle, read end)
        self._watch_pipes: dict[int, tuple[typing.Any, int]] = {}
        # set from start() to stop(): the entry that makes this loop the running loop
        self._activation: _Activation | None = None
        # set while the loop runs: the calls other threads hand over through call_from_thread()
        self._thread_calls: _ThreadCalls | None = None

    @property
    def widget(self) -> AbstractWidget:
        """Property for the topmost widget used to draw the screen.

        This must be a box widget.
        """
        return self._widget

    @widget.setter
    def widget(self, widget: AbstractWidget) -> None:
        self._widget = widget
        if self.pop_ups and hasattr(self._topmost_widget, "original_widget"):
            # pyrefly: ignore[missing-attribute]  # hasattr() does not narrow
            self._topmost_widget.original_widget = self._widget
        else:
            self._topmost_widget = self._widget

    @property
    def pop_ups(self) -> bool:
        """Return whether pop-up widgets opened via :class:`PopUpLauncher` are shown automatically."""
        return self._pop_ups

    @pop_ups.setter
    def pop_ups(self, pop_ups: bool) -> None:
        self._pop_ups = pop_ups
        if pop_ups:
            self._topmost_widget = PopUpTarget(self._widget)
        else:
            self._topmost_widget = self._widget

    def _make_alarm_callback(
        self,
        callback: Callable[[Self, _T | None], typing.Any],
        user_data: _T | None,
    ) -> Callable[[], typing.Any]:
        """Wrap *callback* for :attr:`event_loop`, preserving ``async def`` support.

        An event loop implementation that supports scheduling an ``async def`` callback
        detects it by checking the callback it is directly given, so the wrapper returned
        here has to be an ``async def`` function itself whenever *callback* is one.

        :param callback: function to call with this main loop object and *user_data*
        :param user_data: user data to pass to *callback*
        :returns: a zero-argument callback suitable for :meth:`EventLoop.alarm`
        """
        if inspect.iscoroutinefunction(callback):

            async def cb() -> None:
                with self._as_running():
                    try:
                        await callback(self, user_data)
                    except ExitMainLoop:
                        raise
                    except Exception:
                        self.logger.exception("Unhandled exception in alarm callback %r", callback)

        else:

            def cb() -> None:  # type: ignore[misc]  # intentionally the sync variant of the branch above
                with self._as_running():
                    try:
                        callback(self, user_data)
                    except ExitMainLoop:
                        raise
                    except Exception:
                        self.logger.exception("Unhandled exception in alarm callback %r", callback)

        return cb

    def set_alarm_in(
        self,
        sec: float,
        callback: Callable[[Self, _T | None], typing.Any],
        user_data: _T | None = None,
    ) -> typing.Any:
        """Schedule an alarm in *sec* seconds that will call *callback* from the within the :meth:`run` method.

        :param sec: seconds until alarm
        :param callback: function to call with two parameters: this main loop
                         object and *user_data*
        :param user_data: optional user data to pass to the callback
        :returns: a handle that may be passed to :meth:`remove_alarm`.

        .. note::
            *callback* may be an ``async def`` function on an :attr:`event_loop`
            implementation that supports one; see the note on :class:`MainLoop`.

        .. note::
            *callback* is called as ``callback(loop, user_data)``.
            Exceptions raised by *callback* (for example from a callback
            declared with the wrong signature) are logged with their
            traceback, naming the callback, and do not stop the loop.
            :exc:`ExitMainLoop` still exits the loop as usual.
        """
        self.logger.debug(f"Setting alarm in {sec!r} seconds with callback {callback!r}")
        return self.event_loop.alarm(sec, self._make_alarm_callback(callback, user_data))

    def set_alarm_at(
        self,
        tm: float,
        callback: Callable[[Self, _T | None], typing.Any],
        user_data: _T | None = None,
    ) -> typing.Any:
        """Schedule an alarm at *tm* time that will call *callback* from the within the :meth:`run` function.

        :param tm: time to call callback e.g. ``time.time() + 5``
        :param callback: function to call with two parameters: this main loop
                         object and *user_data*
        :param user_data: optional user data to pass to the callback
        :returns: a handle that may be passed to :meth:`remove_alarm`.

        .. note::
            *callback* may be an ``async def`` function on an :attr:`event_loop`
            implementation that supports one; see the note on :class:`MainLoop`.

        .. note::
            Exceptions raised by *callback* are logged with their traceback,
            naming the callback, and do not stop the loop.
            :exc:`ExitMainLoop` still exits the loop as usual.
        """
        sec = tm - time.time()
        self.logger.debug(f"Setting alarm in {sec!r} seconds with callback {callback!r}")
        return self.event_loop.alarm(sec, self._make_alarm_callback(callback, user_data))

    def remove_alarm(self, handle: typing.Any) -> bool:
        """Remove an alarm. Return ``True`` if *handle* was found, ``False`` otherwise."""
        return self.event_loop.remove_alarm(handle)

    if not IS_WINDOWS and sys.implementation.name != "graalpy":

        def watch_pipe(self, callback: Callable[[bytes], bool | None]) -> int:
            """Create a pipe used by another thread or subprocess to trigger *callback* in the main loop.

            :param callback: function taking one parameter to call from within the process/thread running the main loop

            This method returns a file descriptor attached to the write end of a pipe.
            The read end of the pipe is added to the list of files :attr:`event_loop` is watching.
            When data is written to the pipe the callback function will be called
            and passed a single value containing data read from the pipe.

            This method may be used any time you want to update widgets from a subprocess.
            Another thread hands work to the loop with :meth:`call_from_thread` instead.

            Data may be written to the returned file descriptor with ``os.write(fd, data)``.
            Ensure that data is less than 512 bytes (or 4K on Linux)
            so that the callback will be triggered just once with the complete value of data passed in.

            If the callback returns ``False`` then the watch will be removed from :attr:`event_loop`
            and the read end of the pipe will be closed.
            The same happens once every write end is closed: the callback then receives ``b""`` one last time.
            You are responsible for closing the write end of the pipe with ``os.close(fd)``.

            .. note::
                *callback* may be an ``async def`` function on an :attr:`event_loop`
                implementation that supports one; see the note on :class:`MainLoop`.
            """
            import fcntl

            pipe_rd, pipe_wr = os.pipe()
            fcntl.fcntl(pipe_rd, fcntl.F_SETFL, os.O_NONBLOCK)
            entry: tuple[typing.Any, int] | None = None

            # A callback acts only while its own entry is registered: once remove_watch_pipe() closed the read end,
            # its descriptor number may already belong to another file.
            if inspect.iscoroutinefunction(callback):

                async def cb() -> None:
                    if self._watch_pipes.get(pipe_wr) is not entry:
                        return
                    try:
                        data = os.read(pipe_rd, PIPE_BUFFER_READ_SIZE)
                    except BlockingIOError:
                        return  # a task started by an earlier wake-up already read the data
                    with self._as_running():
                        if not data:
                            # Removed before awaiting: the pipe stays readable at its end, starting a task per pass.
                            self.remove_watch_pipe(pipe_wr)
                            await callback(data)
                        elif await callback(data) is False and self._watch_pipes.get(pipe_wr) is entry:
                            self.remove_watch_pipe(pipe_wr)

            else:

                def cb() -> None:  # type: ignore[misc]  # intentionally the sync variant of the branch above
                    if self._watch_pipes.get(pipe_wr) is not entry:
                        return
                    data = os.read(pipe_rd, PIPE_BUFFER_READ_SIZE)
                    with self._as_running():
                        if (callback(data) is False or not data) and self._watch_pipes.get(pipe_wr) is entry:
                            self.remove_watch_pipe(pipe_wr)

            # An entry left under this number belongs to a write end the caller has closed since.
            self.remove_watch_pipe(pipe_wr)
            entry = (self.event_loop.watch_file(pipe_rd, cb), pipe_rd)
            self._watch_pipes[pipe_wr] = entry
            return pipe_wr

        def remove_watch_pipe(self, write_fd: int) -> bool:
            """
            Close the read end of the pipe and remove the watch created by :meth:`watch_pipe`.

            :returns: ``True`` if the watch pipe exists, ``False`` otherwise

            .. note:: You are responsible for closing the write end of the pipe.
            """
            try:
                watch_handle, pipe_rd = self._watch_pipes.pop(write_fd)
            except KeyError:
                return False

            self.event_loop.remove_watch_file(watch_handle)
            os.close(pipe_rd)
            return True

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> typing.Any:
        """Call *callback* when *fd* has some data to read. No parameters are passed to callback.

        :returns: a handle that may be passed to :meth:`remove_watch_file`.

        .. note::
            *callback* may be an ``async def`` function on an :attr:`event_loop`
            implementation that supports one; see the note on :class:`MainLoop`.

        .. note::
            On Windows, with a screen that has no event loop support, such as the curses screen,
            *fd* is checked only after the screen returned input, as expired alarms are.
        """
        self.logger.debug(f"Setting watch file descriptor {fd!r} with {callback!r}")
        if inspect.iscoroutinefunction(callback):

            async def cb() -> typing.Any:
                with self._as_running():
                    return await callback()

        else:

            def cb() -> typing.Any:  # type: ignore[misc]  # intentionally the sync variant of the branch above
                with self._as_running():
                    return callback()

        return self.event_loop.watch_file(fd, cb)

    def remove_watch_file(self, handle: typing.Any) -> bool:
        """Remove a watch file. Returns ``True`` if the watch file exists, ``False`` otherwise."""
        return self.event_loop.remove_watch_file(handle)

    def call_from_thread(
        self,
        callback: Callable[_Spec, object],
        /,
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> None:
        """Run ``callback(*args, **kwargs)`` on the thread running the event loop, soon.

        Safe to call from any thread, and from a signal handler.
        A signal handler catches the :exc:`RuntimeError`: the signal can arrive while the loop stops.
        The callback runs on the loop thread with this loop as the running loop, like an alarm callback:

        - a widget it changes is drawn on the way back to idle;
        - :exc:`ExitMainLoop` raised by it stops the loop;
        - any other exception is logged, and the loop goes on.

        Calls run in the order they were made.
        Called on the loop thread itself, it defers the callback the same way instead of running it at once.
        Calls still queued when the loop stops are dropped.
        With a screen that has no event loop support, such as the curses screen, a call waits up to 0.1 seconds,
        and on Windows until the next input.

        :raises TypeError: *callback* is an ``async def`` function, which this method cannot await.
        :raises RuntimeError: the loop is not running: before :meth:`start` or :meth:`run`, or after :meth:`stop`.
        """
        if inspect.iscoroutinefunction(callback):
            msg = f"call_from_thread() cannot await {callback!r}"
            raise TypeError(msg)
        if (state := self._thread_calls) is None:
            raise RuntimeError(_NOT_RUNNING)
        state.calls.append(functools.partial(callback, *args, **kwargs))
        with suppress(BlockingIOError):  # a full buffer means wake-ups are already pending
            state.writer.send(b"\0")
        if not state.active:
            # The loop stopped since the state was read, and the call sits in the deque of the ended run.
            raise RuntimeError(_NOT_RUNNING)

    def _open_thread_calls(self) -> None:
        """Start accepting :meth:`call_from_thread` calls, unless a run of this loop already does."""
        if self._thread_calls is not None:
            return
        # A socket pair rather than a pipe: select() on Windows takes sockets only.
        reader, writer = socket.socketpair()
        try:
            reader.setblocking(False)
            writer.setblocking(False)
            state = _ThreadCalls(reader, writer)
            state.handle = self.event_loop.watch_file(reader.fileno(), functools.partial(self._run_thread_calls, state))
        except BaseException:
            reader.close()
            writer.close()
            raise
        # Closed once nothing holds the state, so no sender is inside send(): a send() on a closed or shut down socket
        # would write into a reused descriptor number, or raise SIGPIPE where the application restored its default.
        weakref.finalize(state, reader.close)
        weakref.finalize(state, writer.close)
        self._thread_calls = state

    def _close_thread_calls(self) -> None:
        """Stop accepting :meth:`call_from_thread` calls and drop the calls still queued."""
        if (state := self._thread_calls) is None:
            return
        try:
            self._thread_calls = None
            state.active = False
            self.event_loop.remove_watch_file(state.handle)
        finally:
            state.calls.clear()

    def _run_thread_calls(self, state: _ThreadCalls) -> None:
        """Run up to :data:`_THREAD_CALLS_PER_PASS` calls that :meth:`call_from_thread` queued.

        Calls left in the deque get a new wake-up, so the event loop serves input and alarms before running them.
        """
        with suppress(BlockingIOError):
            state.reader.recv(PIPE_BUFFER_READ_SIZE)
        if not state.active:
            return  # dispatched after the run ended
        try:
            # The select loop goes idle, and draws, only when no descriptor is ready:
            # under a stream of calls a pass that follows a pass draws first.
            if not state.drawn:
                self.entering_idle()
            state.drawn = False
            with self._as_running():
                for _ in range(_THREAD_CALLS_PER_PASS):
                    try:
                        call = state.calls.popleft()
                    except IndexError:
                        break
                    try:
                        call()
                    except ExitMainLoop:
                        raise
                    except Exception:
                        self.logger.exception("Unhandled exception in callback %r called from a thread", call)
                    if not state.active:
                        break  # a call stopped the loop
        finally:
            # Also after ExitMainLoop: an event loop the application runs itself may go on.
            if state.active and state.calls:
                with suppress(BlockingIOError):
                    state.writer.send(b"\0")

    def run(self) -> None:
        """Start the main loop handling input events and updating the screen.

        The loop will continue until an :exc:`ExitMainLoop` exception is raised.

        If you would prefer to manage the event loop yourself, don't use this
        method.  Instead, call :meth:`start` before starting the event loop,
        and :meth:`stop` once it's finished.
        """
        with suppress(ExitMainLoop):
            self._run()

    def _test_run(self) -> None:
        """Doctest for :meth:`run`.

        >>> w = _refl("widget")  # _refl prints out function calls
        >>> w.render_rval = "fake canvas"  # *_rval is used for return values
        >>> scr = _refl("screen")
        >>> scr.get_input_descriptors_rval = [42]
        >>> scr.get_cols_rows_rval = (20, 10)
        >>> scr.started = True
        >>> scr._urwid_signals = {}
        >>> evl = _refl("event_loop")
        >>> evl.enter_idle_rval = 1
        >>> evl.watch_file_rval = 2
        >>> ml = MainLoop(w, [], scr, event_loop=evl)
        >>> ml.run()  # doctest:+ELLIPSIS
        screen.start()
        screen.set_mouse_tracking()
        screen.unhook_event_loop(...)
        screen.hook_event_loop(...)
        event_loop.watch_file(..., functools.partial(<bound method MainLoop._run_thread_calls...>, ...))
        event_loop.enter_idle(<bound method MainLoop.entering_idle...>)
        event_loop.run()
        event_loop.remove_watch_file(2)
        event_loop.remove_enter_idle(1)
        screen.unhook_event_loop(...)
        screen.stop()
        >>> ml.draw_screen()  # doctest:+ELLIPSIS
        screen.get_cols_rows()
        widget.render((20, 10), focus=True)
        screen.draw_screen((20, 10), 'fake canvas')
        """

    def start(self) -> StoppingContext:
        """Set up the main loop, hooking into the event loop where necessary.

        Starts the :attr:`screen` if it hasn't already been started.

        If you want to control starting and stopping the event loop yourself,
        you should call this method before starting, and call `stop` once the
        loop has finished.  You may also use this method as a context manager,
        which will stop the loop automatically at the end of the block:

            with main_loop.start():
                ...

        Note that some event loop implementations don't handle exceptions
        specially if you manage the event loop yourself.  In particular, the
        Twisted and asyncio loops won't stop automatically when
        :exc:`ExitMainLoop` (or anything else) is raised.

        Once started, the loop is what :func:`get_running_loop` returns in the caller's thread and task,
        and in everything that copies their context, and it accepts :meth:`call_from_thread`.

        :raises CantUseExternalLoop: the screen does not support external event loops.
        """
        self.logger.debug(f"Starting event loop {self.event_loop.__class__.__name__!r} to manage display.")

        self.screen.start()

        if self.handle_mouse:
            self.screen.set_mouse_tracking()

        if not hasattr(self.screen, "hook_event_loop"):
            raise CantUseExternalLoop(f"Screen {self.screen!r} doesn't support external event loops")

        with suppress(NameError):
            signals.connect_signal(self.screen, INPUT_DESCRIPTORS_CHANGED, self._reset_input_descriptors)

        # watch our input descriptors
        self._reset_input_descriptors()
        self._open_thread_calls()
        self.idle_handle = self.event_loop.enter_idle(self.entering_idle)

        # the screen is redrawn automatically after input and alarms,
        # however, there can be none of those at the start,
        # so draw the initial screen here unconditionally
        self.event_loop.alarm(0, self.entering_idle)

        self._activate()
        return StoppingContext(self)

    def stop(self) -> None:
        """Clean up any hooks added to the event loop.

        Only call this if you're managing the event loop yourself, after the loop stops.

        The loop stops being the running loop everywhere :meth:`start` made it one, also when a cleanup step raises.
        """
        try:
            self._stop_hooks()
        finally:
            self._deactivate()

    def _stop_hooks(self) -> None:
        """Remove the hooks :meth:`start` added to the event loop and stop the screen."""
        try:
            self._close_thread_calls()
        finally:
            self.event_loop.remove_enter_idle(self.idle_handle)
            self.idle_handle = None
            signals.disconnect_signal(self.screen, INPUT_DESCRIPTORS_CHANGED, self._reset_input_descriptors)
            typing.cast("_ExternalLoopScreen", self.screen).unhook_event_loop(self.event_loop)

            self.screen.stop()

    @contextmanager
    def paused(self) -> Iterator[None]:
        """Hand the terminal to another program for the duration of the block.

        The :attr:`screen` is stopped on entry, which gives the terminal back its normal mode and buffer
        and stops reading its input, and is started again on exit, also when the block raises.
        On exit the mouse tracking is restored when :attr:`handle_mouse` is set,
        the screen is cleared and the screen size is read again, so the next draw repaints all of it
        at the terminal's current size.
        A screen that is not started is left alone on both sides of the block.
        The screen is restarted the way :meth:`start` starts it:
        an application that started its screen with ``alternate_buffer=False`` comes back in the alternate buffer.

        Run an editor on a file:

        >>> editor = shlex.split(os.environ.get("EDITOR", "")) or ["vi"]  # doctest: +SKIP
        >>> with loop.paused():  # doctest: +SKIP
        ...     subprocess.run([*editor, path], check=False)

        The block runs in the event loop's thread and holds it until the block ends,
        so no input, alarm or watched file is handled meanwhile: the terminal belongs to the other program.

        .. important::
            Call it only from the thread running the event loop, like every other widget and screen change.

        .. warning::
            Do not use it with the web display, :class:`urwid.display.web.Screen`, which has no terminal to hand over:
            stopping it ends the browser session, and starting it again reads a new client request from standard input.
        """
        was_started = self.screen.started
        if was_started:
            self.screen.stop()
        try:
            yield
        finally:
            if was_started:
                self.screen.start()
                if self.handle_mouse:
                    self.screen.set_mouse_tracking()
                self.screen.clear()
                self.screen_size = None

    def _activate(self) -> None:
        """Make this loop the running loop of the current context until :meth:`_deactivate`."""
        self._activation = _Activation(self, running=True, previous=self._activation)
        _running.set((*(entry for entry in _running.get() if entry.loop is not None), self._activation))

    def _deactivate(self) -> None:
        """End the entry of the latest :meth:`_activate` in every context holding it.

        Nothing happens when there is no such entry.
        """
        if (activation := self._activation) is None:
            return
        self._activation = activation.previous
        activation.loop = activation.previous = None
        if activation in (entries := _running.get()):
            _running.set(tuple(entry for entry in entries if entry.loop is not None))

    @contextmanager
    def _as_running(self, *, explicit: bool = False) -> Generator[None]:
        """Make this loop the running loop of the current context for the duration of the block.

        A loop callback (*explicit* false) pushes a mask under the start entry,
        so a callback that runs after :meth:`stop`, or goes on after it, sees no running loop.
        An explicit call pushes the start entry,
        or a temporary entry when the loop is not started, so a render or input fed by hand finds the loop.
        It pushes nothing when the loop stopped during a callback of its own that is still running.
        """
        entries = tuple(entry for entry in _running.get() if entry.loop is not None)
        activation = self._activation
        ended: _Activation | None = None  # the entry this block creates, ended on exit
        if not explicit:
            ended = _Activation(self, running=False)
            entries = (*entries, ended)
        elif activation is None and not (entries and entries[-1].loop is self and not entries[-1].running):
            activation = ended = _Activation(self, running=True)
        if activation is not None:
            entries = (*entries, activation)
        token = _running.set(entries)
        try:
            yield
        finally:
            if ended is not None:
                ended.loop = None
            # A suspended async callback closed by the garbage collector ends here in another context,
            # whose value this block never set and must not change.
            with suppress(ValueError):
                _running.reset(token)

    def _reset_input_descriptors(self) -> None:
        screen = typing.cast("_ExternalLoopScreen", self.screen)
        screen.unhook_event_loop(self.event_loop)
        screen.hook_event_loop(self.event_loop, self._update)

    def _run(self) -> None:
        try:
            self.start()
        except CantUseExternalLoop:
            self._activate()
            try:
                self._open_thread_calls()
                self._run_screen_event_loop()
                return
            finally:
                try:
                    self._close_thread_calls()
                finally:
                    self._deactivate()
                    self.screen.stop()
        except BaseException:
            # start() may have failed after starting the screen or hooking the event loop.
            # It raised before making the loop the running one, so an enclosing run stays the running one.
            self._stop_hooks()
            raise

        try:
            self.event_loop.run()
        finally:
            self.stop()

    def _update(self, keys: list[str | tuple[str, int, int, int]], raw: list[int]) -> None:
        """Filter *keys* and pass them to :meth:`process_input`, resetting :attr:`screen_size` on a window resize.

        >>> w = _refl("widget")
        >>> w.selectable_rval = True
        >>> w.mouse_event_rval = True
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (15, 5)
        >>> evl = _refl("event_loop")
        >>> ml = MainLoop(w, [], scr, event_loop=evl)
        >>> ml._input_timeout = "old timeout"
        >>> ml._update(["y"], [121])  # doctest:+ELLIPSIS
        screen.get_cols_rows()
        widget.selectable()
        widget.keypress((15, 5), 'y')
        >>> ml._update([("mouse press", 1, 5, 4)], [])
        widget.mouse_event((15, 5), 'mouse press', 1, 5, 4, focus=True)
        >>> ml._update([], [])
        """
        with self._as_running():
            if keys := self.input_filter(keys, raw):
                self.process_input(keys)
                if "window resize" in keys:
                    self.screen_size = None

    def _run_screen_event_loop(self) -> None:
        """Run the screen event loop, used when the screen does not support using external event loops.

        The alarms and watched files stored in the SelectEventLoop in :attr:`event_loop` are handled by this method.
        While a file is watched, the wait for input is cut into polls, except on Windows,
        where the curses screen cannot stop waiting before a key arrives.
        """
        # pylint: disable=protected-access  # special case for alarms and watched files handling
        self.logger.debug(f"Starting screen {self.screen!r} event loop")

        screen = typing.cast("_ExternalLoopScreen", self.screen)
        event_loop = typing.cast("_EventLoopWithAlarmsStore", self.event_loop)

        # The alarms stay in the heap until they run, so a callback can add an earlier alarm or remove a pending one.
        alarms = event_loop._alarms
        watch_files = event_loop._watch_files

        while True:
            self.draw_screen()

            keys: list[str | tuple[str, int, int, int]] = []
            raw: list[int] = []
            while not keys:
                timeout = max(0.0, alarms[0][0] - time.monotonic()) if alarms else None
                if watch_files and not IS_WINDOWS:
                    timeout = _SCREEN_LOOP_WATCH_POLL if timeout is None else min(timeout, _SCREEN_LOOP_WATCH_POLL)
                screen.set_input_timeouts(timeout)
                keys, raw = screen.get_input(True)

                watch_ran = False
                if watch_files:
                    with _selectors.read_selector(watch_files.items()) as selector:
                        ready = selector.select(0)
                    for record, _events in ready:
                        # An earlier callback in this pass may have removed or replaced the watch and closed its fd.
                        callback = watch_files.get(typing.cast("int", record.fileobj))
                        if callback is not None and callback is record.data:
                            callback()
                            watch_ran = True
                if not keys and (watch_ran or (alarms and alarms[0][0] <= time.monotonic())):
                    break

            if keys := self.input_filter(keys, raw):
                self.process_input(keys)

            while alarms and alarms[0][0] <= time.monotonic():
                _tm, _tie_break, callback = heapq.heappop(alarms)
                callback()

            if "window resize" in keys:
                self.screen_size = None

    def _test_run_screen_event_loop(self) -> None:
        """Doctest for :meth:`_run_screen_event_loop`.

        >>> w = _refl("widget")
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (10, 5)
        >>> scr.get_input_rval = [], []
        >>> ml = MainLoop(w, screen=scr)
        >>> def stop_now(loop, data):
        ...     raise ExitMainLoop
        >>> handle = ml.set_alarm_in(0, stop_now)
        >>> try:
        ...     ml._run_screen_event_loop()
        ... except ExitMainLoop:
        ...     pass
        screen.get_cols_rows()
        widget.render((10, 5), focus=True)
        screen.draw_screen((10, 5), None)
        screen.set_input_timeouts(0.0)
        screen.get_input(True)
        """

    def process_input(self, keys: Iterable[str | tuple[str, int, int, int]]) -> bool:
        """Pass keyboard input and mouse events to :attr:`widget`.

        This method is called automatically from the :meth:`run` method when
        there is input, but may also be called to simulate input from the user.

        *keys* is a list of input returned from :attr:`screen`'s get_input() method or its event loop hook.
        The widgets handle it with this loop as the running loop, also when the loop is not started.

        :returns: ``True`` if any key was handled by a widget or the :meth:`unhandled_input` method.
        :raises TypeError: an item of *keys* is neither a key name nor a mouse event tuple.
        """
        with self._as_running(explicit=True):
            self.logger.debug(f"Processing input: keys={keys!r}")
            if not self.screen_size:
                self.screen_size = self.screen.get_cols_rows()

            something_handled = False

            for key in keys:
                if key == "window resize":
                    continue

                # a handler of an earlier key may have paused the loop, which drops the screen size
                if not self.screen_size:
                    self.screen_size = self.screen.get_cols_rows()

                if isinstance(key, str):
                    if self._topmost_widget.selectable():
                        if handled_key := self._topmost_widget.keypress(self.screen_size, key):
                            key = handled_key  # noqa: PLW2901

                        else:
                            something_handled = True
                            continue

                elif is_mouse_event(key):
                    event, button, col, row = key
                    if hasattr(self._topmost_widget, "mouse_event") and self._topmost_widget.mouse_event(
                        self.screen_size,
                        event,
                        button,
                        col,
                        row,
                        focus=True,
                    ):
                        something_handled = True
                        continue

                else:
                    raise TypeError(f"{key!r} is not str | tuple[str, int, int, int]")

                if key:
                    if command_map[key] == Command.REDRAW_SCREEN:  # type: ignore[index]  # not `str` is mouse event
                        self.screen.clear()
                        something_handled = True
                    else:
                        something_handled |= bool(self.unhandled_input(key))
                else:
                    something_handled = True

            return something_handled

    def _test_process_input(self) -> None:
        """Doctest for :meth:`process_input`.

        >>> w = _refl("widget")
        >>> w.selectable_rval = True
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (10, 5)
        >>> ml = MainLoop(w, [], scr)
        >>> ml.process_input(["enter", ("mouse drag", 1, 14, 20)])
        screen.get_cols_rows()
        widget.selectable()
        widget.keypress((10, 5), 'enter')
        widget.mouse_event((10, 5), 'mouse drag', 1, 14, 20, focus=True)
        True
        """

    def input_filter(
        self,
        keys: list[str | tuple[str, int, int, int]],
        raw: list[int],
    ) -> list[str | tuple[str, int, int, int]]:
        """Pass each of the input events and raw keystroke values through *input_filter*.

        These values are passed to the *input_filter* function passed to the constructor. That function must
        return a list of keys to be passed to the widgets to handle. If no *input_filter* was defined this
        implementation will return all the input events.
        """
        if self._input_filter:
            return self._input_filter(keys, raw)
        return keys

    def unhandled_input(self, data: str | tuple[str, int, int, int]) -> bool | None:
        """Call the *unhandled_input* function passed to the constructor with any input not handled by the widgets.

        If no *unhandled_input* was defined then the input will be ignored.

        *input* is the keyboard or mouse input.

        The *unhandled_input* function should return ``True`` if it handled
        the input.
        """
        if self._unhandled_input:
            return self._unhandled_input(data)
        return False

    def entering_idle(self) -> None:
        """Call :meth:`draw_screen` to update the screen when anything has changed.

        This method is called whenever the event loop is about to enter the idle state.
        """
        with self._as_running():
            if self.screen.started:
                self.draw_screen()
            else:
                self.logger.debug(f"No redrawing screen: {self.screen!r} is not started.")

    def draw_screen(self) -> None:
        """Render the widgets and paint the screen.

        This method is called automatically from :meth:`entering_idle`, which runs whenever the
        event loop is about to go idle -- including after handling input
        and after an alarm callback fires. So screen updates made from
        input handlers or alarm callbacks are redrawn automatically.

        If you modify the widgets displayed from a callback that does not go through the event loop's idle handling,
        you will need to call this method yourself to repaint the screen.

        .. important::
            Call it only from the thread running the event loop, like every other widget and screen change.
            Another thread hands the work over with :meth:`call_from_thread` instead.

        The widgets render with this loop as the running loop, also when the loop is not started.
        """
        with self._as_running(explicit=True):
            if (thread_calls := self._thread_calls) is not None:
                thread_calls.drawn = True
            if not self.screen_size:
                self.screen_size = self.screen.get_cols_rows()
                self.logger.debug(f"Screen size recalculated: {self.screen_size!r}")

            canvas = self._topmost_widget.render(self.screen_size, focus=True)
            self.screen.draw_screen(self.screen_size, canvas)


def _refl(name: str, rval: _T | None = None, loop_exit: bool = False) -> Callable[..., _T | typing.Any]:
    """Build a reflection helper used to test the main loop classes.

    >>> scr = _refl("screen")
    >>> scr.function("argument")
    screen.function('argument')
    >>> scr.callme(when="now")
    screen.callme(when='now')
    >>> scr.want_something_rval = 42
    >>> x = scr.want_something()
    screen.want_something()
    >>> x
    42

    """

    class Reflect:
        """Callable stand-in that records its calls and returns a fixed value."""

        def __init__(self, name: str, rval: typing.Any = None) -> None:
            self._name = name
            self._rval = rval

        def __call__(self, *argl: typing.Any, **argd: typing.Any) -> typing.Any:
            """
            Record the call and return the configured return value.

            :raises ExitMainLoop: this call was set up to leave the main loop.
            """
            args = ", ".join([repr(a) for a in argl])
            if args and argd:
                args = f"{args}, "
            args += ", ".join([f"{k}={v!r}" for k, v in argd.items()])
            print(f"{self._name}({args})")
            if loop_exit:
                raise ExitMainLoop
            return self._rval

        def __getattr__(self, attr: str) -> Reflect:  # pylint: disable=undefined-variable
            """
            Return a nested :class:`Reflect` that records access to *attr*.

            :raises AttributeError: *attr* names a return-value slot rather than a call.
            """
            if attr.endswith("_rval"):
                raise AttributeError
            # print(self._name+"."+attr)
            if hasattr(self, f"{attr}_rval"):
                return Reflect(f"{self._name}.{attr}", getattr(self, f"{attr}_rval"))
            return Reflect(f"{self._name}.{attr}")

    return Reflect(name)


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
