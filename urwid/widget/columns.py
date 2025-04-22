from __future__ import annotations

import typing
import warnings
from itertools import chain, repeat

import urwid
from urwid.canvas import Canvas, CanvasJoin, CompositeCanvas, SolidCanvas
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .constants import Align, Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin, _ContainerElementSizingFlag
from .monitored_list import MonitoredFocusList, MonitoredList
from .widget import Widget, WidgetError, WidgetWarning

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from typing_extensions import Literal


class ColumnsError(WidgetError):
    """Columns related errors."""


class ColumnsWarning(WidgetWarning):
    """Columns related warnings."""


class Columns(Widget, WidgetContainerMixin, WidgetContainerListContentsMixin):
    """
    Widgets arranged horizontally in columns from left to right
    """

    def sizing(self) -> frozenset[Sizing]:
        """Sizing supported by widget.

        :return: Calculated widget sizing
        :rtype: frozenset[Sizing]

        Due to the nature of container with mutable contents, this method cannot be cached.

        Rules:
        * WEIGHT BOX -> BOX
        * GIVEN BOX -> Can be included in FIXED and FLOW depends on the other columns
        * PACK BOX -> Unsupported
        * BOX-only widget without `box_columns` disallow FLOW render

        * WEIGHT FLOW -> FLOW
        * GIVEN FLOW -> FIXED (known width and widget knows its height) + FLOW (historic)
        * PACK FLOW -> FLOW (widget fit in provided size)

        * WEIGHT FIXED -> Need also FLOW or/and BOX to properly render due to width calculation
        * GIVEN FIXED -> Unsupported
        * PACK FIXED -> FIXED (widget knows its size)

        Backward compatibility rules:
        * GIVEN BOX -> Allow BOX

        BOX can be only if ALL widgets support BOX.
        FIXED can be only if no BOX without "box_columns" flag and no strict FLOW.

        >>> from urwid import BigText, Edit, SolidFill, Text, Thin3x3Font
        >>> font = Thin3x3Font()

        # BOX-only widget
        >>> Columns((SolidFill("#"),))
        <Columns box widget (1 item)>

        # BOX-only widget with "get height from max"
        >>> Columns((SolidFill("#"),), box_columns=(0,))
        <Columns box widget (1 item)>

        # FLOW-only
        >>> Columns((Edit(),))
        <Columns selectable flow widget (1 item)>

        # FLOW allowed by "box_columns"
        >>> Columns((Edit(), SolidFill("#")), box_columns=(1,))
        <Columns selectable flow widget (2 items) focus_column=0>

        # FLOW/FIXED
        >>> Columns((Text("T"),))
        <Columns fixed/flow widget (1 item)>

        # GIVEN BOX only -> BOX only
        >>> Columns(((5, SolidFill("#")),), box_columns=(0,))
        <Columns box widget (1 item)>

        # No FLOW - BOX only
        >>> Columns(((5, SolidFill("#")), SolidFill("*")), box_columns=(0, 1))
        <Columns box widget (2 items) focus_column=0>

        # FIXED only -> FIXED (and FLOW via drop/expand)
        >>> Columns(((WHSettings.PACK, BigText("1", font)),))
        <Columns fixed/flow widget (1 item)>

        # Invalid sizing combination -> use fallback settings (and produce warning)
        >>> Columns(((WHSettings.PACK, SolidFill("#")),))
        <Columns box/flow widget (1 item)>

        # Special case: empty columns widget sizing is impossible to calculate
        >>> Columns(())
        <Columns box/flow widget ()>
        """
        if not self.contents:
            return frozenset((urwid.BOX, urwid.FLOW))

        strict_box = False
        has_flow = False

        block_fixed = False
        has_fixed = False
        supported: set[Sizing] = set()

        box_flow_fixed = (
            _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
        )
        flow_fixed = _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
        given_box = _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.WH_GIVEN

        # This is a set of _ContainerElementSizingFlag ORed together.
        flags: set[int] = set()

        for idx, (widget, (size_kind, _size_weight, is_box)) in enumerate(self.contents):
            w_sizing = widget.sizing()

            flag = _ContainerElementSizingFlag.NONE

            if size_kind == WHSettings.WEIGHT:
                flag |= _ContainerElementSizingFlag.WH_WEIGHT
                if Sizing.BOX in w_sizing:
                    flag |= _ContainerElementSizingFlag.BOX
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW
                if Sizing.FIXED in w_sizing and w_sizing & {Sizing.BOX, Sizing.FLOW}:
                    flag |= _ContainerElementSizingFlag.FIXED

            elif size_kind == WHSettings.GIVEN:
                flag |= _ContainerElementSizingFlag.WH_GIVEN
                if Sizing.BOX in w_sizing:
                    flag |= _ContainerElementSizingFlag.BOX
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FIXED
                    flag |= _ContainerElementSizingFlag.FLOW

            else:
                flag |= _ContainerElementSizingFlag.WH_PACK
                if Sizing.FIXED in w_sizing:
                    flag |= _ContainerElementSizingFlag.FIXED
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW

            if not flag & box_flow_fixed:
                warnings.warn(
                    f"Sizing combination of widget {widget} (position={idx}) not supported: "
                    f"{size_kind.name} box={is_box}",
                    ColumnsWarning,
                    stacklevel=3,
                )
                return frozenset((Sizing.BOX, Sizing.FLOW))

            flags.add(flag)

            if flag & _ContainerElementSizingFlag.BOX and not (is_box or flag & flow_fixed):
                strict_box = True

            if flag & _ContainerElementSizingFlag.FLOW:
                has_flow = True
            if flag & _ContainerElementSizingFlag.FIXED:
                has_fixed = True
            elif flag & given_box != given_box:
                block_fixed = True

        if all(flag & _ContainerElementSizingFlag.BOX for flag in flags):
            # Only if ALL widgets can be rendered as BOX, widget can be rendered as BOX.
            # Hacky "BOX" render for FLOW-only is still present,
            # due to incorrected implementation can be used by downstream
            supported.add(Sizing.BOX)

        if not strict_box:
            if has_flow:
                supported.add(Sizing.FLOW)

            if has_fixed and not block_fixed:
                supported.add(Sizing.FLOW)
                supported.add(Sizing.FIXED)

        if not supported:
            warnings.warn(
                f"Columns widget contents flags not allow to determine supported render kind:\n"
                f"{', '.join(sorted(_ContainerElementSizingFlag.log_string(flag) for flag in flags))}\n"
                f"Using fallback hardcoded BOX|FLOW sizing kind.",
                ColumnsWarning,
                stacklevel=3,
            )
            return frozenset((Sizing.BOX, Sizing.FLOW))

        return frozenset(supported)

    def __init__(
        self,
        widget_list: Iterable[
            Widget
            | tuple[Literal["pack", WHSettings.PACK] | int, Widget]
            | tuple[Literal["given", WHSettings.GIVEN], int, Widget]
            | tuple[Literal["weight", WHSettings.WEIGHT], int | float, Widget]
        ],
        dividechars: int = 0,
        focus_column: int | Widget | None = None,
        min_width: int = 1,
        box_columns: Iterable[int] | None = None,
    ):
        """
        :param widget_list: iterable of flow or box widgets
        :param dividechars: number of blank characters between columns
        :param focus_column: index into widget_list of column in focus or focused widget instance,
            if ``None`` the first selectable widget will be chosen.
        :param min_width: minimum width for each column which is not
            calling widget.pack() in *widget_list*.
        :param box_columns: a list of column indexes containing box widgets
            whose height is set to the maximum of the rows
            required by columns not listed in *box_columns*.

        *widget_list* may also contain tuples such as:

        (*given_width*, *widget*)
            make this column *given_width* screen columns wide, where *given_width* is an int
        (``'pack'``, *widget*)
            call :meth:`pack() <Widget.pack>` to calculate the width of this column
        (``'weight'``, *weight*, *widget*)
            give this column a relative *weight* (number) to calculate its width from th screen columns remaining

        Widgets not in a tuple are the same as (``'weight'``, ``1``, *widget*)

        If the Columns widget is treated as a box widget then all children
        are treated as box widgets, and *box_columns* is ignored.

        If the Columns widget is treated as a flow widget then the rows
        are calculated as the largest rows() returned from all columns
        except the ones listed in *box_columns*.  The box widgets in
        *box_columns* will be displayed with this calculated number of rows,
        filling the full height.
        """
        self._selectable = False
        self._cache_column_widths: list[int] = []
        super().__init__()
        self._contents: MonitoredFocusList[
            tuple[
                Widget,
                tuple[Literal[WHSettings.PACK], None, bool]
                | tuple[Literal[WHSettings.GIVEN], int, bool]
                | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
            ],
        ] = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)

        box_columns = set(box_columns or ())

        for i, original in enumerate(widget_list):
            w = original
            if not isinstance(w, tuple):
                self.contents.append((w, (WHSettings.WEIGHT, 1, i in box_columns)))
            elif w[0] in {Sizing.FLOW, WHSettings.PACK}:  # 'pack' used to be called 'flow'
                _ignored, w = w
                self.contents.append((w, (WHSettings.PACK, None, i in box_columns)))
            elif len(w) == 2 or w[0] in {Sizing.FIXED, WHSettings.GIVEN}:  # backwards compatibility: FIXED -> GIVEN
                width, w = w[-2:]
                self.contents.append((w, (WHSettings.GIVEN, width, i in box_columns)))
            elif w[0] == WHSettings.WEIGHT:
                _ignored, width, w = w
                self.contents.append((w, (WHSettings.WEIGHT, width, i in box_columns)))
            else:
                raise ColumnsError(f"initial widget list item invalid: {original!r}")
            if focus_column == w or (focus_column is None and w.selectable()):
                focus_column = i

            if not isinstance(w, Widget):
                warnings.warn(f"{w!r} is not a Widget", ColumnsWarning, stacklevel=3)

        self.dividechars = dividechars

        if self.contents and focus_column is not None:
            self.focus_position = focus_column
        self.pref_col = None
        self.min_width = min_width
        self._cache_maxcol = None

    def _repr_words(self) -> list[str]:
        if len(self.contents) > 1:
            contents_string = f"({len(self.contents)} items)"
        elif self.contents:
            contents_string = "(1 item)"
        else:
            contents_string = "()"
        return [*super()._repr_words(), contents_string]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "dividechars": self.dividechars,
            "focus_column": self.focus_position if len(self._contents) > 1 else None,
            "min_width": self.min_width,
        }
        return remove_defaults(attrs, Columns.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        widget_list: list[
            Widget
            | tuple[Literal[WHSettings.PACK] | int, Widget]
            | tuple[Literal[WHSettings.WEIGHT], int | float, Widget]
        ] = []
        box_columns: list[int] = []
        for idx, (w_instance, (sizing, amount, is_box)) in enumerate(self._contents):
            if sizing == WHSettings.GIVEN:
                widget_list.append((amount, w_instance))
            elif sizing == WHSettings.PACK:
                widget_list.append((WHSettings.PACK, w_instance))
            elif amount == 1:
                widget_list.append(w_instance)
            else:
                widget_list.append((WHSettings.WEIGHT, amount, w_instance))

            if is_box:
                box_columns.append(idx)

        yield "widget_list", widget_list
        yield "dividechars", self.dividechars
        yield "focus_column", self.focus_position if self._contents else None
        yield "min_width", self.min_width
        yield "box_columns", box_columns

    def __len__(self) -> int:
        return len(self._contents)

    def _contents_modified(self) -> None:
        """
        Recalculate whether this widget should be selectable whenever the
        contents has been changed.
        """
        self._selectable = any(w.selectable() for w, o in self.contents)
        self._invalidate()

    def _validate_contents_modified(self, slc, new_items) -> None:
        invalid_items: list[tuple[Widget, tuple[typing.Any, typing.Any, typing.Any]]] = []
        try:
            for item in new_items:
                _w, (t, n, b) = item
                if any(
                    (
                        t not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT},
                        (n is not None and (not isinstance(n, (int, float)) or n < 0)),
                        not isinstance(b, bool),
                    )
                ):
                    invalid_items.append(item)
        except (TypeError, ValueError) as exc:
            raise ColumnsError(f"added content invalid {exc}").with_traceback(exc.__traceback__) from exc

        if invalid_items:
            raise ColumnsError(f"added content invalid: {invalid_items!r}")

    @property
    def widget_list(self) -> MonitoredList:
        """
        A list of the widgets in this Columns

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(w for w, t in self.contents)

        def user_modified():
            self.widget_list = ml

        ml.set_modified_callback(user_modified)
        return ml

    @widget_list.setter
    def widget_list(self, widgets):
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        focus_position = self.focus_position
        self.contents = [
            # need to grow contents list if widgets is longer
            (new, options)
            for (new, (w, options)) in zip(
                widgets,
                chain(self.contents, repeat((None, (WHSettings.WEIGHT, 1, False)))),
            )
        ]
        if focus_position < len(widgets):
            self.focus_position = focus_position

    @property
    def column_types(self) -> MonitoredList:
        """
        A list of the old partial options values for widgets in this Pile,
        for backwards compatibility only.  You should use the new standard
        container property .contents to modify Pile contents.
        """
        warnings.warn(
            "for backwards compatibility only."
            "You should use the new standard container property .contents to modify Pile contents."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(
            # return the old column type names
            ({WHSettings.GIVEN: Sizing.FIXED, WHSettings.PACK: Sizing.FLOW}.get(t, t), n)
            for w, (t, n, b) in self.contents
        )

        def user_modified():
            self.column_types = ml

        ml.set_modified_callback(user_modified)
        return ml

    @column_types.setter
    def column_types(self, column_types):
        warnings.warn(
            "for backwards compatibility only."
            "You should use the new standard container property .contents to modify Pile contents."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        focus_position = self.focus_position
        self.contents = [
            (w, ({Sizing.FIXED: WHSettings.GIVEN, Sizing.FLOW: WHSettings.PACK}.get(new_t, new_t), new_n, b))
            for ((new_t, new_n), (w, (t, n, b))) in zip(column_types, self.contents)
        ]
        if focus_position < len(column_types):
            self.focus_position = focus_position

    @property
    def box_columns(self) -> MonitoredList:
        """
        A list of the indexes of the columns that are to be treated as
        box widgets when the Columns is treated as a flow widget.

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility.You should use the new standard container property `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(i for i, (w, (t, n, b)) in enumerate(self.contents) if b)

        def user_modified():
            self.box_columns = ml

        ml.set_modified_callback(user_modified)
        return ml

    @box_columns.setter
    def box_columns(self, box_columns):
        warnings.warn(
            "only for backwards compatibility.You should use the new standard container property `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        box_columns = set(box_columns)
        self.contents = [(w, (t, n, i in box_columns)) for (i, (w, (t, n, b))) in enumerate(self.contents)]

    @property
    def has_flow_type(self) -> bool:
        """
        .. deprecated:: 1.0 Read values from :attr:`contents` instead.
        """
        warnings.warn(
            ".has_flow_type is deprecated, read values from .contents instead. API will be removed in version 4.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return WHSettings.PACK in self.column_types

    @has_flow_type.setter
    def has_flow_type(self, value):
        warnings.warn(
            ".has_flow_type is deprecated, read values from .contents instead. API will be removed in version 4.0.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def contents(
        self,
    ) -> MonitoredFocusList[
        tuple[
            Widget,
            tuple[Literal[WHSettings.PACK], None, bool]
            | tuple[Literal[WHSettings.GIVEN], int, bool]
            | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
        ],
    ]:
        """
        The contents of this Columns as a list of `(widget, options)` tuples.
        This list may be modified like a normal list and the Columns
        widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method
        """
        return self._contents

    @contents.setter
    def contents(
        self,
        c: Sequence[
            Widget,
            tuple[Literal[WHSettings.PACK], None, bool]
            | tuple[Literal[WHSettings.GIVEN], int, bool]
            | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
        ],
    ) -> None:
        self._contents[:] = c

    @staticmethod
    def options(
        width_type: Literal[
            "pack", "given", "weight", WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT
        ] = WHSettings.WEIGHT,
        width_amount: int | float | None = 1,  # noqa: PYI041  # provide explicit for IDEs
        box_widget: bool = False,
    ) -> (
        tuple[Literal[WHSettings.PACK], None, bool]
        | tuple[Literal[WHSettings.GIVEN], int, bool]
        | tuple[Literal[WHSettings.WEIGHT], int | float, bool]
    ):
        """
        Return a new options tuple for use in a Pile's .contents list.

        This sets an entry's width type: one of the following:

        ``'pack'``
            Call the widget's :meth:`Widget.pack` method to determine how wide
            this column should be. *width_amount* is ignored.
        ``'given'``
            Make column exactly width_amount screen-columns wide.
        ``'weight'``
            Allocate the remaining space to this column by using
            *width_amount* as a weight value.

        :param width_type: ``'pack'``, ``'given'`` or ``'weight'``
        :param width_amount: ``None`` for ``'pack'``, a number of screen columns
            for ``'given'`` or a weight value (number) for ``'weight'``
        :param box_widget: set to `True` if this widget is to be treated as a box
            widget when the Columns widget itself is treated as a flow widget.
        :type box_widget: bool
        """
        if width_type == WHSettings.PACK:
            return (WHSettings.PACK, None, box_widget)
        if width_type in {WHSettings.GIVEN, WHSettings.WEIGHT} and width_amount is not None:
            return (WHSettings(width_type), width_amount, box_widget)
        raise ColumnsError(f"invalid combination: width_type={width_type!r}, width_amount={width_amount!r}")

    def _invalidate(self) -> None:
        self._cache_maxcol = None
        super()._invalidate()

    def set_focus_column(self, num: int) -> None:
        """
        Set the column in focus by its index in :attr:`widget_list`.

        :param num: index of focus-to-be entry
        :type num: int

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus_position` to set the focus.
        """
        warnings.warn(
            "only for backwards compatibility.You may also use the new standard container property `focus_position`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.focus_position = num

    def get_focus_column(self) -> int:
        """
        Return the focus column index.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus_position` to get the focus.
        """
        warnings.warn(
            "only for backwards compatibility.You may also use the new standard container property `focus_position`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.focus_position

    def set_focus(self, item: Widget | int) -> None:
        """
        Set the item in focus

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus_position` to get the focus.

        :param item: widget or integer index"""
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus_position` to get the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if isinstance(item, int):
            self.focus_position = item
            return
        for i, (w, _options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in Columns contents: {item!r}")

    @property
    def focus(self) -> Widget | None:
        """
        the child widget in focus or None when Columns is empty

        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus` to get the focus.
        """
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus` to get the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @property
    def focus_position(self) -> int | None:
        """
        index of child widget in focus.
        Raises :exc:`IndexError` if read when Columns is empty, or when set to an invalid index.
        """
        if not self.contents:
            raise IndexError("No focus_position, Columns is empty")
        return self.contents.focus

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No Columns child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Columns child widget at position {position}").with_traceback(
                exc.__traceback__
            ) from exc
        self.contents.focus = position

    @property
    def focus_col(self):
        """
        A property for reading and setting the index of the column in
        focus.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus_position` to get the focus.
        """
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus_position` to get the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.focus_position

    @focus_col.setter
    def focus_col(self, new_position) -> None:
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus_position` to get the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.focus_position = new_position

    def column_widths(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> list[int]:
        """
        Return a list of column widths.

        0 values in the list means hide the corresponding column completely
        """
        maxcol = size[0]
        # FIXME: get rid of this check and recalculate only when a 'pack' widget has been modified.
        if maxcol == self._cache_maxcol and not any(t == WHSettings.PACK for w, (t, n, b) in self.contents):
            return self._cache_column_widths

        widths = []

        weighted = []
        shared = maxcol + self.dividechars

        for i, (w, (t, width, b)) in enumerate(self.contents):
            if t == WHSettings.GIVEN:
                static_w = width
            elif t == WHSettings.PACK:
                if isinstance(w, Widget):
                    w_sizing = w.sizing()
                else:
                    warnings.warn(f"{w!r} is not a Widget", ColumnsWarning, stacklevel=3)
                    w_sizing = frozenset((urwid.BOX, urwid.FLOW))

                if w_sizing & frozenset((Sizing.FIXED, Sizing.FLOW)):
                    candidate_size = 0

                    if Sizing.FIXED in w_sizing:
                        candidate_size = w.pack((), focus and i == self.focus_position)[0]

                    if Sizing.FLOW in w_sizing and (not candidate_size or candidate_size > maxcol):
                        # FIXME: should be able to pack with a different maxcol value
                        candidate_size = w.pack((maxcol,), focus and i == self.focus_position)[0]

                    static_w = candidate_size

                else:
                    warnings.warn(
                        f"Unusual widget {w} sizing for {t} (box={b}). "
                        f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for width calculation",
                        ColumnsWarning,
                        stacklevel=3,
                    )
                    static_w = w.pack((maxcol,), focus and i == self.focus_position)[0]

            else:
                static_w = self.min_width

            if shared < static_w + self.dividechars and i > self.focus_position:
                break

            widths.append(static_w)
            shared -= static_w + self.dividechars
            if t not in {WHSettings.GIVEN, WHSettings.PACK}:
                weighted.append((width, i))

        # drop columns on the left until we fit
        for i, width_ in enumerate(widths):
            if shared >= 0:
                break
            shared += width_ + self.dividechars
            widths[i] = 0
            if weighted and weighted[0][1] == i:
                del weighted[0]

        if shared:
            # divide up the remaining space between weighted cols
            wtotal = sum(weight for weight, i in weighted)
            grow = shared + len(weighted) * self.min_width
            for weight, i in sorted(weighted):
                width = max(int(grow * weight / wtotal + 0.5), self.min_width)

                widths[i] = width
                grow -= width
                wtotal -= weight

        self._cache_maxcol = maxcol
        self._cache_column_widths = widths
        return widths

    def _get_fixed_column_sizes(
        self,
        focus: bool = False,
    ) -> tuple[Sequence[int], Sequence[int], Sequence[tuple[int] | tuple[()]]]:
        """Get column widths, heights and render size parameters"""
        widths: dict[int, int] = {}
        heights: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}
        box: list[int] = []
        weighted: dict[int, list[tuple[Widget, int, bool, bool]]] = {}
        weights: list[int] = []
        weight_max_sizes: dict[int, int] = {}

        for i, (widget, (size_kind, size_weight, is_box)) in enumerate(self.contents):
            w_sizing = widget.sizing()
            focused = focus and i == self.focus_position

            if size_kind == WHSettings.GIVEN:
                widths[i] = size_weight
                if is_box:
                    box.append(i)
                elif Sizing.FLOW in w_sizing:
                    heights[i] = widget.rows((size_weight,), focused)
                    w_h_args[i] = (size_weight,)
                else:
                    raise ColumnsError(f"Unsupported combination of {size_kind} box={is_box!r} for {widget}")

            elif size_kind == WHSettings.PACK and Sizing.FIXED in w_sizing and not is_box:
                width, height = widget.pack((), focused)
                widths[i] = width
                heights[i] = height
                w_h_args[i] = ()

            elif size_weight <= 0:
                widths[i] = 0
                heights[i] = 1
                if is_box:
                    box.append(i)
                else:
                    w_h_args[i] = (0,)

            elif Sizing.FLOW in w_sizing or is_box:
                if Sizing.FIXED in w_sizing:
                    width, height = widget.pack((), focused)
                else:
                    width = self.min_width

                weighted.setdefault(size_weight, []).append((widget, i, is_box, focused))
                weights.append(size_weight)
                weight_max_sizes.setdefault(size_weight, width)
                weight_max_sizes[size_weight] = max(weight_max_sizes[size_weight], width)
            else:
                raise ColumnsError(f"Unsupported combination of {size_kind} box={is_box!r} for {widget}")

        if weight_max_sizes:
            max_weighted_coefficient = max(width / weight for weight, width in weight_max_sizes.items())

            for weight in weight_max_sizes:
                width = max(int(max_weighted_coefficient * weight + 0.5), self.min_width)
                for widget, i, is_box, focused in weighted[weight]:
                    widths[i] = width

                    if not is_box:
                        heights[i] = widget.rows((width,), focused)
                        w_h_args[i] = (width,)
                    else:
                        box.append(i)

        if not heights:
            raise ColumnsError(f"No height information for pack {self!r} as FIXED")

        max_height = max(heights.values())
        for idx in box:
            heights[idx] = max_height
            w_h_args[idx] = (widths[idx], max_height)

        return (
            tuple(widths[idx] for idx in range(len(widths))),
            tuple(heights[idx] for idx in range(len(heights))),
            tuple(w_h_args[idx] for idx in range(len(w_h_args))),
        )

    def get_column_sizes(
        self,
        size: tuple[int, int] | tuple[int] | tuple[()],
        focus: bool = False,
    ) -> tuple[Sequence[int], Sequence[int], Sequence[tuple[int, int] | tuple[int] | tuple[()]]]:
        """Get column widths, heights and render size parameters"""
        if not size:
            return self._get_fixed_column_sizes(focus=focus)

        widths = tuple(self.column_widths(size=size, focus=focus))
        heights: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}
        box: list[int] = []
        box_need_height: list[int] = []

        for i, (width, (widget, (size_kind, _size_weight, is_box))) in enumerate(zip(widths, self.contents)):
            if isinstance(widget, Widget):
                w_sizing = widget.sizing()
            else:
                warnings.warn(f"{widget!r} is not Widget.", ColumnsWarning, stacklevel=3)
                # This branch should be fully deleted later.
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            if len(size) == 2 and Sizing.BOX in w_sizing:
                heights[i] = size[1]
                w_h_args[i] = (width, size[1])

            elif is_box:
                box.append(i)

            elif Sizing.FLOW in w_sizing:
                if width > 0:
                    heights[i] = widget.rows((width,), focus and i == self.focus_position)
                else:
                    heights[i] = 0
                w_h_args[i] = (width,)

            elif size_kind == WHSettings.PACK:
                if width > 0:
                    heights[i] = widget.pack((), focus and i == self.focus_position)[1]
                else:
                    heights[i] = 0
                w_h_args[i] = ()

            else:
                box_need_height.append(i)

        if len(size) == 1:
            if heights:
                max_height = max(heights.values())
                if box_need_height:
                    warnings.warn(
                        f"Widgets in columns {box_need_height} "
                        f"({[self.contents[i][0] for i in box_need_height]}) "
                        f'are BOX widgets not marked "box_columns" while FLOW render is requested (size={size!r})',
                        ColumnsWarning,
                        stacklevel=3,
                    )
            else:
                max_height = 1
        else:
            max_height = size[1]

        for idx in (*box, *box_need_height):
            heights[idx] = max_height
            w_h_args[idx] = (widths[idx], max_height)

        return (
            widths,
            tuple(heights[idx] for idx in range(len(heights))),
            tuple(w_h_args[idx] for idx in range(len(w_h_args))),
        )

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Get packed sized for widget."""
        if size:
            return super().pack(size, focus)
        widths, heights, _ = self.get_column_sizes(size, focus)
        return (sum(widths) + self.dividechars * max(len(widths) - 1, 0), max(heights))

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> SolidCanvas | CompositeCanvas:
        """
        Render columns and return canvas.

        :param size: see :meth:`Widget.render` for details
        :param focus: ``True`` if this widget is in focus
        :type focus: bool
        """
        widths, _, size_args = self.get_column_sizes(size, focus)

        data: list[tuple[Canvas, int, bool, int]] = []
        for i, (width, w_size, (w, _)) in enumerate(zip(widths, size_args, self.contents)):
            # if the widget has a width of 0, hide it
            if width <= 0:
                continue

            if i < len(widths) - 1:
                width += self.dividechars  # noqa: PLW2901
            data.append(
                (
                    w.render(w_size, focus=focus and self.focus_position == i),
                    i,
                    self.focus_position == i,
                    width,
                )
            )

        if not data:
            if size:
                return SolidCanvas(" ", size[0], (*size[1:], 1)[0])
            raise ColumnsError("No data to render")

        canvas = CanvasJoin(data)
        if size and canvas.cols() < size[0]:
            canvas.pad_trim_left_right(0, size[0] - canvas.cols())
        return canvas

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates from the focus widget."""
        w, _ = self.contents[self.focus_position]

        if not w.selectable():
            return None
        if not hasattr(w, "get_cursor_coords"):
            return None

        widths, _, size_args = self.get_column_sizes(size, focus=True)
        if len(widths) <= self.focus_position:
            return None

        if (coords := w.get_cursor_coords(size_args[self.focus_position])) is not None:
            x, y = coords
            x += sum(self.dividechars + wc for wc in widths[: self.focus_position] if wc > 0)
            return x, y

        return None

    def move_cursor_to_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        col: int | Literal["left", "right"],
        row: int,
    ) -> bool:
        """
        Choose a selectable column to focus based on the coords.

        see :meth:`Widget.move_cursor_coords` for details
        """
        try:
            widths, _, size_args = self.get_column_sizes(size, focus=True)
        except Exception as exc:
            raise ValueError(self.contents, size, col, row) from exc

        best = None
        x = 0
        for i, (width, (w, _options)) in enumerate(zip(widths, self.contents)):
            end = x + width
            if w.selectable():
                if col != Align.RIGHT and (col == Align.LEFT or x > col) and best is None:
                    # no other choice
                    best = i, x, end, w
                    break
                if col != Align.RIGHT and x > col and col - best[2] < x - col:
                    # choose one on left
                    break
                best = i, x, end, w
                if col != Align.RIGHT and col < end:
                    # choose this one
                    break
            x = end + self.dividechars

        if best is None:
            return False
        i, x, end, w = best
        if hasattr(w, "move_cursor_to_coords"):
            if isinstance(col, int):
                move_x = min(max(0, col - x), end - x - 1)
            else:
                move_x = col

            if w.move_cursor_to_coords(size_args[i], move_x, row) is False:
                return False

        self.focus_position = i
        self.pref_col = col
        return True

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """
        Send event to appropriate column.
        May change focus on button 1 press.
        """
        widths, _, size_args = self.get_column_sizes(size, focus=focus)

        x = 0
        for i, (width, w_size, (w, _)) in enumerate(zip(widths, size_args, self.contents)):
            if col < x:
                return False
            w = self.contents[i][0]  # noqa: PLW2901
            end = x + width

            if col >= end:
                x = end + self.dividechars
                continue

            focus = focus and self.focus_position == i
            if is_mouse_press(event) and button == 1 and w.selectable():
                self.focus_position = i

            if not hasattr(w, "mouse_event"):
                warnings.warn(
                    f"{w.__class__.__module__}.{w.__class__.__name__} is not subclass of Widget",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return False

            return w.mouse_event(w_size, event, button, col - x, row, focus)
        return False

    def get_pref_col(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> int:
        """Return the pref col from the column in focus."""
        widths, _, size_args = self.get_column_sizes(size, focus=True)

        w, _ = self.contents[self.focus_position]
        if len(widths) <= self.focus_position:
            return 0
        col = None
        cwidth = widths[self.focus_position]

        if hasattr(w, "get_pref_col"):
            col = w.get_pref_col(size_args[self.focus_position])
            if isinstance(col, int):
                col += self.focus_position * self.dividechars
                col += sum(widths[: self.focus_position])
        if col is None:
            col = self.pref_col

        if col is None and w.selectable():
            col = cwidth // 2
            col += self.focus_position * self.dividechars
            col += sum(widths[: self.focus_position])
        return col

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the number of rows required by the columns.
        This only makes sense if :attr:`widget_list` contains flow widgets.

        see :meth:`Widget.rows` for details
        """
        _, heights, _ = self.get_column_sizes(size, focus)
        if heights:
            return max(1, *heights)
        return 1

    def keypress(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        key: str,
    ) -> str | None:
        """
        Pass keypress to the focus column.

        :param size: Widget size correct for the supported sizing
        :type size: tuple[()] | tuple[int] | tuple[int, int]
        :param key: a single keystroke value
        :type key: str
        """
        if self.focus_position is None:
            return key

        widths, _, size_args = self.get_column_sizes(size, focus=True)
        if self.focus_position >= len(widths):
            return key

        i = self.focus_position
        w, _ = self.contents[i]
        if self._command_map[key] not in {Command.UP, Command.DOWN, Command.PAGE_UP, Command.PAGE_DOWN}:
            self.pref_col = None
        if w.selectable():
            key = w.keypress(size_args[i], key)

        if self._command_map[key] not in {Command.LEFT, Command.RIGHT}:
            return key

        if self._command_map[key] == Command.LEFT:
            candidates = list(range(i - 1, -1, -1))  # count backwards to 0
        else:  # key == 'right'
            candidates = list(range(i + 1, len(self.contents)))

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self.focus_position = j
            return None
        return key
