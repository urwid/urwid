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


"""Overlay stack: dialogs opened on top of a base widget and of each other."""

from __future__ import annotations

import typing
from typing import Literal

from urwid import signals
from urwid.split_repr import remove_defaults

from .constants import Align, Sizing, VAlign, WHSettings
from .overlay import Overlay
from .widget import Widget, WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ("OverlayStack",)

_Width = Literal["pack", WHSettings.PACK] | int | tuple[Literal["relative", WHSettings.RELATIVE], int]


class _Level(typing.NamedTuple):
    """One open dialog: the widget passed to :meth:`OverlayStack.open`, its overlay and its close callback."""

    widget: Widget
    overlay: Overlay[Widget, Widget]
    on_close: Callable[[typing.Any], object] | None


class OverlayStack(WidgetWrap[Widget]):
    """A box widget showing dialogs on top of a base widget.

    Each dialog is an :class:`Overlay` over the one below.
    :meth:`open` puts a widget on top and :meth:`close` takes it down again with a result.
    Only the top dialog receives keys and mouse presses.
    The widgets below keep their own focus, so closing a dialog returns the input to where it was.
    The stack adds no frame: wrap a dialog in a :class:`LineBox` or an :class:`AttrMap` before opening it.

    The base is a box widget, usually the application's :class:`Frame`,
    and the stack is meant to be the :attr:`MainLoop.widget`.

    Sends ``"closed"`` once per closed dialog, after the dialog is removed and after its ``on_close`` callback.
    Its handlers receive the stack, the widget that was closed and the result.

    .. important::
        Call every method from the thread running the loop, like every other widget change.
        Another thread hands the call over with :meth:`MainLoop.call_from_thread`.

    >>> from urwid import SolidFill, Text
    >>> stack = OverlayStack(SolidFill("."))
    >>> stack.open(Text("hi"))
    >>> stack.render((10, 3)).text
    [b'..........', b'.hi      .', b'..........']
    >>> stack.close()
    True
    >>> stack.close()
    False
    """

    signals: typing.ClassVar[list[str]] = ["closed"]

    def __init__(
        self,
        base: Widget,
        *,
        close_on_menu: bool = False,
        close_on_click_outside: bool = False,
    ) -> None:
        """Build a stack with no dialog open.

        :param base: box widget shown under every dialog, see :attr:`base`.
        :param close_on_menu: default of :meth:`open`'s *close_on_menu*, see :attr:`close_on_menu`.
        :param close_on_click_outside: default of :meth:`open`'s *close_on_click_outside*,
            see :attr:`close_on_click_outside`.
        """
        super().__init__(base)
        self._base = base
        self._levels: list[_Level] = []
        self._close_on_menu = close_on_menu
        self._close_on_click_outside = close_on_click_outside

    def _repr_words(self) -> list[str]:
        """Return the base repr words followed by the number of open dialogs."""
        return [*super()._repr_words(), f"(depth {len(self._levels)})"]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor flags that differ from their defaults, for the repr."""
        attrs = {
            **super()._repr_attrs(),
            "close_on_menu": self._close_on_menu,
            "close_on_click_outside": self._close_on_click_outside,
        }
        return remove_defaults(attrs, OverlayStack.__init__)

    def sizing(self) -> frozenset[Sizing]:
        """Return box sizing, whatever is open."""
        return frozenset((Sizing.BOX,))

    @property
    def base(self) -> Widget:
        """The box widget shown under every dialog.

        Setting it replaces the widget under the lowest dialog and keeps the dialogs open.
        """
        return self._base

    @base.setter
    def base(self, base: Widget) -> None:
        self._base = base
        if self._levels:
            self._levels[0].overlay.bottom_w = base
        else:
            self._w = base

    @property
    def levels(self) -> tuple[Widget, ...]:
        """The widgets of the open dialogs, as passed to :meth:`open`, the lowest first."""
        return tuple(level.widget for level in self._levels)

    @property
    def depth(self) -> int:
        """The number of open dialogs."""
        return len(self._levels)

    @property
    def close_on_menu(self) -> bool:
        """Whether a dialog opened from now on closes on a key for the ``menu`` command (:kbd:`esc` by default).

        The key closes the dialog only when the dialog leaves it unhandled.
        A change does not affect the dialogs already open.
        """
        return self._close_on_menu

    @close_on_menu.setter
    def close_on_menu(self, close_on_menu: bool) -> None:
        self._close_on_menu = close_on_menu

    @property
    def close_on_click_outside(self) -> bool:
        """Whether a dialog opened from now on closes on a press of mouse button 1, 2 or 3 outside it.

        The press closes the dialog only, and does not reach the widget under it.
        A change does not affect the dialogs already open.
        """
        return self._close_on_click_outside

    @close_on_click_outside.setter
    def close_on_click_outside(self, close_on_click_outside: bool) -> None:
        self._close_on_click_outside = close_on_click_outside

    def open(
        self,
        widget: Widget,
        *,
        align: (
            Literal["left", "center", "right"]
            | Align
            | tuple[Literal["relative", "fixed left", "fixed right", WHSettings.RELATIVE], int]
        ) = Align.CENTER,
        width: _Width | None = None,
        valign: (
            Literal["top", "middle", "bottom"]
            | VAlign
            | tuple[Literal["relative", "fixed top", "fixed bottom", WHSettings.RELATIVE], int]
        ) = VAlign.MIDDLE,
        height: _Width | None = None,
        min_width: int | None = None,
        min_height: int | None = None,
        left: int = 0,
        right: int = 0,
        top: int = 0,
        bottom: int = 0,
        shrink_to_fit: bool = False,
        close_on_menu: bool | None = None,
        close_on_click_outside: bool | None = None,
        on_close: Callable[[typing.Any], object] | None = None,
    ) -> None:
        """Open *widget* as a dialog on top of the stack.

        The layout options are those of :class:`Overlay`, and are passed to it unchanged.
        A *width* or *height* of ``None`` is chosen from ``widget.sizing()``:

        - *width* is ``"pack"`` for a widget that is fixed only, and ``("relative", 80)`` otherwise.
        - *height* is ``"pack"`` for a flow widget, ``("relative", 80)`` for a box widget that is not a flow
          widget, and ``"pack"`` for a widget that is fixed only.

        Nothing is opened when an exception is raised.

        :param widget: the dialog, a box, flow or fixed widget.
        :param align: horizontal alignment, as for :class:`Overlay`.
        :param width: width, as for :class:`Overlay`, or ``None`` to choose it from the sizing.
        :param valign: vertical alignment, as for :class:`Overlay`.
        :param height: height, as for :class:`Overlay`, or ``None`` to choose it from the sizing.
        :param min_width: minimum number of columns for a relative width.
        :param min_height: minimum number of rows for a relative height.
        :param left: columns of padding on the left of the dialog.
        :param right: columns of padding on the right of the dialog.
        :param top: rows of padding above the dialog.
        :param bottom: rows of padding below the dialog.
        :param shrink_to_fit: with a ``"pack"`` height, render a dialog that also supports ``"box"`` and is taller
            than the rows available as a box at those rows, as for :class:`Overlay`.
        :param close_on_menu: close this dialog on a key for the ``menu`` command it leaves unhandled.
            ``None`` uses :attr:`close_on_menu`.
        :param close_on_click_outside: close this dialog on a press of mouse button 1, 2 or 3 outside it.
            ``None`` uses :attr:`close_on_click_outside`.
        :param on_close: called with the result when the dialog is closed, before ``"closed"`` is sent.
        :raises ValueError: *widget* is already open in this stack.
            Also raised when *align* or *valign* is a string that names no alignment.
        :raises OverlayError: a layout option is not valid for :class:`Overlay`.
        """
        if any(level.widget is widget for level in self._levels):
            raise ValueError(f"{widget!r} is already open in this stack")

        sizing = widget.sizing()
        if width is None:
            width = (WHSettings.RELATIVE, 80) if sizing & {Sizing.FLOW, Sizing.BOX} else WHSettings.PACK
        if height is None:
            height = (
                (WHSettings.RELATIVE, 80) if Sizing.BOX in sizing and Sizing.FLOW not in sizing else WHSettings.PACK
            )

        overlay: Overlay[Widget, Widget] = Overlay(
            widget,
            self._w,
            align,
            width,
            valign,
            height,
            min_width,
            min_height,
            left,
            right,
            top,
            bottom,
            shrink_to_fit=shrink_to_fit,
        )
        if self._close_on_menu if close_on_menu is None else close_on_menu:
            signals.connect_signal(overlay, "menu", _close_by_signal, weak_args=(self,), user_args=(widget,))
        if self._close_on_click_outside if close_on_click_outside is None else close_on_click_outside:
            signals.connect_signal(
                overlay,
                "click outside",
                _close_by_signal,
                weak_args=(self,),
                user_args=(widget,),
            )

        self._levels.append(_Level(widget, overlay, on_close))
        self._w = overlay

    def close(self, result: typing.Any = None, *, widget: Widget | None = None) -> bool:
        """Close the top dialog, or *widget* and every dialog above it.

        Each dialog above *widget* is closed first, the top one first, with the result ``None``.
        Per dialog, in order: it is removed, its ``on_close`` is called, and ``"closed"`` is sent.
        A callback may therefore open or close dialogs itself.

        ::

            widget given and not open, or nothing open -> return False
            loop:
                remove the top dialog, show the one below
                on_close(result if it is widget else None), then "closed"
                it was widget, or a callback closed widget -> return True
                otherwise (widget still open, maybe under dialogs a callback opened) -> loop

        :param result: passed to ``on_close`` and to the ``"closed"`` handlers of the dialog closed last.
        :param widget: the dialog to close, as passed to :meth:`open`.
            ``None`` closes the top dialog.
        :returns: whether a dialog was closed.
            It is ``False`` when no dialog is open, or when *widget* is not open in this stack.
        """
        if widget is None:
            if not self._levels:
                return False
            widget = self._levels[-1].widget
        elif all(level.widget is not widget for level in self._levels):
            return False

        while True:
            level = self._levels.pop()
            self._w = self._levels[-1].overlay if self._levels else self._base
            is_target = level.widget is widget
            level_result = result if is_target else None
            if level.on_close is not None:
                level.on_close(level_result)
            self._emit("closed", level.widget, level_result)
            # A callback may have opened dialogs above *widget*, which close too, or closed *widget* itself.
            if is_target or all(open_level.widget is not widget for open_level in self._levels):
                return True


def _close_by_signal(stack: OverlayStack, widget: Widget, _overlay: Overlay[Widget, Widget]) -> bool:
    """Close *widget* in *stack* with the result ``None``.

    It handles the ``"menu"`` and ``"click outside"`` signals of the dialog's overlay.
    The overlay holds *stack* weakly, so an open dialog does not keep a dropped stack alive.

    :returns: ``True``, which consumes the key or the press.
    """
    stack.close(widget=widget)
    return True
