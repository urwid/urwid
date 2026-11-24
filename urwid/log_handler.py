# Copyright (C) 2026 Urwid developers
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


"""Logging handlers that show log records in widgets, from any thread.

The module is not imported by :mod:`urwid`; use ``import urwid.log_handler``.
"""

from __future__ import annotations

import collections
import logging
import typing
from collections.abc import Hashable

from urwid.event_loop import ExitMainLoop, get_running_loop_or_none
from urwid.event_loop.main_loop import _get_running_loop_of_this_thread
from urwid.widget.constants import Severity
from urwid.widget.notifications import Notifications, _Unset
from urwid.widget.text import Text

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    from urwid.event_loop import MainLoop

__all__ = ("ListWalkerHandler", "NotificationsHandler")

_logger = logging.getLogger(__name__)

# Entries one _drain() call shows; MainLoop may run the next call in the same pass, see _LoopHandler.
_ENTRIES_PER_DRAIN: typing.Final = 32


class _Appendable(typing.Protocol):
    """A list walker that takes a new row at its end."""

    def append(self, item: Text, /) -> None:
        """Add *item* after the last row."""


def _severity(levelno: int) -> Severity:
    """Return the :class:`Severity` of a logging level.

    A level between two default ones takes the lower one.
    """
    if levelno >= logging.CRITICAL:
        return Severity.CRITICAL
    if levelno >= logging.ERROR:
        return Severity.ERROR
    if levelno >= logging.WARNING:
        return Severity.WARNING
    if levelno >= logging.INFO:
        return Severity.INFO
    return Severity.DEBUG


class _UrwidFilter(logging.Filter):
    """Reject records of the ``urwid`` logger and its children."""

    def __init__(self) -> None:
        super().__init__("urwid")

    def filter(self, record: logging.LogRecord) -> bool:
        """Return whether *record* comes from outside the ``urwid`` logger."""
        return not super().filter(record)


class _LoopHandler(logging.Handler):
    """Hand formatted records to the thread of a :class:`~urwid.MainLoop`, which shows them.

    :meth:`emit` formats a record on the logging thread and queues the text with its :class:`Severity`.
    The record itself is not kept.
    The queue holds at most *max_pending* entries, and the oldest is dropped first.
    One call of :meth:`_drain`, handed to :meth:`~urwid.MainLoop.call_from_thread`, shows the queued entries
    on the loop thread, at most :data:`_ENTRIES_PER_DRAIN` of them, and queues the next call for the rest.
    The loop may run that next call in the same pass, up to its own limit of calls per pass,
    so a sustained flood shows up to :data:`_ENTRIES_PER_DRAIN` times that limit before input is served again.

    Records held while the loop does not run are shown after :meth:`resume`, which starts each run.
    :meth:`flush` shows the queued entries at once, from the loop thread.
    The widget is changed by :meth:`_drain` and :meth:`flush` only, so on the loop thread only.

    State, read and written under the handler lock:

    - ``_scheduled``: a :meth:`_drain` call was handed to the loop and has not started.
    - ``_draining``: a :meth:`_drain` or :meth:`flush` call is showing entries.
    - ``_shut``: :meth:`close` was called.
    """

    def __init__(self, *, loop: MainLoop, level: int | str, max_pending: int) -> None:
        """Create the handler with its filter of the ``urwid`` loggers.

        :raises ValueError: *max_pending* is below 1, or *level* is a name :mod:`logging` does not know.
        :raises TypeError: *level* is neither an int nor a str.
        """
        if max_pending < 1:
            raise ValueError(f"max_pending must be >= 1, not {max_pending!r}")
        super().__init__(level)
        if self.lock is None:
            raise RuntimeError("logging.Handler.__init__() did not create the handler lock")
        # The lock Handler.handle() holds around emit(), under a name the type checker knows is set.
        self._lock: typing.Final = self.lock
        self.loop: typing.Final = loop
        self._pending: collections.deque[tuple[str, Severity]] = collections.deque(maxlen=max_pending)
        self._scheduled = False
        self._draining = False
        self._shut = False
        #: Filter rejecting records of the ``urwid`` logger and its children.
        #: urwid logs at DEBUG on each redraw and each alarm it sets, so showing those records logs again without end.
        self.urwid_filter: typing.Final = _UrwidFilter()
        self.addFilter(self.urwid_filter)

    def emit(self, record: logging.LogRecord) -> None:
        """Queue the formatted *record* and hand a call that shows it to the loop.

        A failure of the formatter goes to :meth:`~logging.Handler.handleError`.
        Records of this module's own logger are ignored, so a failing widget cannot report its failures to itself.
        """
        if self._shut or record.name == _logger.name:
            return
        try:
            entry = (self.format(record), _severity(record.levelno))
        except Exception:  # noqa: BLE001  # handleError() is where logging reports a failed record
            self.handleError(record)
            return
        with self._lock:
            if self._shut:
                return
            self._pending.append(entry)
            self._schedule()

    def _schedule(self) -> None:
        """Hand a :meth:`_drain` call to the loop, unless one is queued or running.

        Call it with the handler lock held.
        A loop that does not run holds the entries until :meth:`resume`.
        """
        if self._scheduled or self._draining or self._shut:
            return
        try:
            self.loop.call_from_thread(self._drain)
        except RuntimeError:
            return
        self._scheduled = True

    def resume(self) -> None:
        """Hand a call that shows the queued records to the loop.

        Call it once at the start of each run of the loop, inside ``with loop.start():``
        or from an alarm set before :meth:`~urwid.MainLoop.run`.
        :meth:`~urwid.MainLoop.stop` drops a queued call, and without :meth:`resume` the records held
        before :meth:`~urwid.MainLoop.start` or after the drop stay queued, also when new records arrive.
        It is safe from any thread, and does nothing after :meth:`close`.

        :raises RuntimeError: the loop is not running, or its event loop cannot watch files,
            see :meth:`~urwid.MainLoop.call_from_thread`.
        """
        with self._lock:
            if self._shut:
                return
            self.loop.call_from_thread(self._drain)
            self._scheduled = True

    def _drain(self) -> None:
        """Show up to :data:`_ENTRIES_PER_DRAIN` queued entries, oldest first.

        Only the loop runs it, through :meth:`~urwid.MainLoop.call_from_thread`.
        Showing stops before the next entry once the loop is no longer the running loop, such as after a widget
        callback stopped it, and after :meth:`close`.
        A nested call, from a widget callback that runs a pass of the loop, shows nothing.
        :exc:`~urwid.ExitMainLoop` from the widget propagates.
        Any other exception is logged and the next entry is shown.
        """
        self._deliver(drain=True)

    def flush(self) -> None:
        """Show the records queued now in the widget.

        Call it on the loop thread while the loop runs, for example before a widget callback stops the loop or
        reads the widget, so the widget shows every record logged before the call, without waiting for the loop to
        hand them over.
        Records logged while it shows them, such as by the widget, wait for the next hand-over;
        when they fill ``max_pending``, the oldest queued records are dropped as usual.
        On any other thread, also one that runs in a copy of the loop's context, and after :meth:`close`,
        it does nothing and the records stay queued.
        A call from a widget callback during a hand-over shows nothing, and leaves the rest to that hand-over.
        Any exception from the widget other than :exc:`~urwid.ExitMainLoop` is logged and the next entry is shown.

        :raises ~urwid.ExitMainLoop: the widget stopped the loop.
        """
        if _get_running_loop_of_this_thread() is self.loop:
            self._deliver(drain=False)

    def _deliver(self, *, drain: bool) -> None:
        """Show queued entries, oldest first, and hand the loop a call for the rest.

        A hand-over (*drain* true) shows up to :data:`_ENTRIES_PER_DRAIN` entries,
        otherwise every entry queued at the call.
        Showing stops before the next entry once the loop is no longer the running loop, and after :meth:`close`.
        Call it on the loop thread only.
        """
        with self._lock:
            if drain:
                self._scheduled = False
            if self._draining:
                return
            self._draining = True
            count = _ENTRIES_PER_DRAIN if drain else len(self._pending)
        try:
            for _ in range(count):
                if get_running_loop_or_none() is not self.loop:
                    break
                with self._lock:
                    if self._shut or not self._pending:
                        break
                    text, severity = self._pending.popleft()
                try:
                    self._show(text, severity)
                except ExitMainLoop:
                    raise
                except Exception:
                    _logger.exception("%r failed to show a log record", self)
        finally:
            with self._lock:
                self._draining = False
                # Also after ExitMainLoop: an event loop the application runs itself may go on.
                if self._pending and get_running_loop_or_none() is self.loop:
                    self._schedule()

    def _show(self, text: str, severity: Severity) -> None:
        """Show one formatted record in the widget, on the loop thread."""
        raise NotImplementedError

    def close(self) -> None:
        """Drop the queued records and ignore later ones, without touching the widget."""
        with self._lock:
            self._shut = True
            self._pending.clear()
        # Outside the handler lock: the base takes the logging module lock, which logging.config holds
        # while it takes handler locks.
        super().close()


class ListWalkerHandler(_LoopHandler):
    """Append each log record as a :class:`~urwid.Text` row to a list walker, on the thread of the loop.

    Records may be logged from any thread.
    A :class:`~urwid.SimpleFocusDequeWalker` with ``maxlen`` and ``follow_end=True`` keeps the newest rows
    and keeps the newest one in view in a :class:`~urwid.ListBox`.
    The handler needs :meth:`~urwid.MainLoop.call_from_thread`, so an event loop that can watch files.
    Call :meth:`resume` once at the start of each run; ``with loop.start():`` lets its error reach the caller,
    while an alarm set before :meth:`~urwid.MainLoop.run` only logs it.
    :attr:`urwid_filter` rejects records of the ``urwid`` loggers.
    To show them, set the handler's level to ``INFO`` or above and remove the filter:
    urwid logs at DEBUG on each redraw, and each shown record redraws.

    >>> import logging
    >>> import urwid
    >>> from urwid.testing import ScriptedScreen, VirtualClockEventLoop
    >>> walker = urwid.SimpleFocusDequeWalker([], maxlen=100, follow_end=True)
    >>> event_loop = VirtualClockEventLoop()
    >>> loop = urwid.MainLoop(urwid.ListBox(walker), screen=ScriptedScreen(inputs=None), event_loop=event_loop)
    >>> handler = ListWalkerHandler(walker, loop=loop, severity_attr={urwid.Severity.WARNING: "warning"})
    >>> logger = logging.getLogger("example.walker")
    >>> logger.addHandler(handler)
    >>> logger.warning("disk almost full")
    >>> with loop.start():
    ...     handler.resume()
    ...     event_loop.advance(0)
    >>> walker[0].get_text()
    ('disk almost full', [('warning', 16)])
    >>> logger.removeHandler(handler)
    """

    def __init__(
        self,
        walker: _Appendable,
        *,
        loop: MainLoop,
        level: int | str = logging.NOTSET,
        severity_attr: Mapping[Severity, Hashable] | None = None,
        max_pending: int = 1000,
    ) -> None:
        """Create a handler that appends to *walker*.

        :param walker: list walker with an ``append()`` method.
        :param loop: loop whose thread changes *walker*.
        :param level: lowest level handled.
        :param severity_attr: display attribute of a row for each :class:`Severity`;
            a severity with no entry is not coloured.
        :param max_pending: records held until the loop shows them; the oldest is dropped first.
        :raises ValueError: *max_pending* is below 1, or *level* is a name :mod:`logging` does not know.
        :raises TypeError: *level* is neither an int nor a str, a key of *severity_attr* is not a :class:`Severity`,
            or a value is not hashable.
        """
        attrs = dict(severity_attr or {})
        # Checked here: a bad attribute is only found when the row is drawn, which ends the application.
        for severity, attr in attrs.items():
            if not isinstance(severity, Severity):
                raise TypeError(f"severity_attr keys must be Severity members, not {severity!r}")
            if not isinstance(attr, Hashable):
                raise TypeError(f"severity_attr values must be hashable display attributes, not {attr!r}")
        super().__init__(loop=loop, level=level, max_pending=max_pending)
        self.walker: typing.Final = walker
        self.severity_attr: typing.Final[dict[Severity, Hashable]] = attrs

    def _show(self, text: str, severity: Severity) -> None:
        """Append *text* as a row with the attribute of *severity*."""
        attr = self.severity_attr.get(severity)
        self.walker.append(Text(text if attr is None else (attr, text)))


class NotificationsHandler(_LoopHandler):
    """Post each log record as a message of :class:`~urwid.Notifications`, on the thread of the loop.

    Records may be logged from any thread.
    The message carries the record's :class:`Severity`.
    The handler needs :meth:`~urwid.MainLoop.call_from_thread`, so an event loop that can watch files.
    Call :meth:`resume` once at the start of each run; ``with loop.start():`` lets its error reach the caller,
    while an alarm set before :meth:`~urwid.MainLoop.run` only logs it.
    :attr:`urwid_filter` rejects records of the ``urwid`` loggers.
    To show them, set the handler's level to ``INFO`` or above and remove the filter:
    urwid logs at DEBUG on each alarm it sets, and each message sets one.

    >>> import logging
    >>> import urwid
    >>> from urwid.testing import ScriptedScreen, VirtualClockEventLoop
    >>> notifications = urwid.Notifications(timeout=5)
    >>> event_loop = VirtualClockEventLoop()
    >>> loop = urwid.MainLoop(urwid.Filler(notifications), screen=ScriptedScreen(inputs=None), event_loop=event_loop)
    >>> handler = NotificationsHandler(notifications, loop=loop)
    >>> logger = logging.getLogger("example.notifications")
    >>> logger.addHandler(handler)
    >>> logger.error("upload failed")
    >>> with loop.start():
    ...     handler.resume()
    ...     event_loop.advance(0)
    ...     notifications.notifications
    (<Notification 'upload failed' severity=ERROR>,)
    >>> logger.removeHandler(handler)
    """

    def __init__(
        self,
        notifications: Notifications,
        *,
        loop: MainLoop,
        level: int | str = logging.NOTSET,
        timeout: float | typing.Literal[_Unset.UNSET] | None = _Unset.UNSET,
        max_pending: int = 1000,
    ) -> None:
        """Create a handler that posts to *notifications*.

        :param notifications: widget the messages are posted to.
        :param loop: loop whose thread posts the messages; it also runs their alarms.
        :param level: lowest level handled.
        :param timeout: seconds a message stays, ``None`` to keep it, or left out to use the widget's timeout.
        :param max_pending: records held until the loop shows them; the oldest is dropped first.
        :raises ValueError: *notifications* is bound to another loop, *timeout* is not finite and > 0,
            *max_pending* is below 1, or *level* is a name :mod:`logging` does not know.
        :raises TypeError: *level* is neither an int nor a str, or *timeout* is not a number or ``None``.
        """
        if notifications.loop is not None and notifications.loop is not loop:
            raise ValueError(f"{notifications!r} sets its alarms on another loop than {loop!r}")
        if timeout is not _Unset.UNSET:
            # Checked here rather than at each record, where it would fail every delivery.
            timeout = Notifications._valid_timeout(timeout)
        super().__init__(loop=loop, level=level, max_pending=max_pending)
        self.notifications: typing.Final = notifications
        self.timeout: typing.Final = timeout

    def _show(self, text: str, severity: Severity) -> None:
        """Post *text* as a message of *severity*."""
        self.notifications.notify(text, severity=severity, timeout=self.timeout)
