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


"""Notifications: messages that are shown for a while, such as in the footer of a :class:`Frame`."""

from __future__ import annotations

import enum
import functools
import math
import typing

from urwid.split_repr import remove_defaults

from .attr_map import AttrMap, _attr_map_dict, _attr_map_dicts
from .constants import Align, Severity, Sizing, WHSettings, WrapMode
from .pile import Pile
from .text import Text
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Mapping

    from urwid.event_loop import MainLoop
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike

__all__ = ("Notification", "Notifications")


class _Unset(enum.Enum):
    """Marker for an argument that was not passed."""

    UNSET = enum.auto()

    def __repr__(self) -> str:
        return "<unset>"


class Notification:
    """One message shown by :class:`Notifications`, as :meth:`Notifications.notify` returns it.

    Pass it to :meth:`Notifications.dismiss` to take the message down before its timeout.
    """

    __slots__ = ("__weakref__", "_severity", "_timeout", "_widget")

    def __init__(self, widget: Text, severity: Severity, timeout: float | None) -> None:
        """Hold the message's text widget, its severity and its timeout."""
        self._widget = widget
        self._severity = severity
        self._timeout = timeout

    def __repr__(self) -> str:
        """Return the class name, the text and the severity."""
        return f"<{self.__class__.__name__} {self._widget.text!r} severity={self._severity.name}>"

    @property
    def widget(self) -> Text:
        """The text widget showing the message."""
        return self._widget

    @property
    def severity(self) -> Severity:
        """How serious the message is."""
        return self._severity

    @property
    def timeout(self) -> float | None:
        """Seconds the message is shown before it is dismissed, or ``None`` when it stays until dismissed."""
        return self._timeout


class Notifications(WidgetWrap[Pile]):
    """A flow widget listing messages, each shown until its timeout runs out or it is dismissed.

    The oldest message is at the top.
    With :attr:`max_count` set, a new message dismisses the oldest ones over that count,
    so ``max_count=1`` makes a status line.
    While no message is showing, the :attr:`default` text is shown, or nothing, in zero rows.

    A message with a timeout sets an alarm on :attr:`loop`,
    or, without one, on the :class:`MainLoop` running when :meth:`notify` is called
    (see :func:`~urwid.get_running_loop`).
    The loop redraws the screen after the alarm, so an expired message disappears with no further call.

    Sends ``"change"`` once per :meth:`notify`, :meth:`dismiss`, :meth:`clear`, expiry,
    or lowered :attr:`max_count` that changed the messages shown, once the change is complete.
    Its handlers receive the widget.
    An exception raised by a handler during an expiry is logged by the loop, as for every alarm callback.

    .. important::
        Call every method from the thread running the loop, like every other widget change.
        Another thread hands the message over with :meth:`MainLoop.call_from_thread` instead.

    >>> status = Notifications(max_count=1, default="ready")
    >>> status.render((8,)).text
    [b'ready   ']
    >>> saved = status.notify("saved", timeout=None)
    >>> status.render((8,)).text
    [b'saved   ']
    >>> status.dismiss(saved)
    True
    >>> status.render((8,)).text
    [b'ready   ']
    """

    signals: typing.ClassVar[list[str]] = ["change"]

    def __init__(
        self,
        *,
        timeout: float | None = 5.0,
        max_count: int | None = None,
        severity_attr: Mapping[Severity, _AttrMapLike] | None = None,
        default: _TagMarkup | None = None,
        default_attr: _AttrMapLike | None = None,
        loop: MainLoop | None = None,
        align: typing.Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: typing.Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
    ) -> None:
        """Build an empty notification list.

        :param timeout: seconds a message stays when :meth:`notify` is not given one, see :attr:`timeout`.
        :param max_count: messages shown at once, see :attr:`max_count`.
        :param severity_attr: attribute map applied to a message for each :class:`Severity`,
            see :attr:`severity_attr`.
        :param default: text markup shown while no message is showing, or ``None`` to show nothing.
        :param default_attr: attribute map applied to the default text, in any form :class:`AttrMap` takes.
        :param loop: loop the alarms are set on.
            ``None`` uses the loop running at each :meth:`notify`.
        :param align: alignment of the text of every message and of the default text.
        :param wrap: wrap mode of the text of every message and of the default text.
        :raises TypeError: *timeout* is not a number or ``None``, *max_count* is not an int or ``None``,
            or a key of *severity_attr* is not a :class:`Severity`.
        :raises ValueError: *timeout* is not finite and > 0, or *max_count* is < 1.
        :raises TextError: *align* or *wrap* is not supported by the text layout.
        :raises TagMarkupException: *default* is not valid text markup.
        :raises AttrMapError: a key or value of an attribute map is not hashable.
        """
        super().__init__(Pile([]))
        self._timeout = self._valid_timeout(timeout)
        self._max_count = self._valid_max_count(max_count)
        self._severity_attr = self._severity_attr_maps(severity_attr)
        self._align = align
        self._wrap = wrap
        self._default_markup = default
        # Built even without a default text, so that an unsupported align or wrap is rejected here.
        self._default = Text("" if default is None else default, align, wrap)
        self._default_attr = None if default_attr is None else _attr_map_dict(default_attr)
        self._loop = loop
        self._notifications: list[Notification] = []
        # The loop and the handle of each alarm still pending, so that dismissing a message removes its alarm.
        self._alarms: dict[Notification, tuple[MainLoop, typing.Any]] = {}
        self._show()

    @staticmethod
    def _valid_timeout(timeout: float | None) -> float | None:
        """Return *timeout* unchanged.

        :raises TypeError: it is not an int, a float or ``None``.
        :raises ValueError: it is not finite and > 0.
        """
        if timeout is None:
            return None
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise TypeError(f"timeout must be a number of seconds or None, not {timeout!r}")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"timeout must be finite and > 0, not {timeout!r}")
        return timeout

    @staticmethod
    def _valid_max_count(max_count: int | None) -> int | None:
        """Return *max_count* unchanged.

        :raises TypeError: it is not an int or ``None``.
        :raises ValueError: it is < 1.
        """
        if max_count is None:
            return None
        if not isinstance(max_count, int) or isinstance(max_count, bool):
            raise TypeError(f"max_count must be an int or None, not {max_count!r}")
        if max_count < 1:
            raise ValueError(f"max_count must be >= 1, not {max_count!r}")
        return max_count

    @staticmethod
    def _severity_attr_maps(
        attr_maps: Mapping[Severity, _AttrMapLike] | None,
    ) -> dict[Severity, dict[Hashable, Hashable]]:
        """Return *attr_maps* with each value as an attribute mapping dictionary.

        :raises TypeError: a key is not a :class:`Severity`.
        :raises AttrMapError: a key or value of an attribute map is not hashable.
        """
        if attr_maps is not None and not all(isinstance(severity, Severity) for severity in attr_maps):
            raise TypeError(f"severity_attr keys must be Severity members, not {list(attr_maps)!r}")
        return _attr_map_dicts(attr_maps)

    def _repr_words(self) -> list[str]:
        """Return the base repr words followed by the number of messages."""
        count = len(self._notifications)
        return [*super()._repr_words(), f"({count} message{'' if count == 1 else 's'})"]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor arguments that differ from their defaults, for the repr."""
        attrs = {
            **super()._repr_attrs(),
            "timeout": self._timeout,
            "max_count": self._max_count,
            "severity_attr": self._severity_attr or None,
            "default": self._default_markup,
            "default_attr": self._default_attr,
            "loop": self._loop,
            "align": self._align,
            "wrap": self._wrap,
        }
        return remove_defaults(attrs, Notifications.__init__)

    def _show(self) -> None:
        """Put the messages, or the default text while there are none, into the wrapped :class:`Pile`."""
        widgets: list[Text | AttrMap[Text]] = [
            AttrMap(n.widget, self._severity_attr[n.severity]) if n.severity in self._severity_attr else n.widget
            for n in self._notifications
        ]
        if not widgets and self._default_markup is not None:
            widgets.append(self._default if self._default_attr is None else AttrMap(self._default, self._default_attr))
        self._w.contents[:] = [(widget, self._w.options(WHSettings.PACK)) for widget in widgets]

    def sizing(self) -> frozenset[Sizing]:
        """Return flow sizing, whatever is showing."""
        return frozenset((Sizing.FLOW,))

    @property
    def notifications(self) -> tuple[Notification, ...]:
        """The messages showing, the oldest first."""
        return tuple(self._notifications)

    @property
    def loop(self) -> MainLoop | None:
        """Loop the alarms are set on, or ``None`` to use the loop running at each :meth:`notify`."""
        return self._loop

    @property
    def timeout(self) -> float | None:
        """Seconds a message stays when :meth:`notify` is not given a timeout, or ``None`` to keep it.

        A new value applies to later messages only.

        :raises TypeError: the new value is not a number or ``None``.
        :raises ValueError: the new value is not finite and > 0.
        """
        return self._timeout

    @timeout.setter
    def timeout(self, timeout: float | None) -> None:
        self._timeout = self._valid_timeout(timeout)

    @property
    def max_count(self) -> int | None:
        """Messages shown at once, or ``None`` for no limit.

        A new message over the count dismisses the oldest one.
        Lowering it dismisses the oldest messages over the new count at once.

        :raises TypeError: the new value is not an int or ``None``.
        :raises ValueError: the new value is < 1.
        """
        return self._max_count

    @max_count.setter
    def max_count(self, max_count: int | None) -> None:
        self._max_count = self._valid_max_count(max_count)
        if max_count is not None and len(self._notifications) > max_count:
            for notification in self._notifications[:-max_count]:
                self._remove(notification)
            self._show()
            self._emit("change")

    @property
    def severity_attr(self) -> dict[Severity, dict[Hashable, Hashable]]:
        """Attribute map applied to a message for each :class:`Severity`.

        It is set from a mapping of :class:`Severity` to what :class:`AttrMap` takes as its attribute map, or ``None``.
        A severity with no entry is not coloured.
        A copy is returned.

        :raises TypeError: a key of the new mapping is not a :class:`Severity`.
        :raises AttrMapError: a key or value of an attribute map is not hashable.
        """
        return {severity: attr_map.copy() for severity, attr_map in self._severity_attr.items()}

    @severity_attr.setter
    def severity_attr(self, attr_maps: Mapping[Severity, _AttrMapLike] | None) -> None:
        self._severity_attr = self._severity_attr_maps(attr_maps)
        self._show()

    @property
    def default(self) -> _TagMarkup | None:
        """Text markup shown while no message is showing, or ``None`` to show nothing.

        :raises TagMarkupException: the new value is not valid text markup.
        """
        return self._default_markup

    @default.setter
    def default(self, default: _TagMarkup | None) -> None:
        self._default = Text("" if default is None else default, self._align, self._wrap)
        self._default_markup = default
        self._show()

    @property
    def default_attr(self) -> dict[Hashable, Hashable] | None:
        """Attribute map applied to the default text, or ``None``.

        A copy is returned.

        :raises AttrMapError: a key or value of the new map is not hashable.
        """
        return None if self._default_attr is None else self._default_attr.copy()

    @default_attr.setter
    def default_attr(self, default_attr: _AttrMapLike | None) -> None:
        self._default_attr = None if default_attr is None else _attr_map_dict(default_attr)
        self._show()

    def notify(
        self,
        markup: _TagMarkup,
        *,
        severity: Severity = Severity.INFO,
        timeout: float | typing.Literal[_Unset.UNSET] | None = _Unset.UNSET,
    ) -> Notification:
        """Show a message below the others.

        A call that raises leaves the widget as it was, unless a ``"change"`` handler raised.
        An exception from a handler reaches the caller after the message is showing and its alarm is set.

        :param markup: text markup of the message.
        :param severity: how serious the message is, which selects its :attr:`severity_attr` entry.
        :param timeout: seconds until the message is dismissed, ``None`` to keep it until :meth:`dismiss`,
            or left out to use :attr:`timeout`.
        :returns: the message, to pass to :meth:`dismiss`.
        :raises TypeError: *severity* is not a :class:`Severity`, or *timeout* is not a number or ``None``.
        :raises ValueError: *timeout* is not finite and > 0.
        :raises TagMarkupException: *markup* is not valid text markup.
        :raises RuntimeError: the message has a timeout, there is no :attr:`loop`, and no loop is running.
            Pass ``loop=`` to post a message before the loop runs.
        """
        if not isinstance(severity, Severity):
            raise TypeError(f"severity must be a Severity, not {severity!r}")
        timeout = self._timeout if timeout is _Unset.UNSET else self._valid_timeout(timeout)
        notification = Notification(Text(markup, self._align, self._wrap), severity, timeout)
        if timeout is not None:
            loop = self._loop
            if loop is None:
                # urwid.event_loop imports urwid.widget, so it cannot be imported at module scope here
                from urwid.event_loop import get_running_loop

                loop = get_running_loop()
            self._alarms[notification] = (
                loop,
                loop.set_alarm_in(timeout, functools.partial(self._expire, notification)),
            )

        if self._max_count is not None:
            for oldest in self._notifications[: max(0, len(self._notifications) + 1 - self._max_count)]:
                self._remove(oldest)
        self._notifications.append(notification)
        self._show()
        self._emit("change")
        return notification

    def dismiss(self, notification: Notification) -> bool:
        """Take a message down and remove its alarm.

        :returns: whether the message was showing.
            It is ``False`` for a message that expired or was dismissed before.
        """
        if notification not in self._notifications:
            return False
        self._remove(notification)
        self._show()
        self._emit("change")
        return True

    def clear(self) -> None:
        """Take every message down and remove their alarms."""
        if not self._notifications:
            return
        for notification in tuple(self._notifications):
            self._remove(notification)
        self._show()
        self._emit("change")

    def _remove(self, notification: Notification) -> None:
        """Remove *notification* from the list and its pending alarm from its loop, without showing the change."""
        self._notifications.remove(notification)
        # The alarm's callback holds the notification and this widget: remove it, so they can be freed.
        if (alarm := self._alarms.pop(notification, None)) is not None:
            loop, handle = alarm
            loop.remove_alarm(handle)

    def _expire(self, notification: Notification, _loop: MainLoop, _user_data: None) -> None:
        """Dismiss *notification*, whose alarm has fired."""
        del self._alarms[notification]
        self.dismiss(notification)
