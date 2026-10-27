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
import weakref

from urwid.command_map import Command
from urwid.util import is_mouse_press

from .attr_map import AttrMap
from .columns import Columns
from .constants import WrapMode
from .list_walker import SimpleFocusListWalker
from .listbox import ListBox
from .popup import PopUpLauncher
from .scrollable import ScrollBar
from .text import Text
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Mapping

    from urwid.canvas import Canvas, CompositeCanvas
    from urwid.util import _TagMarkup

    from .popup import PopUpParametersModel


class _DropDownItem(SelectableIcon):
    """One option of an open drop-down list: activating it, or clicking it, chooses the option."""

    def __init__(self, label: _TagMarkup, index: int, on_choose: Callable[[int], None]) -> None:
        super().__init__(label, 0, wrap=WrapMode.ELLIPSIS)
        self._index = index
        # Weak, so the open list does not keep its DropDown alive.
        self._on_choose = weakref.WeakMethod(on_choose)

    def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:  # type: ignore[override]
        """Choose this option on the ``activate`` command."""
        if self._command_map[key] != Command.ACTIVATE:
            return key
        if on_choose := self._on_choose():
            on_choose(self._index)
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
        """Choose this option on a button 1 press."""
        if button != 1 or not is_mouse_press(event):
            return False
        if on_choose := self._on_choose():
            on_choose(self._index)
        return True


class DropDown(PopUpLauncher[Columns]):
    """Drop-down choice: shows the selected option, and on activation opens a list of all options below it.

    The list opens with the selected option focused. It moves above the widget when it does not fit below, and
    when it fits on neither side it takes the side with more rows and scrolls. :kbd:`enter`, :kbd:`space` or a
    click chooses the focused option and closes the list; :kbd:`esc` closes it without a change.

    .. important::
        DropDown requires ``MainLoop(..., pop_ups=True)``, or another :class:`PopUpTarget <urwid.PopUpTarget>`
        above it. The list is a pop-up, and without a target activating the widget shows nothing.

    Signals supported: ``'change'``, sent as ``callback(drop_down, new_index)`` before :attr:`selected` changes,
    so the callback still reads the previous value there.

    >>> drop_down = DropDown(["red", "green", "blue"], selected=1)
    >>> drop_down.render(()).text
    [b'green v']
    >>> drop_down.selected = 2
    >>> drop_down.render((10,)).text
    [b'blue     v']
    """

    #: Widget drawn after the selected option; a subclass replaces it to change the indicator.
    drop_down_indicator: typing.ClassVar[Text] = Text("v")

    signals: typing.ClassVar[list[str]] = ["change"]

    def __init__(
        self,
        options: Iterable[_TagMarkup],
        *,
        selected: int = 0,
        max_visible_items: int = 10,
        attr_map: Hashable | Mapping[Hashable, Hashable] = None,
        focus_map: Hashable | Mapping[Hashable, Hashable] = None,
    ) -> None:
        """Create a drop-down over `options`, with the option at index `selected` shown.

        :param options: markup of each option, in list order; see :class:`Text <urwid.Text>` for markup.
        :param selected: index of the option shown first.
        :param max_visible_items: most options the open list shows at once; it scrolls through the rest.
        :param attr_map: display attribute of each option in the open list, as for :class:`AttrMap <urwid.AttrMap>`.
        :param focus_map: display attribute of the focused option in the open list.
        :raises ValueError: `options` is empty, or `max_visible_items` is less than 1.
        :raises IndexError: `selected` is not an index of `options`.
        """
        self._options: tuple[_TagMarkup, ...] = tuple(options)
        if not self._options:
            raise ValueError("DropDown needs at least one option")
        if max_visible_items < 1:
            raise ValueError(f"max_visible_items must be at least 1, got {max_visible_items!r}")

        self._max_visible_items = max_visible_items
        self._attr_map = attr_map
        self._focus_map = focus_map
        # Widest option, so the widget and its list do not change width with the selection.
        self._options_width = max(Text(option).pack()[0] for option in self._options)
        indicator_width = self.drop_down_indicator.pack()[0]
        self._fixed_width = self._options_width + 1 + indicator_width

        self._label = SelectableIcon(self._options[0], 0, wrap=WrapMode.ELLIPSIS)
        super().__init__(
            Columns([self._label, (indicator_width, self.drop_down_indicator)], dividechars=1),
            close_on_menu=True,
        )

        self._selected = 0
        self.selected = selected

    @property
    def options(self) -> tuple[_TagMarkup, ...]:
        """Markup of each option, in list order."""
        return self._options

    @property
    def selected(self) -> int:
        """Index of the selected option.

        Setting it sends the ``'change'`` signal when the index differs from the current one.

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
        self._selected = index
        self._label.set_text(self._options[index])

    def _choose(self, index: int) -> None:
        self.close_pop_up()
        self.selected = index

    def create_pop_up(self) -> ScrollBar[ListBox[int]]:
        """Return the list of all options, with the selected one focused; it scrolls when they do not all fit."""
        items = [
            AttrMap(_DropDownItem(option, index, self._choose), self._attr_map, self._focus_map)
            for index, option in enumerate(self._options)
        ]
        list_box = ListBox(SimpleFocusListWalker(items))
        list_box.focus_position = self._selected
        return ScrollBar(list_box)

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return the list position directly below this widget, anchored to it so it can move above it."""
        # Before the first render, the size the widget packs to with no size given.
        width, rows = self.launcher_size or (self._fixed_width, 1)
        return {
            "left": 0,
            "top": rows,
            # One column more than the widest option leaves room for the scroll bar.
            "overlay_width": max(width, self._options_width + 1),
            "overlay_height": min(len(self._options), self._max_visible_items),
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
        """Open the list on the ``activate`` command."""
        if self._command_map[key] != Command.ACTIVATE:
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
        """Open the list on a button 1 press."""
        if button != 1 or not is_mouse_press(event):
            return False
        self.open_pop_up()
        return True
