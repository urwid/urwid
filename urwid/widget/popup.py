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

    from .widget import Widget

    class PopUpParametersModel(TypedDict):
        left: int
        top: int
        overlay_width: int
        overlay_height: int


WrappedWidget = typing.TypeVar("WrappedWidget")


class PopUpLauncher(delegate_to_widget_mixin("_original_widget"), WidgetDecoration[WrappedWidget]):
    def __init__(self, original_widget: [WrappedWidget]) -> None:
        super().__init__(original_widget)
        self._pop_up_widget = None

    def create_pop_up(self) -> Widget:
        """
        Subclass must override this method and return a widget
        to be used for the pop-up.  This method is called once each time
        the pop-up is opened.
        """
        raise NotImplementedError("Subclass must override this method")

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """
        Subclass must override this method and have it return a dict, eg:

        {'left':0, 'top':1, 'overlay_width':30, 'overlay_height':4}

        This method is called each time this widget is rendered.
        """
        raise NotImplementedError("Subclass must override this method")

    def open_pop_up(self) -> None:
        self._pop_up_widget = self.create_pop_up()
        self._invalidate()

    def close_pop_up(self) -> None:
        self._pop_up_widget = None
        self._invalidate()

    def render(self, size, focus: bool = False) -> CompositeCanvas | Canvas:
        canv = super().render(size, focus)
        if self._pop_up_widget:
            canv = CompositeCanvas(canv)
            canv.set_pop_up(self._pop_up_widget, **self.get_pop_up_parameters())
        return canv


class PopUpTarget(WidgetDecoration[WrappedWidget]):
    # FIXME: this whole class is a terrible hack and must be fixed when layout and rendering are separated
    _sizing = frozenset((Sizing.BOX,))
    _selectable = True

    def __init__(self, original_widget: WrappedWidget) -> None:
        super().__init__(original_widget)
        self._pop_up = None
        self._current_widget = self._original_widget

    def _update_overlay(self, size: tuple[int, int], focus: bool) -> None:
        canv = self._original_widget.render(size, focus=focus)
        self._cache_original_canvas = canv  # imperfect performance hack

        if pop_up := canv.get_pop_up():
            left, top, (w, overlay_width, overlay_height) = pop_up
            if self._pop_up != w:
                self._pop_up = w
                self._current_widget = Overlay(
                    top_w=w,
                    bottom_w=self._original_widget,
                    align=Align.LEFT,
                    width=overlay_width,
                    valign=VAlign.TOP,
                    height=overlay_height,
                    left=left,
                    top=top,
                )
            else:
                self._current_widget.set_overlay_parameters(
                    align=Align.LEFT,
                    width=overlay_width,
                    valign=VAlign.TOP,
                    height=overlay_height,
                    left=left,
                    top=top,
                )
        else:
            self._pop_up = None
            self._current_widget = self._original_widget

    def render(self, size: tuple[int, int], focus: bool = False) -> Canvas:
        self._update_overlay(size, focus)
        return self._current_widget.render(size, focus=focus)

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        self._update_overlay(size, True)
        return self._current_widget.get_cursor_coords(size)

    def get_pref_col(self, size: tuple[int, int]) -> int:
        self._update_overlay(size, True)
        return self._current_widget.get_pref_col(size)

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        self._update_overlay(size, True)
        return self._current_widget.keypress(size, key)

    def move_cursor_to_coords(self, size: tuple[int, int], x: int, y: int):
        self._update_overlay(size, True)
        return self._current_widget.move_cursor_to_coords(size, x, y)

    def mouse_event(
        self,
        size: tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        self._update_overlay(size, focus)
        return self._current_widget.mouse_event(size, event, button, col, row, focus)

    def pack(self, size: tuple[int, int] | None = None, focus: bool = False) -> tuple[int, int]:
        self._update_overlay(size, focus)
        return self._current_widget.pack(size)


def _test():
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
