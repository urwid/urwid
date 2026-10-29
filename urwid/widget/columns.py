"""Columns: a container that places widgets side by side."""

from __future__ import annotations

import functools
import math
import sys
import typing
import warnings
from typing import Literal

import urwid
from urwid import _deprecation
from urwid.canvas import Canvas, CanvasJoin, CompositeCanvas, SolidCanvas
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .constants import Align, Sizing, WHSettings
from .container import (
    _SELECT_COMMANDS,
    SelectNavigationListContentsMixin,
    _ContainerElementSizingFlag,
)
from .monitored_list import MonitoredFocusList
from .widget import (
    AbstractBoxWidget,
    AbstractFixedWidget,
    AbstractFlowWidget,
    AbstractWidget,
    Widget,
    WidgetError,
    WidgetWarning,
)

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator, Sequence


# Flag combinations tested on every element of every ``Columns.sizing()`` call, hoisted out of the loop
# so that the enum member lookups and the OR-ing happen once per import instead of once per element.
_BOX_FLOW_FIXED = _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
_FLOW_FIXED = _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
_GIVEN_BOX = _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.WH_GIVEN
_BOX_OR_FLOW = frozenset((Sizing.BOX, Sizing.FLOW))


class ColumnsError(WidgetError):
    """Columns related errors."""


class ColumnsWarning(WidgetWarning):
    """Columns related warnings."""


class Columns(
    Widget,
    SelectNavigationListContentsMixin[
        tuple[
            AbstractFlowWidget | AbstractFixedWidget,
            tuple[Literal[WHSettings.PACK], None, bool],
        ]
        | tuple[
            AbstractBoxWidget | AbstractFlowWidget,
            tuple[Literal[WHSettings.GIVEN], int, bool] | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
        ]
    ],
):
    """Widgets arranged horizontally in columns from left to right.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`contents`.
    Its handlers receive the container, the old and the new focus position, which is ``None`` while it is empty.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed"]

    def sizing(self) -> frozenset[Sizing]:
        """Sizing supported by widget.

        :returns: Calculated widget sizing
        :warns ColumnsWarning: a column's width type does not suit its widget's sizing,
            or no sizing fits all columns and the BOX/FLOW fallback is used.

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

        # This is a set of _ContainerElementSizingFlag ORed together.
        flags: set[int] = set()

        for idx, (widget, (size_kind, _size_weight, is_box)) in enumerate(self.contents):
            w_sizing = widget.sizing()

            flag: int = _ContainerElementSizingFlag.NONE

            if size_kind == WHSettings.WEIGHT:
                flag |= _ContainerElementSizingFlag.WH_WEIGHT
                if Sizing.BOX in w_sizing:
                    flag |= _ContainerElementSizingFlag.BOX
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW
                if Sizing.FIXED in w_sizing and w_sizing & _BOX_OR_FLOW:
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

            if not flag & _BOX_FLOW_FIXED:
                warnings.warn(
                    f"Sizing combination of widget {widget} (position={idx}) not supported: "
                    f"{size_kind.name} box={is_box}",
                    ColumnsWarning,
                    stacklevel=3,
                )
                return frozenset((Sizing.BOX, Sizing.FLOW))

            flags.add(flag)

            if flag & _ContainerElementSizingFlag.BOX and not (is_box or flag & _FLOW_FIXED):
                strict_box = True

            if flag & _ContainerElementSizingFlag.FLOW:
                has_flow = True
            if flag & _ContainerElementSizingFlag.FIXED:
                has_fixed = True
            elif flag & _GIVEN_BOX != _GIVEN_BOX:
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
            AbstractBoxWidget
            | AbstractFlowWidget
            | tuple[Literal["pack", WHSettings.PACK], AbstractFlowWidget | AbstractFixedWidget]
            | tuple[int, AbstractBoxWidget | AbstractFlowWidget]
            | tuple[Literal["given", WHSettings.GIVEN], int, AbstractBoxWidget | AbstractFlowWidget]
            | tuple[Literal["weight", WHSettings.WEIGHT], int | float, AbstractBoxWidget | AbstractFlowWidget]
        ],
        dividechars: int = 0,
        focus_column: int | AbstractWidget | None = None,
        min_width: int = 1,
        box_columns: Iterable[int] | None = None,
        *,
        select_navigation: bool = False,
    ) -> None:
        """Initialize a new Columns instance.

        :param widget_list: iterable of flow or box widgets
        :param dividechars: number of blank characters between columns
        :param focus_column: index into widget_list of column in focus or focused widget instance,
            if ``None`` the first selectable widget will be chosen.
        :param min_width: minimum width for each column which is not
            calling widget.pack() in *widget_list*.
        :param box_columns: a list of column indexes containing box widgets
            whose height is set to the maximum of the rows
            required by columns not listed in *box_columns*.
        :param select_navigation: handle the ``'next selectable'`` and ``'prev selectable'`` commands,
            see :ref:`select-navigation`.
        :raises ColumnsError: an item of *widget_list* is not a widget or a valid ``(width, widget)`` pair.
        :raises ValueError: *focus_column* is a widget that is not in *widget_list*.
        :warns ColumnsWarning: an item of *widget_list* is not a widget.
            A ``'pack'`` column is listed in *box_columns*.

        *widget_list* may also contain tuples such as:

        (*given_width*, *widget*)
            make this column *given_width* screen columns wide, where *given_width* is an int
        (``'given'``, *given_width*, *widget*)
            the same as (*given_width*, *widget*), in the expanded form that repeats the :attr:`contents` options.
            ``'fixed'`` is accepted as an older name for ``'given'``.
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
        self._cache_column_widths: list[int] = []
        self._cache_pack_widths: dict[int, int] = {}
        self._cache_hidden_packs: frozenset[int] = frozenset()
        super().__init__()
        self._contents: MonitoredFocusList[
            tuple[
                AbstractFlowWidget | AbstractFixedWidget,
                tuple[Literal[WHSettings.PACK], None, bool],
            ]
            | tuple[
                AbstractBoxWidget | AbstractFlowWidget,
                tuple[Literal[WHSettings.GIVEN], int, bool] | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
            ]
        ] = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)

        box_columns = set(box_columns or ())

        width: Literal["pack", WHSettings.PACK] | int | float | None
        w: AbstractBoxWidget | AbstractFlowWidget | AbstractFixedWidget

        for i, original in enumerate(widget_list):
            if not isinstance(original, tuple):
                w = original
                self.contents.append((w, (WHSettings.WEIGHT, 1, i in box_columns)))

            elif len(original) == 2:
                width, w = original
                if width in {Sizing.FLOW, WHSettings.PACK}:  # 'pack' used to be called 'flow'
                    if i in box_columns:
                        warnings.warn(
                            f"Widget {w} is listed as a box column, but sizing is {width} (Counted as PACK).",
                            ColumnsWarning,
                            stacklevel=2,
                        )
                    self.contents.append(
                        (
                            typing.cast("AbstractFlowWidget | AbstractFixedWidget", w),
                            (WHSettings.PACK, None, False),
                        )
                    )
                else:
                    self.contents.append(
                        (
                            typing.cast("AbstractBoxWidget | AbstractFlowWidget", w),
                            (WHSettings.GIVEN, typing.cast("int", width), i in box_columns),
                        )
                    )

            # Not deprecated: the expanded form of (width, widget) repeating the internal storage (GIVEN, width).
            # "fixed" is its older name, kept for backward compatibility.
            elif original[0] in {Sizing.FIXED, WHSettings.GIVEN}:
                width, w = original[-2:]
                self.contents.append((w, (WHSettings.GIVEN, typing.cast("int", width), i in box_columns)))

            elif original[0] == WHSettings.WEIGHT:
                _ignored, width, w = original
                self.contents.append((w, (WHSettings.WEIGHT, width, i in box_columns)))

            else:
                raise ColumnsError(f"initial widget list item invalid: {original!r}")

            if focus_column == w or (focus_column is None and w.selectable()):
                focus_column = i

            if not isinstance(w, AbstractWidget):
                warnings.warn(f"{w!r} is not a Widget", ColumnsWarning, stacklevel=3)

        self._dividechars = dividechars

        if self.contents and focus_column is not None:
            if not isinstance(focus_column, int):
                raise ValueError(f"Widget not found in Columns contents: {focus_column!r}")
            self.focus_position = focus_column
        self.pref_col: Literal["left", "right", Align.LEFT, Align.RIGHT] | int | None = None
        self._min_width = min_width
        self._cache_maxcol: int | None = None
        self.select_navigation = select_navigation
        # connected last, so that filling the contents during construction sends no signal
        self._contents.set_focus_moved_callback(functools.partial(self._emit, "focus changed"))

    def _repr_words(self) -> list[str]:
        """Return the base repr words followed by the number of items in the contents."""
        if len(self.contents) > 1:
            contents_string = f"({len(self.contents)} items)"
        elif self.contents:
            contents_string = "(1 item)"
        else:
            contents_string = "()"
        return [*super()._repr_words(), contents_string]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor arguments that differ from their defaults, for the repr.

        The focus position is included only when there is more than one item.
        """
        attrs = {
            **super()._repr_attrs(),
            "dividechars": self.dividechars,
            "focus_column": self.focus_position if len(self._contents) > 1 else None,
            "min_width": self.min_width,
            "select_navigation": self.select_navigation,
        }
        return remove_defaults(attrs, Columns.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield this widget's constructor arguments as `(name, value)` pairs, for `rich`'s repr protocol."""
        # We do not care about exact typing here: used only for debug purposes
        widget_list: list[
            AbstractWidget
            | tuple[Literal[WHSettings.PACK] | int, AbstractWidget]
            | tuple[Literal[WHSettings.WEIGHT], int | float, AbstractWidget]
        ] = []
        box_columns: list[int] = []
        for idx, (w_instance, options) in enumerate(self._contents):
            if options[0] == WHSettings.GIVEN:
                widget_list.append((options[1], w_instance))
            elif options[0] == WHSettings.PACK:
                widget_list.append((WHSettings.PACK, w_instance))
            elif options[1] == 1:
                widget_list.append(w_instance)
            else:
                widget_list.append((WHSettings.WEIGHT, options[1], w_instance))

            if options[2]:
                box_columns.append(idx)

        yield "widget_list", widget_list
        yield "dividechars", self.dividechars
        yield "focus_column", self.focus_position if self._contents else None
        yield "min_width", self.min_width
        yield "box_columns", box_columns
        yield "select_navigation", self.select_navigation, False

    def __len__(self) -> int:
        """Return the number of columns."""
        return len(self._contents)

    def _contents_modified(self) -> None:
        """Invalidate this widget whenever the contents has been changed."""
        # the hidden pack columns of the last layout are kept by position, which a change of the contents moves
        self._cache_hidden_packs = frozenset()
        self._invalidate()

    def selectable(self) -> bool:
        """Return whether any child widget is selectable.

        Asked on every call rather than cached,
        since a child such as :class:`~urwid.WidgetPlaceholder` may change its selectability after it was added.
        """
        return any(w.selectable() for w, _ in self.contents)

    def _validate_contents_modified(
        self,
        slc: tuple[int, int, int],
        new_items: Collection[
            tuple[
                AbstractFlowWidget | AbstractFixedWidget,
                tuple[Literal[WHSettings.PACK], None, bool],
            ]
            | tuple[
                AbstractBoxWidget | AbstractFlowWidget,
                tuple[Literal[WHSettings.GIVEN], int, bool] | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
            ]
        ],
    ) -> None:
        """
        Reject contents changes that would put an invalid item into the Columns.

        :raises ColumnsError: an added item is not a valid ``(widget, options)`` pair.
        """
        invalid_items: list[tuple[AbstractWidget, tuple[typing.Any, typing.Any, typing.Any]]] = []
        try:
            for item in new_items:
                _w, (t, n, b) = item
                if any(
                    (
                        t not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT},
                        (n is not None and (not isinstance(n, (int, float)) or n < 0 or not math.isfinite(float(n)))),
                        t == WHSettings.GIVEN and not isinstance(n, int),
                        not isinstance(b, bool),
                    )
                ):
                    invalid_items.append(item)
        # OverflowError: float() of an int too large for a float
        except (TypeError, ValueError, OverflowError) as exc:
            raise ColumnsError(f"added content invalid {exc}").with_traceback(exc.__traceback__) from exc

        if invalid_items:
            raise ColumnsError(f"added content invalid: {invalid_items!r}")

    @property
    def contents(
        self,
    ) -> MonitoredFocusList[
        tuple[
            AbstractFlowWidget | AbstractFixedWidget,
            tuple[Literal[WHSettings.PACK], None, bool],
        ]
        | tuple[
            AbstractBoxWidget | AbstractFlowWidget,
            tuple[Literal[WHSettings.GIVEN], int, bool] | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
        ]
    ]:
        """Return the contents of this Columns as a list of `(widget, options)` tuples.

        This list may be modified like a normal list and the Columns widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method
        """
        return self._contents

    @contents.setter
    def contents(
        self,
        new_contents: Sequence[
            tuple[
                AbstractFlowWidget | AbstractFixedWidget,
                tuple[Literal[WHSettings.PACK], None, bool],
            ]
            | tuple[
                AbstractBoxWidget | AbstractFlowWidget,
                tuple[Literal[WHSettings.GIVEN], int, bool] | tuple[Literal[WHSettings.WEIGHT], int | float, bool],
            ]
        ],
    ) -> None:
        """Replace the contents with *new_contents*.

        :param new_contents: `(widget, options)` tuples, with options made by the :meth:`options` method
        :raises ColumnsError: an item is not a valid ``(widget, options)`` pair.
        """
        self._contents[:] = new_contents

    @typing.overload
    @staticmethod
    def options(
        width_type: Literal["pack", WHSettings.PACK],
        width_amount: int | float | None = ...,  # noqa: PYI041  # provide explicit for IDEs
        box_widget: bool = ...,
    ) -> tuple[Literal[WHSettings.PACK], None, bool]: ...

    @typing.overload
    @staticmethod
    def options(
        width_type: Literal["given", WHSettings.GIVEN],
        width_amount: int = ...,
        box_widget: bool = ...,
    ) -> tuple[Literal[WHSettings.GIVEN], int, bool]: ...

    @typing.overload
    @staticmethod
    def options(
        width_type: Literal["weight", WHSettings.WEIGHT] = ...,
        width_amount: int | float = ...,  # noqa: PYI041  # provide explicit for IDEs
        box_widget: bool = ...,
    ) -> tuple[Literal[WHSettings.WEIGHT], int | float, bool]: ...

    @typing.overload
    @staticmethod
    def options(
        width_type: Literal["pack", "given", "weight", WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT] = ...,
        width_amount: int | float | None = ...,  # noqa: PYI041  # provide explicit for IDEs
        box_widget: bool = ...,
    ) -> (
        tuple[Literal[WHSettings.PACK], None, bool]
        | tuple[Literal[WHSettings.GIVEN], int, bool]
        | tuple[Literal[WHSettings.WEIGHT], int | float, bool]
    ): ...

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
        Return a new options tuple for use in a Columns .contents list.

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
        :raises ColumnsError: *width_type* and *width_amount* are not a valid combination.
        """
        if width_type == WHSettings.PACK:
            return (WHSettings.PACK, None, box_widget)
        if width_type == WHSettings.GIVEN and isinstance(width_amount, int):
            return (WHSettings.GIVEN, width_amount, box_widget)
        if width_type == WHSettings.WEIGHT and width_amount is not None:
            return (WHSettings.WEIGHT, width_amount, box_widget)
        raise ColumnsError(f"invalid combination: width_type={width_type!r}, width_amount={width_amount!r}")

    def _invalidate(self) -> None:
        """Drop the cached column widths and the cached canvases."""
        self._cache_maxcol = None
        super()._invalidate()

    @property
    def dividechars(self) -> int:
        """Number of blank characters between two visible columns."""
        return self._dividechars

    @dividechars.setter
    def dividechars(self, dividechars: int) -> None:
        self._dividechars = dividechars
        self._invalidate()

    @property
    def min_width(self) -> int:
        """Minimum width of a weighted column."""
        return self._min_width

    @min_width.setter
    def min_width(self, min_width: int) -> None:
        self._min_width = min_width
        self._invalidate()

    def _select_candidates(self, *, reverse: bool, from_edge: bool) -> Iterator[int]:
        """Yield the selectable positions as the base class does, skipping pack columns the last layout found 0 wide.

        A pack column counts as 0 wide only when its widget packs to 0 columns focused as well as unfocused.
        """
        for position in super()._select_candidates(reverse=reverse, from_edge=from_edge):
            if position not in self._cache_hidden_packs:
                yield position

    @property
    def focus(self) -> AbstractWidget | None:
        """The child widget in focus or None when Columns is empty."""
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @property
    def focus_position(self) -> int:
        """Return the index of the child widget in focus.

        Raises :exc:`IndexError` if read when Columns is empty, or when set to an invalid index.

        :raises IndexError: the Columns is empty.
        """
        if (focus := self.contents.focus) is not None:
            return focus

        raise IndexError("No focus_position, Columns is empty")

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        :param position: index of child widget to be made focus
        :raises IndexError: *position* is not an index of a child widget.
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No Columns child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Columns child widget at position {position}").with_traceback(
                exc.__traceback__
            ) from exc
        self.contents.focus = position

    def column_widths(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> list[int]:
        """
        Return a list of column widths.

        0 values in the list means hide the corresponding column completely
        """
        maxcol = size[0]

        def pack_width(
            widget: AbstractWidget,
            size_kind: WHSettings,
            is_box: bool,
            focused: bool,
        ) -> int:
            """Calculate the width a 'pack' column takes by packing its widget.

            :warns ColumnsWarning: the column holds an object that is not a widget,
                or its widget supports neither FIXED nor FLOW sizing.
            """
            if isinstance(widget, AbstractWidget):
                w_sizing = widget.sizing()
            else:
                warnings.warn(f"{widget!r} is not a Widget", ColumnsWarning, stacklevel=4)
                w_sizing = frozenset((urwid.BOX, urwid.FLOW))

            if w_sizing & frozenset((Sizing.FIXED, Sizing.FLOW)):
                candidate_size = 0

                if Sizing.FIXED in w_sizing:
                    candidate_size = widget.pack(
                        (),
                        focused,
                    )[0]

                if Sizing.FLOW in w_sizing and (not candidate_size or candidate_size > maxcol):
                    # FIXME: should be able to pack with a different maxcol value
                    candidate_size = widget.pack(
                        (maxcol,),
                        focused,
                    )[0]

                return candidate_size

            warnings.warn(
                f"Unusual widget {widget} sizing for {size_kind} (box={is_box}). "
                f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for width calculation",
                ColumnsWarning,
                stacklevel=4,
            )
            return widget.pack((maxcol,), focused)[0]

        # 'pack' widgets can change their packed width without invalidating the cache,
        # so recompute their widths and reuse the cached result only when nothing changed.
        pack_widths = {
            i: pack_width(w, t, b, focus and i == self.focus_position)
            for i, (w, (t, width, b)) in enumerate(self.contents)
            if t == WHSettings.PACK
        }
        # pack columns 0 wide even when focused: the focus navigation skips them, as it does (GIVEN, 0) ones
        self._cache_hidden_packs = frozenset(
            i
            for i, width in pack_widths.items()
            if width == 0 and pack_width(self.contents[i][0], WHSettings.PACK, self.contents[i][1][2], True) == 0
        )
        if maxcol == self._cache_maxcol and pack_widths == self._cache_pack_widths:
            return self._cache_column_widths

        widths = []
        # the divider each column reserves on its right: none for a column of static width 0, which render hides,
        # and one for every weighted column, even one that ends up 0 wide
        dividers: list[int] = []

        weighted: list[tuple[int | float, int]] = []
        shared = maxcol + self.dividechars

        static_w: int

        for i, (_w, options) in enumerate(self.contents):
            if options[0] == WHSettings.GIVEN:
                static_w = options[1]
            elif options[0] == WHSettings.PACK:
                static_w = pack_widths[i]
            else:
                static_w = self.min_width

            divider = self.dividechars if static_w > 0 or options[0] not in {WHSettings.GIVEN, WHSettings.PACK} else 0
            if shared < static_w + divider and i > self.focus_position:
                break

            widths.append(static_w)
            dividers.append(divider)
            shared -= static_w + divider
            if options[0] not in {WHSettings.GIVEN, WHSettings.PACK}:
                weighted.append((options[1], i))

        # drop columns on the left until we fit
        for i, width_ in enumerate(widths):
            if shared >= 0:
                break
            shared += width_ + dividers[i]
            widths[i] = 0
            if weighted and weighted[0][1] == i:
                del weighted[0]

        grow = shared + len(weighted) * self.min_width
        if weighted and (max_weight := max(weight for weight, _i in weighted)) > sys.float_info.max / (
            len(weighted) * max(grow, 1)
        ):
            # grow * wtotal could overflow a float: scale weights to at most 1, keeping their ratios
            weighted = [(weight / max_weight, i) for weight, i in weighted]

        wtotal = sum(weight for weight, _i in weighted)
        if shared and wtotal:
            # divide up the remaining space between weighted cols
            for weight, i in sorted(weighted):
                width = max(int(grow * weight / wtotal + 0.5), self.min_width)

                widths[i] = width
                grow -= width
                wtotal -= weight

        self._cache_maxcol = maxcol
        self._cache_column_widths = widths
        self._cache_pack_widths = pack_widths
        return widths

    def _get_fixed_column_sizes(
        self,
        focus: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int] | tuple[int] | tuple[()], ...]]:
        """Get column widths, heights and render size parameters.

        :raises ColumnsError: a child widget does not support a sizing mode this Columns needs, no child can provide
            a height, or the weights are too far apart to keep their ratio at a fixed size.
        """
        widths: dict[int, int] = {}
        heights: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}
        box: list[int] = []
        weighted: dict[int | float, list[tuple[AbstractWidget, int, bool, bool]]] = {}
        weights: list[int | float] = []
        weight_max_sizes: dict[int | float, int] = {}

        for i, (widget, options) in enumerate(self.contents):
            size_kind, is_box = options[0], options[2]
            w_sizing = widget.sizing()
            focused = focus and i == self.focus_position

            if options[0] == WHSettings.GIVEN:
                given_width = options[1]
                widths[i] = given_width
                if is_box:
                    box.append(i)
                elif Sizing.FLOW in w_sizing:
                    heights[i] = typing.cast("AbstractFlowWidget", widget).rows((given_width,), focused)
                    w_h_args[i] = (given_width,)
                else:
                    raise ColumnsError(f"Unsupported combination of {size_kind} box={is_box!r} for {widget}")

            elif options[0] == WHSettings.PACK:
                if Sizing.FIXED not in w_sizing or is_box:
                    raise ColumnsError(f"Unsupported combination of {size_kind} box={is_box!r} for {widget}")
                width, height = typing.cast("AbstractFixedWidget", widget).pack((), focused)
                widths[i] = width
                heights[i] = height
                w_h_args[i] = ()

            elif options[1] <= 0:
                widths[i] = 0
                heights[i] = 1
                if is_box:
                    box.append(i)
                else:
                    w_h_args[i] = (0,)

            elif Sizing.FLOW in w_sizing or is_box:
                if Sizing.FIXED in w_sizing:
                    width, height = typing.cast("AbstractFixedWidget", widget).pack((), focused)
                else:
                    width = self.min_width

                size_weight = options[1]

                weighted.setdefault(size_weight, []).append((widget, i, is_box, focused))
                weights.append(size_weight)
                weight_max_sizes.setdefault(size_weight, width)
                weight_max_sizes[size_weight] = max(weight_max_sizes[size_weight], width)
            else:
                raise ColumnsError(f"Unsupported combination of {size_kind} box={is_box!r} for {widget}")

        if weight_max_sizes:
            max_weighted_coefficient = max(width / weight for weight, width in weight_max_sizes.items())

            for weight in weight_max_sizes:
                try:
                    width = max(int(max_weighted_coefficient * weight + 0.5), self.min_width)
                except OverflowError as exc:
                    raise ColumnsError(
                        f"Weights of {self!r} are too far apart to keep their ratio at a fixed size"
                    ) from exc
                for widget, i, is_box, focused in weighted[weight]:
                    widths[i] = width

                    if not is_box:
                        heights[i] = typing.cast("AbstractFlowWidget", widget).rows((width,), focused)
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
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int] | tuple[int] | tuple[()], ...]]:
        """Get column widths, heights and render size parameters.

        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        :warns ColumnsWarning: a column holds an object that is not a widget.
            A FLOW render is requested and a BOX-only column is not listed in ``box_columns``.
        """
        if not size:
            return self._get_fixed_column_sizes(focus=focus)

        widths = tuple(self.column_widths(size=size, focus=focus))
        # Every index gets a height and a render size argument before returning, either in the loop below
        # or in the box fixup after it, so plain lists are used instead of index-keyed dicts.
        heights: list[int] = [0] * len(widths)
        w_h_args: list[tuple[int, int] | tuple[int] | tuple[()]] = [()] * len(widths)
        box: list[int] = []
        box_need_height: list[int] = []
        # -1 marks "no height was calculated in the loop", which a plain 0 cannot: a zero-width column
        # stores a real height of 0.
        max_height = -1
        focus_position = self.focus_position if focus and self.contents else -1

        for i, (width, (widget, (size_kind, _size_weight, is_box))) in enumerate(
            zip(widths, self.contents, strict=False)
        ):
            if isinstance(widget, AbstractWidget):
                w_sizing = widget.sizing()
            else:
                warnings.warn(f"{widget!r} is not a Widget.", ColumnsWarning, stacklevel=3)
                # This branch should be fully deleted later.
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            if len(size) == 2 and Sizing.BOX in w_sizing:
                height = size[1]
                w_h_args[i] = (width, height)

            elif is_box:
                box.append(i)
                continue

            elif Sizing.FLOW in w_sizing:
                if width > 0:
                    height = typing.cast("AbstractFlowWidget", widget).rows((width,), i == focus_position)
                else:
                    height = 0
                w_h_args[i] = (width,)

            elif size_kind == WHSettings.PACK:
                if width > 0:
                    height = typing.cast("AbstractFixedWidget", widget).pack((), i == focus_position)[1]
                else:
                    height = 0
                w_h_args[i] = ()

            else:
                box_need_height.append(i)
                continue

            heights[i] = height
            max_height = max(max_height, height)

        if len(size) == 2:
            max_height = size[1]
        elif max_height < 0:
            max_height = 1
        elif box_need_height:
            warnings.warn(
                f"Widgets in columns {box_need_height} "
                f"({[self.contents[i][0] for i in box_need_height]}) "
                f'are BOX widgets not marked "box_columns" while FLOW render is requested (size={size!r})',
                ColumnsWarning,
                stacklevel=3,
            )

        for idx in (*box, *box_need_height):
            heights[idx] = max_height
            w_h_args[idx] = (widths[idx], max_height)

        return (widths, tuple(heights), tuple(w_h_args))

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Get packed size for widget.

        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if size:
            return super().pack(size, focus)
        widths, heights, _ = self.get_column_sizes(size, focus)
        visible = sum(1 for width in widths if width > 0)
        return (sum(widths) + self.dividechars * max(visible - 1, 0), max(heights))

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> SolidCanvas | CompositeCanvas:
        """
        Render columns and return canvas.

        :param size: see :meth:`Widget.render` for details
        :param focus: ``True`` if this widget is in focus
        :raises ColumnsError: the Columns has no visible column to render, or *size* is ``()`` and the children cannot
            be sized as a fixed widget.
        """
        widths, _, size_args = self.get_column_sizes(size, focus)
        # a divider separates two visible columns: hidden columns and the end of the row get none
        last_visible = max((i for i, width in enumerate(widths) if width > 0), default=-1)

        data: list[tuple[Canvas, int, bool, int]] = []
        for i, (width, w_size, (w, _)) in enumerate(zip(widths, size_args, self.contents, strict=False)):
            # if the widget has a width of 0, hide it
            if width <= 0:
                continue

            if i < last_visible:
                width += self.dividechars  # noqa: PLW2901
            data.append(
                (
                    # widget kind and size arguments matched separately
                    w.render(w_size, focus=focus and self.focus_position == i),  # type: ignore[arg-type]
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
        """Return the cursor coordinates from the focus widget.

        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        w, _ = self.contents[self.focus_position]

        if not w.selectable():
            return None
        if not hasattr(w, "get_cursor_coords"):
            return None

        widths, _, size_args = self.get_column_sizes(size, focus=True)
        if len(widths) <= self.focus_position or widths[self.focus_position] <= 0:
            # the focus column is hidden: render shows no cursor
            return None

        if (coords := w.get_cursor_coords(size_args[self.focus_position])) is not None:
            x, y = coords
            x += sum(self.dividechars + wc for wc in widths[: self.focus_position] if wc > 0)
            return x, y

        return None

    def move_cursor_to_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        col: int | Literal["left", "right", Align.LEFT, Align.RIGHT],
        row: int,
    ) -> bool:
        """
        Choose a selectable column to focus based on the coords.

        see :meth:`Widget.move_cursor_coords` for details

        A hidden column, one with a width of 0, is never chosen.

        :raises ValueError: the column sizes cannot be computed for *size*, for example *size* is ``()`` and the
            children cannot be sized as a fixed widget.
        """
        try:
            widths, _, size_args = self.get_column_sizes(size, focus=True)
        except Exception as exc:
            raise ValueError(self.contents, size, col, row) from exc

        best: tuple[int, int, int, AbstractWidget] | None = None
        x = 0
        for i, (width, (w, _options)) in enumerate(zip(widths, self.contents, strict=False)):
            end: int = x + width
            if width > 0 and w.selectable():
                if not isinstance(col, int):
                    best = i, x, end, w
                    if col == Align.LEFT:
                        # the first selectable column
                        break
                elif x > col:
                    # past the column: keep the one on the left if it is closer
                    if best is not None:
                        _best_i, _best_x, best_end, _best_w = best
                        if col - best_end < x - col:
                            break
                    best = i, x, end, w
                    break
                else:
                    best = i, x, end, w
                    if col < end:
                        # choose this one
                        break
            if width > 0:
                x = end + self.dividechars

        if best is None:
            return False

        i, x, end, w = best
        if hasattr(w, "move_cursor_to_coords"):
            if isinstance(col, int):
                move_x: int | Literal["left", "right", Align.LEFT, Align.RIGHT] = min(max(0, col - x), end - x - 1)
            else:
                # pyrefly: ignore[bad-assignment]  # comparing with Align members widens the Literal
                move_x = col

            if w.move_cursor_to_coords(size_args[i], move_x, row) is False:
                return False

            # The child may have changed this Columns' contents while moving its cursor.
            if i >= len(self.contents) or self.contents[i][0] is not w:
                return False

        self.focus_position = i
        # pyrefly: ignore[bad-assignment]  # comparing with Align members widens the Literal
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
        """Send event to appropriate column. May change focus on button 1 press.

        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.

        .. deprecated:: 2.4.0
            Support for a column that does not implement ``mouse_event`` is deprecated.
            Support will be removed in version 7.0.
        """
        widths, _, size_args = self.get_column_sizes(size, focus=focus)

        x = 0
        for i, (width, w_size, (w, _)) in enumerate(zip(widths, size_args, self.contents, strict=False)):
            if col < x:
                return False
            w = self.contents[i][0]  # noqa: PLW2901
            end = x + width

            if col >= end:
                if width > 0:
                    x = end + self.dividechars
                continue

            focus = focus and self.focus_position == i
            if is_mouse_press(event) and button == 1 and w.selectable():
                self.focus_position = i

            if not hasattr(w, "mouse_event"):
                _deprecation.warn(
                    f"{w.__class__.__module__}.{w.__class__.__name__} is not implementing Widget API.",
                    since="2.4.0",
                    removed_in="7.0",
                )
                return False

            # widget kind and size arguments matched separately
            return w.mouse_event(w_size, event, button, col - x, row, focus)  # type: ignore[arg-type]
        return False

    def get_pref_col(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
    ) -> Literal["left", "right", Align.LEFT, Align.RIGHT] | int | None:
        """Return the pref col from the column in focus.

        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        widths, _, size_args = self.get_column_sizes(size, focus=True)

        w, _ = self.contents[self.focus_position]
        if len(widths) <= self.focus_position or widths[self.focus_position] <= 0:
            return 0
        col: Literal["left", "right", Align.LEFT, Align.RIGHT] | int | None = None
        cwidth = widths[self.focus_position]
        # hidden columns are rendered without a divider
        x = sum(self.dividechars + wc for wc in widths[: self.focus_position] if wc > 0)

        if hasattr(w, "get_pref_col"):
            col = w.get_pref_col(size_args[self.focus_position])
            if isinstance(col, int):
                col += x
        if col is None:
            col = self.pref_col

        if col is None and w.selectable():
            col = cwidth // 2 + x
        return col

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows required by the columns.

        This only makes sense if :attr:`contents` contains flow widgets.

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

        A hidden focus column, one with a width of 0, gets no keys: the key is left unhandled by it.
        Unhandled :kbd:`left` and :kbd:`right` keys may cause a focus change.
        With :attr:`select_navigation`, so do unhandled ``'next selectable'`` and ``'prev selectable'`` commands.

        :param size: Widget size correct for the supported sizing
        :param key: a single keystroke value
        :returns: ``None`` if the key was handled, otherwise the key left unhandled,
            as the focus column returned it.
        :raises ColumnsError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if not self.contents:
            return key

        widths, _, size_args = self.get_column_sizes(size, focus=True)
        if self.focus_position >= len(widths):
            return key

        i = self.focus_position
        w, _ = self.contents[i]
        if self._command_map[key] not in {Command.UP, Command.DOWN, Command.PAGE_UP, Command.PAGE_DOWN}:
            self.pref_col = None
        if widths[i] > 0 and w.selectable():
            # widget kind and size arguments matched separately
            if (processed := w.keypress(size_args[i], key)) is not None:  # type: ignore[arg-type]
                key = processed
            else:
                return None

        if self.select_navigation and self._command_map[key] in _SELECT_COMMANDS:
            return self._select_keypress_unhandled(key)
        if self._command_map[key] not in {Command.LEFT, Command.RIGHT} or not self.contents:
            return key

        # The child may have changed this Columns' contents or focus while handling the key,
        # so the candidates are taken from the current focus.
        for j in self._select_candidates(reverse=self._command_map[key] == Command.LEFT, from_edge=False):
            self.focus_position = j
            return None
        return key
