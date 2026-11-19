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


"""Parts of the pop-up lists that DropDown and ActionMenu open: a choosable row and the list around the rows."""

from __future__ import annotations

import dataclasses
import types
import typing
import weakref

from urwid.command_map import Command
from urwid.util import is_mouse_press

from .columns import Columns
from .constants import BOX_SYMBOLS, MouseButton, Sizing, WrapMode
from .divider import Divider
from .frame import Frame
from .list_walker import SimpleFocusListWalker
from .listbox import ListBox
from .scrollable import SCROLLBAR_LEFT, ScrollBar, _scrollbar_arguments
from .text import Text
from .widget import Widget
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from typing import Literal

    from urwid.canvas import Canvas
    from urwid.util import _TagMarkup

    from .widget import AbstractFlowWidget, AbstractWidget

_Choice = typing.TypeVar("_Choice")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class _BarSettings:
    """Settings of the scroll bar of a pop-up list.

    They are the :class:`ScrollBar` arguments, and the columns and the side those arguments give.
    """

    arguments: Mapping[str, typing.Any]
    width: int
    side: Literal["left", "right"]


def _bar_settings(owner: str, options: Mapping[str, typing.Any]) -> _BarSettings:
    """Return the settings of the ``scrollbar_`` keyword arguments `options` given to `owner`.

    :raises TypeError: a key of `options` is not a ``scrollbar_`` parameter.
    :raises ValueError: :class:`ScrollBar` rejects one of the values.
    """
    arguments = _scrollbar_arguments(owner, options)
    # A bar over an empty list checks the values now rather than when the list opens,
    # and applies ScrollBar's own defaults and limits to the width and the side.
    probe = ScrollBar(ListBox(SimpleFocusListWalker([])), **arguments)
    return _BarSettings(types.MappingProxyType(arguments), probe.scrollbar_width, probe.scrollbar_side)


class _PopUpListItem(SelectableIcon, typing.Generic[_Choice]):
    """One row of an open pop-up list: activating it, or clicking it, chooses its `choice`."""

    def __init__(self, label: _TagMarkup, choice: _Choice, on_choose: Callable[[_Choice], None]) -> None:
        super().__init__(label, 0, wrap=WrapMode.ELLIPSIS)
        self._choice = choice
        # Weak, so the open list does not keep the widget that opened it alive.
        self._on_choose = weakref.WeakMethod(on_choose)

    def _chosen(self) -> None:
        """Pass the choice to the callback, if its owner still exists."""
        if on_choose := self._on_choose():
            on_choose(self._choice)

    def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:  # type: ignore[override]
        """Choose this row on the ``activate`` command."""
        if self._command_map[key] != Command.ACTIVATE:
            return key
        self._chosen()
        return None

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        """Choose this row on a button 1 press."""
        if button != MouseButton.LEFT or not is_mouse_press(event):
            return False
        self._chosen()
        return True


def _boxed_list(
    rows: Iterable[AbstractFlowWidget | None],
    focus: int,
    *,
    border: bool,
    bar: _BarSettings,
    separator: str = BOX_SYMBOLS.LIGHT.HORIZONTAL,
) -> tuple[ListBox[int], AbstractWidget]:
    """Return the list box of `rows` and the pop-up widget around it.

    With `border`, each row is drawn between box sides, and a separator line joins them with tees.
    The scroll bar is drawn whenever the list has more rows than the height it is drawn at shows,
    outside the box on the side `bar` gives when there is one.
    A list that fits gets no bar column.

    :param rows: the rows in list order, ``None`` for a separator line of `separator` characters.
    :param focus: index of the focused row.
    :param bar: the scroll bar.
    :returns: the list box, and the widget that shows it with its border and scroll bar.
    """
    light = BOX_SYMBOLS.LIGHT
    framed: list[AbstractFlowWidget] = []
    for row in rows:
        if row is None:
            line = Divider(separator)
            framed.append(Columns([(1, Text(light.LEFT_T)), line, (1, Text(light.RIGHT_T))]) if border else line)
        else:
            framed.append(Columns([(1, Text(light.VERTICAL)), row, (1, Text(light.VERTICAL))]) if border else row)
    # Home and End skip separators and disabled rows, which are not selectable.
    list_box = ListBox(SimpleFocusListWalker(framed), home_end="selectable")
    # The setter rather than the walker's focus: it replaces the list box's initial move to the first selectable row,
    # so the first render keeps the rows above the focused one in view.
    list_box.focus_position = focus
    scroll_bar = ScrollBar(list_box, **bar.arguments)
    if not border:
        return list_box, scroll_bar

    def box(body: AbstractWidget, pad_width: int) -> Frame[typing.Any, typing.Any, typing.Any]:
        # The top and bottom edges leave the scroll bar's columns blank.
        pad: tuple[tuple[int, Text], ...] = ((pad_width, Text("")),) if pad_width else ()
        before, after = (pad, ()) if bar.side == SCROLLBAR_LEFT else ((), pad)
        return Frame(
            body,
            header=Columns([*before, _edge(light.TOP_LEFT, light.HORIZONTAL, light.TOP_RIGHT), *after]),
            footer=Columns([*before, _edge(light.BOTTOM_LEFT, light.HORIZONTAL, light.BOTTOM_RIGHT), *after]),
        )

    return list_box, _HeightChoice(len(framed) + 2, box(list_box, 0), box(scroll_bar, bar.width))


class _HeightChoice(Widget):
    """Box widget that draws one of two widgets: `fits` when it has at least `rows` rows, `taller` otherwise.

    Both widgets show the same list box, so its focus and its scrolling carry over from one to the other.
    """

    _sizing = frozenset((Sizing.BOX,))
    _selectable = True

    def __init__(self, rows: int, fits: AbstractWidget, taller: AbstractWidget) -> None:
        super().__init__()
        self._rows = rows
        self._fits = fits
        self._taller = taller

    def _widget(self, size: tuple[int, int]) -> AbstractWidget:
        return self._fits if size[1] >= self._rows else self._taller

    def render(self, size: tuple[int, int], focus: bool = False) -> Canvas:  # type: ignore[override]
        """Render the widget that the height of `size` selects."""
        return self._widget(size).render(size, focus)

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Pass `key` to the widget that the height of `size` selects."""
        return self._widget(size).keypress(size, key)

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor position of the widget that the height of `size` selects."""
        return self._widget(size).get_cursor_coords(size)  # type: ignore[attr-defined,no-any-return]

    def mouse_event(
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the event to the widget that the height of `size` selects."""
        return self._widget(size).mouse_event(size, event, button, col, row, focus)


def _edge(left: str, fill: str, right: str) -> Columns:
    """Return a row of `fill` between two one-column end characters."""
    return Columns([(1, Text(left)), Divider(fill), (1, Text(right))])
