# Urwid Window-Icon-Menu-Pointer-style widget classes
#    Copyright (C) 2004-2011  Ian Ward
#
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


"""Pop-up support: a launcher widget and the target that displays its pop-up."""

from __future__ import annotations

import typing

from urwid.canvas import CompositeCanvas
from urwid.command_map import Command
from urwid.util import is_mouse_press

from .constants import Align, MouseButton, Sizing, VAlign
from .filler import Filler
from .overlay import Overlay
from .widget import WidgetError, delegate_to_widget_mixin
from .widget_decoration import WidgetDecoration

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal, NotRequired, TypedDict

    from urwid.canvas import Canvas, PopUpLeft, PopUpSize, PopUpTop

    from .widget import AbstractBoxWidget, AbstractWidget, _DelegateToWidgetMixin

    class PopUpParametersModel(TypedDict):
        """Position and box size a :class:`PopUpLauncher` requests for its pop-up."""

        left: PopUpLeft
        top: PopUpTop
        overlay_width: PopUpSize
        overlay_height: PopUpSize
        anchor_height: NotRequired[int]


WrappedWidget = typing.TypeVar("WrappedWidget", bound="AbstractBoxWidget")
# The launcher wraps a widget of any sizing; the pop-up target is a box widget.
LauncherWidget = typing.TypeVar("LauncherWidget", bound="AbstractWidget")


if typing.TYPE_CHECKING:
    _PopUpLauncherDelegate = _DelegateToWidgetMixin
else:
    _PopUpLauncherDelegate = delegate_to_widget_mixin("_original_widget")


class PopUpLauncher(
    _PopUpLauncherDelegate,
    WidgetDecoration[LauncherWidget],
):
    """Decoration that lets a wrapped widget open and close a pop-up drawn over other widgets by a PopUpTarget."""

    # Class-level defaults, so a launcher pickled before these attributes existed still loads.
    _close_on_menu: bool = False
    _close_on_click_outside: bool = False
    _launcher_size: tuple[int, int] | None = None

    def __init__(
        self,
        original_widget: LauncherWidget,
        *,
        close_on_menu: bool = False,
        close_on_click_outside: bool = False,
    ) -> None:
        """Wrap `original_widget`, with no pop-up open yet.

        :param original_widget: widget that opens the pop-up.
        :param close_on_menu: close the pop-up when it leaves a key for the ``menu`` command (:kbd:`esc` by
            default) unhandled while it is the topmost open pop-up.
        :param close_on_click_outside: close the pop-up on a press of mouse button 1, 2 or 3 outside it
            while it is the topmost open pop-up.
            The press closes the pop-up only, and does not reach the widget under it.
        """
        super().__init__(original_widget)
        self._close_on_menu = close_on_menu
        self._close_on_click_outside = close_on_click_outside
        self._pop_up_widget: AbstractWidget | None = None
        self._launcher_size = None

    @property
    def pop_up_widget(self) -> AbstractWidget | None:
        """The open pop-up widget, or ``None`` when the pop-up is closed."""
        return self._pop_up_widget

    @property
    def launcher_size(self) -> tuple[int, int] | None:
        """The (*columns*, *rows*) of the last render that was not served from the canvas cache, or ``None`` before it.

        It is set before :meth:`get_pop_up_parameters` is called, so inside that method it is always the size being
        rendered.
        """
        return self._launcher_size

    def create_pop_up(self) -> AbstractWidget:
        """Return the widget to be used for the pop-up.

        Subclass must override this method. It is called once each time
        the pop-up is opened.

        :class:`PopUpTarget` renders the pop-up with the box size declared by
        :meth:`get_pop_up_parameters`, so the widget returned here must accept an
        (*overlay_width*, *overlay_height*) size.  Wrap a flow or fixed widget in a
        :class:`Filler <urwid.Filler>` (or in another box container) before returning it.

        With a ``'pack'`` size the widget is measured instead:

        - a ``'pack'`` width needs a fixed widget, and takes the columns it packs to;
        - a ``'pack'`` height needs a flow widget, and takes its rows at the pop-up width.

        Such a widget that cannot take a box size is rendered as a flow widget,
        with the rows that do not fit on screen cut off.
        A :class:`ListBox(flow=True) <urwid.ListBox>` takes the box size and scrolls instead.

        :class:`PopUpTarget` raises :exc:`WidgetError <urwid.WidgetError>` when it renders a widget that does not
        meet these rules:

        - a ``'pack'`` width on a widget that is not fixed;
        - a ``'pack'`` height on a widget that is not flow;
        - a ``'pack'`` width on a fixed-only widget, such as :class:`BigText <urwid.BigText>`, since it can be
          rendered neither at the box size nor as a flow widget.

        :raises NotImplementedError: the subclass does not override this method.
        """
        raise NotImplementedError("Subclass must override this method")

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return a dict of pop-up parameters.

        For example: ``{'left': 0, 'top': 1, 'overlay_width': 30, 'overlay_height': 4, 'anchor_height': 1}``.
        A size can also be ``('relative', percentage)`` of the space from the pop-up's edge to the far edge
        of the :class:`PopUpTarget`, or ``'pack'`` for the size of the pop-up widget itself (see :meth:`create_pop_up`).
        A position can also be an alignment inside the whole :class:`PopUpTarget`:
        ``'left'``, ``'center'`` or ``'right'`` for ``left``, and ``'top'``, ``'middle'`` or ``'bottom'`` for ``top``.

        Subclass must override this method. It is called each time this widget is rendered.

        The optional ``anchor_height`` key makes :class:`PopUpTarget` move the pop-up above the launcher, or clip
        its height, when it does not fit below;
        see :meth:`CompositeCanvas.set_pop_up <urwid.CompositeCanvas.set_pop_up>`.

        :raises NotImplementedError: the subclass does not override this method.
        """
        raise NotImplementedError("Subclass must override this method")

    def open_pop_up(self) -> None:
        """Create the pop-up widget via :meth:`create_pop_up` and invalidate this widget."""
        self._pop_up_widget = self.create_pop_up()
        self._invalidate()

    def close_pop_up(self) -> None:
        """Discard the currently open pop-up widget, if any, and invalidate this widget."""
        self._pop_up_widget = None
        self._invalidate()

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas | Canvas:
        """Render the wrapped widget, attaching the open pop-up widget to the canvas, if any."""
        canv = super().render(size, focus)
        self._launcher_size = (canv.cols(), canv.rows())
        if self._pop_up_widget is not None:
            canv = CompositeCanvas(canv)
            canv.set_pop_up(
                self._pop_up_widget,
                **self.get_pop_up_parameters(),
                on_unhandled_key=self._close_on_menu_key if self._close_on_menu else None,
                on_click_outside=self.close_pop_up if self._close_on_click_outside else None,
            )
        return canv

    def _close_on_menu_key(self, key: str) -> str | None:
        """Close the pop-up on the ``menu`` command; return any other key unhandled."""
        if self._command_map[key] != Command.MENU:
            return key
        self.close_pop_up()
        return None


def _place_anchored(maxrow: int, top: int, height: int, anchor_height: int) -> tuple[int, int]:
    """Return the (top, height) of a pop-up kept off the `anchor_height` launcher rows directly above `top`.

    The pop-up goes below the launcher when it fits there, above it when it fits there, and otherwise on the side
    with more rows (below on a tie), clipped to that side. When neither side has a row, the position is returned
    unchanged and :class:`Overlay` shifts the pop-up over the launcher, as it does for a pop-up without an anchor.

    >>> _place_anchored(24, 5, 10, 1)  # fits below
    (5, 10)
    >>> _place_anchored(24, 20, 10, 1)  # flips above
    (9, 10)
    >>> _place_anchored(24, 12, 30, 1)  # clipped below: 12 rows below, 11 above
    (12, 12)
    >>> _place_anchored(24, 13, 30, 1)  # clipped above: 11 rows below, 12 above
    (0, 12)
    >>> _place_anchored(24, 20, 10, 3)  # flips above a 3-row launcher on rows 17-19
    (7, 10)
    """
    rows_below = maxrow - top
    rows_above = top - anchor_height
    if height <= rows_below:
        return top, height
    if height <= rows_above:
        return rows_above - height, height
    if max(rows_below, rows_above) < 1:
        return top, height
    if rows_below >= rows_above:
        return top, rows_below
    return 0, rows_above


def _aligned_start(space: int, length: int, align: str) -> int:
    """Return the first of `length` cells aligned inside `space` cells, at least 0.

    >>> _aligned_start(10, 4, "center")
    3
    >>> _aligned_start(10, 4, "bottom")
    6
    >>> _aligned_start(3, 5, "right")  # longer than the space: Overlay shrinks it from the start
    0

    :raises ValueError: `align` is not a member of :class:`Align` or :class:`VAlign`.
    """
    match align:
        case Align.LEFT | VAlign.TOP:
            start = 0
        case Align.CENTER | VAlign.MIDDLE:
            # Overlay's own centring: an odd spare cell goes after the pop-up.
            start = (space - length) // 2
        case Align.RIGHT | VAlign.BOTTOM:
            start = space - length
        case _:
            raise ValueError(f"Not a pop-up alignment: {align!r}")
    return max(start, 0)


class PopUpTarget(WidgetDecoration[WrappedWidget]):
    """Box widget that overlays the pop-up(s) declared by a :class:`PopUpLauncher` inside it.

    Pop-ups nest: a pop-up widget may itself be a :class:`PopUpLauncher` with its own pop-up
    open, in which case it is drawn overlaid on top of the pop-up that opened it, and so on for
    as many levels as are open at once.
    """

    # FIXME: this whole class is a terrible hack and must be fixed when layout and rendering are separated
    _sizing = frozenset((Sizing.BOX,))
    _selectable = True

    def __init__(self, original_widget: WrappedWidget) -> None:
        """Wrap *original_widget*, which is rendered with any open pop-up(s) overlaid on top.

        :param original_widget: box widget to wrap; typically contains a :class:`PopUpLauncher`.
        """
        super().__init__(original_widget)
        # One (widget, Overlay) entry per currently open pop-up, outermost first.
        self._pop_up_levels: list[tuple[AbstractWidget, Overlay[AbstractWidget, AbstractWidget]]] = []
        self._current_widget: AbstractWidget = self._original_widget
        # Unhandled key callback of the topmost open pop-up.
        self._pop_up_unhandled_key: Callable[[str], str | None] | None = None
        # Outside click callback of the topmost open pop-up and the (left, right, top, bottom) padding around it,
        # or None when its launcher set no callback.
        self._pop_up_click_outside: tuple[Callable[[], None], tuple[int, int, int, int]] | None = None
        self._cache_original_canvas: Canvas | None = None

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Do nothing: every focus under this widget is kept when a parent container enters it.

        The widget that receives keys is known only after the pop-ups were laid out at the current size,
        which the entry hook does not have, see :ref:`select-navigation`.
        """

    def _update_overlay(self, size: tuple[int, int], focus: bool) -> None:
        """Rebuild :attr:`_current_widget` as a chain of Overlay widgets, one per open pop-up.

        Level 0 wraps :attr:`_original_widget`'s own pop-up, if any; level 1 wraps a further
        pop-up declared by level 0's pop-up widget, if that widget is itself a
        :class:`PopUpLauncher` with its own pop-up open; and so on. Each level's pop-up widget
        is rendered directly to discover whether it declares a further nested pop-up, rather
        than inspecting the wrapping Overlay's merged canvas, whose "pop up" coordinate can go
        stale once nothing re-declares it. A nested pop-up's position is relative to the pop-up
        widget that declares it, so it is offset by where that widget was placed.

        :param size: box size to render :attr:`_original_widget` and every pop-up level at.
        :param focus: whether this widget is in focus.
        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        canv = self._original_widget.render(size, focus=focus)
        self._cache_original_canvas = canv  # imperfect performance hack

        old_levels = self._pop_up_levels
        new_levels: list[tuple[AbstractWidget, Overlay[AbstractWidget, AbstractWidget]]] = []
        bottom_widget: AbstractWidget = self._original_widget
        # Once a level is rebuilt, every deeper level must be rebuilt too: a reused Overlay's
        # bottom_w still points at the previous (now discarded) widget at the shallower level.
        rebuilding = False

        pop_up = canv.get_pop_up()
        anchor_height = canv.get_pop_up_anchor_height()
        h_align, v_align = canv.get_pop_up_align()
        on_unhandled_key = canv.get_pop_up_unhandled_key()
        on_click_outside = canv.get_pop_up_click_outside()
        top_unhandled_key = None
        top_click_outside = None
        # Position of the widget that declared the current pop-up; the original widget fills this widget.
        offset_left = offset_top = 0
        while pop_up:
            left, top, (w, overlay_width, overlay_height) = pop_up
            # An aligned axis is placed inside the whole target once the size is known, so its space starts at 0.
            left = offset_left + left if h_align is None else 0
            top = offset_top + top if v_align is None else 0
            sizing = w.sizing()
            packed = isinstance(overlay_width, str) or isinstance(overlay_height, str)
            # Resolve a relative or "pack" size to cells, so the anchor placement gets a number of rows.
            # A relative size uses Overlay's own rounding (half up), and is capped at the larger of that space and the
            # whole target, because a huge percentage gives an infinite product that has no integer value.
            # A "pack" height is the rows at the width the Overlay leaves once it has shrunk the pop-up to the target.
            # Either is at least one cell, like a size given in cells.
            width: int
            if isinstance(overlay_width, tuple):
                space = max(size[0] - left, 0)
                width = max(int(min(space * overlay_width[1] / 100, max(space, size[0])) + 0.5), 1)
            elif isinstance(overlay_width, str):
                if Sizing.FIXED not in sizing:
                    raise WidgetError(f"A 'pack' pop-up width needs a FIXED widget, got {w!r}")
                width = max(w.pack((), focus)[0], 1)
            else:
                width = overlay_width
            height: int
            if isinstance(overlay_height, tuple):
                space = max(size[1] - top, 0)
                height = max(int(min(space * overlay_height[1] / 100, max(space, size[1])) + 0.5), 1)
            elif isinstance(overlay_height, str):
                if Sizing.FLOW not in sizing:
                    raise WidgetError(f"A 'pack' pop-up height needs a FLOW widget, got {w!r}")
                height = max(w.pack((min(width, size[0]),), focus)[1], 1)
            else:
                height = overlay_height
            if h_align is not None:
                left = _aligned_start(size[0], width, h_align)
            if v_align is not None:
                top = _aligned_start(size[1], height, v_align)
            if anchor_height is not None:
                top, height = _place_anchored(size[1], top, height, anchor_height)
            level = len(new_levels)
            reuse = not rebuilding and level < len(old_levels) and old_levels[level][0] == w
            # A measured widget that cannot take a box size is shown as a flow widget, with the rows that do not fit
            # the box cut off, so it stays off the anchor rows.
            top_w = w
            if packed and Sizing.BOX not in sizing:
                if Sizing.FLOW not in sizing:
                    raise WidgetError(f"A pop-up with a 'pack' size needs a FLOW or BOX widget, got {w!r}")
                previous = old_levels[level][1].top_w if reuse else None
                top_w = (
                    previous
                    if isinstance(previous, Filler) and previous.original_widget is w
                    else Filler(w, valign=VAlign.TOP)
                )
            overlay: Overlay[AbstractWidget, AbstractWidget]
            if reuse:
                overlay = old_levels[level][1]
                if overlay.top_w is not top_w:
                    overlay.top_w = top_w
                overlay.set_overlay_parameters(
                    align=Align.LEFT,
                    width=width,
                    valign=VAlign.TOP,
                    height=height,
                    left=left,
                    top=top,
                )
            else:
                rebuilding = True
                overlay = Overlay(
                    top_w=top_w,
                    bottom_w=bottom_widget,
                    align=Align.LEFT,
                    width=width,
                    valign=VAlign.TOP,
                    height=height,
                    left=left,
                    top=top,
                )
            new_levels.append((w, overlay))
            bottom_widget = overlay
            top_unhandled_key = on_unhandled_key

            # Check w itself for a further nested pop-up; see the docstring for why. Render it where and at the
            # size the Overlay puts it, which differs from the request when it does not fit, through the Filler
            # that shows a flow pop-up.
            padding = overlay.calculate_padding_filler(size, focus)
            top_click_outside = None if on_click_outside is None else (on_click_outside, padding)
            pad_left, pad_right, pad_top, pad_bottom = padding
            offset_left, offset_top = pad_left, pad_top
            # Both dimensions were given to the Overlay in cells, so it returns a box size.
            w_size = typing.cast("tuple[int, int]", overlay.top_w_size(size, pad_left, pad_right, pad_top, pad_bottom))
            w_canv = top_w.render(w_size, focus=focus)
            pop_up = w_canv.get_pop_up()
            anchor_height = w_canv.get_pop_up_anchor_height()
            h_align, v_align = w_canv.get_pop_up_align()
            on_unhandled_key = w_canv.get_pop_up_unhandled_key()
            on_click_outside = w_canv.get_pop_up_click_outside()

        self._pop_up_levels = new_levels
        self._current_widget = bottom_widget
        self._pop_up_unhandled_key = top_unhandled_key
        self._pop_up_click_outside = top_click_outside

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> Canvas:
        """Rebuild the pop-up overlay chain for *size* and render the resulting widget.

        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, focus)
        return self._current_widget.render(size, focus=focus)

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """
        Return the cursor coordinates of the current widget.

        :raises TypeError: the current widget has no ``get_cursor_coords`` method.
        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, True)

        if not hasattr(self._current_widget, "get_cursor_coords"):
            raise TypeError(f"widget {type(self._current_widget)} has no get_cursor_coords method")

        return self._current_widget.get_cursor_coords(size)  # type: ignore[no-any-return]

    def get_pref_col(self, size: tuple[int, int]) -> int | Literal["left", "right", Align.LEFT, Align.RIGHT] | None:
        """
        Return the preferred cursor column of the current widget, or None if it has none.

        :raises TypeError: the current widget has no ``get_pref_col`` method.
        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, True)

        if not hasattr(self._current_widget, "get_pref_col"):
            raise TypeError(f"widget {type(self._current_widget)} has no get_pref_col method")

        pref_col: int | Literal["left", "right", Align.LEFT, Align.RIGHT] | None = self._current_widget.get_pref_col(
            size
        )
        return pref_col

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Rebuild the pop-up overlay chain for *size* and forward the keypress to it.

        A key the topmost pop-up leaves unhandled goes to the ``on_unhandled_key`` callback its launcher set, if
        any; see :meth:`CompositeCanvas.set_pop_up <urwid.CompositeCanvas.set_pop_up>`.

        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, True)
        unhandled = self._current_widget.keypress(size, key)
        if unhandled is not None and self._pop_up_unhandled_key is not None:
            return self._pop_up_unhandled_key(unhandled)
        return unhandled

    def move_cursor_to_coords(self, size: tuple[int, int], x: int, y: int) -> bool:
        """
        Move the cursor of the current widget to ``(x, y)``.

        :raises TypeError: the current widget has no ``move_cursor_to_coords`` method.
        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, True)

        if not hasattr(self._current_widget, "move_cursor_to_coords"):
            raise TypeError(f"widget {type(self._current_widget)} has no move_cursor_to_coords method")

        return typing.cast("bool", self._current_widget.move_cursor_to_coords(size, x, y))

    def mouse_event(
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Rebuild the pop-up overlay chain for *size* and forward the mouse event to it.

        A press of mouse button 1, 2 or 3 outside the topmost pop-up goes to the ``on_click_outside`` callback its
        launcher set, if any.
        The press is then handled and does not reach the widgets under the pop-up.
        See :meth:`CompositeCanvas.set_pop_up <urwid.CompositeCanvas.set_pop_up>`.

        :raises WidgetError: a pop-up widget cannot take its ``'pack'`` size,
            see :meth:`PopUpLauncher.create_pop_up`.
        """
        self._update_overlay(size, focus)
        if (
            self._pop_up_click_outside is not None
            and button in {MouseButton.LEFT, MouseButton.MIDDLE, MouseButton.RIGHT}
            and is_mouse_press(event)
        ):
            on_click_outside, (left, right, top, bottom) = self._pop_up_click_outside
            if not (left <= col < size[0] - right and top <= row < size[1] - bottom):
                on_click_outside()
                return True
        return self._current_widget.mouse_event(size, event, button, col, row, focus)

    def pack(  # type: ignore[override]
        self,
        size: tuple[int, int] | tuple[()] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Rebuild the pop-up overlay chain for *size* and return the current widget's packed size."""
        self._update_overlay(size, focus)  # type: ignore[arg-type]
        return self._current_widget.pack(size)


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
