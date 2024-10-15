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

from __future__ import annotations

import contextlib
import enum
import typing

from typing_extensions import Protocol, runtime_checkable

from .constants import BOX_SYMBOLS, SHADE_SYMBOLS, Sizing
from .widget_decoration import WidgetDecoration, WidgetError

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Literal

    from urwid import Canvas, CompositeCanvas

    from .widget import Widget


__all__ = ("ScrollBar", "Scrollable", "ScrollableError", "ScrollbarSymbols")


WrappedWidget = typing.TypeVar("WrappedWidget", bound="SupportsScroll")


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
SCROLLBAR_LEFT = "left"
SCROLLBAR_RIGHT = "right"


class ScrollbarSymbols(str, enum.Enum):
    """Common symbols suitable for scrollbar."""

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


@runtime_checkable
class WidgetProto(Protocol):
    """Protocol for widget.

    Due to protocol cannot inherit non-protocol bases, define several obligatory Widget methods.
    """

    # Base widget methods (from Widget)
    def sizing(self) -> frozenset[Sizing]: ...

    def selectable(self) -> bool: ...

    def pack(self, size: tuple[int, int], focus: bool = False) -> tuple[int, int]: ...

    @property
    def base_widget(self) -> Widget:
        raise NotImplementedError

    def keypress(self, size: tuple[int, int], key: str) -> str | None: ...

    def mouse_event(
        self,
        size: tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None: ...

    def render(self, size: tuple[int, int], focus: bool = False) -> Canvas: ...


@runtime_checkable
class SupportsScroll(WidgetProto, Protocol):
    """Scroll specific methods."""

    def get_scrollpos(self, size: tuple[int, int], focus: bool = False) -> int: ...

    def rows_max(self, size: tuple[int, int] | None = None, focus: bool = False) -> int: ...


@runtime_checkable
class SupportsRelativeScroll(WidgetProto, Protocol):
    """Relative scroll-specific methods."""

    def require_relative_scroll(self, size: tuple[int, int], focus: bool = False) -> bool: ...

    def get_first_visible_pos(self, size: tuple[int, int], focus: bool = False) -> int: ...

    def get_visible_amount(self, size: tuple[int, int], focus: bool = False) -> int: ...


def orig_iter(w: Widget) -> Iterator[Widget]:
    visited = {w}
    yield w
    while hasattr(w, "original_widget"):
        w = w.original_widget
        if w in visited:
            break
        visited.add(w)
        yield w


class Scrollable(WidgetDecoration[WrappedWidget]):
    def sizing(self) -> frozenset[Sizing]:
        return frozenset((Sizing.BOX,))

    def selectable(self) -> bool:
        return True

    def __init__(self, widget: WrappedWidget, force_forward_keypress: bool = False) -> None:
        """Box widget that makes a fixed or flow widget vertically scrollable

        .. note::
            Focusable widgets are handled, including switching focus, but possibly not intuitively,
            depending on the arrangement of widgets.

            When switching focus to a widget that is ouside of the visible part of the original widget,
            the canvas scrolls up/down to the focused widget.

            It would be better to scroll until the next focusable widget is in sight first.
            But for that to work we must somehow obtain a list of focusable rows in the original canvas.
        """
        if not widget.sizing() & frozenset((Sizing.FIXED, Sizing.FLOW)):
            raise ValueError(f"Not a fixed or flow widget: {widget!r}")

        self._trim_top = 0
        self._scroll_action = None
        self._forward_keypress = None
        self._old_cursor_coords = None
        self._rows_max_cached = 0
        self.force_forward_keypress = force_forward_keypress
        super().__init__(widget)

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        from urwid import canvas

        maxcol, maxrow = size

        def automove_cursor() -> None:
            ch = 0
            last_hidden = False
            first_visible = False
            for pwi, (w, _o) in enumerate(ow.contents):
                wcanv = w.render((maxcol,))
                wh = wcanv.rows()
                if wh:
                    ch += wh

                if not last_hidden and ch >= self._trim_top:
                    last_hidden = True

                elif last_hidden:
                    if not first_visible:
                        first_visible = True

                    if not w.selectable():
                        continue

                    ow.focus_item = pwi

                    st = None
                    nf = ow.get_focus()
                    if hasattr(nf, "key_timeout"):
                        st = nf
                    elif hasattr(nf, "original_widget"):
                        no = nf.original_widget
                        if hasattr(no, "original_widget"):
                            st = no.original_widget
                        elif hasattr(no, "key_timeout"):
                            st = no

                    if st and hasattr(st, "key_timeout") and callable(getattr(st, "keypress", None)):
                        st.keypress(None, None)

                    break

        # Render complete original widget
        ow = self._original_widget
        ow_size = self._get_original_widget_size(size)
        canv_full = ow.render(ow_size, focus)

        # Make full canvas editable
        canv = canvas.CompositeCanvas(canv_full)
        canv_cols, canv_rows = canv.cols(), canv.rows()

        if canv_cols <= maxcol:
            pad_width = maxcol - canv_cols
            if pad_width > 0:
                # Canvas is narrower than available horizontal space
                canv.pad_trim_left_right(0, pad_width)

        if canv_rows <= maxrow:
            fill_height = maxrow - canv_rows
            if fill_height > 0:
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
        from urwid.command_map import Command

        # Maybe offer key to original widget
        if self._forward_keypress or self.force_forward_keypress:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)

            # Remember the previous cursor position if possible
            if hasattr(ow, "get_cursor_coords"):
                self._old_cursor_coords = ow.get_cursor_coords(ow_size)

            key = ow.keypress(ow_size, key)
            if key is None:
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
        ow = self._original_widget
        if hasattr(ow, "mouse_event"):
            ow_size = self._get_original_widget_size(size)
            row += self._trim_top
            return ow.mouse_event(ow_size, event, button, col, row, focus)

        return False

    def _adjust_trim_top(self, canv: Canvas, size: tuple[int, int]) -> None:
        """Adjust self._trim_top according to self._scroll_action"""
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

        def ensure_bounds(new_trim_top: int) -> int:
            return max(0, min(canv_rows - maxrow, new_trim_top))

        if action == SCROLL_LINE_UP:
            self._trim_top = ensure_bounds(trim_top - 1)
        elif action == SCROLL_LINE_DOWN:
            self._trim_top = ensure_bounds(trim_top + 1)

        elif action == SCROLL_PAGE_UP:
            self._trim_top = ensure_bounds(trim_top - maxrow + 1)
        elif action == SCROLL_PAGE_DOWN:
            self._trim_top = ensure_bounds(trim_top + maxrow - 1)

        elif action == SCROLL_TO_TOP:
            self._trim_top = 0
        elif action == SCROLL_TO_END:
            self._trim_top = canv_rows - maxrow

        else:
            self._trim_top = ensure_bounds(trim_top)

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
        size: tuple[int, int],  # type: ignore[override]
    ) -> tuple[int] | tuple[()]:
        ow = self._original_widget
        sizing = ow.sizing()
        if Sizing.FLOW in sizing:
            return (size[0],)
        if Sizing.FIXED in sizing:
            return ()
        raise ScrollableError(f"{ow!r} sizing is not supported")

    def get_scrollpos(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Current scrolling position.

        Lower limit is 0, upper limit is the maximum number of rows with the given maxcol minus maxrow.

        ..note::
            The returned value may be too low or too high if the position has
            changed but the widget wasn't rendered yet.
        """
        return self._trim_top

    def set_scrollpos(self, position: typing.SupportsInt) -> None:
        """Set scrolling position

        If `position` is positive it is interpreted as lines from the top.
        If `position` is negative it is interpreted as lines from the bottom.

        Values that are too high or too low values are automatically adjusted during rendering.
        """
        self._trim_top = int(position)
        self._invalidate()

    def rows_max(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Return the number of rows for `size`

        If `size` is not given, the currently rendered number of rows is returned.
        """
        if size is not None:
            ow = self._original_widget
            ow_size = self._get_original_widget_size(size)
            sizing = ow.sizing()
            if Sizing.FIXED in sizing:
                self._rows_max_cached = ow.pack(ow_size, focus)[1]
            elif Sizing.FLOW in sizing:
                self._rows_max_cached = ow.rows(ow_size, focus)
            else:
                raise ScrollableError(f"Not a flow/box widget: {self._original_widget!r}")
        return self._rows_max_cached


class ScrollBar(WidgetDecoration[WrappedWidget]):
    Symbols = ScrollbarSymbols

    def sizing(self) -> frozenset[Sizing]:
        return frozenset((Sizing.BOX,))

    def selectable(self) -> bool:
        return True

    def __init__(
        self,
        widget: WrappedWidget,
        thumb_char: str = ScrollbarSymbols.FULL_BLOCK,
        trough_char: str = " ",
        side: Literal["left", "right"] = SCROLLBAR_RIGHT,
        width: int = 1,
    ) -> None:
        """Box widget that adds a scrollbar to `widget`

        `widget` must be a box widget with the following methods:
          - `get_scrollpos` takes the arguments `size` and `focus` and returns the index of the first visible row.
          - `set_scrollpos` (optional; needed for mouse click support) takes the index of the first visible row.
          - `rows_max` takes `size` and `focus` and returns the total number of rows `widget` can render.

        `thumb_char` is the character used for the scrollbar handle.
        `trough_char` is used for the space above and below the handle.
        `side` must be 'left' or 'right'.
        `width` specifies the number of columns the scrollbar uses.
        """
        if Sizing.BOX not in widget.sizing():
            raise ValueError(f"Not a box widget: {widget!r}")

        if not any(isinstance(w, SupportsScroll) for w in orig_iter(widget)):
            raise TypeError(f"Not a scrollable widget: {widget!r}")

        super().__init__(widget)
        self._thumb_char = thumb_char
        self._trough_char = trough_char
        self.scrollbar_side = side
        self.scrollbar_width = max(1, width)
        self._original_widget_size = (0, 0)

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> Canvas:
        from urwid import canvas

        def render_no_scrollbar() -> Canvas:
            self._original_widget_size = size
            return ow.render(size, focus)

        def render_for_scrollbar() -> Canvas:
            self._original_widget_size = ow_size
            return ow.render(ow_size, focus)

        maxcol, maxrow = size

        ow_size = (max(0, maxcol - self._scrollbar_width), maxrow)
        sb_width = maxcol - ow_size[0]

        ow = self._original_widget
        ow_base = self.scrolling_base_widget

        # Use hasattr instead of protocol: hasattr will return False in case of getattr raise AttributeError
        # Use __length_hint__ first since it's less resource intensive
        use_relative = (
            isinstance(ow_base, SupportsRelativeScroll)
            and any(hasattr(ow_base, attrib) for attrib in ("__length_hint__", "__len__"))
            and ow_base.require_relative_scroll(size, focus)
        )

        if use_relative:
            # `operator.length_hint` is Protocol (Spec) over class based and can end false-negative on the instance
            # use length_hint-like approach with safe `AttributeError` handling
            ow_len = getattr(ow_base, "__len__", getattr(ow_base, "__length_hint__", int))()
            ow_canv = render_for_scrollbar()
            visible_amount = ow_base.get_visible_amount(ow_size, focus)
            pos = ow_base.get_first_visible_pos(ow_size, focus)

            # in the case of estimated length, it can be smaller than real widget length
            ow_len = max(ow_len, visible_amount, pos)
            posmax = ow_len - visible_amount
            thumb_weight = min(1.0, visible_amount / max(1, ow_len))

            if ow_len == visible_amount:
                # Corner case: formally all contents indexes should be visible, but this does not mean all rows
                use_relative = False

        if not use_relative:
            ow_rows_max = ow_base.rows_max(size, focus)
            if ow_rows_max <= maxrow:
                # Canvas fits without scrolling - no scrollbar needed
                return render_no_scrollbar()

            ow_canv = render_for_scrollbar()
            ow_rows_max = ow_base.rows_max(ow_size, focus)
            pos = ow_base.get_scrollpos(ow_size, focus)
            posmax = ow_rows_max - maxrow
            thumb_weight = min(1.0, maxrow / max(1, ow_rows_max))

        # Thumb shrinks/grows according to the ratio of <number of visible lines> / <number of total lines>
        thumb_height = max(1, round(thumb_weight * maxrow))  # pylint: disable=possibly-used-before-assignment

        # Thumb may only touch top/bottom if the first/last row is visible
        top_weight = float(pos) / max(1, posmax)  # pylint: disable=possibly-used-before-assignment
        top_height = int((maxrow - thumb_height) * top_weight)
        if top_height == 0 and top_weight > 0:
            top_height = 1

        # Bottom part is remaining space
        bottom_height = maxrow - thumb_height - top_height

        # Create scrollbar canvas
        # Creating SolidCanvases of correct height may result in
        # "cviews do not fill gaps in shard_tail!" or "cviews overflow gaps in shard_tail!" exceptions.
        # Stacking the same SolidCanvas is a workaround.
        # https://github.com/urwid/urwid/issues/226#issuecomment-437176837
        top = canvas.SolidCanvas(self._trough_char, sb_width, 1)
        thumb = canvas.SolidCanvas(self._thumb_char, sb_width, 1)
        bottom = canvas.SolidCanvas(self._trough_char, sb_width, 1)
        sb_canv = canvas.CanvasCombine(
            (
                *((top, None, False) for _ in range(top_height)),
                *((thumb, None, False) for _ in range(thumb_height)),
                *((bottom, None, False) for _ in range(bottom_height)),
            ),
        )

        combinelist = [
            (ow_canv, None, True, ow_size[0]),  # pylint: disable=possibly-used-before-assignment
            (sb_canv, None, False, sb_width),
        ]

        if self._scrollbar_side != SCROLLBAR_LEFT:
            return canvas.CanvasJoin(combinelist)

        return canvas.CanvasJoin(reversed(combinelist))

    @property
    def scrollbar_width(self) -> int:
        """Columns the scrollbar uses"""
        return max(1, self._scrollbar_width)

    @scrollbar_width.setter
    def scrollbar_width(self, width: typing.SupportsInt) -> None:
        self._scrollbar_width = max(1, int(width))
        self._invalidate()

    @property
    def scrollbar_side(self) -> Literal["left", "right"]:
        """Where to display the scrollbar; must be 'left' or 'right'"""
        return self._scrollbar_side

    @scrollbar_side.setter
    def scrollbar_side(self, side: Literal["left", "right"]) -> None:
        if side not in {SCROLLBAR_LEFT, SCROLLBAR_RIGHT}:
            raise ValueError(f'scrollbar_side must be "left" or "right", not {side!r}')
        self._scrollbar_side = side
        self._invalidate()

    @property
    def scrolling_base_widget(self) -> SupportsScroll | SupportsRelativeScroll:
        """Nearest `original_widget` that is compatible with the scrolling API"""

        w = self

        for w in orig_iter(self):
            if isinstance(w, SupportsScroll):
                return w

        raise ScrollableError(f"Not compatible to be wrapped by ScrollBar: {w!r}")

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        return self._original_widget.keypress(self._original_widget_size, key)

    def mouse_event(
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        ow = self._original_widget
        ow_size = self._original_widget_size
        handled: bool | None = False
        if hasattr(ow, "mouse_event"):
            handled = ow.mouse_event(ow_size, event, button, col, row, focus)

        if not handled and hasattr(ow, "set_scrollpos"):
            if button == 4:  # scroll wheel up
                pos = ow.get_scrollpos(ow_size)
                newpos = max(pos - 1, 0)
                ow.set_scrollpos(newpos)
                return True
            if button == 5:  # scroll wheel down
                pos = ow.get_scrollpos(ow_size)
                ow.set_scrollpos(pos + 1)
                return True

        return handled
