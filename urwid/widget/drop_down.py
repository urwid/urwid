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

from urwid.canvas import CompositeCanvas
from urwid.command_map import Command
from urwid.util import is_mouse_press

from ._pop_up_list import _bar_settings, _boxed_list, _PopUpListItem
from .attr_map import AttrMap, _attr_map_dict
from .columns import Columns
from .constants import BOX_SYMBOLS, MouseButton, WrapMode
from .divider import Divider
from .popup import PopUpLauncher
from .text import Text
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from urwid.canvas import Canvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .popup import PopUpParametersModel
    from .scrollable import _ScrollBarOptions
    from .widget import AbstractFlowWidget, AbstractWidget


class DropDown(PopUpLauncher[Columns]):
    """Drop-down choice: shows the selected option, and on activation opens a list of all options below it.

    The list opens with the selected option focused. It moves above the widget when it does not fit below, and
    when it fits on neither side it takes the side with more rows and scrolls. :kbd:`enter`, :kbd:`space` or a
    click chooses the focused option and closes the list.
    :kbd:`esc`, or a click outside the list, closes it without a change.

    ``None`` among the options draws a separator line, and an option whose index is in `disabled` is drawn with
    `disabled_map`.
    Neither can be focused or chosen, so :kbd:`up`, :kbd:`down`, :kbd:`home` and :kbd:`end` skip them.

    With a single option that can be chosen there is nothing to choose, so the widget is read-only: it is not
    selectable, it is drawn with `disabled_map`, and activating it opens no list.

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
    >>> sizes = DropDown(["any", None, "small", "large"], disabled={3})
    >>> sizes.selected
    0
    """

    #: Widget drawn after the selected option; a subclass replaces it to change the indicator.
    drop_down_indicator: typing.ClassVar[Text] = Text("v")
    #: Character of a separator line; a subclass replaces it.
    separator: typing.ClassVar[str] = BOX_SYMBOLS.LIGHT.HORIZONTAL

    signals: typing.ClassVar[list[str]] = ["change", "postchange"]

    def __init__(
        self,
        options: Iterable[_TagMarkup | None],
        *,
        selected: int | None = None,
        disabled: Collection[int] = (),
        max_visible_items: int = 10,
        attr_map: _AttrMapLike = None,
        focus_map: _AttrMapLike = None,
        disabled_map: _AttrMapLike = None,
        border: bool = False,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None:
        """Create a drop-down over `options`, with the option at index `selected` shown.

        :param options: markup of each option, in list order, or ``None`` for a separator;
            see :class:`Text <urwid.Text>` for markup.
        :param selected: index of the option shown first; ``None`` for the first option that can be chosen.
        :param disabled: indexes of the options that are shown in the open list but cannot be chosen.
        :param max_visible_items: most rows the open list shows at once, separators included;
            it scrolls through the rest.
        :param attr_map: display attribute of each option in the open list, as for :class:`AttrMap <urwid.AttrMap>`.
        :param focus_map: display attribute of the focused option in the open list.
        :param disabled_map: display attribute of a disabled option in the open list, applied over `attr_map`,
            and of the whole widget while it is read-only.
        :param border: draw a box around the open list, with its scroll bar outside the box,
            in the display attribute of `attr_map`; every option must then be one line.
        :param scrollbar_options: the :class:`ScrollBar <urwid.ScrollBar>` parameters of the open list's scroll bar,
            with a ``scrollbar_`` prefix, such as ``scrollbar_thumb_char``, ``scrollbar_end_markers``,
            ``scrollbar_side`` and ``scrollbar_attr``; ``visible`` and ``delegate_selectable`` are left out.
        :raises ValueError: one of these holds:

            - `options` has no option that can be chosen.
            - `selected` is a separator or a disabled option.
            - `disabled` names a separator.
            - `max_visible_items` is less than 1.
            - `border` is set and an option takes more than one line.
            - :class:`ScrollBar <urwid.ScrollBar>` rejects the value of a ``scrollbar_`` parameter.
        :raises TypeError: a keyword argument is neither a parameter of the drop-down nor one of `scrollbar_options`.
        :raises IndexError: `selected` or an index in `disabled` is not an index of `options`.
        :raises AttrMapError: a key or value of `disabled_map` is not hashable.
        """
        self._bar = _bar_settings(type(self).__name__, scrollbar_options)
        self._options: tuple[_TagMarkup | None, ...] = tuple(options)
        self._disabled = frozenset(disabled)
        for index in self._disabled:
            self._check_index("disabled", index)
            if self._options[index] is None:
                raise ValueError(f"disabled names separator {index!r}, which cannot be chosen anyway")
        choosable = [
            index for index, option in enumerate(self._options) if option is not None and index not in self._disabled
        ]
        if not choosable:
            raise ValueError("DropDown needs at least one option that is neither a separator nor disabled")
        if max_visible_items < 1:
            raise ValueError(f"max_visible_items must be at least 1, got {max_visible_items!r}")
        labels = [option for option in self._options if option is not None]
        if border and any(Text(option).pack()[1] > 1 for option in labels):
            raise ValueError("A DropDown with a border needs options of one line, as its box sides are one row high")
        if selected is None:
            selected = choosable[0]
        else:
            self._check_choosable(selected)

        self._max_visible_items = max_visible_items
        self._attr_map = attr_map
        self._focus_map = focus_map
        self._disabled_map = _attr_map_dict(disabled_map)
        self._border = border
        self._choosable_count = len(choosable)
        # Widest option, so the widget and its list do not change width with the selection.
        self._options_width = max(Text(option).pack()[0] for option in labels)
        indicator_width = self.drop_down_indicator.pack()[0]
        self._fixed_width = self._options_width + 1 + indicator_width

        self._selected = selected
        # A choosable option is never a separator.
        self._label = SelectableIcon(typing.cast("_TagMarkup", self._options[selected]), 0, wrap=WrapMode.ELLIPSIS)
        super().__init__(
            Columns([self._label, (indicator_width, self.drop_down_indicator)], dividechars=1),
            close_on_menu=True,
            close_on_click_outside=True,
        )

    def _check_index(self, name: str, index: int) -> None:
        """Check that `index` is an index of the options.

        :raises IndexError: it is not; the message names the value as `name`.
        """
        if not 0 <= index < len(self._options):
            raise IndexError(f"{name} must be in range(0, {len(self._options)}), got {index!r}")

    def _check_choosable(self, index: int) -> None:
        """Raise when `index` cannot be the selected option.

        :raises IndexError: `index` is not an index of the options.
        :raises ValueError: the option at `index` is a separator or disabled.
        """
        self._check_index("selected", index)
        if self._options[index] is None or index in self._disabled:
            raise ValueError(f"selected must name an option that is neither a separator nor disabled, got {index!r}")

    def selectable(self) -> bool:
        """Return whether there is more than one option to choose from."""
        return self._choosable_count > 1

    @property
    def options(self) -> tuple[_TagMarkup | None, ...]:
        """Markup of each option, in list order, ``None`` for a separator."""
        return self._options

    @property
    def disabled(self) -> frozenset[int]:
        """Indexes of the options that are shown in the open list but cannot be chosen."""
        return self._disabled

    @property
    def selected(self) -> int:
        """Index of the selected option.

        Setting it to an index that differs from the current one sends two signals:

        - ``'change'``, with the new index, before the selection changes;
        - ``'postchange'``, with the previous index, once :attr:`selected` and the label show the new option.

        :raises IndexError: the new value is not an index of :attr:`options`.
        :raises ValueError: the new value names a separator or a disabled option.
        """
        return self._selected

    @selected.setter
    def selected(self, index: int) -> None:
        self._check_choosable(index)
        if index == self._selected:
            return
        self._emit("change", index)
        previous, self._selected = self._selected, index
        self._label.set_text(typing.cast("_TagMarkup", self._options[index]))
        self._emit("postchange", previous)

    def _choose(self, index: int) -> None:
        self.close_pop_up()
        self.selected = index

    def create_pop_up(self) -> AbstractWidget:
        """Return the list of all options, with the selected one focused; it scrolls when they do not all fit."""
        items: list[AbstractFlowWidget | None] = []
        for index, option in enumerate(self._options):
            if option is None:
                # A bordered list draws its own separator, joined to the box; the box is already in `attr_map`.
                items.append(None if self._border else AttrMap(Divider(self.separator), self._attr_map))
            elif index in self._disabled:
                items.append(AttrMap(AttrMap(Text(option, wrap=WrapMode.ELLIPSIS), self._disabled_map), self._attr_map))
            else:
                items.append(AttrMap(_PopUpListItem(option, index, self._choose), self._attr_map, self._focus_map))
        _list_box, body = _boxed_list(
            items,
            self._selected,
            border=self._border,
            bar=self._bar,
            separator=self.separator,
        )
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
        """Render the selected option and the indicator, with the list attached when it is open.

        A read-only drop-down is drawn with `disabled_map`.
        """
        canv = super().render(size or (self._fixed_width,), focus)
        if self.selectable():
            return canv
        canv = CompositeCanvas(canv)
        canv.fill_attr_apply(self._disabled_map)
        return canv

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
