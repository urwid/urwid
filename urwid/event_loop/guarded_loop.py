"""Event loop wrapper that hands the errors of its callbacks to a handler instead of stopping the loop."""

from __future__ import annotations

import functools
import inspect
import typing

from .abstract_loop import EventLoop

if typing.TYPE_CHECKING:
    import asyncio
    import signal
    from collections.abc import Callable
    from concurrent.futures import Executor, Future
    from types import FrameType
    from typing import ParamSpec

    _T = typing.TypeVar("_T")
    _Spec = ParamSpec("_Spec")

__all__ = ("GuardedEventLoop",)


class GuardedEventLoop(EventLoop):
    """Event loop that passes the exceptions of its callbacks to a handler.

    It registers every callback on another event loop.
    Without it, an exception raised by a callback stops the event loop,
    which ends every application that runs on it.
    Give each :class:`~urwid.MainLoop` that shares one event loop its own wrapper:
    an exception in one application's input handler, alarm or redraw then reaches that application's handler,
    and the event loop and the other applications go on.

    The handler receives every :exc:`Exception`, :exc:`~urwid.ExitMainLoop` included,
    and decides what ends: usually the application whose callback raised.
    A :exc:`BaseException` that is not an :exc:`Exception`, such as :exc:`KeyboardInterrupt`, is not caught.
    An exception the handler raises goes to the wrapped event loop.

    The wrapper suits a screen that hands its input to the event loop,
    such as :class:`urwid.display.websocket.Screen`.

    A handler that records the errors, and stops the loop on :exc:`~urwid.ExitMainLoop`:

    >>> import urwid
    >>> errors = []
    >>> def on_error(exc):
    ...     errors.append(type(exc).__name__)
    ...     if isinstance(exc, urwid.ExitMainLoop):
    ...         raise exc
    >>> def stop():
    ...     raise urwid.ExitMainLoop
    >>> loop = GuardedEventLoop(urwid.SelectEventLoop(), on_error)
    >>> _ = loop.alarm(0, lambda: 1 / 0)
    >>> _ = loop.alarm(0.01, stop)
    >>> loop.run()
    >>> errors
    ['ZeroDivisionError', 'ExitMainLoop']
    """

    __slots__ = ("__weakref__", "_loop", "_on_error")

    def __init__(self, loop: EventLoop, on_error: Callable[[Exception], object]) -> None:
        """Wrap *loop* with *on_error* as the handler.

        :param loop: the event loop that runs the callbacks; it may be shared with other wrappers.
        :param on_error: called with each exception a callback raised.
        """
        super().__init__()
        self._loop = loop
        self._on_error = on_error

    @property
    def loop(self) -> EventLoop:
        """Return the wrapped event loop."""
        return self._loop

    def _guard(self, callback: Callable[[], typing.Any]) -> Callable[[], typing.Any]:
        """Return *callback* wrapped so that an exception it raises goes to the handler.

        An ``async def`` callback stays one, so the wrapped loop still schedules it as a task.
        """
        if inspect.iscoroutinefunction(callback):

            @functools.wraps(callback)
            async def guarded_coroutine() -> typing.Any:
                try:
                    return await callback()
                except Exception as exc:  # noqa: BLE001  # the handler is where the exception is reported
                    self._on_error(exc)
                    return None

            return guarded_coroutine

        @functools.wraps(callback)
        def guarded() -> typing.Any:
            try:
                return callback()
            except Exception as exc:  # noqa: BLE001  # the handler is where the exception is reported
                self._on_error(exc)
                return None

        return guarded

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> typing.Any:
        """Call *callback* on the wrapped loop *seconds* from now.

        :returns: the wrapped loop's handle, for :meth:`remove_alarm`.
        """
        return self._loop.alarm(seconds, self._guard(callback))

    def remove_alarm(self, handle: typing.Any) -> bool:
        """Remove an alarm from the wrapped loop.

        :returns: whether the alarm was pending.
        """
        return self._loop.remove_alarm(handle)

    def enter_idle(self, callback: Callable[[], typing.Any]) -> typing.Any:
        """Call *callback* whenever the wrapped loop enters idle.

        :returns: the wrapped loop's handle, for :meth:`remove_enter_idle`.
        """
        return self._loop.enter_idle(self._guard(callback))

    def remove_enter_idle(self, handle: typing.Any) -> bool:
        """Remove an idle callback from the wrapped loop.

        :returns: whether the callback was registered.
        """
        return self._loop.remove_enter_idle(handle)

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> typing.Any:
        """Call *callback* whenever *fd* is readable.

        :returns: the wrapped loop's handle, for :meth:`remove_watch_file`.
        """
        return self._loop.watch_file(fd, self._guard(callback))

    def remove_watch_file(self, handle: typing.Any) -> bool:
        """Stop watching a file.

        :returns: whether the file was watched.
        """
        return self._loop.remove_watch_file(handle)

    def run(self) -> None:
        """Run the wrapped event loop."""
        self._loop.run()

    def run_in_executor(
        self,
        executor: Executor,
        func: Callable[_Spec, _T],
        *args: _Spec.args,
        **kwargs: _Spec.kwargs,
    ) -> Future[_T] | asyncio.Future[_T]:
        """Run *func* in *executor* through the wrapped loop.

        :raises NotImplementedError: the wrapped loop cannot run callables in an executor.
        """
        return self._loop.run_in_executor(executor, func, *args, **kwargs)

    def set_signal_handler(
        self,
        signum: int,
        handler: Callable[[int, FrameType | None], typing.Any] | int | signal.Handlers,
    ) -> Callable[[int, FrameType | None], typing.Any] | int | signal.Handlers | None:
        """Set the handler of signal *signum* through the wrapped loop."""
        return self._loop.set_signal_handler(signum, handler)
