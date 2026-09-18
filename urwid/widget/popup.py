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


from __future__ import annotations

import typing

from urwid.canvas import CompositeCanvas

from .constants import Align, Sizing, VAlign
from .overlay import Overlay
from .widget import delegate_to_widget_mixin
from .widget_decoration import WidgetDecoration

if typing.TYPE_CHECKING:
    from typing_extensions import TypedDict

    from urwid.canvas import Canvas

    from .widget import AbstractBoxWidget, AbstractWidget

    class PopUpParametersModel(TypedDict):
        left: int
        top: int
        overlay_width: int
        overlay_height: int


WrappedWidget = typing.TypeVar("WrappedWidget", bound="AbstractBoxWidget")


class PopUpLauncher(
    delegate_to_widget_mixin("_original_widget"),  # type: ignore[misc]
    WidgetDecoration[WrappedWidget],
):
    def __init__(self, original_widget: WrappedWidget) -> None:
        super().__init__(original_widget)
        self._pop_up_widget: AbstractWidget | None = None

    def create_pop_up(self) -> AbstractWidget:
        """
        Subclass must override this method and return a widget
        to be used for the pop-up.  This method is called once each time
        the pop-up is opened.

        :class:`PopUpTarget` renders the pop-up with the box size declared by
        :meth:`get_pop_up_parameters`, so the widget returned here must accept an
        (*overlay_width*, *overlay_height*) size.  Wrap a flow or fixed widget in a
        :class:`Filler <urwid.Filler>` (or in another box container) before returning it.

        :raises NotImplementedError: the subclass does not override this method.
        """
        raise NotImplementedError("Subclass must override this method")

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """
        Subclass must override this method and have it return a dict, eg:

        {'left':0, 'top':1, 'overlay_width':30, 'overlay_height':4}

        This method is called each time this widget is rendered.

        :raises NotImplementedError: the subclass does not override this method.
        """
        raise NotImplementedError("Subclass must override this method")

    def open_pop_up(self) -> None:
        self._pop_up_widget = self.create_pop_up()
        self._invalidate()

    def close_pop_up(self) -> None:
        self._pop_up_widget = None
        self._invalidate()

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas | Canvas:
        canv = super().render(size, focus)
        if self._pop_up_widget:
            canv = CompositeCanvas(canv)
            canv.set_pop_up(self._pop_up_widget, **self.get_pop_up_parameters())
        return canv


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

    def _update_overlay(self, size: tuple[int, int], focus: bool) -> None:
        """Rebuild :attr:`_current_widget` as a chain of Overlay widgets, one per open pop-up.

        Level 0 wraps :attr:`_original_widget`'s own pop-up, if any; level 1 wraps a further
        pop-up declared by level 0's pop-up widget, if that widget is itself a
        :class:`PopUpLauncher` with its own pop-up open; and so on. Each level's pop-up widget
        is rendered directly to discover whether it declares a further nested pop-up, rather
        than inspecting the wrapping Overlay's merged canvas, whose "pop up" coordinate can go
        stale once nothing re-declares it.

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
        while pop_up:
            left, top, (w, overlay_width, overlay_height) = pop_up
            level = len(new_levels)
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

            # Check w itself for a further nested pop-up; see the docstring for why.
            pop_up = w.render((overlay_width, overlay_height), focus=focus).get_pop_up()

        self._pop_up_levels = new_levels
        self._current_widget = bottom_widget

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> Canvas:
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

        return self._current_widget.get_cursor_coords(size)

    def get_pref_col(self, size: tuple[int, int]) -> int:
        """
        Return the preferred cursor column of the current widget.

        :raises TypeError: the current widget has no ``get_pref_col`` method.
        """
        self._update_overlay(size, True)

        if not hasattr(self._current_widget, "get_pref_col"):
            raise TypeError(f"widget {type(self._current_widget)} has no get_pref_col method")

        return typing.cast("int", self._current_widget.get_pref_col(size))

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        self._update_overlay(size, True)
        return self._current_widget.keypress(size, key)

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
        self._update_overlay(size, focus)
        return self._current_widget.mouse_event(size, event, button, col, row, focus)

    def pack(  # type: ignore[override]
        self,
        size: tuple[int, int] | tuple[()] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        self._update_overlay(size, focus)  # type: ignore[arg-type]
        return self._current_widget.pack(size)  # type: ignore[arg-type]


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
