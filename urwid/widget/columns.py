from __future__ import annotations

import typing
import warnings
from itertools import chain, repeat

from urwid.canvas import Canvas, CanvasJoin, CompositeCanvas, SolidCanvas
from urwid.monitored_list import MonitoredFocusList, MonitoredList
from urwid.util import is_mouse_press

from .constants import Align, Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin, _ContainerElementSizingFlag
from .widget import Widget, WidgetError, WidgetWarning

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, MutableSequence, Sequence

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

        FIXED can be only if no BOX and no strict FLOW.

        >>> from urwid import BigText, Edit, SolidFill, Text, Thin3x3Font
        >>> font = Thin3x3Font()

        # BOX-only widget
        >>> Columns((SolidFill("#"),))
        <Columns box widget>

        # BOX-only widget with "get height from max"
        >>> Columns((SolidFill("#"),), box_columns=(0,))
        <Columns box widget>

        # FLOW-only
        >>> Columns((Edit(),))
        <Columns selectable flow widget>

        # BOX-only enforced by BOX-only widget
        >>> Columns((Edit(), SolidFill("#")))
        <Columns selectable box widget>

        # BOX/FLOW allowed by "box_columns"
        >>> Columns((Edit(), SolidFill("#")), box_columns=(1,))
        <Columns selectable box/flow widget>

        # Corner case: BOX only
        >>> Columns((Edit(), SolidFill("#"), SolidFill("#")), box_columns=(1,))
        <Columns selectable box widget>

        # FLOW/FIXED
        >>> Columns((Text("T"),))
        <Columns fixed/flow widget>

        # GIVEN BOX only -> BOX only
        >>> Columns(((5, SolidFill("#")),), box_columns=(0,))
        <Columns box widget>

        # No FLOW - BOX only
        >>> Columns(((5, SolidFill("#")), SolidFill("*")), box_columns=(0, 1))
        <Columns box widget>

        # We can everything: GIVEN BOX + FLOW/FIXED
        >>> Columns(((5, SolidFill("#")), (3, Text("T"))), box_columns=(0,))
        <Columns widget>

        # FIXED only -> FIXED
        >>> Columns(((WHSettings.PACK, BigText("1", font)),))
        <Columns fixed widget>

        # Invalid sizing combination -> use fallback settings (and produce warning)
        >>> Columns(((WHSettings.PACK, SolidFill("#")),))
        <Columns box/flow widget>
        """
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

        for idx, (widget, (size_kind, _size_weight, is_box)) in enumerate(self.contents):
            w_sizing = widget.sizing()

            flag = _ContainerElementSizingFlag.NONE

            if size_kind == WHSettings.WEIGHT:
                flag |= _ContainerElementSizingFlag.WH_WEIGHT
                if Sizing.BOX in w_sizing:
                    flag |= _ContainerElementSizingFlag.BOX
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW
                if Sizing.FIXED in w_sizing:
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
                    f"Sizing combination of widget {idx} not supported: "
                    f"{size_kind.name} {'|'.join(w_sizing).upper()} and box={is_box}",
                    ColumnsWarning,
                    stacklevel=3,
                )
                return frozenset((Sizing.BOX, Sizing.FLOW))

            if flag & _ContainerElementSizingFlag.BOX:
                supported.add(Sizing.BOX)
            if not (is_box or flag & flow_fixed):
                strict_box = True
                break

            if flag & _ContainerElementSizingFlag.FLOW:
                has_flow = True
            if flag & _ContainerElementSizingFlag.FIXED:
                has_fixed = True
            elif flag & given_box != given_box:
                block_fixed = True

        if not strict_box:
            if has_flow:
                supported.add(Sizing.FLOW)

            if has_fixed and not block_fixed:
                supported.add(Sizing.FIXED)

        return frozenset(supported)

    def __init__(
        self,
        widget_list: Iterable[
            Widget
            | tuple[Literal["pack", WHSettings.PACK] | int, Widget]
            | tuple[Literal["weight", "given", WHSettings.WEIGHT, WHSettings.GIVEN], int, Widget]
        ],
        dividechars: int = 0,
        focus_column: int | None = None,
        min_width: int = 1,
        box_columns: Iterable[int] | None = None,
    ):
        """
        :param widget_list: iterable of flow or box widgets
        :param dividechars: number of blank characters between columns
        :param focus_column: index into widget_list of column in focus,
            if ``None`` the first selectable widget will be chosen.
        :param min_width: minimum width for each column which is not
            calling widget.pack() in *widget_list*.
        :param box_columns: a list of column indexes containing box widgets
            whose height is set to the maximum of the rows
            required by columns not listed in *box_columns*.

        *widget_list* may also contain tuples such as:

        (*given_width*, *widget*)
            make this column *given_width* screen columns wide, where *given_width*
            is an int
        (``'pack'``, *widget*)
            call :meth:`pack() <Widget.pack>` to calculate the width of this column
        (``'weight'``, *weight*, *widget*)
            give this column a relative *weight* (number) to calculate its width from the
            screen columns remaining

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
        super().__init__()
        self._contents = MonitoredFocusList()
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
            if focus_column is None and w.selectable():
                focus_column = i

        self.dividechars = dividechars

        if self.contents and focus_column is not None:
            self.focus_position = focus_column
        self.pref_col = None
        self.min_width = min_width
        self._cache_maxcol = None

    def _contents_modified(self) -> None:
        """
        Recalculate whether this widget should be selectable whenever the
        contents has been changed.
        """
        self._selectable = any(w.selectable() for w, o in self.contents)
        self._invalidate()

    def _validate_contents_modified(self, slc, new_items) -> None:
        for item in new_items:
            try:
                _w, (t, _n, _b) = item
                if t not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT}:
                    raise ColumnsError(f"added content invalid {item!r}")
            except (TypeError, ValueError) as exc:  # noqa: PERF203
                raise ColumnsError(f"added content invalid {item!r}").with_traceback(exc.__traceback__) from exc

    @property
    def widget_list(self) -> MonitoredList:
        """
        A list of the widgets in this Columns

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container `contents`",
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
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container `contents`",
            PendingDeprecationWarning,
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
            "You should use the new standard container property .contents to modify Pile contents.",
            PendingDeprecationWarning,
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
            "You should use the new standard container property .contents to modify Pile contents.",
            PendingDeprecationWarning,
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
            "only for backwards compatibility.You should use the new standard container property `contents`",
            PendingDeprecationWarning,
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
            "only for backwards compatibility.You should use the new standard container property `contents`",
            PendingDeprecationWarning,
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
            ".has_flow_type is deprecated, read values from .contents instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return WHSettings.PACK in self.column_types

    @has_flow_type.setter
    def has_flow_type(self, value):
        warnings.warn(
            ".has_flow_type is deprecated, read values from .contents instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def contents(
        self,
    ) -> MutableSequence[
        Widget,
        tuple[Literal[WHSettings.PACK], None, bool] | tuple[Literal[WHSettings.GIVEN, WHSettings.WEIGHT], int, bool],
    ]:
        """
        The contents of this Columns as a list of `(widget, options)` tuples.
        This list may be modified like a normal list and the Columns
        widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method
        """
        return self._contents

    @contents.setter
    def contents(self, c):
        self._contents[:] = c

    @staticmethod
    def options(
        width_type: (
            Literal["pack", "given", "weight", WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT]
        ) = WHSettings.WEIGHT,
        width_amount: int | None = 1,
        box_widget: bool = False,
    ) -> tuple[Literal[WHSettings.PACK], None, bool] | tuple[Literal[WHSettings.GIVEN, WHSettings.WEIGHT], int, bool]:
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
            width_amount = None
        if width_type not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT}:
            raise ColumnsError(f"invalid width_type: {width_type!r}")
        return (WHSettings(width_type), width_amount, box_widget)

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
            "only for backwards compatibility.You may also use the new standard container property `focus_position`",
            PendingDeprecationWarning,
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
            "only for backwards compatibility.You may also use the new standard container property `focus_position`",
            PendingDeprecationWarning,
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
            "You may also use the new standard container property `focus_position` to get the focus.",
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

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus` to get the focus.
        """
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus` to get the focus.",
            PendingDeprecationWarning,
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

    def _get_focus_position(self) -> int | None:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus_position` is deprecated, "
            f"please use `{self.__class__.__name__}.focus_position` property",
            DeprecationWarning,
            stacklevel=3,
        )
        if not self.contents:
            raise IndexError("No focus_position, Columns is empty")
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
            "You may also use the new standard container property `focus_position` to get the focus.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.focus_position

    @focus_col.setter
    def focus_col(self, new_position) -> None:
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus_position` to get the focus.",
            PendingDeprecationWarning,
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
                w_sizing = w.sizing()
                if Sizing.FLOW in w_sizing:
                    # FIXME: should be able to pack with a different maxcol value
                    w_size = (maxcol,)
                elif Sizing.FIXED in w_sizing:
                    w_size = ()
                else:
                    warnings.warn(
                        f"Unusual widget {i} sizing {w_sizing} for {t} (box={b}). "
                        f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for width calculation",
                        ColumnsWarning,
                        stacklevel=3,
                    )
                    w_size = (maxcol,)
                static_w = w.pack(w_size, focus and i == self.focus_position)[0]
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
                    raise ColumnsError(f"Unsupported combination of {size_kind}, {w_sizing} and box={is_box!r}")

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

            elif Sizing.FIXED in w_sizing and (Sizing.FLOW in w_sizing or is_box):
                width, height = widget.pack()
                weighted.setdefault(size_weight, []).append((widget, i, is_box, focused))
                weights.append(size_weight)
                weight_max_sizes.setdefault(size_weight, width)
                weight_max_sizes[size_weight] = max(weight_max_sizes[size_weight], width)

            else:
                raise ColumnsError(f"Unsupported combination of {size_kind}, {w_sizing}, box={is_box!r}")

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
            w_sizing = widget.sizing()

            if size_kind == WHSettings.GIVEN:
                if is_box:
                    box.append(i)
                elif Sizing.FLOW in w_sizing and not is_box:
                    heights[i] = widget.rows((width,), focus and i == self.focus_position)
                    w_h_args[i] = (width,)
                else:
                    box_need_height.append(i)

            elif size_kind == WHSettings.PACK:
                if Sizing.FLOW in w_sizing:
                    heights[i] = widget.rows((width,), focus and i == self.focus_position)
                    w_h_args[i] = (width,)
                else:
                    heights[i] = widget.pack((), focus and i == self.focus_position)[1]
                    w_h_args[i] = ()

            elif is_box:
                box.append(i)

            elif Sizing.FLOW in w_sizing:
                heights[i] = widget.rows((width,), focus and i == self.focus_position)
                w_h_args[i] = (width,)

            else:
                box_need_height.append(i)

        if len(size) == 1:
            if heights:
                max_height = max(heights.values())
                if box_need_height:
                    raise ColumnsError(f'Widgets in columns {box_need_height} are BOX widgets not marked "box_columns"')
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

    def pack(self, size: tuple[()] | tuple[int] | tuple[int, int], focus: bool = False) -> tuple[int, int]:
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
                return SolidCanvas(" ", size[0], (size[1:] + (1,))[0])
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

        coords = w.get_cursor_coords(size_args[self.focus_position])
        if coords is None:
            return None

        x, y = coords
        x += sum(self.dividechars + wc for wc in widths[: self.focus_position] if wc > 0)
        return x, y

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
        widths, _, size_args = self.get_column_sizes(size, focus=True)

        best = None
        x = 0
        for i, (width, (w, options)) in enumerate(zip(widths, self.contents)):
            end = x + width
            if w.selectable():
                if col != Align.RIGHT and (col == Align.LEFT or x > col) and best is None:
                    # no other choice
                    best = i, x, end, w, options
                    break
                if col != Align.RIGHT and x > col and col - best[2] < x - col:
                    # choose one on left
                    break
                best = i, x, end, w, options
                if col != Align.RIGHT and col < end:
                    # choose this one
                    break
            x = end + self.dividechars

        if best is None:
            return False
        i, x, end, w, (_t, _n, b) = best
        if hasattr(w, "move_cursor_to_coords"):
            if isinstance(col, int):
                move_x = min(max(0, col - x), end - x - 1)
            else:
                move_x = col
            rval = w.move_cursor_to_coords(size_args[i], move_x, row)
            if rval is False:
                return False

        self.focus_position = i
        self.pref_col = col
        return True

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event,
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

    def rows(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> int:
        """
        Return the number of rows required by the columns.
        This only makes sense if :attr:`widget_list` contains flow widgets.

        see :meth:`Widget.rows` for details
        """
        widths = self.column_widths(size, focus)

        rows = 1
        for i, (mc, (w, (_t, _n, b))) in enumerate(zip(widths, self.contents)):
            if b:
                continue
            rows = max(rows, w.rows((mc,), focus=focus and self.focus_position == i))
        return rows

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """
        Pass keypress to the focus column.

        :param size: `(maxcol,)` if :attr:`widget_list` contains flow widgets or
            `(maxcol, maxrow)` if it contains box widgets.
        :type size: int, int
        """
        if self.focus_position is None:
            return key

        widths, _, size_args = self.get_column_sizes(size, focus=True)
        if self.focus_position >= len(widths):
            return key

        i = self.focus_position
        w, _ = self.contents[i]
        if self._command_map[key] not in {"cursor up", "cursor down", "cursor page up", "cursor page down"}:
            self.pref_col = None
        if w.selectable():
            key = w.keypress(size_args[i], key)

        if self._command_map[key] not in {"cursor left", "cursor right"}:
            return key

        if self._command_map[key] == "cursor left":
            candidates = list(range(i - 1, -1, -1))  # count backwards to 0
        else:  # key == 'right'
            candidates = list(range(i + 1, len(self.contents)))

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self.focus_position = j
            return None
        return key
