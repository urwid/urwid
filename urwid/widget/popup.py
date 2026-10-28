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

from .constants import Align, Sizing, VAlign
from .overlay import Overlay
from .widget import delegate_to_widget_mixin
from .widget_decoration import WidgetDecoration

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal, NotRequired, TypedDict

    from urwid.canvas import Canvas

    from .widget import AbstractBoxWidget, AbstractWidget, _DelegateToWidgetMixin

    class PopUpParametersModel(TypedDict):
        """Position and box size a :class:`PopUpLauncher` requests for its pop-up."""

        left: int
        top: int
        overlay_width: int
        overlay_height: int
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
    _launcher_size: tuple[int, int] | None = None

    def __init__(self, original_widget: LauncherWidget, *, close_on_menu: bool = False) -> None:
        """Wrap `original_widget`, with no pop-up open yet.

        :param original_widget: widget that opens the pop-up.
        :param close_on_menu: close the pop-up when it leaves a key for the ``menu`` command (:kbd:`esc` by
            default) unhandled while it is the topmost open pop-up.
        """
        super().__init__(original_widget)
        self._close_on_menu = close_on_menu
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

        :raises NotImplementedError: the subclass does not override this method.
        """
        raise NotImplementedError("Subclass must override this method")

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return a dict of pop-up parameters.

        For example: ``{'left': 0, 'top': 1, 'overlay_width': 30, 'overlay_height': 4, 'anchor_height': 1}``.

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
        on_unhandled_key = canv.get_pop_up_unhandled_key()
        top_unhandled_key = None
        # Position of the widget that declared the current pop-up; the original widget fills this widget.
        offset_left = offset_top = 0
        while pop_up:
            left, top, (w, overlay_width, overlay_height) = pop_up
            left += offset_left
            top += offset_top
            if anchor_height is not None:
                top, overlay_height = _place_anchored(size[1], top, overlay_height, anchor_height)
            level = len(new_levels)
            overlay: Overlay[AbstractWidget, AbstractWidget]
            if not rebuilding and level < len(old_levels) and old_levels[level][0] == w:
                overlay = old_levels[level][1]
                overlay.set_overlay_parameters(
                    align=Align.LEFT,
                    width=overlay_width,
                    valign=VAlign.TOP,
                    height=overlay_height,
                    left=left,
                    top=top,
                )
            else:
                rebuilding = True
                overlay = Overlay(
                    top_w=w,
                    bottom_w=bottom_widget,
                    align=Align.LEFT,
                    width=overlay_width,
                    valign=VAlign.TOP,
                    height=overlay_height,
                    left=left,
                    top=top,
                )
            new_levels.append((w, overlay))
            bottom_widget = overlay
            top_unhandled_key = on_unhandled_key

            # Check w itself for a further nested pop-up; see the docstring for why. Render it where and at the
            # size the Overlay puts it, which differs from the request when it does not fit.
            pad_left, pad_right, pad_top, pad_bottom = overlay.calculate_padding_filler(size, focus)
            offset_left, offset_top = pad_left, pad_top
            w_size = overlay.top_w_size(size, pad_left, pad_right, pad_top, pad_bottom)
            w_canv = w.render(w_size, focus=focus)
            pop_up = w_canv.get_pop_up()
            anchor_height = w_canv.get_pop_up_anchor_height()
            on_unhandled_key = w_canv.get_pop_up_unhandled_key()

        self._pop_up_levels = new_levels
        self._current_widget = bottom_widget
        self._pop_up_unhandled_key = top_unhandled_key

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> Canvas:
        """Rebuild the pop-up overlay chain for *size* and render the resulting widget."""
        self._update_overlay(size, focus)
        return self._current_widget.render(size, focus=focus)

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """
        Return the cursor coordinates of the current widget.

        :raises TypeError: the current widget has no ``get_cursor_coords`` method.
        """
        self._update_overlay(size, True)

        if not hasattr(self._current_widget, "get_cursor_coords"):
            raise TypeError(f"widget {type(self._current_widget)} has no get_cursor_coords method")

        return self._current_widget.get_cursor_coords(size)  # type: ignore[no-any-return]

    def get_pref_col(self, size: tuple[int, int]) -> int | Literal["left", "right", Align.LEFT, Align.RIGHT] | None:
        """
        Return the preferred cursor column of the current widget, or None if it has none.

        :raises TypeError: the current widget has no ``get_pref_col`` method.
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
        """Rebuild the pop-up overlay chain for *size* and forward the mouse event to it."""
        self._update_overlay(size, focus)
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
