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


"""Drop-down choice widget: shows the selected option and opens a list of all options below it."""

from __future__ import annotations

import typing

from urwid.command_map import Command
from urwid.util import is_mouse_press

from ._pop_up_list import _bar_settings, _boxed_list, _PopUpListItem
from .attr_map import AttrMap
from .columns import Columns
from .constants import MouseButton, WrapMode
from .popup import PopUpLauncher
from .text import Text
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from urwid.canvas import Canvas, CompositeCanvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .popup import PopUpParametersModel
    from .scrollable import _ScrollBarOptions
    from .widget import AbstractWidget


class DropDown(PopUpLauncher[Columns]):
    """Drop-down choice: shows the selected option, and on activation opens a list of all options below it.

    The list opens with the selected option focused. It moves above the widget when it does not fit below, and
    when it fits on neither side it takes the side with more rows and scrolls. :kbd:`enter`, :kbd:`space` or a
    click chooses the focused option and closes the list.
    :kbd:`esc`, or a click outside the list, closes it without a change.

    With a single option there is nothing to choose, so the widget is read-only: it is not selectable, and
    activating it opens no list.

    .. important::
        DropDown requires ``MainLoop(..., pop_ups=True)``, or another :class:`PopUpTarget <urwid.PopUpTarget>`
        above it. The list is a pop-up, and without a target activating the widget shows nothing.

    Signals supported:

    - ``'change'``, sent as ``callback(drop_down, new_index)`` before :attr:`selected` changes,
      so the callback still reads the previous value there.
    - ``'postchange'``, sent as ``callback(drop_down, previous_index)`` after :attr:`selected` and the label changed,
      so the callback reads the new value there.

    >>> drop_down = DropDown(["red", "green", "blue"], selected=1)
    >>> drop_down.render(()).text
    [b'green v']
    >>> drop_down.selected = 2
    >>> drop_down.render((10,)).text
    [b'blue     v']
    """

    #: Widget drawn after the selected option; a subclass replaces it to change the indicator.
    drop_down_indicator: typing.ClassVar[Text] = Text("v")

    signals: typing.ClassVar[list[str]] = ["change", "postchange"]

    def __init__(
        self,
        options: Iterable[_TagMarkup],
        *,
        selected: int = 0,
        max_visible_items: int = 10,
        attr_map: _AttrMapLike = None,
        focus_map: _AttrMapLike = None,
        border: bool = False,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None:
        """Create a drop-down over `options`, with the option at index `selected` shown.

        :param options: markup of each option, in list order; see :class:`Text <urwid.Text>` for markup.
        :param selected: index of the option shown first.
        :param max_visible_items: most options the open list shows at once; it scrolls through the rest.
        :param attr_map: display attribute of each option in the open list, as for :class:`AttrMap <urwid.AttrMap>`.
        :param focus_map: display attribute of the focused option in the open list.
        :param border: draw a box around the open list, with its scroll bar outside the box,
            in the display attribute of `attr_map`; every option must then be one line.
        :param scrollbar_options: the :class:`ScrollBar <urwid.ScrollBar>` parameters of the open list's scroll bar,
            with a ``scrollbar_`` prefix, such as ``scrollbar_thumb_char``, ``scrollbar_end_markers``,
            ``scrollbar_side`` and ``scrollbar_attr``; ``visible`` and ``delegate_selectable`` are left out.
        :raises ValueError: `options` is empty, `max_visible_items` is less than 1, `border` is set and an
            option takes more than one line, or :class:`ScrollBar <urwid.ScrollBar>` rejects the value of a
            ``scrollbar_`` parameter.
        :raises TypeError: a keyword argument is neither a parameter of the drop-down nor one of `scrollbar_options`.
        :raises IndexError: `selected` is not an index of `options`.
        """
        self._bar = _bar_settings(type(self).__name__, scrollbar_options)
        self._options: tuple[_TagMarkup, ...] = tuple(options)
        if not self._options:
            raise ValueError("DropDown needs at least one option")
        if max_visible_items < 1:
            raise ValueError(f"max_visible_items must be at least 1, got {max_visible_items!r}")
        if border and any(Text(option).pack()[1] > 1 for option in self._options):
            raise ValueError("A DropDown with a border needs options of one line, as its box sides are one row high")

        self._max_visible_items = max_visible_items
        self._attr_map = attr_map
        self._focus_map = focus_map
        self._border = border
        # Widest option, so the widget and its list do not change width with the selection.
        self._options_width = max(Text(option).pack()[0] for option in self._options)
        indicator_width = self.drop_down_indicator.pack()[0]
        self._fixed_width = self._options_width + 1 + indicator_width

        self._label = SelectableIcon(self._options[0], 0, wrap=WrapMode.ELLIPSIS)
        super().__init__(
            Columns([self._label, (indicator_width, self.drop_down_indicator)], dividechars=1),
            close_on_menu=True,
            close_on_click_outside=True,
        )

        self._selected = 0
        self.selected = selected

    def selectable(self) -> bool:
        """Return whether there is more than one option to choose from."""
        return len(self._options) > 1

    @property
    def options(self) -> tuple[_TagMarkup, ...]:
        """Markup of each option, in list order."""
        return self._options

    @property
    def selected(self) -> int:
        """Index of the selected option.

        Setting it to an index that differs from the current one sends two signals:

        - ``'change'``, with the new index, before the selection changes;
        - ``'postchange'``, with the previous index, once :attr:`selected` and the label show the new option.

        :raises IndexError: the new value is not an index of :attr:`options`.
        """
        return self._selected

    @selected.setter
    def selected(self, index: int) -> None:
        if not 0 <= index < len(self._options):
            raise IndexError(f"selected must be in range(0, {len(self._options)}), got {index!r}")
        if index == self._selected:
            return
        self._emit("change", index)
        previous, self._selected = self._selected, index
        self._label.set_text(self._options[index])
        self._emit("postchange", previous)

    def _choose(self, index: int) -> None:
        self.close_pop_up()
        self.selected = index

    def create_pop_up(self) -> AbstractWidget:
        """Return the list of all options, with the selected one focused; it scrolls when they do not all fit."""
        items = [
            AttrMap(_PopUpListItem(option, index, self._choose), self._attr_map, self._focus_map)
            for index, option in enumerate(self._options)
        ]
        _list_box, body = _boxed_list(items, self._selected, border=self._border, bar=self._bar)
        return AttrMap(body, self._attr_map) if self._border else body

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return the list position directly below this widget, anchored to it so it can move above it."""
        # Before the first render, the size the widget packs to with no size given.
        width, rows = self.launcher_size or (self._fixed_width, 1)
        visible = min(len(self._options), self._max_visible_items)
        if self._border:
            # A blank column after the widest option, the box sides, and the scroll bar outside the box.
            list_width = self._options_width + 3 + (self._bar.width if len(self._options) > visible else 0)
            visible += 2
        else:
            # Room for the scroll bar beside the widest option.
            list_width = self._options_width + self._bar.width
        return {
            "left": 0,
            "top": rows,
            "overlay_width": max(width, list_width),
            "overlay_height": visible,
            "anchor_height": rows,
        }

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the size of this widget; with no `size`, as wide as the widest option."""
        return super().pack(size or (self._fixed_width,), focus)

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas | Canvas:
        """Render the selected option and the indicator, with the list attached when it is open."""
        return super().render(size or (self._fixed_width,), focus)

    def keypress(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        key: str,
    ) -> str | None:
        """Open the list on the ``activate`` command.

        When the widget is not selectable, the list does not open and the key is returned unhandled.
        """
        if self._command_map[key] != Command.ACTIVATE or not self.selectable():
            return key
        self.open_pop_up()
        return None

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        """Open the list on a button 1 press.

        When the widget is not selectable, the list does not open and the press is not handled.
        """
        if button != MouseButton.LEFT or not is_mouse_press(event) or not self.selectable():
            return False
        self.open_pop_up()
        return True
