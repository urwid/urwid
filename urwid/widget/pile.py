from __future__ import annotations

import typing
import warnings
from itertools import chain, repeat

from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.monitored_list import MonitoredFocusList, MonitoredList
from urwid.util import is_mouse_press

from .constants import Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin
from .widget import Widget

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Literal


class PileError(Exception):
    pass


class Pile(Widget, WidgetContainerMixin, WidgetContainerListContentsMixin):
    """
    A pile of widgets stacked vertically from top to bottom
    """

    _sizing = frozenset([Sizing.FLOW, Sizing.BOX])

    def __init__(
        self,
        widget_list: Iterable[
            Widget
            | tuple[Literal["pack", WHSettings.PACK] | int, Widget]
            | tuple[Literal["weight", WHSettings.WEIGHT], int, Widget]
        ],
        focus_item: Widget | int | None = None,
    ) -> None:
        """
        :param widget_list: child widgets
        :type widget_list: iterable
        :param focus_item: child widget that gets the focus initially.
            Chooses the first selectable widget if unset.
        :type focus_item: Widget or int

        *widget_list* may also contain tuples such as:

        (*given_height*, *widget*)
            always treat *widget* as a box widget and give it *given_height* rows,
            where given_height is an int
        (``'pack'``, *widget*)
            allow *widget* to calculate its own height by calling its :meth:`rows`
            method, ie. treat it as a flow widget.
        (``'weight'``, *weight*, *widget*)
            if the pile is treated as a box widget then treat widget as a box
            widget with a height based on its relative weight value, otherwise
            treat the same as (``'pack'``, *widget*).

        Widgets not in a tuple are the same as (``'weight'``, ``1``, *widget*)`

        .. note:: If the Pile is treated as a box widget there must be at least
            one ``'weight'`` tuple in :attr:`widget_list`.
        """
        self._selectable = False
        super().__init__()
        self._contents = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)

        for i, original in enumerate(widget_list):
            w = original
            if not isinstance(w, tuple):
                self.contents.append((w, (WHSettings.WEIGHT, 1)))
            elif w[0] in (Sizing.FLOW, WHSettings.PACK):
                f, w = w
                self.contents.append((w, (WHSettings.PACK, None)))
            elif len(w) == 2:
                height, w = w
                self.contents.append((w, (WHSettings.GIVEN, height)))
            elif w[0] == Sizing.FIXED:  # backwards compatibility
                _ignore, height, w = w
                self.contents.append((w, (WHSettings.GIVEN, height)))
            elif w[0] == WHSettings.WEIGHT:
                f, height, w = w
                self.contents.append((w, (f, height)))
            else:
                raise PileError(f"initial widget list item invalid {original!r}")
            if focus_item is None and w.selectable():
                focus_item = i

        if self.contents and focus_item is not None:
            self.focus = focus_item

        self.pref_col = 0

    def _contents_modified(self) -> None:
        """
        Recalculate whether this widget should be selectable whenever the
        contents has been changed.
        """
        self._selectable = any(w.selectable() for w, o in self.contents)
        self._invalidate()

    def _validate_contents_modified(self, slc, new_items):
        for item in new_items:
            try:
                w, (t, n) = item
                if t not in (WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT):
                    raise PileError(f"added content invalid: {item!r}")
            except (TypeError, ValueError) as exc:  # noqa: PERF203
                raise PileError(f"added content invalid: {item!r}").with_traceback(exc.__traceback__) from exc

    @property
    def widget_list(self):
        """
        A list of the widgets in this Pile

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container property `contents`",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(w for w, t in self.contents)

        def user_modified():
            self.widget_list = ml

        ml.set_modified_callback(user_modified)
        return ml

    @widget_list.setter
    def widget_list(self, widgets):
        focus_position = self.focus_position
        self.contents = [
            (new, options)
            for (new, (w, options)) in zip(
                widgets,
                # need to grow contents list if widgets is longer
                chain(self.contents, repeat((None, (WHSettings.WEIGHT, 1)))),
            )
        ]
        if focus_position < len(widgets):
            self.focus_position = focus_position

    @property
    def item_types(self):
        """
        A list of the options values for widgets in this Pile.

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container property `contents`",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(
            # return the old item type names
            ({WHSettings.GIVEN: Sizing.FIXED, WHSettings.PACK: Sizing.FLOW}.get(f, f), height)
            for w, (f, height) in self.contents
        )

        def user_modified():
            self.item_types = ml

        ml.set_modified_callback(user_modified)
        return ml

    @item_types.setter
    def item_types(self, item_types):
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container property `contents`",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        focus_position = self.focus_position
        self.contents = [
            (w, ({Sizing.FIXED: WHSettings.GIVEN, Sizing.FLOW: WHSettings.PACK}.get(new_t, new_t), new_height))
            for ((new_t, new_height), (w, options)) in zip(item_types, self.contents)
        ]
        if focus_position < len(item_types):
            self.focus_position = focus_position

    @property
    def contents(self):
        """
        The contents of this Pile as a list of (widget, options) tuples.

        options currently may be one of

        (``'pack'``, ``None``)
            allow widget to calculate its own height by calling its
            :meth:`rows <Widget.rows>` method, i.e. treat it as a flow widget.
        (``'given'``, *n*)
            Always treat widget as a box widget with a given height of *n* rows.
        (``'weight'``, *w*)
            If the Pile itself is treated as a box widget then
            the value *w* will be used as a relative weight for assigning rows
            to this box widget. If the Pile is being treated as a flow
            widget then this is the same as (``'pack'``, ``None``) and the *w*
            value is ignored.

        If the Pile itself is treated as a box widget then at least one
        widget must have a (``'weight'``, *w*) options value, or the Pile will
        not be able to grow to fill the required number of rows.

        This list may be modified like a normal list and the Pile widget
        will updated automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method
        """
        return self._contents

    @contents.setter
    def contents(self, c):
        self._contents[:] = c

    @staticmethod
    def options(
        height_type: Literal["pack", "given", "weight"] = WHSettings.WEIGHT,
        height_amount: int | None = 1,
    ) -> tuple[Literal["pack"], None] | tuple[Literal["given", "weight"], int]:
        """
        Return a new options tuple for use in a Pile's :attr:`contents` list.

        :param height_type: ``'pack'``, ``'given'`` or ``'weight'``
        :param height_amount: ``None`` for ``'pack'``, a number of rows for
            ``'fixed'`` or a weight value (number) for ``'weight'``
        """

        if height_type == WHSettings.PACK:
            return (WHSettings.PACK, None)
        if height_type not in (WHSettings.GIVEN, WHSettings.WEIGHT):
            raise PileError(f"invalid height_type: {height_type!r}")
        return (height_type, height_amount)

    @property
    def focus(self) -> Widget | None:
        """the child widget in focus or None when Pile is empty"""
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @focus.setter
    def focus(self, item: Widget | int) -> None:
        """
        Set the item in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`focus_position`.
            to set the position by integer index instead.

        :param item: element to focus
        :type item: Widget or int
        """
        if isinstance(item, int):
            self.focus_position = item
            return
        for i, (w, _options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in Pile contents: {item!r}")

    def _get_focus(self) -> Widget:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus` is deprecated, "
            f"please use `{self.__class__.__name__}.focus` property",
            DeprecationWarning,
            stacklevel=3,
        )
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    def get_focus(self) -> Widget | None:
        """
        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        warnings.warn(
            "for backwards compatibility."
            "You may also use the new standard container property .focus to get the child widget in focus.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    def set_focus(self, item: Widget | int) -> None:
        warnings.warn(
            "for backwards compatibility."
            "You may also use the new standard container property .focus to get the child widget in focus.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        if isinstance(item, int):
            self.focus_position = item
            return
        for i, (w, _options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in Pile contents: {item!r}")

    @property
    def focus_item(self):
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container properties "
            "`focus` and `focus_position` to get the child widget in focus or modify the focus position.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.focus

    @focus_item.setter
    def focus_item(self, new_item):
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container properties "
            "`focus` and `focus_position` to get the child widget in focus or modify the focus position.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.focus = new_item

    @property
    def focus_position(self) -> int:
        """
        index of child widget in focus.
        Raises :exc:`IndexError` if read when Pile is empty, or when set to an invalid index.
        """
        if not self.contents:
            raise IndexError("No focus_position, Pile is empty")
        return self.contents.focus

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No Pile child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Pile child widget at position {position}").with_traceback(exc.__traceback__) from exc
        self.contents.focus = position

    def _get_focus_position(self) -> int | None:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus_position` is deprecated, "
            f"please use `{self.__class__.__name__}.focus_position` property",
            DeprecationWarning,
            stacklevel=3,
        )
        if not self.contents:
            raise IndexError("No focus_position, Pile is empty")
        return self.contents.focus

    def _set_focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        warnings.warn(
            f"method `{self.__class__.__name__}._set_focus_position` is deprecated, "
            f"please use `{self.__class__.__name__}.focus_position` property",
            DeprecationWarning,
            stacklevel=3,
        )
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No Pile child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Pile child widget at position {position}").with_traceback(exc.__traceback__) from exc
        self.contents.focus = position

    def get_pref_col(self, size):
        """Return the preferred column for the cursor, or None."""
        if not self.selectable():
            return None
        self._update_pref_col_from_focus(size)
        return self.pref_col

    def get_item_size(
        self,
        size: tuple[int] | tuple[int, int],
        i: int,
        focus: bool,
        item_rows: list[int] | None = None,
    ) -> tuple[int] | tuple[int, int]:
        """
        Return a size appropriate for passing to self.contents[i][0].render
        """
        maxcol = size[0]
        w, (f, height) = self.contents[i]
        if f == WHSettings.GIVEN:
            return (maxcol, height)

        if f == WHSettings.WEIGHT and len(size) == 2:
            if not item_rows:
                item_rows = self.get_item_rows(size, focus)
            return (maxcol, item_rows[i])

        return (maxcol,)

    def get_item_rows(self, size: tuple[int] | tuple[int, int], focus: bool) -> list[int]:
        """
        Return a list of the number of rows used by each widget
        in self.contents
        """
        remaining = None
        maxcol = size[0]
        if len(size) == 2:
            remaining = size[1]

        rows_numbers = []

        if remaining is None:
            # pile is a flow widget
            for w, (f, height) in self.contents:
                if f == WHSettings.GIVEN:
                    rows_numbers.append(height)
                else:
                    rows_numbers.append(w.rows((maxcol,), focus=focus and self.focus == w))
            return rows_numbers

        # pile is a box widget
        # do an extra pass to calculate rows for each widget
        wtotal = 0
        for w, (f, height) in self.contents:
            if f == WHSettings.PACK:
                rows = w.rows((maxcol,), focus=focus and self.focus == w)
                rows_numbers.append(rows)
                remaining -= rows
            elif f == WHSettings.GIVEN:
                rows_numbers.append(height)
                remaining -= height
            elif height:
                rows_numbers.append(None)
                wtotal += height
            else:
                rows_numbers.append(0)  # zero-weighted items treated as ('given', 0)

        if wtotal == 0:
            raise PileError("No weighted widgets found for Pile treated as a box widget")

        if remaining < 0:
            remaining = 0

        for i, (_w, (_f, height)) in enumerate(self.contents):
            li = rows_numbers[i]
            if li is None:
                rows = int(float(remaining) * height / wtotal + 0.5)
                rows_numbers[i] = rows
                remaining -= rows
                wtotal -= height
        return rows_numbers

    def render(self, size, focus=False):
        maxcol = size[0]
        item_rows = None

        combinelist = []
        for i, (w, (f, height)) in enumerate(self.contents):
            item_focus = self.focus == w
            canv = None
            if f == WHSettings.GIVEN:
                canv = w.render((maxcol, height), focus=focus and item_focus)
            elif f == WHSettings.PACK or len(size) == 1:
                canv = w.render((maxcol,), focus=focus and item_focus)
            else:
                if item_rows is None:
                    item_rows = self.get_item_rows(size, focus)
                rows = item_rows[i]
                if rows > 0:
                    canv = w.render((maxcol, rows), focus=focus and item_focus)
            if canv:
                combinelist.append((canv, i, item_focus))
        if not combinelist:
            return SolidCanvas(" ", size[0], (size[1:] + (0,))[0])

        out = CanvasCombine(combinelist)
        if len(size) == 2 and size[1] != out.rows():
            # flow/fixed widgets rendered too large/small
            out = CompositeCanvas(out)
            out.pad_trim_top_bottom(0, size[1] - out.rows())
        return out

    def get_cursor_coords(self, size: tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focus widget."""
        if not self.selectable():
            return None
        if not hasattr(self.focus, "get_cursor_coords"):
            return None

        i = self.focus_position
        w, (f, height) = self.contents[i]
        item_rows = None
        maxcol = size[0]
        if f == WHSettings.GIVEN or (f == WHSettings.WEIGHT and len(size) == 2):
            if f == WHSettings.GIVEN:
                maxrow = height
            else:
                if item_rows is None:
                    item_rows = self.get_item_rows(size, focus=True)
                maxrow = item_rows[i]
            coords = self.focus.get_cursor_coords((maxcol, maxrow))
        else:
            coords = self.focus.get_cursor_coords((maxcol,))

        if coords is None:
            return None
        x, y = coords
        if i > 0:
            if item_rows is None:
                item_rows = self.get_item_rows(size, focus=True)
            for r in item_rows[:i]:
                y += r
        return x, y

    def rows(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> int:
        return sum(self.get_item_rows(size, focus))

    def keypress(self, size: tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the keypress to the widget in focus.
        Unhandled 'up' and 'down' keys may cause a focus change."""
        if not self.contents:
            return key

        item_rows = None
        if len(size) == 2:
            item_rows = self.get_item_rows(size, focus=True)

        i = self.focus_position
        if self.selectable():
            tsize = self.get_item_size(size, i, True, item_rows)
            key = self.focus.keypress(tsize, key)
            if self._command_map[key] not in ("cursor up", "cursor down"):
                return key

        if self._command_map[key] == "cursor up":
            candidates = list(range(i - 1, -1, -1))  # count backwards to 0
        else:  # self._command_map[key] == 'cursor down'
            candidates = list(range(i + 1, len(self.contents)))

        if not item_rows:
            item_rows = self.get_item_rows(size, focus=True)

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self._update_pref_col_from_focus(size)
            self.focus_position = j
            if not hasattr(self.focus, "move_cursor_to_coords"):
                return None

            rows = item_rows[j]
            if self._command_map[key] == "cursor up":
                rowlist = list(range(rows - 1, -1, -1))
            else:  # self._command_map[key] == 'cursor down'
                rowlist = list(range(rows))
            for row in rowlist:
                tsize = self.get_item_size(size, j, True, item_rows)
                if self.focus.move_cursor_to_coords(tsize, self.pref_col, row):
                    break
            return None

        # nothing to select
        return key

    def _update_pref_col_from_focus(self, size: tuple[int] | tuple[int, int]) -> None:
        """Update self.pref_col from the focus widget."""

        if not hasattr(self.focus, "get_pref_col"):
            return
        i = self.focus_position
        tsize = self.get_item_size(size, i, True)
        pref_col = self.focus.get_pref_col(tsize)
        if pref_col is not None:
            self.pref_col = pref_col

    def move_cursor_to_coords(self, size: tuple[int] | tuple[int, int], col: int, row: int) -> bool:
        """Capture pref col and set new focus."""
        self.pref_col = col

        # FIXME guessing focus==True
        focus = True
        wrow = 0
        item_rows = self.get_item_rows(size, focus)
        for i, (r, w) in enumerate(zip(item_rows, (w for (w, options) in self.contents))):  # noqa: B007
            if wrow + r > row:
                break
            wrow += r
        else:
            return False

        if not w.selectable():
            return False

        if hasattr(w, "move_cursor_to_coords"):
            tsize = self.get_item_size(size, i, focus, item_rows)
            rval = w.move_cursor_to_coords(tsize, col, row - wrow)
            if rval is False:
                return False

        self.focus_position = i
        return True

    def mouse_event(
        self,
        size: tuple[int] | tuple[int, int],
        event,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """
        Pass the event to the contained widget.
        May change focus on button 1 press.
        """
        wrow = 0
        item_rows = self.get_item_rows(size, focus)
        for i, (r, w) in enumerate(zip(item_rows, (w for (w, options) in self.contents))):  # noqa: B007
            if wrow + r > row:
                break
            wrow += r
        else:
            return False

        focus = focus and self.focus == w
        if is_mouse_press(event) and button == 1 and w.selectable():
            self.focus_position = i

        if not hasattr(w, "mouse_event"):
            return False

        tsize = self.get_item_size(size, i, focus, item_rows)
        return w.mouse_event(tsize, event, button, col, row - wrow, focus)
