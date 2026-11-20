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


"""Action menu: a launcher that opens a list of actions, with separators, accelerator keys and submenus."""

from __future__ import annotations

import dataclasses
import typing
import weakref

from urwid.command_map import Command
from urwid.signals import connect_signal
from urwid.util import is_mouse_press

from ._pop_up_list import _bar_settings, _BarSettings, _boxed_list, _PopUpListItem
from .attr_map import AttrMap
from .columns import Columns
from .constants import BOX_SYMBOLS, MouseButton, WrapMode
from .popup import PopUpLauncher
from .scrollable import SCROLLBAR_LEFT
from .text import Text
from .widget import WidgetWrap
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Sequence
    from typing import Literal, Self

    from urwid.canvas import Canvas, CompositeCanvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .popup import PopUpParametersModel
    from .scrollable import _ScrollBarOptions
    from .widget import AbstractFlowWidget, AbstractWidget

    # One entry of an item list: an item, markup for an item with that label, or None for a separator.
    _MenuEntry: typing.TypeAlias = "MenuItem | _TagMarkup | None"

_T = typing.TypeVar("_T")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class MenuItem:
    """One action of an :class:`ActionMenu`.

    >>> MenuItem("(D)elete", "delete", key="d")
    MenuItem(label='(D)elete', value='delete', enabled=True, key='d', submenu=())
    >>> MenuItem("Send to", submenu=["Mail", None, "Printer"]).submenu[2]
    MenuItem(label='Printer', value=None, enabled=True, key=None, submenu=())
    """

    #: Markup of the row; see :class:`Text <urwid.Text>` for markup.
    label: _TagMarkup
    #: Value for the application, which the menu itself does not read.
    value: typing.Any = None
    _: dataclasses.KW_ONLY
    #: A disabled item is drawn with the menu's ``disabled_map``, and it cannot be focused or chosen.
    enabled: bool = True
    #: Key that chooses the item while its list is open.
    key: str | None = None
    #: Entries of a child menu that this item opens instead of being chosen, as for :class:`ActionMenu` `items`.
    #: They are kept as a tuple of items, with ``None`` for a separator.
    submenu: Sequence[_MenuEntry] = ()

    def __post_init__(self) -> None:
        """Turn the entries of `submenu` into a tuple of items and separators.

        :raises ValueError: the label holds a line break, which a row of one line cannot show,
            `submenu` holds separators only, or two of its items have the same key.
        """
        if Text(self.label).pack()[1] > 1:
            raise ValueError(f"A menu item label must be one line, got {self.label!r}")
        entries = tuple(self.submenu)
        object.__setattr__(self, "submenu", _menu_entries(entries) if entries else ())


def _submenu(item: MenuItem) -> tuple[MenuItem | None, ...]:
    """Return the entries of `item`'s submenu, which ``MenuItem.__post_init__`` turned into items."""
    return typing.cast("tuple[MenuItem | None, ...]", item.submenu)


def _is_usable(item: MenuItem | None) -> bool:
    """Return whether `item` can be chosen or opened: it is enabled, and its submenu, if any, has such an item."""
    return item is not None and item.enabled and (not item.submenu or any(map(_is_usable, _submenu(item))))


def _menu_entries(entries: Iterable[_MenuEntry]) -> tuple[MenuItem | None, ...]:
    """Return `entries` with markup turned into items.

    :raises ValueError: there is no item, only separators, or two items have the same key.
    """
    items = tuple(entry if entry is None or isinstance(entry, MenuItem) else MenuItem(entry) for entry in entries)
    if all(item is None for item in items):
        raise ValueError(f"A menu needs at least one item, got {items!r}")
    keys = [item.key for item in items if item is not None and item.key is not None]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Menu item keys must differ, got {keys!r}")
    return items


@dataclasses.dataclass(frozen=True, slots=True)
class _MenuStyle:
    """Settings one menu shares with every list it opens, its submenus included."""

    align: Literal["left", "right"]
    border: bool
    show_keys: bool
    max_visible_items: int
    attr_map: _AttrMapLike
    focus_map: _AttrMapLike
    disabled_map: _AttrMapLike
    separator: str
    menu_indicator: Text
    bar: _BarSettings


@dataclasses.dataclass(frozen=True, slots=True)
class _ListLayout:
    """Size of one open list of a menu."""

    #: Columns of the pop-up: the rows, the border, and the scroll bar columns when the list scrolls.
    width: int
    #: Rows of the pop-up, the border included.
    height: int
    #: Whether the list has more rows than it shows, so it gets a scroll bar outside the border.
    scrolls: bool
    #: Columns of the key column, 0 when it is not drawn.
    key_width: int


def _list_layout(items: tuple[MenuItem | None, ...], style: _MenuStyle) -> _ListLayout:
    """Return the size of the open list of `items`."""
    indicator = style.menu_indicator.pack()[0]
    key_width = 0
    if style.show_keys:
        key_width = max((Text(item.key).pack()[0] for item in items if item is not None and item.key), default=0)
    content = max(
        Text(item.label).pack()[0] + (1 + indicator if item.submenu else 0) for item in items if item is not None
    ) + (key_width + 2 if key_width else 0)
    border = 2 if style.border else 0
    scrolls = len(items) > style.max_visible_items
    # One blank column after the widest row keeps the text off the right border.
    return _ListLayout(
        width=content + 1 + border + (style.bar.width if scrolls else 0),
        height=min(len(items), style.max_visible_items) + border,
        scrolls=scrolls,
        key_width=key_width,
    )


class _MenuOwner(PopUpLauncher[typing.Any]):
    """Launcher that opens one list of a menu: the menu itself, or the row of a submenu."""

    _items: tuple[MenuItem | None, ...]
    _style: _MenuStyle
    #: Whether the list is a child menu, which the key back towards its parent closes.
    _is_submenu: typing.ClassVar[bool] = False

    def _choose(self, item: MenuItem) -> None:
        """Close the list on a choice of `item`, and pass the choice on."""
        raise NotImplementedError

    def _back_command(self) -> Command | None:
        """Return the arrow command that points from the open list back to its parent, or ``None`` for none."""
        return None

    def create_pop_up(self) -> _MenuList:
        """Return the list of the items, focused on the first item that can be chosen."""
        return _MenuList(
            self._items,
            self._style,
            on_choose=self._choose,
            on_close=self.close_pop_up if self._is_submenu else None,
            back_command=self._back_command,
        )


class _MenuList(WidgetWrap[typing.Any]):
    """Open list of one menu level; it handles the accelerator keys, and the key that closes a submenu."""

    def __init__(
        self,
        items: tuple[MenuItem | None, ...],
        style: _MenuStyle,
        *,
        on_choose: Callable[[MenuItem], None],
        on_close: Callable[[], None] | None,
        back_command: Callable[[], Command | None],
    ) -> None:
        """Build the rows of `items`.

        :param on_choose: method of the launcher that opened the list, called with the chosen item.
        :param on_close: method that closes a submenu, called on the arrow back towards the parent list;
            ``None`` for the top list.
        :param back_command: method of the launcher that returns that arrow's command, from where the list was
            drawn; ``None`` for the top list.
        """
        # Weak, so the open list does not keep the launcher that opened it alive.
        self._on_choose = weakref.WeakMethod(on_choose)
        self._on_close = None if on_close is None else weakref.WeakMethod(on_close)
        self._back_command = weakref.WeakMethod(back_command)
        self._items = items
        self._style = style
        layout = _list_layout(items, style)
        rows: list[AbstractFlowWidget | None] = []
        # Submenu rows by item index, so an accelerator key can open one.
        self._submenu_rows: dict[int, _SubmenuRow] = {}
        for index, item in enumerate(items):
            if item is None:
                rows.append(None)
                continue
            row = self._row(item, style, layout, on_choose, weakref.ref(self))
            if isinstance(row, _SubmenuRow):
                self._submenu_rows[index] = row
            rows.append(row)
        focus = next((index for index, item in enumerate(items) if _is_usable(item)), 0)
        self._list_box, body = _boxed_list(rows, focus, border=style.border, bar=style.bar, separator=style.separator)
        super().__init__(AttrMap(body, style.attr_map))
        # Columns the list was last drawn in, which its launcher can make wider than the layout.
        self._drawn_width = layout.width
        self._rows_left = self._left_of_rows(layout.height)

    @property
    def back_command(self) -> Command | None:
        """Arrow command that points from this list back to its parent list, ``None`` for the top list."""
        back_command = self._back_command()
        return None if back_command is None else back_command()

    @property
    def drawn_width(self) -> int:
        """Columns of the list as last drawn, the border and the scroll bar included."""
        return self._drawn_width

    @property
    def rows_left(self) -> int:
        """Columns left of the rows of the list as last drawn.

        They are the border, and the scroll bar when it is on the left.
        """
        return self._rows_left

    def _left_of_rows(self, height: int) -> int:
        """Return the columns left of the rows when the list is drawn `height` rows high."""
        border = 1 if self._style.border else 0
        # Every entry is one row, so the bar is drawn when the entries and the border edges do not fit.
        bar_drawn = len(self._items) + 2 * border > height
        return border + (self._style.bar.width if bar_drawn and self._style.bar.side == SCROLLBAR_LEFT else 0)

    def render(self, size: tuple[int, int], focus: bool = False) -> Canvas:  # type: ignore[override]
        """Render the list, and remember where its rows are for the submenus opened from them."""
        self._drawn_width = size[0]
        self._rows_left = self._left_of_rows(size[1])
        return super().render(size, focus)

    @staticmethod
    def _row(
        item: MenuItem,
        style: _MenuStyle,
        layout: _ListLayout,
        on_choose: Callable[[MenuItem], None],
        parent_list: weakref.ref[_MenuList],
    ) -> AbstractFlowWidget:
        """Return the row of `item`: a choosable row, the launcher of its submenu, or a disabled row."""
        if _is_usable(item) and item.submenu:
            return _SubmenuRow(item, style, on_choose, layout, parent_list)
        label: AbstractFlowWidget = (
            _PopUpListItem(item.label, item, on_choose)
            if _is_usable(item)
            else Text(item.label, wrap=WrapMode.ELLIPSIS)
        )
        row = _labelled_row(label, item, style, layout)
        return AttrMap(row, None, style.focus_map) if _is_usable(item) else AttrMap(row, style.disabled_map)

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Pass `key` to the list; choose the item an unhandled key belongs to, and close a submenu on the way back."""
        if (unhandled := super().keypress(size, key)) is None:
            return None
        for index, item in enumerate(self._items):
            if item is not None and item.key == unhandled:
                if not _is_usable(item):
                    return None
                self._list_box.focus_position = index
                if item.submenu:
                    self._submenu_rows[index].open_pop_up()
                elif on_choose := self._on_choose():
                    on_choose(item)
                return None
        if self._on_close is not None and self._command_map[unhandled] == self.back_command:
            if on_close := self._on_close():
                on_close()
            return None
        return unhandled


def _labelled_row(
    label: AbstractFlowWidget,
    item: MenuItem,
    style: _MenuStyle,
    layout: _ListLayout,
) -> AbstractFlowWidget:
    """Return `label` with the submenu indicator after it and the key column before it, where they apply."""
    row = label
    if item.submenu:
        row = Columns([row, (style.menu_indicator.pack()[0], style.menu_indicator)], dividechars=1)
    if layout.key_width:
        row = Columns([(layout.key_width, Text(item.key or "")), row], dividechars=2)
    return row


class _SubmenuRow(_MenuOwner):
    """Row of a list that opens a child menu beside the list, and keeps its focus colour while the child is open."""

    _is_submenu = True

    def __init__(
        self,
        item: MenuItem,
        style: _MenuStyle,
        parent_choose: Callable[[MenuItem], None],
        parent_layout: _ListLayout,
        parent_list: weakref.ref[_MenuList],
    ) -> None:
        content = _labelled_row(SelectableIcon(item.label, 0, wrap=WrapMode.ELLIPSIS), item, style, parent_layout)
        super().__init__(AttrMap(content, None, style.focus_map), close_on_menu=True, close_on_click_outside=True)
        # The row's own attribute map, put back when the child menu closes.
        self._row_attr_map = self.original_widget.get_attr_map()
        self._items = _submenu(item)
        self._style = style
        self._parent_choose = weakref.WeakMethod(parent_choose)
        self._parent_list = parent_list
        # The side of the child list the parent list is on, as PopUpTarget last placed the child;
        # until then the side the alignment prefers.
        self._anchor_side: Literal["left", "right"] = "right" if style.align == "right" else "left"

    def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:  # type: ignore[override]
        """Open the child menu on the ``activate`` command, or on an arrow that does not lead back.

        In the top list both Left and Right open it.
        In a child list the arrow back towards its parent closes that list, and the other one opens this child.
        """
        parent_list = self._parent_list()
        back = None if parent_list is None else parent_list.back_command
        command = self._command_map[key]
        if command == Command.ACTIVATE or (command in {Command.LEFT, Command.RIGHT} and command != back):
            self.open_pop_up()
            return None
        return key

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        """Open the child menu on a button 1 press."""
        if button != MouseButton.LEFT or not is_mouse_press(event):
            return False
        self.open_pop_up()
        return True

    def open_pop_up(self) -> None:
        """Open the child menu and draw this row with the focus attribute while it is open."""
        super().open_pop_up()
        if self._style.focus_map is not None:
            self.original_widget.set_attr_map(self.original_widget.get_focus_map())

    def close_pop_up(self) -> None:
        """Close the child menu and draw this row as usual again."""
        super().close_pop_up()
        self.original_widget.set_attr_map(self._row_attr_map)

    def _back_command(self) -> Command:
        """Return the arrow that points from the child list back to the parent list, as it was drawn last."""
        return Command.LEFT if self._anchor_side == "left" else Command.RIGHT

    def _anchor_placed(self, side: Literal["left", "right"]) -> None:
        """Remember the side of the child list the parent list ended up on."""
        self._anchor_side = side

    def _choose(self, item: MenuItem) -> None:
        """Close the child menu, then pass the choice to the list this row is in."""
        self.close_pop_up()
        if parent_choose := self._parent_choose():
            parent_choose(item)

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return the child menu beside the parent list, continuing in the direction the menu opens.

        A child of the top list prefers the side the menu's alignment gives.
        A child of a child list prefers the direction that list went from its own parent, so a deep menu keeps
        going one way instead of turning back over the lists before it.
        The parent list is the horizontal anchor, so the child moves to the other side of it near a screen edge,
        and it never covers the parent while one side has room.
        """
        layout = _list_layout(self._items, self._style)
        inset = 1 if self._style.border else 0
        parent_list = self._parent_list()
        parent_width = parent_list.drawn_width if parent_list is not None else 0
        rows_left = parent_list.rows_left if parent_list is not None else inset
        back = None if parent_list is None else parent_list.back_command
        prefer_left = self._style.align == "right" if back is None else back == Command.RIGHT
        # The parent list starts `rows_left` columns left of this row, and is `parent_width` columns wide.
        if prefer_left:
            left, side = -rows_left, "right"
        else:
            left, side = parent_width - rows_left, "left"
        return {
            "left": left,
            # The first item of the child is level with this row.
            "top": -inset,
            "overlay_width": layout.width,
            "overlay_height": layout.height,
            "anchor_width": parent_width,
            "anchor_side": typing.cast("Literal['left', 'right']", side),
            "on_anchor_side": self._anchor_placed,
        }


class ActionMenu(_MenuOwner):
    """Launcher that opens a list of actions; choosing one closes the list and sends ``"action"``.

    The list opens below the launcher and moves above it when it does not fit there.
    With ``placement="center"`` it opens in the middle of the screen instead.
    :kbd:`up`, :kbd:`down`, :kbd:`home` and :kbd:`end` skip separators and disabled items.
    :kbd:`enter`, :kbd:`space`, a click, or an item's own `key` chooses it.
    An item with a `submenu` opens its child menu beside the list instead: a child of the top list on the side
    `align` prefers, a deeper one in the direction its parent list went, and either on the other side near a
    screen edge.
    :kbd:`left` and :kbd:`right` follow where the child is drawn:
    the arrow back towards the parent closes only the child, as :kbd:`esc` does,
    and the other arrow on a submenu row opens a further child.
    In the top list either arrow opens a child.
    With ``pass_arrows_below=True``, as for a menu bar, an arrow on a row of the top list with no submenu goes to
    the widgets under the list while the launcher has the focus.
    When one of them takes it, as a :class:`Columns <urwid.Columns>` of launchers does by moving the focus,
    the list closes; otherwise it stays open and the arrow is returned unhandled.
    :kbd:`esc`, or a click outside the list, closes it without a choice.

    Opening keys and buttons are set by `open_keys` and `open_buttons`; every other key and button goes to the
    launcher, so a list row given as `launcher` keeps working as a row.
    With no item that can be chosen there is nothing to open:
    the default label launcher is then not selectable and is drawn with `disabled_map`,
    and a `launcher` widget keeps every key and button, the opening ones included.

    .. important::
        ActionMenu requires ``MainLoop(..., pop_ups=True)``, or another :class:`PopUpTarget <urwid.PopUpTarget>`
        above it. The list is a pop-up, and without a target opening it shows nothing.

    Signals supported:

    - ``'action'``, sent as ``callback(menu, item)`` with the chosen :class:`MenuItem` after the list closed.
    - ``'open'`` and ``'close'``, sent as ``callback(menu)`` when the list opens and closes;
      see :class:`PopUpLauncher <urwid.PopUpLauncher>`.

    >>> menu = ActionMenu("Actions", ["Open", None, MenuItem("Delete", "delete", key="d")])
    >>> menu.render(()).text
    [b'Actions >']
    """

    #: Widget drawn after the label of the default launcher and of a submenu row; a subclass replaces it.
    menu_indicator: typing.ClassVar[Text] = Text(">")
    #: Character of a separator line; a subclass replaces it.
    separator: typing.ClassVar[str] = BOX_SYMBOLS.LIGHT.HORIZONTAL

    signals: typing.ClassVar[list[str]] = ["action"]

    @typing.overload
    def __init__(
        self,
        label: _TagMarkup | None,
        items: Iterable[_MenuEntry],
        *,
        launcher: AbstractWidget | None = ...,
        on_action: Callable[[Self, MenuItem, _T], typing.Any] | None = ...,
        user_data: _T = ...,
        open_keys: Collection[str] | None = ...,
        open_buttons: Collection[int] = ...,
        align: Literal["left", "right"] = ...,
        placement: Literal["launcher", "center"] = ...,
        pass_arrows_below: bool = ...,
        border: bool = ...,
        show_keys: bool = ...,
        max_visible_items: int = ...,
        attr_map: _AttrMapLike = ...,
        focus_map: _AttrMapLike = ...,
        disabled_map: _AttrMapLike = ...,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None: ...

    @typing.overload
    def __init__(
        self,
        label: _TagMarkup | None,
        items: Iterable[_MenuEntry],
        *,
        launcher: AbstractWidget | None = ...,
        on_action: Callable[[Self, MenuItem], typing.Any] | None = ...,
        user_data: None = None,
        open_keys: Collection[str] | None = ...,
        open_buttons: Collection[int] = ...,
        align: Literal["left", "right"] = ...,
        placement: Literal["launcher", "center"] = ...,
        pass_arrows_below: bool = ...,
        border: bool = ...,
        show_keys: bool = ...,
        max_visible_items: int = ...,
        attr_map: _AttrMapLike = ...,
        focus_map: _AttrMapLike = ...,
        disabled_map: _AttrMapLike = ...,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None: ...

    def __init__(
        self,
        label: _TagMarkup | None,
        items: Iterable[_MenuEntry],
        *,
        launcher: AbstractWidget | None = None,
        on_action: Callable[[Self, MenuItem, _T], typing.Any] | Callable[[Self, MenuItem], typing.Any] | None = None,
        user_data: _T | None = None,
        open_keys: Collection[str] | None = None,
        open_buttons: Collection[int] = (MouseButton.LEFT,),
        align: Literal["left", "right"] = "left",
        placement: Literal["launcher", "center"] = "launcher",
        pass_arrows_below: bool = False,
        border: bool = True,
        show_keys: bool = False,
        max_visible_items: int = 10,
        attr_map: _AttrMapLike = None,
        focus_map: _AttrMapLike = None,
        disabled_map: _AttrMapLike = None,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None:
        """Create a menu of `items`, opened from a label or from the `launcher` widget.

        :param label: markup of the default launcher, drawn with :attr:`menu_indicator` after it;
            ``None`` when `launcher` is given.
        :param items: the entries in list order: a :class:`MenuItem`, markup for an item with that label,
            or ``None`` for a separator.
        :param launcher: widget that opens the menu instead of the label, such as a row of a list.
        :param on_action: connected to ``"action"``, called as ``on_action(menu, item)``,
            or ``on_action(menu, item, user_data)`` when `user_data` is given.
        :param user_data: passed to `on_action`.
        :param open_keys: keys that open the list where `placement` says; ``None`` for the keys of the ``activate``
            command.
        :param open_buttons: mouse buttons whose press on the launcher opens the list as an opening key does.
        :param align: ``"right"`` lines up the right edge of the list with the launcher's, and opens submenus to the
            left; ``"left"`` does the opposite.
        :param placement: where an opening key or button opens the list: ``"launcher"`` at the launcher's edge,
            ``"center"`` in the middle of the :class:`PopUpTarget <urwid.PopUpTarget>`.
            :meth:`open_at` opens it at the given cell either way.
        :param pass_arrows_below: offer :kbd:`left` and :kbd:`right` on a row of the top list with no submenu
            to the widgets under the list, and close the list when they take it.
            A row of menu launchers then moves between menus; a lone menu keeps the arrow in its list.
        :param border: draw a box around each list, with separators joined to it.
        :param show_keys: draw each item's key in a column before its label.
        :param max_visible_items: most entries a list shows at once; it scrolls through the rest.
        :param attr_map: display attribute of the lists, as for :class:`AttrMap <urwid.AttrMap>`.
        :param focus_map: display attribute of the focused item, and of a submenu row while its child is open.
        :param disabled_map: display attribute of a disabled item, and of the default launcher with no item that
            can be chosen.
        :param scrollbar_options: the :class:`ScrollBar <urwid.ScrollBar>` parameters of the scroll bar of each list,
            with a ``scrollbar_`` prefix, such as ``scrollbar_thumb_char``, ``scrollbar_end_markers``,
            ``scrollbar_side`` and ``scrollbar_attr``; ``visible`` and ``delegate_selectable`` are left out.
        :raises ValueError: there is no item, `max_visible_items` is less than 1, two items of one list have the
            same key, an item label given as markup holds a line break, `align` is neither ``"left"`` nor
            ``"right"``, `placement` is neither ``"launcher"`` nor ``"center"``,
            `label` and `launcher` are both given or both ``None``,
            or :class:`ScrollBar <urwid.ScrollBar>` rejects the value of a ``scrollbar_`` parameter.
        :raises TypeError: `open_keys` is a single string rather than a collection of keys,
            or a keyword argument is neither a parameter of the menu nor one of `scrollbar_options`.
        """
        if max_visible_items < 1:
            raise ValueError(f"max_visible_items must be at least 1, got {max_visible_items!r}")
        if align not in ("left", "right"):
            raise ValueError(f"align must be 'left' or 'right', got {align!r}")
        if placement not in ("launcher", "center"):
            raise ValueError(f"placement must be 'launcher' or 'center', got {placement!r}")
        self._placement: Literal["launcher", "center"] = placement
        self._pass_arrows_below = pass_arrows_below
        self._items = _menu_entries(items)
        self._style = _MenuStyle(
            align=align,
            border=border,
            show_keys=show_keys,
            max_visible_items=max_visible_items,
            attr_map=attr_map,
            focus_map=focus_map,
            disabled_map=disabled_map,
            separator=self.separator,
            menu_indicator=self.menu_indicator,
            bar=_bar_settings(type(self).__name__, scrollbar_options),
        )
        if isinstance(open_keys, str):
            raise TypeError(f"open_keys must be a collection of keys, not one string, got {open_keys!r}")
        self._open_keys = None if open_keys is None else frozenset(open_keys)
        self._open_buttons = frozenset(open_buttons)
        self._usable = any(_is_usable(item) for item in self._items)
        # Where open_at() asked for the list, or None for the launcher's edge.
        self._pointer: tuple[int, int] | None = None
        self._fixed_width: int | None = None
        # Focus of the render in progress, see render().
        self._render_focus = False
        if label is not None and launcher is None:
            indicator_width = self.menu_indicator.pack()[0]
            self._fixed_width = Text(label).pack()[0] + 1 + indicator_width
            launcher = Columns(
                [SelectableIcon(label, 0, wrap=WrapMode.ELLIPSIS), (indicator_width, self.menu_indicator)],
                dividechars=1,
            )
            if not self._usable:
                launcher = AttrMap(launcher, disabled_map)
        elif label is not None or launcher is None:
            raise ValueError("ActionMenu needs either a label or a launcher widget, not both")
        super().__init__(launcher, close_on_menu=True, close_on_click_outside=True, signal_open_close=True)
        if on_action is not None:
            connect_signal(self, "action", on_action, user_data)

    @property
    def items(self) -> tuple[MenuItem | None, ...]:
        """Items of the menu in list order, ``None`` for a separator."""
        return self._items

    def selectable(self) -> bool:
        """Return whether the launcher takes keys: the default one only while there is an item to choose."""
        if self._fixed_width is not None:
            return self._usable
        return super().selectable()

    def open_pop_up(self) -> None:
        """Open the list where `placement` says; with no item that can be chosen, do nothing."""
        self._pointer = None
        if self._usable:
            super().open_pop_up()

    def open_at(self, col: int, row: int) -> None:
        """Open the list below column `col` of row `row` of the launcher.

        An application that opens the menu from its own key or mouse handler uses it,
        for example to open a context menu at the pointer.
        With no item that can be chosen, it does nothing.
        """
        if self._usable:
            self._pointer = (col, row)
            super().open_pop_up()

    def _choose(self, item: MenuItem) -> None:
        """Close the list, then send ``"action"`` with `item`."""
        self.close_pop_up()
        self._emit("action", item)

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return the list below the launcher's edge, in the middle, or below the cell given to :meth:`open_at`.

        Below an edge or a cell, the rows above the list are the vertical anchor,
        so it moves above them when it does not fit below.
        With `pass_arrows_below`, while the launcher has the focus, unused arrows are offered to the widgets
        under the list.
        """
        layout = _list_layout(self._items, self._style)
        parameters: PopUpParametersModel
        if self._pointer is not None:
            col, row = self._pointer
            parameters = {
                "left": col if self._style.align == "left" else col + 1 - layout.width,
                "top": row + 1,
                "overlay_width": layout.width,
                "overlay_height": layout.height,
                "anchor_height": 1,
            }
        else:
            match self._placement:
                case "center":
                    parameters = {
                        "left": "center",
                        "top": "middle",
                        "overlay_width": layout.width,
                        "overlay_height": layout.height,
                    }
                case "launcher":
                    # Before the first render, the size the default launcher packs to with no size given.
                    launcher_width, launcher_rows = self.launcher_size or (self._fixed_width or layout.width, 1)
                    width = max(launcher_width, layout.width) if self._style.align == "left" else layout.width
                    parameters = {
                        "left": 0 if self._style.align == "left" else launcher_width - width,
                        "top": launcher_rows,
                        "overlay_width": width,
                        "overlay_height": layout.height,
                        "anchor_height": launcher_rows,
                    }
                case _:
                    typing.assert_never(self._placement)
        # Only a launcher on the focus path receives what the widgets under the list do with the arrow,
        # so an unfocused one keeps it from the focused widget, which has nothing to do with the menu.
        if self._pass_arrows_below and self._render_focus:
            parameters["pass_key_below"] = self._pass_arrow_below
        return parameters

    def _pass_arrow_below(self, key: str, send_below: Callable[[str], str | None]) -> str | None:
        """Offer a left or right arrow the top list left unhandled to the widgets under it.

        The list closes when they handle the arrow, as a container of launchers does when it moves the focus.

        :returns: the key when it is not such an arrow, the list is already closed,
            or nothing under the list handled it, otherwise ``None``.
        """
        if self._command_map[key] not in {Command.LEFT, Command.RIGHT} or self.pop_up_widget is None:
            return key
        if (unhandled := send_below(key)) is None:
            self.close_pop_up()
        return unhandled

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the size of this widget; with no `size`, the default launcher is as wide as its label."""
        return super().pack(size or ((self._fixed_width,) if self._fixed_width is not None else ()), focus)

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas | Canvas:
        """Render the launcher, with the list attached when it is open."""
        if not size and self._fixed_width is not None:
            size = (self._fixed_width,)
        # Read by get_pop_up_parameters() during this render; the canvas cache keys each canvas by focus,
        # so a cached canvas carries the callback that matches its own focus.
        self._render_focus = focus
        return super().render(size, focus)

    def keypress(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        key: str,
    ) -> str | None:
        """Open the list on an opening key; pass every other key to the launcher.

        With no item that can be chosen, every key goes to the launcher.
        """
        opens = self._command_map[key] == Command.ACTIVATE if self._open_keys is None else key in self._open_keys
        if opens and self._usable:
            self.open_pop_up()
            return None
        if self._fixed_width is not None:
            return key
        return super().keypress(size, key)

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Open the list on a press of an opening button; pass every other event to the launcher.

        The list opens where `placement` says, as it does for an opening key.
        The opening press also asks the containers around the menu for the focus, see :meth:`Widget.request_focus`.
        With no item that can be chosen, every event goes to the launcher.
        """
        if self._usable and button in self._open_buttons and is_mouse_press(event):
            self.request_focus()
            self.open_pop_up()
            return True
        return super().mouse_event(size, event, button, col, row, focus)
