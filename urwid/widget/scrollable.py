# Copyright (C) 2024 Urwid developers
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
#
# Copyright (C) 2017-2024 rndusr (https://github.com/rndusr)
# Re-licensed from gpl-3.0 with author permission.
# Permission comment link: https://github.com/markqvist/NomadNet/pull/46#issuecomment-1892712616

"""Scrollable and ScrollBar: decorations that scroll a box widget."""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import math
import typing

from urwid.util import is_mouse_press

from .constants import BOX_SYMBOLS, SHADE_SYMBOLS, Sizing
from .widget import AbstractBoxWidget, AbstractWidget
from .widget_decoration import WidgetDecoration, WidgetError

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterator
    from typing import Literal

    from urwid import Canvas, CompositeCanvas

    from .container import WidgetContainerListContentsMixin
    from .listbox import ListBox
    from .widget import AbstractFixedWidget, AbstractFlowWidget


__all__ = (
    "ScrollBar",
    "Scrollable",
    "ScrollableError",
    "ScrollbarSymbols",
    "SupportsRelativeScroll",
    "SupportsScroll",
)


WrappedScrollableWidget = typing.TypeVar("WrappedScrollableWidget", bound="SupportsScroll")
WrappedScrollWidget = typing.TypeVar("WrappedScrollWidget", bound="AbstractFlowWidget | AbstractFixedWidget")


class ScrollableError(WidgetError):
    """Scrollable specific widget errors."""


# Scroll actions
SCROLL_LINE_UP = "line up"
SCROLL_LINE_DOWN = "line down"
SCROLL_PAGE_UP = "page up"
SCROLL_PAGE_DOWN = "page down"
SCROLL_TO_TOP = "to top"
SCROLL_TO_END = "to end"

# Scrollbar positions
SCROLLBAR_LEFT: typing.Final = "left"
SCROLLBAR_RIGHT: typing.Final = "right"

# Mouse wheel buttons, vertical and horizontal: they send no release, so they never start or follow a drag.
_WHEEL_BUTTONS: typing.Final = frozenset((4, 5, 6, 7))


class ScrollbarSymbols(enum.StrEnum):
    """Common symbols suitable for scrollbar.

    The thumb and trough symbols come first, and the ``ARROW_*`` pairs for the end markers follow them.

    Only these members are also drawn on terminals without UTF-8, where the others are drawn as ``?``:

    - ASCII: :attr:`ARROW_ASCII_UP` and :attr:`ARROW_ASCII_DOWN`.
    - DEC special graphics: :attr:`MEDIUM_SHADE`, :attr:`DRAWING_LIGHT`, :attr:`BLACK_VERTICAL_RECTANGLE`
      and :attr:`MIDDLE_DOT`.
    """

    FULL_BLOCK = SHADE_SYMBOLS.FULL_BLOCK
    DARK_SHADE = SHADE_SYMBOLS.DARK_SHADE
    MEDIUM_SHADE = SHADE_SYMBOLS.MEDIUM_SHADE
    LITE_SHADE = SHADE_SYMBOLS.LITE_SHADE

    DRAWING_LIGHT = BOX_SYMBOLS.LIGHT.VERTICAL
    DRAWING_LIGHT_2_DASH = BOX_SYMBOLS.LIGHT.VERTICAL_2_DASH
    DRAWING_LIGHT_3_DASH = BOX_SYMBOLS.LIGHT.VERTICAL_3_DASH
    DRAWING_LIGHT_4_DASH = BOX_SYMBOLS.LIGHT.VERTICAL_4_DASH

    DRAWING_HEAVY = BOX_SYMBOLS.HEAVY.VERTICAL
    DRAWING_HEAVY_2_DASH = BOX_SYMBOLS.HEAVY.VERTICAL_2_DASH
    DRAWING_HEAVY_3_DASH = BOX_SYMBOLS.HEAVY.VERTICAL_3_DASH
    DRAWING_HEAVY_4_DASH = BOX_SYMBOLS.HEAVY.VERTICAL_4_DASH

    DRAWING_DOUBLE = BOX_SYMBOLS.DOUBLE.VERTICAL

    BLACK_VERTICAL_RECTANGLE = "▮"
    MIDDLE_DOT = "·"

    ARROW_TRIANGLE_UP = "▲"
    ARROW_TRIANGLE_DOWN = "▼"
    ARROW_SMALL_TRIANGLE_UP = "▴"
    ARROW_SMALL_TRIANGLE_DOWN = "▾"
    ARROW_WHITE_TRIANGLE_UP = "△"
    ARROW_WHITE_TRIANGLE_DOWN = "▽"
    ARROW_UP = "↑"
    ARROW_DOWN = "↓"
    ARROW_ASCII_UP = "^"
    ARROW_ASCII_DOWN = "v"


@typing.runtime_checkable
class SupportsScroll(AbstractBoxWidget, typing.Protocol):
    """Scroll specific methods."""

    def get_scrollpos(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the index of the first visible row."""
        ...

    def rows_max(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Return the total number of rows the widget can render."""
        ...


@typing.runtime_checkable
class SupportsRelativeScroll(AbstractBoxWidget, typing.Protocol):
    """Relative scroll-specific methods."""

    def require_relative_scroll(self, size: tuple[int, int], focus: bool = False) -> bool:
        """Return whether the widget should be scrolled using relative position rather than absolute rows."""
        ...

    def get_first_visible_pos(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the index of the first visible item."""
        ...

    def get_visible_amount(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the number of items currently visible."""
        ...


def orig_iter(w: AbstractWidget) -> Iterator[AbstractWidget]:
    """Yield `w` and each of its `original_widget` ancestors, stopping at the first cycle."""
    visited = {w}
    yield w
    while (w := getattr(w, "original_widget", w)) not in visited:
        visited.add(w)
        yield w


class Scrollable(WidgetDecoration[WrappedScrollWidget]):
    """Box widget decoration that makes a fixed or flow widget vertically scrollable."""

    def sizing(self) -> frozenset[Sizing]:
        """Return that this widget is always a box widget."""
        return frozenset((Sizing.BOX,))

    def selectable(self) -> bool:
        """Return whether the widget accepts the input focus.

        Always ``True``, unless :attr:`delegate_selectable` is set: then what the wrapped widget returns.
        """
        return not self.delegate_selectable or self._original_widget.selectable()

    def __init__(
        self,
        widget: WrappedScrollWidget,
        force_forward_keypress: bool = False,
        *,
        delegate_selectable: bool = False,
    ) -> None:
        """Box widget that makes a fixed or flow widget vertically scrollable.

        .. note::
            Focusable widgets are handled, including switching focus, but possibly not intuitively,
            depending on the arrangement of widgets.

            When switching focus to a widget that is ouside of the visible part of the original widget,
            the canvas scrolls up/down to the focused widget.

            It would be better to scroll until the next focusable widget is in sight first.
            But for that to work we must somehow obtain a list of focusable rows in the original canvas.

        :param widget: fixed or flow widget to scroll.
        :param force_forward_keypress: pass every key to *widget* first, even when it shows no cursor.
        :param delegate_selectable: take the input focus only when *widget* is selectable.
            A widget that is not, such as a :class:`Text`, then cannot be scrolled by keys.

        :raises ValueError: *widget* is neither a FIXED nor a FLOW widget.
        """
        if not widget.sizing() & frozenset((Sizing.FIXED, Sizing.FLOW)):
            raise ValueError(f"Not a fixed or flow widget: {widget!r}")

        self._trim_top = 0
        self._scroll_action: str | None = None
        self._forward_keypress: bool | None = None
        self._old_cursor_coords: tuple[int, int] | None = None
        self._rows_max_cached = 0
        self.force_forward_keypress = force_forward_keypress
        # whether selectable() asks the wrapped widget instead of reporting True
        self.delegate_selectable = delegate_selectable
        super().__init__(widget)

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render the wrapped widget, trimmed to the current scroll position."""
        from urwid import canvas

        maxcol, maxrow = size

        def automove_cursor() -> None:
            ch = 0
            last_hidden = False
            first_visible = False
            for pwi, (w, _o) in enumerate(
                typing.cast(
                    "WidgetContainerListContentsMixin[tuple[AbstractWidget, typing.Any]]",
                    ow,
                ).contents
            ):
                wcanv = w.render((maxcol,))

                if wh := wcanv.rows():
                    ch += wh

                if not last_hidden and ch >= self._trim_top:
                    last_hidden = True

                elif last_hidden:
                    if not first_visible:
                        first_visible = True

                    if not w.selectable():
                        continue

                    typing.cast(
                        "WidgetContainerListContentsMixin[tuple[AbstractWidget, typing.Any]]",
                        ow,
                    ).focus_position = pwi

                    st = None
                    nf = ow.focus
                    if hasattr(nf, "key_timeout"):
                        st = nf
                    elif (no := getattr(nf, "original_widget", None)) is not None:
                        if hasattr(no, "original_widget"):
                            st = no.original_widget
                        elif hasattr(no, "key_timeout"):
                            st = no

                    if st and hasattr(st, "key_timeout") and callable(getattr(st, "keypress", None)):
                        st.keypress(None, None)  # type: ignore[arg-type]  # Do not break legacy API

                    break

        # Render complete original widget
        ow = self._original_widget
        ow_size = self._get_original_widget_size(size)
        canv_full = ow.render(ow_size, focus)  # type: ignore[arg-type]

        # Make full canvas editable
        canv = canvas.CompositeCanvas(canv_full)
        canv_cols, canv_rows = canv.cols(), canv.rows()

        if canv_cols <= maxcol and (pad_width := maxcol - canv_cols) > 0:
            # Canvas is narrower than available horizontal space
            canv.pad_trim_left_right(0, pad_width)

        if canv_rows <= maxrow and (fill_height := maxrow - canv_rows) > 0:
            # Canvas is lower than available vertical space
            canv.pad_trim_top_bottom(0, fill_height)

        if canv_cols <= maxcol and canv_rows <= maxrow:
            # Canvas is small enough to fit without trimming
            return canv

        self._adjust_trim_top(canv, size)

        # Trim canvas if necessary
        trim_top = self._trim_top
        trim_end = canv_rows - maxrow - trim_top
        trim_right = canv_cols - maxcol
        if trim_top > 0:
            canv.trim(trim_top)
        if trim_end > 0:
            canv.trim_end(trim_end)
        if trim_right > 0:
            canv.pad_trim_left_right(0, -trim_right)

        # Disable cursor display if cursor is outside of visible canvas parts
        if canv.cursor is not None:
            # Pylint check acts here a bit weird.
            _curscol, cursrow = canv.cursor  # pylint: disable=unpacking-non-sequence,useless-suppression
            if cursrow >= maxrow or cursrow < 0:
                canv.cursor = None

        # Figure out whether we should forward keypresses to original widget
        if canv.cursor is not None:
            # Trimmed canvas contains the cursor, e.g. in an Edit widget
            self._forward_keypress = True
        elif canv_full.cursor is not None:
            # Full canvas contains the cursor, but scrolled out of view
            self._forward_keypress = False

            # Reset cursor position on page/up down scrolling
            if getattr(ow, "automove_cursor_on_scroll", False):
                with contextlib.suppress(Exception):
                    automove_cursor()

        else:
            # Original widget does not have a cursor, but may be selectable

            # FIXME: Using ow.selectable() is bad because the original
            # widget may be selectable because it's a container widget with
            # a key-grabbing widget that is scrolled out of view.
            # ow.selectable() returns True anyway because it doesn't know
            # how we trimmed our canvas.
            #
            # To fix this, we need to resolve ow.focus and somehow
            # ask canv whether it contains bits of the focused widget.  I
            # can't see a way to do that.
            self._forward_keypress = ow.selectable()

        return canv

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Handle scrolling keys, forwarding everything else to the wrapped widget when appropriate."""
        from urwid.command_map import Command

        # Maybe offer key to original widget
        if self._forward_keypress or self.force_forward_keypress:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)

            # Remember the previous cursor position if possible
            if hasattr(ow, "get_cursor_coords"):
                self._old_cursor_coords = ow.get_cursor_coords(ow_size)

            if (handled := ow.keypress(ow_size, key)) is not None:  # type: ignore[arg-type]
                key = handled
            else:
                return None

        # Handle up/down, page up/down, etc.
        command_map = self._command_map
        if command_map[key] == Command.UP:
            self._scroll_action = SCROLL_LINE_UP
        elif command_map[key] == Command.DOWN:
            self._scroll_action = SCROLL_LINE_DOWN

        elif command_map[key] == Command.PAGE_UP:
            self._scroll_action = SCROLL_PAGE_UP
        elif command_map[key] == Command.PAGE_DOWN:
            self._scroll_action = SCROLL_PAGE_DOWN

        elif command_map[key] == Command.MAX_LEFT:  # 'home'
            self._scroll_action = SCROLL_TO_TOP
        elif command_map[key] == Command.MAX_RIGHT:  # 'end'
            self._scroll_action = SCROLL_TO_END

        else:
            return key

        self._invalidate()
        return None

    def mouse_event(
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Forward a mouse event to the wrapped widget, adjusting the row for the current scroll position."""
        ow = self._original_widget
        if hasattr(ow, "mouse_event"):
            ow_size = self._get_original_widget_size(size)
            row += self._trim_top
            return ow.mouse_event(
                ow_size,  # type: ignore[arg-type]
                event,
                button,
                col,
                row,
                focus,
            )

        return False

    def _adjust_trim_top(self, canv: Canvas, size: tuple[int, int]) -> None:
        """Adjust self._trim_top according to self._scroll_action."""
        action = self._scroll_action
        self._scroll_action = None

        _maxcol, maxrow = size
        trim_top = self._trim_top
        canv_rows = canv.rows()

        if trim_top < 0:
            # Negative trim_top values use bottom of canvas as reference
            trim_top = canv_rows - maxrow + trim_top + 1

        if canv_rows <= maxrow:
            self._trim_top = 0  # Reset scroll position
            return

        if action == SCROLL_LINE_UP:
            self._trim_top = max(0, min(canv_rows - maxrow, trim_top - 1))
        elif action == SCROLL_LINE_DOWN:
            self._trim_top = max(0, min(canv_rows - maxrow, trim_top + 1))

        elif action == SCROLL_PAGE_UP:
            self._trim_top = max(0, min(canv_rows - maxrow, trim_top - maxrow + 1))
        elif action == SCROLL_PAGE_DOWN:
            self._trim_top = max(0, min(canv_rows - maxrow, trim_top + maxrow - 1))

        elif action == SCROLL_TO_TOP:
            self._trim_top = 0
        elif action == SCROLL_TO_END:
            self._trim_top = canv_rows - maxrow

        else:
            self._trim_top = max(0, min(canv_rows - maxrow, trim_top))

        # If the cursor was moved by the most recent keypress, adjust trim_top
        # so that the new cursor position is within the displayed canvas part.
        # But don't do this if the cursor is at the top/bottom edge so we can still scroll out
        if self._old_cursor_coords is not None and self._old_cursor_coords != canv.cursor and canv.cursor is not None:
            self._old_cursor_coords = None
            _curscol, cursrow = canv.cursor
            if cursrow < self._trim_top:
                self._trim_top = cursrow
            elif cursrow >= self._trim_top + maxrow:
                self._trim_top = max(0, cursrow - maxrow + 1)

    def _get_original_widget_size(
        self,
        size: tuple[int, int],
    ) -> tuple[int] | tuple[()]:
        """
        Return the size to render the wrapped widget with.

        :raises ScrollableError: the wrapped widget supports neither FLOW nor FIXED sizing.
        """
        ow = self._original_widget
        sizing = ow.sizing()
        if Sizing.FLOW in sizing:
            return (size[0],)
        if Sizing.FIXED in sizing:
            return ()
        raise ScrollableError(f"{ow!r} sizing is not supported")

    def get_scrollpos(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Return the current scrolling position.

        Lower limit is 0, upper limit is the maximum number of rows with the given maxcol minus maxrow.

        ..note::
            The returned value may be too low or too high if the position has
            changed but the widget wasn't rendered yet.
        """
        return self._trim_top

    def set_scrollpos(self, position: typing.SupportsInt) -> None:
        """Set scrolling position.

        If `position` is positive it is interpreted as lines from the top.
        If `position` is negative it is interpreted as lines from the bottom.

        Values that are too high or too low values are automatically adjusted during rendering.
        """
        self._trim_top = int(position)
        self._invalidate()

    def rows_max(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Return the number of rows for `size`.

        If `size` is not given, the currently rendered number of rows is returned.

        :raises ScrollableError: the wrapped widget is neither a FLOW nor a FIXED widget.
        """
        if size is not None:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)
            sizing = ow.sizing()
            if Sizing.FIXED in sizing:
                self._rows_max_cached = ow.pack(ow_size, focus)[1]  # type: ignore[arg-type]
            elif Sizing.FLOW in sizing:
                self._rows_max_cached = typing.cast("AbstractFlowWidget", ow).rows(
                    typing.cast("tuple[int]", ow_size),
                    focus,
                )
            else:
                raise ScrollableError(f"Not a flow/fixed widget: {self._original_widget!r}")
        return self._rows_max_cached


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class _ScrollbarLayout:
    """Geometry of a scrollbar rendered next to its wrapped widget.

    Produced by :meth:`ScrollBar._scrollbar_layout` and shared between rendering and mouse handling
    so the scrollbar hit-box and the thumb placement always stay in sync.
    """

    ow_size: tuple[int, int]
    sb_width: int
    pos: int
    posmax: int
    thumb_height: int
    top_height: int
    bottom_height: int
    relative: bool  # pos and posmax count items rather than rows
    markers: bool  # the first and the last row hold the end markers instead of the trough
    start_visible: bool  # the first row of the content is on screen
    end_visible: bool  # the last row of the content is on screen

    @property
    def trough_top(self) -> int:
        """Row at which the trough starts."""
        return int(self.markers)

    @property
    def trough_height(self) -> int:
        """Rows the thumb and the trough share."""
        return self.ow_size[1] - 2 * self.markers

    def marker_step(self, row: int) -> int:
        """Return -1 for the up marker row, 1 for the down marker row, and 0 for any other row."""
        if self.markers:
            if row == 0:
                return -1
            if row == self.ow_size[1] - 1:
                return 1
        return 0


def _thumb_top(pos: int, posmax: int, thumb_travel: int) -> int:
    """Return the trough rows above the thumb for scroll position *pos*."""
    top_weight = float(pos) / max(1, posmax)
    top_height = int(thumb_travel * top_weight)
    # Thumb may only touch top/bottom if the first/last row is visible
    if top_height == 0 and top_weight > 0:
        top_height = min(1, thumb_travel)
    return top_height


def _pos_at_thumb_top(row: int, posmax: int, thumb_travel: int) -> int:
    """Return the scroll position whose thumb is drawn nearest to *row*, inverting :func:`_thumb_top`."""
    if thumb_travel <= 0 or posmax <= 0:
        return 0
    exact = row * posmax / thumb_travel
    # _thumb_top truncates a float product, so the position drawn at row can be one above ceil(exact).
    candidates = [max(0, min(posmax, math.floor(exact) + step)) for step in (0, 1, 2)]
    return min(candidates, key=lambda pos: (abs(_thumb_top(pos, posmax, thumb_travel) - row), abs(pos - exact)))


class ScrollBar(WidgetDecoration[WrappedScrollableWidget]):
    """Box widget decoration that adds a scrollbar alongside a scrollable wrapped widget."""

    Symbols: typing.ClassVar[type[ScrollbarSymbols]] = ScrollbarSymbols

    def sizing(self) -> frozenset[Sizing]:
        """Return that this widget is always a box widget."""
        return frozenset((Sizing.BOX,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the rows of the wrapped widget at the width it is rendered at.

        With :attr:`visible` ``True`` the scrollbar always takes its columns, so the wrapped widget gets the rest.

        :raises AttributeError: the wrapped widget has no ``rows()``, as a :class:`Scrollable` has none.
        """
        (maxcol,) = size
        bar_width = self._scrollbar_width if self._visible is True else 0
        return typing.cast("AbstractFlowWidget", self._original_widget).rows((max(0, maxcol - bar_width),), focus)

    def _flow_without_bar(self, size: tuple[int] | tuple[int, int]) -> bool:
        """Return whether *size* is a flow size that draws no scrollbar.

        A flow size gives the wrapped widget all its rows, so with :attr:`visible` ``None`` it needs no scrollbar,
        whatever the scrolling protocol of the wrapped widget estimates.
        """
        return len(size) == 1 and self._visible is None

    def _box_size(self, size: tuple[int] | tuple[int, int], focus: bool) -> tuple[int, int]:
        """Return *size* as a box size, measuring the wrapped widget for a flow size."""
        if len(size) == 1:
            return (size[0], self.rows((size[0],), focus))
        return size

    def selectable(self) -> bool:
        """Return whether the widget accepts the input focus.

        Always ``True``, unless :attr:`delegate_selectable` is set: then what the wrapped widget returns.
        """
        return not self.delegate_selectable or self._original_widget.selectable()

    def __init__(
        self,
        widget: WrappedScrollableWidget,
        thumb_char: str = ScrollbarSymbols.FULL_BLOCK,
        trough_char: str = " ",
        side: Literal["left", "right"] = SCROLLBAR_RIGHT,
        width: int = 1,
        *,
        visible: bool | None = None,
        scroll_by_focus: bool = False,
        delegate_selectable: bool = False,
        end_markers: tuple[str, str] | None = None,
        attr: Hashable = None,
        focus_attr: Hashable = None,
        thumb_attr: Hashable = None,
        thumb_focus_attr: Hashable = None,
        marker_dim_attr: Hashable = None,
    ) -> None:
        """Box widget that adds a scrollbar to `widget`.

        :param widget: box widget that has, or wraps a widget that has, the following methods:

            - `get_scrollpos` takes the arguments `size` and `focus` and returns the index of the first visible row.
            - `set_scrollpos` (optional; needed for mouse click and drag support on the scrollbar)
              takes the index of the first visible row.
            - `rows_max` takes `size` and `focus` and returns the total number of rows `widget` can render.
        :param thumb_char: character used for the scrollbar handle.
        :param trough_char: character used for the space above and below the handle.
        :param side: side the scrollbar is drawn on, ``'left'`` or ``'right'``.
        :param width: number of columns the scrollbar uses, at least 1.
        :param visible: when the scrollbar is drawn: ``None`` draws it only when `widget` needs scrolling,
            ``True`` always, so the wrapped widget always gets the same width,
            and ``False`` never, so the wrapped widget gets the full width and is still scrolled by keys and wheel.
        :param scroll_by_focus: let a click or drag on the scrollbar scroll a :class:`ListBox`,
            which has no `set_scrollpos`, by moving its focus to the widget at the top of the new view.
            The focus then changes without passing through the ListBox ``keypress`` or ``mouse_event``,
            so this is off by default for code that tracks the focus there.
        :param delegate_selectable: take the input focus only when `widget` is selectable;
            a :class:`ListBox` created with ``focus_when_empty=False`` is not while it is empty.
            Off by default, so a wrapped widget that is not selectable can still be scrolled by keys.
        :param end_markers: characters drawn in the first and the last scrollbar row, or ``None`` for no markers,
            such as ``(ScrollBar.Symbols.ARROW_TRIANGLE_UP, ScrollBar.Symbols.ARROW_TRIANGLE_DOWN)``.
            They are drawn only when the scrollbar has at least 3 rows,
            and a click on one scrolls one step towards its end, as the mouse wheel does.
        :param attr: display attribute of the trough and the end markers.
        :param focus_attr: display attribute of the trough and the end markers when rendered in focus;
            ``None`` uses *attr*.
        :param thumb_attr: display attribute of the thumb; ``None`` uses *attr*.
        :param thumb_focus_attr: display attribute of the thumb when rendered in focus;
            ``None`` uses *thumb_attr* when it is set, and *focus_attr* otherwise.
        :param marker_dim_attr: display attribute of an end marker whose end of the content is visible;
            ``None`` draws it like the other marker.
            An end counts as visible only when the first or last row of the content is on screen.
            A custom widget scrolled by items rather than rows, through ``SupportsRelativeScroll``,
            cannot report cut-off rows, so for it an end counts once its first or last item is on screen.

        :raises ValueError: *widget* is not a BOX widget, or *end_markers* is not a pair.
        :raises TypeError: *widget* does not wrap anything that supports the scrolling protocol.
        """
        if Sizing.BOX not in widget.sizing():
            raise ValueError(f"Not a box widget: {widget!r}")

        if not any(isinstance(w, SupportsScroll) for w in orig_iter(widget)):
            raise TypeError(f"Not a scrollable widget: {widget!r}")

        if end_markers is not None and len(end_markers) != 2:
            raise ValueError(f"end_markers must be a pair of characters, not {end_markers!r}")

        super().__init__(widget)
        self._thumb_char = thumb_char
        self._trough_char = trough_char
        self.scrollbar_side = side
        self.scrollbar_width = max(1, width)
        self.visible = visible
        self.scroll_by_focus = scroll_by_focus
        # whether selectable() asks the wrapped widget instead of reporting True
        self.delegate_selectable = delegate_selectable
        self._end_markers = end_markers
        self._attr = attr
        self._focus_attr = attr if focus_attr is None else focus_attr
        self._thumb_attr = attr if thumb_attr is None else thumb_attr
        if thumb_focus_attr is None:
            thumb_focus_attr = self._focus_attr if thumb_attr is None else thumb_attr
        self._thumb_focus_attr = thumb_focus_attr
        self._marker_dim_attr = marker_dim_attr
        self._press_on_scrollbar: bool | None = None  # where the last unreleased press here went
        self._press_on_marker = False  # the last unreleased press here went to an end marker
        self._original_widget_size = (0, 0)
        self._rendered_size: tuple[int, int] | None = None  # size of the last render, which set the size above

    def _render_original(
        self,
        size: tuple[int, int],
        focus: bool = False,
    ) -> Canvas:
        self._original_widget_size = size
        return self._original_widget.render(size, focus)

    def _scrollbar_layout(
        self,
        size: tuple[int, int],
        focus: bool = False,
        *,
        shows_all: bool = False,
    ) -> _ScrollbarLayout | None:
        """Compute the scrollbar geometry for ``size``.

        With *shows_all*, the wrapped widget is known to show all its rows, as at a flow size,
        so the geometry is measured in rows rather than estimated from item counts.

        :returns: ``None`` is returned as a "not shown" flag when no scrollbar is drawn:
            :attr:`visible` is ``False``, or it is ``None`` and the wrapped widget fits without scrolling.
            Otherwise, the thumb and trough placement is returned,
            so :meth:`render` and :meth:`mouse_event` can share the same geometry without duplicating the maths.
        :raises TypeError: the wrapped widget does not support the scrolling protocol.
        """
        if self._visible is False:
            return None

        from .listbox import ListBox

        maxcol, maxrow = size

        ow_size = (max(0, maxcol - self._scrollbar_width), maxrow)
        sb_width = maxcol - ow_size[0]
        markers = self._end_markers is not None and maxrow >= 3
        trough_height = maxrow - 2 * markers
        ends_visible: tuple[bool, bool] | None = None  # set where the item counts cannot tell

        ow_base = self.scrolling_base_widget

        # Use hasattr instead of protocol: hasattr will return False in case of getattr raise AttributeError
        # Use __length_hint__ first since it's less resource intensive
        require_absolute = True

        if (
            not shows_all
            and isinstance(ow_base, SupportsRelativeScroll)
            and callable(len_getter := getattr(ow_base, "__len__", getattr(ow_base, "__length_hint__", None)))
            and ow_base.require_relative_scroll(size, focus)
        ):
            # `operator.length_hint` is Protocol (Spec) over class base and can end false-negative on the instance
            # use length_hint-like approach with safe `AttributeError` handling
            ow_len = len_getter()
            visible_amount = ow_base.get_visible_amount(ow_size, focus)
            pos = ow_base.get_first_visible_pos(ow_size, focus)

            # in the case of estimated length, it can be smaller than real widget length
            ow_len = max(ow_len, visible_amount, pos)
            posmax = ow_len - visible_amount
            thumb_weight = min(1.0, visible_amount / max(1, ow_len))

            # Corner case possible: formally all contents indexes should be visible, but this does not mean all rows
            if ow_len != visible_amount:
                require_absolute = False

                if markers and isinstance(ow_base, ListBox):
                    ends_visible = _listbox_ends_visible(ow_base, ow_size, focus)

        if require_absolute:
            if not isinstance(ow_base, SupportsScroll):
                raise TypeError(f"Not a scrollable widget: {ow_base!r}")

            # The full-width check is skipped when the scrollbar is drawn anyway
            if self._visible is None and ow_base.rows_max(size, focus) <= maxrow:
                # Canvas fits without scrolling - no scrollbar needed
                return None

            # re-calculate using wrapped size
            ow_rows_max = ow_base.rows_max(ow_size, focus)
            pos = ow_base.get_scrollpos(ow_size, focus)
            posmax = max(0, ow_rows_max - maxrow)
            thumb_weight = min(1.0, maxrow / max(1, ow_rows_max))

        # Thumb shrinks/grows according to the ratio of <number of visible lines> / <number of total lines>,
        # keeping at least one row unless there are no rows at all.
        # pylint: disable-next=possibly-used-before-assignment
        thumb_height = min(trough_height, max(1, round(thumb_weight * trough_height)))

        # pylint: disable-next=possibly-used-before-assignment
        top_height = _thumb_top(pos, posmax, trough_height - thumb_height)

        # Bottom part is remaining space
        bottom_height = trough_height - thumb_height - top_height

        return _ScrollbarLayout(
            ow_size=ow_size,
            sb_width=sb_width,
            pos=pos,
            posmax=posmax,
            thumb_height=thumb_height,
            top_height=top_height,
            bottom_height=bottom_height,
            relative=not require_absolute,
            markers=markers,
            start_visible=pos <= 0 if ends_visible is None else ends_visible[0],
            end_visible=pos >= posmax if ends_visible is None else ends_visible[1],
        )

    def render(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> Canvas:
        """Render the wrapped widget together with the scrollbar, when scrolling is needed.

        A flow *size* renders the wrapped widget at its flow rows, so it never needs scrolling.
        """
        from urwid import canvas

        flow = len(size) == 1
        no_bar = self._visible is False or self._flow_without_bar(size)
        size = self._box_size(size, focus)
        self._rendered_size = size
        if no_bar:
            return self._render_original(size, focus)

        maxcol, maxrow = size

        # Render the wrapped widget first
        # so any pending scroll action is applied before the scroll position is queried for the scrollbar geometry.
        ow_size = (max(0, maxcol - self._scrollbar_width), maxrow)
        ow_canv = self._render_original(ow_size, focus)

        layout = self._scrollbar_layout(size, focus, shows_all=flow)
        if layout is None:
            # Canvas fits without scrolling - no scrollbar needed
            return self._render_original(size, focus)

        def row_canvas(char: str, attr: Hashable) -> CompositeCanvas:
            canv = canvas.CompositeCanvas(canvas.SolidCanvas(char, layout.sb_width, 1))
            canv.fill_attr(attr)
            return canv

        bar_attr = self._focus_attr if focus else self._attr
        thumb_attr = self._thumb_focus_attr if focus else self._thumb_attr

        # Create scrollbar canvas
        # Creating SolidCanvases of correct height may result in
        # "cviews do not fill gaps in shard_tail!" or "cviews overflow gaps in shard_tail!" exceptions.
        # Stacking the same SolidCanvas is a workaround.
        # https://github.com/urwid/urwid/issues/226#issuecomment-437176837
        trough = row_canvas(self._trough_char, bar_attr)
        thumb = row_canvas(self._thumb_char, thumb_attr)
        rows: list[Canvas] = [
            *(trough for _ in range(layout.top_height)),
            *(thumb for _ in range(layout.thumb_height)),
            *(trough for _ in range(layout.bottom_height)),
        ]
        if layout.markers and self._end_markers is not None:
            dim_attr = bar_attr if self._marker_dim_attr is None else self._marker_dim_attr
            up_char, down_char = self._end_markers
            rows.insert(0, row_canvas(up_char, dim_attr if layout.start_visible else bar_attr))
            rows.append(row_canvas(down_char, dim_attr if layout.end_visible else bar_attr))
        if rows:
            sb_canv = canvas.CanvasCombine([(row, None, False) for row in rows])
        else:
            # No rows: an empty combination would lose the width.
            sb_canv = canvas.CompositeCanvas(canvas.SolidCanvas(self._trough_char, layout.sb_width, 0))

        combinelist = [
            (ow_canv, None, True, layout.ow_size[0]),
            (sb_canv, None, False, layout.sb_width),
        ]

        if self._scrollbar_side != SCROLLBAR_LEFT:
            return canvas.CanvasJoin(combinelist)

        return canvas.CanvasJoin(reversed(combinelist))

    @property
    def scrollbar_width(self) -> int:
        """Columns the scrollbar uses."""
        return max(1, self._scrollbar_width)

    @scrollbar_width.setter
    def scrollbar_width(self, width: typing.SupportsInt) -> None:
        self._scrollbar_width = max(1, int(width))
        self._invalidate()

    @property
    def visible(self) -> bool | None:
        """When the scrollbar is drawn: ``None`` when scrolling is needed, ``True`` always, ``False`` never."""
        return self._visible

    @visible.setter
    def visible(self, visible: bool | None) -> None:
        self._visible = visible
        self._invalidate()

    @property
    def scroll_by_focus(self) -> bool:
        """Whether a click or drag on the scrollbar scrolls a :class:`ListBox` by moving its focus."""
        return self._scroll_by_focus

    @scroll_by_focus.setter
    def scroll_by_focus(self, scroll_by_focus: bool) -> None:
        self._scroll_by_focus = scroll_by_focus

    @property
    def scrollbar_side(self) -> Literal["left", "right"]:
        """Where to display the scrollbar; must be 'left' or 'right'."""
        return self._scrollbar_side

    @scrollbar_side.setter
    def scrollbar_side(self, side: Literal["left", "right"]) -> None:
        """
        Set the side of the widget the scrollbar is drawn on.

        :raises ValueError: *side* is neither ``'left'`` nor ``'right'``.
        """
        if side not in {SCROLLBAR_LEFT, SCROLLBAR_RIGHT}:
            raise ValueError(f'scrollbar_side must be "left" or "right", not {side!r}')
        self._scrollbar_side: Literal["left", "right"] = side
        self._invalidate()

    @property
    def scrolling_base_widget(self) -> SupportsScroll:
        """Nearest `original_widget` that is compatible with the scrolling API.

        :raises ScrollableError: no wrapped widget supports the scrolling protocol.
        """
        w: AbstractWidget = self

        for w in orig_iter(self):
            if isinstance(w, SupportsScroll):
                return w

        raise ScrollableError(f"Not compatible to be wrapped by ScrollBar: {w!r}")

    def keypress(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Forward a keypress to the wrapped widget, at the size it is rendered at within ``size``."""
        ow_size = self._original_widget_size
        box_size = self._box_size(size, True)
        if box_size != self._rendered_size:
            # Not rendered at this size yet: a key before the first render, or after a resize.
            layout = None if self._flow_without_bar(size) else self._scrollbar_layout(box_size)
            ow_size = box_size if layout is None else layout.ow_size
        return self._original_widget.keypress(ow_size, key)

    def mouse_event(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Handle a mouse event, dispatching it to the scrollbar thumb/trough or to the wrapped widget.

        A press of button 1 on the scrollbar, and the drag that follows it, move the thumb top to the pointer row.
        So does its release on displays that report the button of a release, such as curses, which send no drags.
        A press of button 1 on an end marker scrolls one step towards that end, as the mouse wheel does,
        and the drag and release that follow it do nothing.
        Events in the wrapped widget's columns go to it. On the scrollbar, the vertical mouse wheel of a widget
        without `set_scrollpos` (such as :class:`ListBox`) is passed on, together with the drags and releases
        described below; other events there are not.

        A drag or release goes where its press went: a drag started on the scrollbar keeps moving the thumb
        over the wrapped widget's columns, and a drag started on the wrapped widget stays with it over the scrollbar.
        A drag or release whose press was not seen here, such as the end of a drag and drop started in another
        widget, goes to the wrapped widget.
        Events outside this widget never reach it, so a release there is not seen; the next press here starts over.
        """
        flow = len(size) == 1
        no_bar = self._flow_without_bar(size)
        size = self._box_size(size, focus)
        ow = self._original_widget
        ow_size = self._original_widget_size
        supports_scroll = hasattr(ow, "set_scrollpos")
        on_scrollbar = False
        ow_col = col

        # The geometry is needed before the event is passed on: the wrapped widget cannot tell
        # that a column belongs to the scrollbar, and would answer a click that is not its own.
        layout = None if no_bar else self._scrollbar_layout(size, focus, shows_all=flow)
        if layout is not None:
            if self._scrollbar_side == SCROLLBAR_LEFT:
                on_scrollbar = col < layout.sb_width
                # The wrapped widget is drawn after the scrollbar, so its own column 0 sits at
                # screen column sb_width and the offset has to be taken back out.
                ow_col = col - layout.sb_width
            else:
                on_scrollbar = col >= layout.ow_size[0]

        on_marker = False
        if button not in _WHEEL_BUTTONS:
            if is_mouse_press(event):
                self._press_on_scrollbar = on_scrollbar
                on_marker = self._press_on_marker = on_scrollbar and layout is not None and layout.marker_step(row) != 0
            elif "drag" in event or "release" in event:
                on_scrollbar = bool(self._press_on_scrollbar)
                on_marker = self._press_on_marker
                if layout is not None and not on_scrollbar:
                    # A drag can leave the wrapped widget's columns; it still gets a column it owns.
                    ow_col = min(max(0, ow_col), max(0, layout.ow_size[0] - 1))
            if "release" in event:
                self._press_on_scrollbar = None
                self._press_on_marker = False

        if layout is not None:
            if on_scrollbar and button == 1:
                if not on_marker:
                    return self._move_thumb(layout, row, focus)
                step = layout.marker_step(row)
                if not is_mouse_press(event) or not step:
                    return True  # the drag or release of a marker press
                # A marker press scrolls one step, as the wheel does.
                button = 4 if step < 0 else 5

            if on_scrollbar and not supports_scroll and button in {4, 5}:
                # A widget without set_scrollpos (such as ListBox) scrolls itself on the wheel.
                # A column past its right edge reaches no child, so the list scrolls even when the
                # child on that row would handle the wheel itself.
                on_scrollbar = False
                ow_col = max(0, ow_col)

        handled: bool | None = False
        if not on_scrollbar and hasattr(ow, "mouse_event"):
            handled = ow.mouse_event(ow_size, event, button, ow_col, row, focus)

        if not handled and supports_scroll:
            if button == 4:  # scroll wheel up
                pos = ow.get_scrollpos(ow_size)
                newpos = max(pos - 1, 0)
                ow.set_scrollpos(newpos)  # type: ignore[attr-defined]  # gated
                return True
            if button == 5:  # scroll wheel down
                pos = ow.get_scrollpos(ow_size)
                ow.set_scrollpos(pos + 1)  # type: ignore[attr-defined]  # gated
                return True

        return handled

    def _move_thumb(self, layout: _ScrollbarLayout, row: int, focus: bool) -> bool:
        """Scroll so the thumb top is at *row*, and return whether the wrapped widget could be scrolled."""
        from .listbox import ListBox

        newpos = _pos_at_thumb_top(row - layout.trough_top, layout.posmax, layout.trough_height - layout.thumb_height)

        ow = self._original_widget
        if hasattr(ow, "set_scrollpos"):
            ow.set_scrollpos(newpos)
            return True

        ow_base = self.scrolling_base_widget
        if self._scroll_by_focus and isinstance(ow_base, ListBox):
            _scroll_listbox_to(ow_base, layout, newpos, focus)
            return True

        return False


def _listbox_ends_visible(listbox: ListBox[typing.Any], size: tuple[int, int], focus: bool) -> tuple[bool, bool]:
    """Return whether the first and the last row of *listbox* content are on screen at *size*.

    An end is on screen when the outermost visible item on that side is not cut off
    and every item beyond it renders no rows, since :meth:`ListBox.calculate_visible` leaves such items out.
    """
    middle, top, bottom = listbox.calculate_visible(size, focus)
    if middle is None or top is None or bottom is None:
        return True, True  # empty body

    body = listbox.body
    maxcol = size[0]

    def only_empty_beyond(position: typing.Any, forward: bool) -> bool:
        while True:
            widget, position = body.get_next(position) if forward else body.get_prev(position)
            if widget is None:
                return True
            if widget.rows((maxcol,)) > 0:
                return False

    first_pos = top.fill[-1].position if top.fill else middle.focus_pos
    last_pos = bottom.fill[-1].position if bottom.fill else middle.focus_pos
    return (
        top.trim == 0 and only_empty_beyond(first_pos, forward=False),
        bottom.trim == 0 and only_empty_beyond(last_pos, forward=True),
    )


def _scroll_listbox_to(listbox: ListBox[typing.Any], layout: _ScrollbarLayout, newpos: int, focus: bool) -> None:
    """Scroll *listbox* so *newpos*, in the units of *layout*, is at its top.

    A ListBox view always contains its focus, so the focus moves to the widget that ends up at the top.
    """
    if newpos == layout.pos:
        return  # the view stays, so the focus it already contains stays too

    middle, top, _bottom = listbox.calculate_visible(layout.ow_size, focus)
    if middle is None or top is None:
        return  # empty body

    if top.fill:
        widget, position = top.fill[-1].widget, top.fill[-1].position
    else:
        widget, position = middle.focus_widget, middle.focus_pos

    body = listbox.body
    maxcol = layout.ow_size[0]

    if layout.relative:
        step = newpos - layout.pos
        while step:
            candidate, candidate_pos = body.get_next(position) if step > 0 else body.get_prev(position)
            if candidate is None:
                break
            position = candidate_pos
            step += -1 if step > 0 else 1
        listbox.change_focus(layout.ow_size, position, 0)
        return

    # Find the widget that holds row newpos, starting from the row at which the top widget begins.
    start = layout.pos - top.trim
    rows = widget.rows((maxcol,))
    while start + rows <= newpos:
        candidate, candidate_pos = body.get_next(position)
        if candidate is None:
            break
        start += rows
        widget, position, rows = candidate, candidate_pos, candidate.rows((maxcol,))
    while start > newpos:
        candidate, candidate_pos = body.get_prev(position)
        if candidate is None:
            break
        widget, position, rows = candidate, candidate_pos, candidate.rows((maxcol,))
        start -= rows
    listbox.change_focus(layout.ow_size, position, min(0, start - newpos))
