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


"""Tabs: a row of tab labels over the body of the selected tab."""

from __future__ import annotations

import functools
import typing

from urwid.canvas import CanvasCombine, CanvasJoin, CompositeCanvas, SolidCanvas
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .attr_map import _attr_map_dict
from .constants import Sizing, VAlign, WrapMode
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin, _UnfocusedFocusAttrMixin
from .monitored_list import MonitoredFocusList
from .text import Text
from .widget import AbstractWidget, Widget, WidgetError, _select_enter_child

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Hashable, Iterable, Sequence

    from urwid.canvas import Canvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .widget import AbstractFlowWidget

__all__ = ("Tabs", "TabsError")

_LabelT = typing.TypeVar("_LabelT", bound=AbstractWidget)


class TabsError(WidgetError):
    """Tabs related errors."""


class Tabs(
    Widget,
    WidgetContainerMixin[int],
    WidgetContainerListContentsMixin[tuple[AbstractWidget, AbstractWidget]],
    _UnfocusedFocusAttrMixin,
):
    """A row of tab labels over (or under) the body of the selected tab.

    The selected tab is the focus of the container: :attr:`focus_position` is its index and :attr:`focus` its body.
    Only the selected body is rendered, and keys go to it.
    A button 1 press on a label selects its tab.
    The ``'next tab'`` and ``'previous tab'`` commands select the neighbour, wrapping around at the ends;
    no key is mapped to them by default, see :class:`~urwid.CommandMap`.

    With ``bar_selectable=True`` the label row can take the keyboard focus:
    the command towards the bar (``'cursor up'`` for a top bar), unhandled by the body, moves the focus to it.
    There ``'cursor left'`` and ``'cursor right'`` move a bar cursor without selecting,
    ``'activate'`` selects the tab under it, and the command towards the body returns the focus there.
    :attr:`focus_position` stays the selected tab while the bar has the keyboard focus,
    so :meth:`get_focus_widgets` names the body then.
    With a single tab there is nothing to switch to: the bar does not take the focus and the tab commands are returned.

    Labels are display-only: each one is rendered as a fixed widget, trimmed to one row, and never gets input,
    so a label should have text.
    When the labels do not fit, the bar shows the selected label (the label under the bar cursor while the bar has
    the focus) centred, or its first column when it is wider than the bar.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`contents`.
    Its handlers receive the container, the old and the new index, which is ``None`` while it is empty.
    It reports the index, not the body: deleting the selected tab when another one follows it keeps the index,
    so the next tab becomes selected without a signal.
    An application that follows the selected body compares :attr:`focus` before and after its own contents changes.

    >>> tabs = Tabs([("Log", Text("log body")), ("Edit", Text("edit body"))])
    >>> tabs.render((12,)).text
    [b'Log Edit    ', b'log body    ']
    >>> tabs.focus_position = 1
    >>> tabs.render((12,)).text
    [b'Log Edit    ', b'edit body   ']
    """

    signals: typing.ClassVar[list[str]] = ["focus changed"]

    def __init__(
        self,
        tabs: Iterable[tuple[_TagMarkup | AbstractWidget, AbstractWidget]] = (),
        *,
        selected: int = 0,
        bar_position: typing.Literal["top", "bottom"] | VAlign = VAlign.TOP,
        bar_selectable: bool = False,
        attr_map: _AttrMapLike | None = None,
        selected_map: _AttrMapLike | None = None,
        focus_map: _AttrMapLike | None = None,
        unfocused_focus_attr: _AttrMapLike | None = None,
        dividechars: int = 1,
    ) -> None:
        """Build the tabs from `(label, body)` pairs.

        :param tabs: one `(label, body)` pair per tab, in order.
            A label is a widget, or markup made into a widget by :meth:`options`.
        :param selected: index of the tab selected first; ignored when *tabs* is empty.
        :param bar_position: ``'top'`` or ``'bottom'``, where the label row is drawn.
        :param bar_selectable: let the label row take the keyboard focus when there are two or more tabs.
        :param attr_map: attribute map applied to every label, in any form :class:`AttrMap` takes.
        :param selected_map: attribute map applied to the label of the selected tab instead of *attr_map*.
        :param focus_map: attribute map applied to the label under the bar cursor while the bar has the focus,
            instead of the other two.
        :param unfocused_focus_attr: attribute map applied over the selected label while the tabs render without
            focus; see :attr:`unfocused_focus_attr`.
        :param dividechars: blank screen columns between two labels.
        :raises TypeError: a body is not a widget.
        :raises TagMarkupException: a label is neither a widget nor valid text markup.
        :raises AttrMapError: a key or value of *attr_map*, *selected_map*, *focus_map* or *unfocused_focus_attr*
            is not hashable.
        :raises ValueError: a label is not a fixed widget, a body is neither a flow nor a box widget,
            *bar_position* is not ``'top'`` or ``'bottom'``, or *dividechars* is not an int >= 0.
        :raises IndexError: *selected* is not an index of *tabs*.
        """
        super().__init__()
        self._bar_position = self._valid_bar_position(bar_position)
        self._dividechars = self._valid_dividechars(dividechars)
        self._bar_selectable = bar_selectable
        self._attr_map = None if attr_map is None else _attr_map_dict(attr_map)
        self._selected_map = None if selected_map is None else _attr_map_dict(selected_map)
        self._focus_map = None if focus_map is None else _attr_map_dict(focus_map)
        self._set_unfocused_focus_attr(unfocused_focus_attr)
        # Whether the label row has the keyboard focus, and the label the bar cursor is on.
        # Only true while _bar_can_focus() holds; _contents_modified and the bar_selectable setter clear it.
        self._bar_focused = False
        self._bar_cursor = 0

        self._contents: MonitoredFocusList[tuple[AbstractWidget, AbstractWidget]] = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda _focus: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)
        self._contents.extend((body, self.options(label)) for label, body in tabs)
        if self._contents:
            self.focus_position = selected
        # connected last, so that filling the contents during construction sends no signal
        self._contents.set_focus_moved_callback(functools.partial(self._emit, "focus changed"))

    @staticmethod
    def _valid_bar_position(bar_position: typing.Literal["top", "bottom"] | VAlign) -> VAlign:
        """Return *bar_position* as a :class:`VAlign`.

        :raises ValueError: it is not ``'top'`` or ``'bottom'``.
        """
        if bar_position not in {VAlign.TOP, VAlign.BOTTOM}:
            raise ValueError(f"bar_position must be 'top' or 'bottom', not {bar_position!r}")
        return VAlign(bar_position)

    @staticmethod
    def _valid_dividechars(dividechars: int) -> int:
        """Return *dividechars* unchanged.

        :raises ValueError: it is not an int >= 0.
        """
        if not isinstance(dividechars, int) or isinstance(dividechars, bool) or dividechars < 0:
            raise ValueError(f"dividechars must be an int >= 0, not {dividechars!r}")
        return dividechars

    def _repr_words(self) -> list[str]:
        """Return the base repr words followed by the number of tabs."""
        count = len(self._contents)
        return [*super()._repr_words(), f"({count} tab{'' if count == 1 else 's'})"]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor arguments that differ from their defaults, for the repr.

        The selected index is included only when there is more than one tab.
        """
        attrs = {
            **super()._repr_attrs(),
            "selected": self.focus_position if len(self._contents) > 1 else 0,
            "bar_position": self._bar_position,
            "bar_selectable": self._bar_selectable,
            "attr_map": self._attr_map,
            "selected_map": self._selected_map,
            "focus_map": self._focus_map,
            "unfocused_focus_attr": self._unfocused_focus_attr,
            "dividechars": self._dividechars,
        }
        return remove_defaults(attrs, Tabs.__init__)

    @typing.overload
    @staticmethod
    def options(label: _LabelT) -> _LabelT: ...

    @typing.overload
    @staticmethod
    def options(label: _TagMarkup) -> Text: ...

    @staticmethod
    def options(label: _TagMarkup | AbstractWidget) -> AbstractWidget:
        """Return the label widget for a :attr:`contents` entry.

        A widget is returned as given, markup as a :class:`Text` that clips at the bar edge.

        :raises TagMarkupException: *label* is neither a widget nor valid text markup.

        >>> Tabs.options("Log").render(()).text
        [b'Log']
        """
        if isinstance(label, AbstractWidget):
            return label
        return Text(label, wrap=WrapMode.CLIP)

    @property
    def contents(self) -> MonitoredFocusList[tuple[AbstractWidget, AbstractWidget]]:
        """The tabs as a list of `(body, label)` pairs, body first as in the other containers.

        The list may be modified like a normal list and the widget is updated.
        :meth:`options` makes a label widget from markup.
        """
        return self._contents

    @contents.setter
    def contents(self, new_contents: Sequence[tuple[AbstractWidget, AbstractWidget]]) -> None:
        """Replace the contents with *new_contents*.

        :raises TypeError: an item is not a `(body, label)` pair of widgets.
        :raises ValueError: a label is not a fixed widget, or a body is neither a flow nor a box widget.
        """
        self._contents[:] = new_contents

    @staticmethod
    def _validate_contents_modified(
        _slc: tuple[int, int, int],
        new_items: Collection[tuple[AbstractWidget, AbstractWidget]],
    ) -> None:
        """Reject contents changes that would put an invalid item into the tabs.

        :raises TypeError: an added item is not a `(body, label)` pair of widgets.
        :raises ValueError: an added label is not a fixed widget, or an added body is neither a flow nor a box widget.
        """
        for item in new_items:
            if not (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], AbstractWidget)
                and isinstance(item[1], AbstractWidget)
            ):
                raise TypeError(f"Tabs contents item must be a (body, label) pair of widgets, not {item!r}")
            body, label = item
            # labels are measured and rendered at size ()
            if Sizing.FIXED not in label.sizing():
                raise ValueError(f"Tabs label must be a fixed widget, such as Text: {label!r}")
            if not body.sizing() & {Sizing.FLOW, Sizing.BOX}:
                raise ValueError(f"Tabs body must be a flow or a box widget, wrap it in Padding or Filler: {body!r}")

    def _contents_modified(self) -> None:
        """Keep the bar cursor on a tab and the bar focus valid, and invalidate this widget."""
        if not self._bar_can_focus():
            self._bar_focused = False
        self._bar_cursor = max(0, min(self._bar_cursor, len(self._contents) - 1))
        self._invalidate()

    @property
    def focus(self) -> AbstractWidget | None:
        """The body of the selected tab, or ``None`` when there are no tabs."""
        if not self._contents:
            return None
        return self._contents[self.focus_position][0]

    @property
    def focus_position(self) -> int:
        """Index of the selected tab.

        :raises IndexError: there are no tabs.
        """
        if (focus := self._contents.focus) is not None:
            return focus
        raise IndexError("No focus_position, Tabs is empty")

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """Select the tab at *position*.

        :raises IndexError: *position* is not an index of a tab.
        """
        try:
            if position < 0 or position >= len(self._contents):
                raise IndexError(f"No Tabs child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Tabs child widget at position {position}").with_traceback(exc.__traceback__) from exc
        self._contents.focus = position

    @property
    def bar_position(self) -> VAlign:
        """Where the label row is drawn, :attr:`VAlign.TOP` or :attr:`VAlign.BOTTOM`.

        :raises ValueError: the new value is not ``'top'`` or ``'bottom'``.
        """
        return self._bar_position

    @bar_position.setter
    def bar_position(self, bar_position: typing.Literal["top", "bottom"] | VAlign) -> None:
        self._bar_position = self._valid_bar_position(bar_position)
        self._invalidate()

    @property
    def bar_selectable(self) -> bool:
        """Whether the label row can take the keyboard focus.

        Setting it to false returns the focus to the body.
        """
        return self._bar_selectable

    @bar_selectable.setter
    def bar_selectable(self, bar_selectable: bool) -> None:
        self._bar_selectable = bar_selectable
        if not self._bar_can_focus():
            self._bar_focused = False
        self._invalidate()

    @property
    def attr_map(self) -> dict[Hashable, Hashable] | None:
        """Attribute map applied to every label, or ``None``.

        A copy is returned.

        :raises AttrMapError: a key or value of the new map is not hashable.
        """
        return None if self._attr_map is None else self._attr_map.copy()

    @attr_map.setter
    def attr_map(self, attr_map: _AttrMapLike | None) -> None:
        self._attr_map = None if attr_map is None else _attr_map_dict(attr_map)
        self._invalidate()

    @property
    def selected_map(self) -> dict[Hashable, Hashable] | None:
        """Attribute map applied to the selected label instead of :attr:`attr_map`, or ``None``.

        A copy is returned.

        :raises AttrMapError: a key or value of the new map is not hashable.
        """
        return None if self._selected_map is None else self._selected_map.copy()

    @selected_map.setter
    def selected_map(self, selected_map: _AttrMapLike | None) -> None:
        self._selected_map = None if selected_map is None else _attr_map_dict(selected_map)
        self._invalidate()

    @property
    def focus_map(self) -> dict[Hashable, Hashable] | None:
        """Attribute map applied to the label under the bar cursor while the bar has the focus.

        ``None`` applies none.
        A copy is returned.

        :raises AttrMapError: a key or value of the new map is not hashable.
        """
        return None if self._focus_map is None else self._focus_map.copy()

    @focus_map.setter
    def focus_map(self, focus_map: _AttrMapLike | None) -> None:
        self._focus_map = None if focus_map is None else _attr_map_dict(focus_map)
        self._invalidate()

    @property
    def dividechars(self) -> int:
        """Blank screen columns between two labels.

        :raises ValueError: the new value is not an int >= 0.
        """
        return self._dividechars

    @dividechars.setter
    def dividechars(self, dividechars: int) -> None:
        self._dividechars = self._valid_dividechars(dividechars)
        self._invalidate()

    def _bar_can_focus(self) -> bool:
        """Return whether the bar may take the keyboard focus: it is selectable and there is a tab to switch to."""
        return self._bar_selectable and len(self._contents) > 1

    def selectable(self) -> bool:
        """Return whether the tabs take keys.

        With two or more tabs they do, so a parent passes them the tab commands.
        A single tab follows its body.
        """
        if len(self._contents) > 1:
            return True
        return bool(self._contents) and self._contents[0][0].selectable()

    def sizing(self) -> frozenset[Sizing]:
        """Return box sizing, plus flow sizing when every body is a flow widget.

        Asked on every call, since the contents may change.
        """
        if all(Sizing.FLOW in body.sizing() for body, _label in self._contents):
            return frozenset((Sizing.BOX, Sizing.FLOW))
        return frozenset((Sizing.BOX,))

    def _geometry(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool,
    ) -> tuple[int | None, int, tuple[int] | tuple[int, int], int]:
        """Return where the bar and the selected body are drawn for *size*.

        The tabs must not be empty.

        :returns: the row of the bar, ``None`` when no row is drawn;
            the first row of the body; the size the body is rendered with; and the number of body rows shown.
        :raises TabsError: *size* is ``()``, or a flow size and the selected body is not a flow widget.
        """
        if not size:
            raise TabsError("Tabs is not a fixed widget, it cannot be rendered at size ()")
        body = self._contents[self.focus_position][0]
        maxcol = size[0]
        body_focus = focus and not self._bar_focused
        body_size: tuple[int] | tuple[int, int]
        if len(size) == 1:
            if Sizing.FLOW not in body.sizing():
                raise TabsError(
                    f"The selected body is not a flow widget, Tabs cannot be rendered at {size!r}: {body!r}"
                )
            body_size = (maxcol,)
            body_rows = typing.cast("AbstractFlowWidget", body).rows(body_size, body_focus)
            rows = body_rows + 1
        else:
            rows = size[1]
            body_rows = max(rows - 1, 0)
            # a body that supports box sizing keeps its own box layout, a flow-only body is padded or trimmed
            body_size = (maxcol, body_rows) if Sizing.BOX in body.sizing() else (maxcol,)
        if not rows:
            return None, 0, body_size, 0
        if self._bar_position == VAlign.TOP:
            return 0, 1, body_size, body_rows
        return body_rows, 0, body_size, body_rows

    def _bar_target(self, focus: bool) -> int:
        """Return the index of the label the bar keeps visible."""
        return self._bar_cursor if focus and self._bar_focused else self.focus_position

    def _bar_starts(self, widths: Sequence[int]) -> list[int]:
        """Return the first bar column of each label, *widths* being the label widths in order."""
        starts = []
        start = 0
        for width in widths:
            starts.append(start)
            start += width + self._dividechars
        return starts

    @staticmethod
    def _bar_offset(starts: Sequence[int], widths: Sequence[int], maxcol: int, target: int) -> int:
        """Return the first bar column shown in *maxcol* columns, keeping label *target* visible.

        The label is centred, or shown from its first column when it is wider than the bar.
        The result depends only on the arguments, so a render and a later click at one width agree.
        """
        total = starts[-1] + widths[-1]
        if total <= maxcol or maxcol == 0:
            return 0
        start, width = starts[target], widths[target]
        offset = start + width // 2 - maxcol // 2 if width <= maxcol else start
        return max(0, min(offset, total - maxcol))

    def _render_bar(self, maxcol: int, focus: bool) -> Canvas:
        """Render the one-row label bar *maxcol* columns wide.

        The only cursor it carries is the bar cursor, while the bar has the focus.
        """
        if not maxcol:
            return SolidCanvas(" ", 0, 1)
        selected = self.focus_position
        cursor = self._bar_cursor if focus and self._bar_focused else None
        canvases: list[Canvas] = []
        for index, (_body, label) in enumerate(self._contents):
            is_selected = index == selected
            canvas = CompositeCanvas(label.render((), focus=focus and is_selected))
            # a selectable label, such as a Button, supplies a cursor that must not replace the body's
            canvas.cursor = None
            if canvas.rows() != 1:
                canvas.pad_trim_top_bottom(0, 1 - canvas.rows())
            if index == cursor and self._focus_map is not None:
                canvas.fill_attr_apply(self._focus_map)
            elif is_selected and self._selected_map is not None:
                canvas.fill_attr_apply(self._selected_map)
            elif self._attr_map is not None:
                canvas.fill_attr_apply(self._attr_map)
            canvases.append(self._mark_unfocused_focus(canvas) if is_selected and not focus else canvas)

        widths = [canvas.cols() for canvas in canvases]
        starts = self._bar_starts(widths)
        last = len(canvases) - 1
        bar = CanvasJoin(
            (canvas, index, index == selected, width + (0 if index == last else self._dividechars))
            for index, (canvas, width) in enumerate(zip(canvases, widths, strict=True))
        )
        offset = self._bar_offset(starts, widths, maxcol, self._bar_target(focus))
        bar.pad_trim_left_right(-offset, maxcol - (bar.cols() - offset))
        if cursor is not None and 0 <= (col := starts[cursor] - offset) < maxcol:
            bar.cursor = (col, 0)
        else:
            bar.cursor = None
        return bar

    def _label_at(self, maxcol: int, col: int, focus: bool) -> int | None:
        """Return the index of the label drawn at bar column *col*, or ``None`` for a gap or outside the bar."""
        if not 0 <= col < maxcol:
            return None
        widths = [label.pack(())[0] for _body, label in self._contents]
        starts = self._bar_starts(widths)
        bar_col = col + self._bar_offset(starts, widths, maxcol, self._bar_target(focus))
        for index, (start, width) in enumerate(zip(starts, widths, strict=True)):
            if start <= bar_col < start + width:
                return index
        return None

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the bar row plus the rows of the selected body.

        It is 0 when there are no tabs.

        :raises TabsError: the selected body is not a flow widget.
        """
        if not self._contents:
            return 0
        _bar_row, _body_top, _body_size, body_rows = self._geometry(size, focus)
        return body_rows + 1

    def render(self, size: tuple[()] | tuple[int] | tuple[int, int], focus: bool = False) -> Canvas:
        """Render the bar and the selected body.

        :raises TabsError: *size* is ``()``, or a flow size and the selected body is not a flow widget.
        """
        if not self._contents:
            # nothing to draw, so an empty widget renders at any size, () included
            return SolidCanvas(" ", (*size, 0)[0], (*size[1:], 0)[0])
        bar_row, _body_top, body_size, body_rows = self._geometry(size, focus)
        maxcol = body_size[0]
        if bar_row is None:
            return SolidCanvas(" ", maxcol, 0)
        bar_focused = focus and self._bar_focused
        parts: list[tuple[Canvas, int | None, bool]] = [(self._render_bar(maxcol, focus), None, bar_focused)]
        if body_rows:
            body = self._contents[self.focus_position][0]
            body_canvas = CompositeCanvas(body.render(body_size, focus=focus and not self._bar_focused))
            if body_canvas.rows() != body_rows:
                # trimming also drops a cursor on the rows cut away
                body_canvas.pad_trim_top_bottom(0, body_rows - body_canvas.rows())
            parts.append((body_canvas, self.focus_position, not bar_focused))
        if self._bar_position == VAlign.BOTTOM:
            parts.reverse()
        return CanvasCombine(parts)

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the bar cursor while the bar has the focus, else the cursor of the selected body if it is shown.

        :raises TabsError: *size* is ``()``, or a flow size and the selected body is not a flow widget.
        """
        if not self.selectable():
            return None
        bar_row, body_top, body_size, body_rows = self._geometry(size, True)
        if self._bar_focused:
            if bar_row is None:
                return None
            canvas = self._render_bar(body_size[0], True)
            return None if (cursor := canvas.cursor) is None else (cursor[0], bar_row)
        body = self._contents[self.focus_position][0]
        if not body_rows or (get_cursor_coords := getattr(body, "get_cursor_coords", None)) is None:
            return None
        if (coords := get_cursor_coords(body_size)) is None:
            return None
        x, y = coords
        if y >= body_rows:
            return None
        return x, y + body_top

    def _select(self, position: int) -> None:
        """Select the tab at *position* and put the bar cursor on it."""
        # The cursor moves first: a "focus changed" handler may remove tabs, and _contents_modified then clamps it.
        self._bar_cursor = position
        self.focus_position = position
        self._invalidate()

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the key to the selected body, or to the bar while it has the focus.

        A body with no rows shown gets no keys.
        The tab commands switch tabs when neither the bar nor the body used the key.
        "Towards the bar" is ``'cursor up'`` for a top bar and ``'cursor down'`` for a bottom bar.

        ::

            no tabs -> return key
            bar focused?
            +- yes: left/right -> move the bar cursor; at an edge return key
            |       activate -> select the tab under the bar cursor
            |       towards the body, body selectable and shown -> focus the body
            |       anything else -> tab commands below
            +- no:  body selectable and shown -> body.keypress(); handled -> done
                    towards the bar and the bar can take the focus -> focus the bar on the selected tab
                    anything else -> tab commands below
            tab commands, two or more tabs -> select the neighbour, wrapping around
            otherwise -> return key

        :raises TabsError: *size* is ``()``, or a flow size and the selected body is not a flow widget.
        """
        if not self._contents:
            return key
        _bar_row, _body_top, body_size, body_rows = self._geometry(size, True)
        command = self._command_map[key]
        top = self._bar_position == VAlign.TOP
        toward_body, toward_bar = (Command.DOWN, Command.UP) if top else (Command.UP, Command.DOWN)
        body = self._contents[self.focus_position][0]

        if self._bar_focused:
            if command in {Command.LEFT, Command.RIGHT}:
                cursor = self._bar_cursor + (1 if command == Command.RIGHT else -1)
                if not 0 <= cursor < len(self._contents):
                    return key
                self._bar_cursor = cursor
                self._invalidate()
                return None
            if command == Command.ACTIVATE:
                self.focus_position = self._bar_cursor
                return None
            if command == toward_body and body.selectable() and body_rows:
                self._bar_focused = False
                self._invalidate()
                return None
        else:
            if body.selectable() and body_rows:
                if (returned := body.keypress(body_size, key)) is None:
                    return None
                key = returned
                command = self._command_map[key]
            if command == toward_bar and self._bar_can_focus():
                self._bar_focused = True
                self._bar_cursor = self.focus_position
                self._invalidate()
                return None

        # the body may have changed the contents while handling the key
        if command in {Command.NEXT_TAB, Command.PREVIOUS_TAB} and len(self._contents) > 1:
            step = 1 if command == Command.NEXT_TAB else -1
            self._select((self.focus_position + step) % len(self._contents))
            return None
        return key

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Handle a mouse event on the bar or on the body.

        A button 1 press on a label selects its tab, and events on the body rows go to the body.

        With a selectable bar the press also moves the keyboard focus to the bar.
        A press on the body while the bar has the focus returns the focus to the body.

        :raises TabsError: *size* is ``()``, or a flow size and the selected body is not a flow widget.
        """
        if not self._contents:
            return False
        bar_row, body_top, body_size, body_rows = self._geometry(size, focus)
        if row == bar_row:
            if button != 1 or not is_mouse_press(event):
                return False
            if (index := self._label_at(body_size[0], col, focus)) is None:
                return False
            if self._bar_can_focus():
                # before the selection, whose "focus changed" handler may remove tabs, as in _select()
                self._bar_focused = True
                self._bar_cursor = index
                self._invalidate()
            self.focus_position = index
            return True
        if not body_top <= row < body_top + body_rows:
            return False
        body = self._contents[self.focus_position][0]
        if is_mouse_press(event) and button == 1 and self._bar_focused and body.selectable():
            self._bar_focused = False
            self._invalidate()
        return body.mouse_event(body_size, event, button, col, row - body_top, focus and not self._bar_focused)

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Put the keyboard focus on the selected body, or on the bar when the body is not selectable.

        It is the entry hook a parent container calls when it moves its focus here.

        :param reverse: passed to the body's own entry hook.
        """
        if (body := self.focus) is None:
            return
        if body.selectable():
            if self._bar_focused:
                self._bar_focused = False
                self._invalidate()
            _select_enter_child(body, reverse=reverse)
        elif self._bar_can_focus() and not self._bar_focused:
            self._bar_focused = True
            self._bar_cursor = self.focus_position
            self._invalidate()
