"""Pile: a container that stacks widgets vertically."""

from __future__ import annotations

import functools
import itertools
import math
import sys
import typing
import warnings
from typing import Literal

from urwid import _deprecation
from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
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

    # Imported by name for type checkers, see urwid._deprecation.
    from typing_extensions import deprecated
else:
    from urwid._deprecation import deprecated


# Flag combinations tested on every element of every ``Pile.sizing()`` call, hoisted out of the loop
# so that the enum member lookups and the OR-ing happen once per import instead of once per element.
_BOX_FLOW_FIXED = _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
_FLOW_FIXED = _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
_BOX_OR_FLOW = frozenset((Sizing.BOX, Sizing.FLOW))


class PileError(WidgetError):
    """Pile related errors."""


class PileWarning(WidgetWarning):
    """Pile related warnings."""


class Pile(
    Widget,
    SelectNavigationListContentsMixin[
        tuple[
            AbstractFlowWidget | AbstractFixedWidget,
            tuple[Literal[WHSettings.PACK], None],
        ]
        | tuple[
            AbstractBoxWidget,
            tuple[Literal[WHSettings.GIVEN], int],
        ]
        | tuple[
            AbstractBoxWidget | AbstractFlowWidget,
            tuple[Literal[WHSettings.WEIGHT], int | float],
        ]
    ],
):
    """A pile of widgets stacked vertically from top to bottom.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`contents`.
    Its handlers receive the container, the old and the new focus position, which is ``None`` while it is empty.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed"]

    def sizing(self) -> frozenset[Sizing]:
        """Sizing supported by widget.

        :returns: Calculated widget sizing
        :warns PileWarning: an item's height type does not suit its widget's sizing.

        Due to the nature of container with mutable contents, this method cannot be cached.

        Rules:
        * WEIGHT BOX -> BOX
        * GIVEN BOX -> FLOW (height is known) & BOX (can be shrinked/padded)
        * PACK BOX -> Unsupported

        * WEIGHT FLOW -> FLOW
        * GIVEN FLOW -> Unsupported
        * PACK FLOW -> FLOW

        * WEIGHT FIXED -> Need also FLOW or/and BOX to properly render due to width calculation
        * GIVEN FIXED -> Unsupported
        * PACK FIXED -> FIXED (widget knows its size)

        >>> from urwid import BigText, ProgressBar, SolidFill, Text, Thin3x3Font
        >>> font = Thin3x3Font()

        # BOX-only widget
        >>> Pile((SolidFill("#"),))
        <Pile box widget (1 item)>

        # GIVEN BOX -> BOX/FLOW
        >>> Pile(((10, SolidFill("#")),))
        <Pile box/flow widget (1 item)>

        # FLOW-only
        >>> Pile((ProgressBar(None, None),))
        <Pile flow widget (1 item)>

        # FIXED -> FIXED
        >>> Pile(((WHSettings.PACK, BigText("0", font)),))
        <Pile fixed widget (1 item)>

        # FLOW/FIXED -> FLOW/FIXED
        >>> Pile(((WHSettings.PACK, Text("text")),))
        <Pile fixed/flow widget (1 item)>

        # FLOW + FIXED widgets -> FLOW/FIXED
        >>> Pile((ProgressBar(None, None), (WHSettings.PACK, BigText("0", font))))
        <Pile fixed/flow widget (2 items) focus_item=0>

        # GIVEN BOX + FIXED widgets -> BOX/FLOW/FIXED (GIVEN BOX allows overriding its height & allows any width)
        >>> Pile(((10, SolidFill("#")), (WHSettings.PACK, BigText("0", font))))
        <Pile widget (2 items) focus_item=0>

        # Invalid sizing combination -> use fallback settings (and produce warning)
        >>> Pile(((WHSettings.WEIGHT, 1, BigText("0", font)),))
        <Pile box/flow widget (1 item)>

        # Special case: empty pile widget sizing is impossible to calculate
        >>> Pile(())
        <Pile box/flow widget ()>
        """
        if not self.contents:
            return frozenset((Sizing.BOX, Sizing.FLOW))
        strict_box = False
        has_flow = False

        has_fixed = False
        supported: set[Sizing] = set()

        for idx, (widget, (size_kind, _size_weight)) in enumerate(self.contents):
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
                    flag |= _ContainerElementSizingFlag.FLOW

            else:
                flag = _ContainerElementSizingFlag.WH_PACK
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW
                if Sizing.FIXED in w_sizing:
                    flag |= _ContainerElementSizingFlag.FIXED

            if not flag & _BOX_FLOW_FIXED:
                warnings.warn(
                    f"Sizing combination of widget {idx} not supported: {size_kind.name} {'|'.join(w_sizing).upper()}",
                    PileWarning,
                    stacklevel=3,
                )
                return frozenset((Sizing.BOX, Sizing.FLOW))

            if flag & _ContainerElementSizingFlag.BOX:
                supported.add(Sizing.BOX)
                if not flag & _FLOW_FIXED:
                    strict_box = True
                    break

            if flag & _ContainerElementSizingFlag.FLOW:
                has_flow = True
            if flag & _ContainerElementSizingFlag.FIXED:
                has_fixed = True

        if not strict_box:
            if has_flow:
                supported.add(Sizing.FLOW)
            if has_fixed:
                supported.add(Sizing.FIXED)

        return frozenset(supported)

    def __init__(
        self,
        widget_list: Iterable[
            AbstractWidget
            | tuple[Literal["pack", WHSettings.PACK], AbstractFlowWidget | AbstractFixedWidget]
            | tuple[int, AbstractBoxWidget]
            | tuple[Literal["given", WHSettings.GIVEN], int, AbstractBoxWidget]
            | tuple[Literal["weight", WHSettings.WEIGHT], int | float, AbstractBoxWidget | AbstractFlowWidget]
        ],
        focus_item: AbstractWidget | int | None = None,
        *,
        select_navigation: bool = False,
    ) -> None:
        """Build the pile from a list of child widgets.

        :param widget_list: child widgets
        :param focus_item: child widget that gets the focus initially.
            Chooses the first selectable widget if unset.
        :param select_navigation: handle the ``'next selectable'`` and ``'prev selectable'`` commands,
            see :ref:`select-navigation`.
        :raises PileError: an item of *widget_list* is not a widget or a valid ``(height, widget)`` pair.
        :warns PileWarning: an item of *widget_list* is not a widget.

        *widget_list* may also contain tuples such as:

        (*given_height*, *widget*)
            always treat *widget* as a box widget and give it *given_height* rows, where given_height is an int
        (``'given'``, *given_height*, *widget*)
            the same as (*given_height*, *widget*), in the expanded form that repeats the :attr:`contents` options.
            ``'fixed'`` is accepted as an older name for ``'given'``.
        (``'pack'``, *widget*)
            allow *widget* to calculate its own height by calling its :meth:`rows` method,
            i.e. treat it as a flow widget.
        (``'weight'``, *weight*, *widget*)
            if the pile is treated as a box widget then treat widget as a box
            widget with a height based on its relative weight value, otherwise treat the same as (``'pack'``, *widget*).

        Widgets not in a tuple are the same as (``'weight'``, ``1``, *widget*)`

        .. note:: If the Pile is treated as a box widget there must be at least
            one ``'weight'`` tuple in *widget_list*.
        """
        super().__init__()
        self._contents: MonitoredFocusList[
            tuple[
                AbstractFlowWidget | AbstractFixedWidget,
                tuple[Literal[WHSettings.PACK], None],
            ]
            | tuple[
                AbstractBoxWidget,
                tuple[Literal[WHSettings.GIVEN], int],
            ]
            | tuple[
                AbstractBoxWidget | AbstractFlowWidget,
                tuple[Literal[WHSettings.WEIGHT], int | float],
            ]
        ] = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)

        for i, original in enumerate(widget_list):
            if not isinstance(original, tuple):
                w = original
                self.contents.append((w, (WHSettings.WEIGHT, 1)))
            elif len(original) == 2:
                if original[0] in {Sizing.FLOW, WHSettings.PACK}:  # 'pack' used to be called 'flow'
                    w = original[-1]
                    self.contents.append(
                        (
                            w,
                            (WHSettings.PACK, None),
                        )
                    )
                else:
                    height, w = original
                    self.contents.append(
                        (
                            typing.cast("AbstractBoxWidget", w),
                            (
                                WHSettings.GIVEN,
                                typing.cast("int", height),
                            ),
                        )
                    )
            elif len(original) == 3:
                settings, amount, w = original
                # Not deprecated: the expanded form of (height, widget) repeating the internal storage (GIVEN, height).
                # "fixed" is its older name, kept for backward compatibility.
                if settings in {Sizing.FIXED, WHSettings.GIVEN}:
                    self.contents.append(
                        (
                            typing.cast("AbstractBoxWidget", w),
                            (
                                WHSettings.GIVEN,
                                typing.cast("int", amount),
                            ),
                        )
                    )
                elif settings == WHSettings.WEIGHT:
                    self.contents.append(
                        (
                            w,
                            (
                                WHSettings.WEIGHT,
                                amount,
                            ),
                        )
                    )
                else:
                    raise PileError(f"initial widget list item invalid {original!r}")
            else:
                raise PileError(f"initial widget list item invalid {original!r}")
            if focus_item is None and w.selectable():
                focus_item = i

            if not isinstance(w, AbstractWidget):
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)

        if self.contents and focus_item is not None:
            self.focus = focus_item

        self.pref_col: int | Literal["left", "right", Align.LEFT, Align.RIGHT] = 0
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
            "focus_item": self.focus_position if len(self._contents) > 1 else None,
            "select_navigation": self.select_navigation,
        }
        return remove_defaults(attrs, Pile.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield this widget's constructor arguments as `(name, value)` pairs, for `rich`'s repr protocol."""
        widget_list: list[
            AbstractWidget
            | tuple[Literal[WHSettings.PACK] | int, AbstractWidget]
            | tuple[Literal[WHSettings.WEIGHT], int | float, AbstractWidget]
        ] = []

        for w_instance, options in self._contents:
            if options[0] == WHSettings.GIVEN:
                widget_list.append((options[1], w_instance))
            elif options[0] == WHSettings.PACK:
                widget_list.append((WHSettings.PACK, w_instance))
            elif options[0] == WHSettings.WEIGHT:
                if options[1] == 1:
                    widget_list.append(w_instance)
                else:
                    widget_list.append((WHSettings.WEIGHT, options[1], w_instance))

        yield "widget_list", widget_list
        yield "focus_item", self.focus_position if self._contents else None
        yield "select_navigation", self.select_navigation, False

    def __len__(self) -> int:
        """Return the number of widgets in the pile."""
        return len(self._contents)

    def _contents_modified(self) -> None:
        """Invalidate this widget whenever the contents has been changed."""
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
                AbstractWidget,
                tuple[Literal[WHSettings.PACK], None]
                | tuple[Literal[WHSettings.GIVEN], int]
                | tuple[Literal[WHSettings.WEIGHT], int | float],
            ]
        ],
    ) -> None:
        """
        Reject contents changes that would put an invalid item into the Pile.

        :raises PileError: an added item is not a valid ``(widget, options)`` pair.
        """
        invalid_items: list[tuple[AbstractWidget, tuple[typing.Any, typing.Any]]] = []
        try:
            for item in new_items:
                _w, (t, n) = item
                if any(
                    (
                        t not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT},
                        (n is not None and (not isinstance(n, (int, float)) or n < 0 or not math.isfinite(float(n)))),
                        t == WHSettings.GIVEN and not isinstance(n, int),
                    )
                ):
                    invalid_items.append(item)

        # OverflowError: float() of an int too large for a float
        except (TypeError, ValueError, OverflowError) as exc:
            raise PileError(f"added content invalid: {exc}").with_traceback(exc.__traceback__) from exc

        if invalid_items:
            raise PileError(f"added content invalid: {invalid_items!r}")

    @property
    def contents(
        self,
    ) -> MonitoredFocusList[
        tuple[
            AbstractFlowWidget | AbstractFixedWidget,
            tuple[Literal[WHSettings.PACK], None],
        ]
        | tuple[
            AbstractBoxWidget,
            tuple[Literal[WHSettings.GIVEN], int],
        ]
        | tuple[
            AbstractBoxWidget | AbstractFlowWidget,
            tuple[Literal[WHSettings.WEIGHT], int | float],
        ]
    ]:
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
    def contents(
        self,
        new_contents: Sequence[
            tuple[
                AbstractFlowWidget | AbstractFixedWidget,
                tuple[Literal[WHSettings.PACK], None],
            ]
            | tuple[
                AbstractBoxWidget,
                tuple[Literal[WHSettings.GIVEN], int],
            ]
            | tuple[
                AbstractBoxWidget | AbstractFlowWidget,
                tuple[Literal[WHSettings.WEIGHT], int | float],
            ]
        ],
    ) -> None:
        """Replace the contents with *new_contents*.

        :param new_contents: `(widget, options)` tuples, with options made by the :meth:`options` method
        :raises PileError: an item is not a valid ``(widget, options)`` pair.
        """
        self._contents[:] = new_contents

    @typing.overload
    @staticmethod
    def options(
        height_type: Literal["pack", WHSettings.PACK],
        height_amount: int | float | None = ...,  # noqa: PYI041  # provide explicit for IDEs
    ) -> tuple[Literal[WHSettings.PACK], None]: ...

    @typing.overload
    @staticmethod
    def options(
        height_type: Literal["given", WHSettings.GIVEN],
        height_amount: int = ...,
    ) -> tuple[Literal[WHSettings.GIVEN], int]: ...

    @typing.overload
    @staticmethod
    def options(
        height_type: Literal["weight", WHSettings.WEIGHT] = ...,
        height_amount: int | float = ...,  # noqa: PYI041  # provide explicit for IDEs
    ) -> tuple[Literal[WHSettings.WEIGHT], int | float]: ...

    @typing.overload
    @staticmethod
    def options(
        height_type: Literal["pack", "given", "weight"] | WHSettings = ...,
        height_amount: int | float | None = ...,  # noqa: PYI041  # provide explicit for IDEs
    ) -> (
        tuple[Literal[WHSettings.PACK], None]
        | tuple[Literal[WHSettings.GIVEN], int]
        | tuple[Literal[WHSettings.WEIGHT], int | float]
    ): ...

    @staticmethod
    def options(
        height_type: Literal["pack", "given", "weight"] | WHSettings = WHSettings.WEIGHT,
        height_amount: int | float | None = 1,  # noqa: PYI041  # provide explicit for IDEs
    ) -> (
        tuple[Literal[WHSettings.PACK], None]
        | tuple[Literal[WHSettings.GIVEN], int]
        | tuple[Literal[WHSettings.WEIGHT], int | float]
    ):
        """
        Return a new options tuple for use in a Pile's :attr:`contents` list.

        :param height_type: ``'pack'``, ``'given'`` or ``'weight'``
        :param height_amount: ``None`` for ``'pack'``, a number of rows for
            ``'given'`` or a weight value (number) for ``'weight'``
        :raises PileError: *height_type* and *height_amount* are not a valid combination.
        """
        if height_type == WHSettings.PACK:
            return (WHSettings.PACK, None)
        if height_type == WHSettings.GIVEN and isinstance(height_amount, int):
            return (WHSettings.GIVEN, height_amount)
        if height_type == WHSettings.WEIGHT and height_amount is not None:
            return (WHSettings.WEIGHT, height_amount)
        raise PileError(f"invalid combination: height_type={height_type!r}, height_amount={height_amount!r}")

    @property
    def focus(self) -> AbstractWidget | None:
        """The child widget in focus or None when Pile is empty."""
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @focus.setter
    def focus(self, item: AbstractWidget | int) -> None:
        """
        Set the item in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`focus_position`.
            to set the position by integer index instead.

        :param item: element to focus
        :raises ValueError: *item* is a widget that is not in the contents.
        """
        if isinstance(item, int):
            self.focus_position = item
            return
        for i, (w, _options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in Pile contents: {item!r}")

    @property
    def focus_position(self) -> int:
        """Index of child widget in focus.

        Raises :exc:`IndexError` if read when Pile is empty, or when set to an invalid index.

        :raises IndexError: the Pile is empty.
        """
        if (focus := self.contents.focus) is not None:
            return focus

        raise IndexError("No focus_position, Pile is empty")

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        :param position: index of child widget to be made focus
        :raises IndexError: *position* is not an index of a child widget.
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No Pile child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No Pile child widget at position {position}").with_traceback(exc.__traceback__) from exc
        self.contents.focus = position

    def get_pref_col(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
    ) -> int | Literal["left", "right", Align.LEFT, Align.RIGHT] | None:
        """Return the preferred column for the cursor, or None.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if not self.selectable():
            return None

        if not self.contents:
            return None

        _, _, size_args = self.get_rows_sizes(size, focus=self.selectable())
        self._update_pref_col_from_focus(size_args[self.focus_position])
        return self.pref_col

    @deprecated(
        "get_item_size is not used by the urwid code base and `get_rows_sizes` serves the same purpose. "
        "Deprecated since urwid 4.1.4, will be removed in version 7.0.",
        category=None,
    )
    def get_item_size(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        i: int,
        focus: bool,
        item_rows: list[int] | None = None,
    ) -> tuple[()] | tuple[int] | tuple[int, int]:
        """
        Return a size appropriate for passing to self.contents[i][0].render.

        :raises PileError: the item uses a height rule that needs size information the caller did not provide, or a
            height rule that is not supported.

        .. deprecated:: 4.1.4
            Not used by the urwid code base. Use :meth:`get_rows_sizes` instead.
            This API will be removed in version 7.0.
        """
        _deprecation.warn(
            "get_item_size is not used by the urwid code base and `get_rows_sizes` serves the same purpose.",
            since="4.1.4",
            removed_in="7.0",
        )
        _w, options = self.contents[i]
        f = options[0]
        if f == WHSettings.PACK:
            if not size:
                return ()
            return (size[0],)

        if not size:
            raise PileError(f"Element {i} using parameters {f} and do not have full size information")

        maxcol = size[0]

        if options[0] == WHSettings.GIVEN:
            return (maxcol, options[1])

        if f == WHSettings.WEIGHT:
            if len(size) == 2:
                if not item_rows:
                    item_rows = self.get_item_rows(size, focus)
                return (maxcol, item_rows[i])

            return (maxcol,)

        raise PileError(f"Unsupported item height rules: {f}")

    def _get_fixed_rows_sizes(
        self,
        focus: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int] | tuple[int] | tuple[()], ...]]:
        """Get rows widths, heights and render size parameters.

        Fixed case expect widget sizes calculation with several cycles for unknown height cases.

        :raises PileError: a child widget does not support a sizing mode this Pile needs, no child can provide a
            width, or the weights are too far apart to keep their ratio at a fixed size.
        """
        if not self.contents:
            return (), (), ()

        widths: dict[int, int] = {}
        heights: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}

        flow: list[tuple[AbstractWidget, int, bool]] = []
        box: list[int] = []
        weighted: dict[int | float, list[int]] = {}
        weights: list[int | float] = []
        weight_max_sizes: dict[int | float, int] = {}

        for idx, (widget, options) in enumerate(self.contents):
            size_kind = options[0]
            w_sizing = widget.sizing()
            focused = focus and self.focus == widget
            if options[0] == WHSettings.PACK:
                if Sizing.FIXED in w_sizing:
                    widths[idx], heights[idx] = typing.cast("AbstractFixedWidget", widget).pack((), focused)
                    w_h_args[idx] = ()
                if Sizing.FLOW in w_sizing:
                    # re-calculate height at the end
                    flow.append((widget, idx, focused))
                if not w_sizing & {Sizing.FIXED, Sizing.FLOW}:
                    raise PileError(f"Unsupported sizing {w_sizing} for {size_kind.upper()}")

            elif options[0] == WHSettings.GIVEN:
                heights[idx] = options[1]
                if Sizing.BOX in w_sizing:
                    box.append(idx)
                else:
                    raise PileError(f"Unsupported sizing {w_sizing} for {size_kind.upper()}")

            elif options[1] <= 0:
                widths[idx] = 0
                heights[idx] = 0
                if Sizing.FLOW in w_sizing:
                    w_h_args[idx] = (0,)
                else:
                    w_h_args[idx] = (0, 0)

            elif Sizing.FIXED in w_sizing and w_sizing & {Sizing.BOX, Sizing.FLOW}:
                width, height = typing.cast("AbstractFixedWidget", widget).pack((), focused)
                widths[idx] = width  # We're fitting everything in case of FIXED

                if Sizing.BOX in w_sizing:
                    size_weight = options[1]
                    weighted.setdefault(size_weight, []).append(idx)
                    weights.append(size_weight)

                    weight_max_sizes.setdefault(size_weight, height)
                    weight_max_sizes[size_weight] = max(weight_max_sizes[size_weight], height)

                else:
                    # width replace is allowed
                    flow.append((widget, idx, focused))

            elif Sizing.FLOW in w_sizing:
                # FLOW WEIGHT widgets are rendered the same as PACK WEIGHT
                flow.append((widget, idx, focused))
            else:
                raise PileError(f"Unsupported combination of {size_kind}, {w_sizing}")

        if not widths:
            raise PileError("No widgets providing width information")

        max_width = max(widths.values())

        for widget, idx, focused in flow:
            widths[idx] = max_width
            heights[idx] = typing.cast("AbstractFlowWidget", widget).rows((max_width,), focused)
            w_h_args[idx] = (max_width,)

        if weight_max_sizes:
            max_weighted_coefficient = max(height / weight for weight, height in weight_max_sizes.items())

            for weight in weight_max_sizes:
                try:
                    height = max(int(max_weighted_coefficient * weight + 0.5), 1)
                except OverflowError as exc:
                    raise PileError(
                        f"Weights of {self!r} are too far apart to keep their ratio at a fixed size"
                    ) from exc
                for idx in weighted[weight]:
                    heights[idx] = height
                    w_h_args[idx] = (max_width, height)

        for idx in box:
            widths[idx] = max_width
            w_h_args[idx] = (max_width, heights[idx])

        return (
            tuple(widths[idx] for idx in range(len(widths))),
            tuple(heights[idx] for idx in range(len(heights))),
            tuple(w_h_args[idx] for idx in range(len(w_h_args))),
        )

    def _get_flow_rows_sizes(
        self,
        size: tuple[int],
        focus: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int] | tuple[int] | tuple[()], ...]]:
        """Get rows widths, heights and render size parameters.

        Flow case is the simplest one: minimum cycles in the logic and no widgets manipulation.
        Here we can make some shortcuts

        :warns PileWarning: an item is not a widget, or its widget does not support the sizing its height type needs.
        """
        maxcol = size[0]
        if not self.contents:
            return (maxcol,), (0,), ()

        widths: tuple[int, ...] = (maxcol,) * len(self.contents)
        heights: list[int] = []
        w_h_args: list[tuple[int, int] | tuple[int] | tuple[()]] = []
        focus_position = self.focus_position

        for i, (w, options) in enumerate(self.contents):
            f = options[0]
            if isinstance(w, AbstractWidget):
                w_sizing = w.sizing()
            else:
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            focused = focus and i == focus_position

            if options[0] == WHSettings.GIVEN:
                height = options[1]
                heights.append(height)
                w_h_args.append((maxcol, height))
            elif Sizing.FLOW in w_sizing:
                heights.append(typing.cast("AbstractFlowWidget", w).rows((maxcol,), focus=focused))
                w_h_args.append((maxcol,))
            elif Sizing.FIXED in w_sizing and f == WHSettings.PACK:
                heights.append(typing.cast("AbstractFixedWidget", w).pack((), focused)[1])
                w_h_args.append(())
            else:
                warnings.warn(
                    f"Unusual widget {i} sizing {w_sizing} for {f.upper()}). "
                    f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for height calculation",
                    PileWarning,
                    stacklevel=3,
                )
                heights.append(typing.cast("AbstractFlowWidget", w).rows((maxcol,), focus=focused))
                w_h_args.append((maxcol,))

        return (widths, tuple(heights), tuple(w_h_args))

    def get_rows_sizes(
        self,
        size: tuple[int, int] | tuple[int] | tuple[()],
        focus: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int] | tuple[int] | tuple[()], ...]]:
        """Get rows widths, heights and render size parameters.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        :warns PileWarning: an item is not a widget, or its widget does not support the sizing its height type needs.
        """
        if not size:
            return self._get_fixed_rows_sizes(focus=focus)
        if len(size) == 1:
            return self._get_flow_rows_sizes(size, focus=focus)

        maxcol, maxrow = size
        if not self.contents:
            return (maxcol,), (maxrow,), ()

        remaining: int = maxrow

        widths: tuple[int, ...] = (maxcol,) * len(self.contents)
        heights: dict[int, int] = {}
        weighted: dict[int, int | float] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}
        focus_position = self.focus_position

        for i, (w, options) in enumerate(self.contents):
            f = options[0]
            if isinstance(w, AbstractWidget):
                w_sizing = w.sizing()
            else:
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            focused = focus and i == focus_position

            if options[0] == WHSettings.GIVEN:
                height = options[1]
                heights[i] = height
                w_h_args[i] = (maxcol, height)
                remaining -= height
            elif options[0] == WHSettings.PACK or len(size) == 1:
                if Sizing.FLOW in w_sizing:
                    w_h_arg: tuple[int] | tuple[()] = (maxcol,)
                elif Sizing.FIXED in w_sizing and f == WHSettings.PACK:
                    w_h_arg = ()
                else:
                    warnings.warn(
                        f"Unusual widget {i} sizing {w_sizing} for {f.upper()}). "
                        f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for height calculation",
                        PileWarning,
                        stacklevel=3,
                    )
                    w_h_arg = (maxcol,)

                # widget kind and size arguments matched separately
                item_height = w.pack(w_h_arg, focused)[1]  # type: ignore[arg-type]
                heights[i] = item_height
                w_h_args[i] = w_h_arg
                remaining -= item_height
            elif options[1]:
                weighted[i] = options[1]
            else:
                heights[i] = 0
                w_h_args[i] = (maxcol, 0)  # zero-weighted items treated as ('given', 0)

        if remaining <= 0 and focus_position in weighted:
            # We need to hide some widgets: focused part will be not displayed by default
            # At this place we have to operate also negative "remaining" to be sure that widget really fit
            before = []
            after = []
            for idx, height in heights.items():
                if height:
                    if idx < focus_position:
                        before.append(idx)
                    else:
                        after.append(idx)

            # Try to move to the center
            offset = len(before) - len(after)
            if not offset:
                indexes: Iterable[int] = itertools.chain.from_iterable(zip(after[::-1], before, strict=True))
            elif offset > 0:
                indexes = (
                    *before[:offset],
                    *itertools.chain.from_iterable(zip(after[::-1], before[offset:], strict=True)),
                )
            else:
                indexes = (
                    *after[-1 : offset - 1 : -1],
                    *itertools.chain.from_iterable(zip(after[offset - 1 :: -1], before, strict=True)),
                )

            for idx in indexes:
                height, heights[idx] = heights[idx], 0
                remaining += height
                if remaining > 0:
                    break

        remaining = max(remaining, 0)

        if weighted and (max_weight := max(weighted.values())) > sys.float_info.max / (
            len(weighted) * max(remaining, 1)
        ):
            # remaining * sum_weight could overflow a float: scale weights to at most 1, keeping their ratios
            weighted = {idx: weight / max_weight for idx, weight in weighted.items()}

        sum_weight = sum(weighted.values())

        for idx in sorted(weighted, key=lambda idx: (idx != focus_position, idx)):
            # We have to sort weighted items way that focused widget will gain render priority
            if remaining == 0:
                rows = 0
            else:
                rows = int(float(remaining) * weighted[idx] / sum_weight + 0.5)
                if not rows and idx == focus_position:
                    # Special case: we have to force as minimum 1 row for focused widget to prevent broken behaviour
                    rows = 1
                remaining -= rows
                sum_weight -= weighted[idx]

            heights[idx] = rows
            w_h_args[idx] = (maxcol, rows)

        return (
            widths,
            tuple(heights[idx] for idx in range(len(heights))),
            tuple(w_h_args[idx] for idx in range(len(w_h_args))),
        )

    def pack(self, size: tuple[()] | tuple[int] | tuple[int, int] = (), focus: bool = False) -> tuple[int, int]:
        """Get packed size for widget.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if size:
            return super().pack(size, focus)
        widths, heights, _ = self.get_rows_sizes(size, focus)
        return (max(widths), sum(heights))

    def get_item_rows(self, size: tuple[int] | tuple[int, int], focus: bool) -> list[int]:
        """Return the number of rows used by each widget in self.contents.

        The result is the heights part of :meth:`get_rows_sizes`.
        """
        return list(self.get_rows_sizes(size, focus)[1])

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> SolidCanvas | CompositeCanvas:
        """
        Render the Pile and return the resulting canvas.

        :raises ValueError: the Pile is empty and no *size* was given.
        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        _widths, heights, size_args = self.get_rows_sizes(size, focus)

        combinelist = []
        for i, (height, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents, strict=False)):
            item_focus = self.focus == w
            canv = None
            if height > 0:
                # widget kind and size arguments matched separately
                canv = w.render(w_size, focus=focus and item_focus)  # type: ignore[arg-type]

            if canv:
                combinelist.append((canv, i, item_focus))

        if not combinelist:
            if not size:
                raise ValueError("size must be provided when no contents are present")

            return SolidCanvas(" ", size[0], (*size[1:], 0)[0])

        out = CanvasCombine(combinelist)
        if len(size) == 2 and size[1] != out.rows():
            # flow/fixed widgets rendered too large/small
            out = CompositeCanvas(out)
            out.pad_trim_top_bottom(0, size[1] - out.rows())
        return out

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focus widget.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if not self.selectable():
            return None

        if (get_cursor_coords := getattr(self.focus, "get_cursor_coords", None)) is not None:
            i = self.focus_position
            _widths, heights, size_args = self.get_rows_sizes(size, focus=True)

            if (coords := get_cursor_coords(size_args[i])) is not None:  # pylint: disable=not-callable
                x, y = coords
                if i > 0:
                    y += sum(heights[:i])

                return x, y

        return None

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the total number of rows occupied by all of the pile's widgets."""
        return sum(self.get_rows_sizes(size, focus)[1])

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the keypress to the widget in focus.

        Unhandled :kbd:`up` and :kbd:`down` keys may cause a focus change.
        With :attr:`select_navigation`, so do unhandled ``'next selectable'`` and ``'prev selectable'`` commands.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        if not self.contents:
            return key

        i = self.focus_position
        _widths, heights, size_args = self.get_rows_sizes(size, focus=self.selectable())
        if self.selectable():
            if (processed := self.focus.keypress(size_args[i], key)) is not None:  # type: ignore[union-attr]
                key = processed
            else:
                return None
            if self.select_navigation and self._command_map[key] in _SELECT_COMMANDS:
                return self._select_keypress_unhandled(key)
            if self._command_map[key] not in {Command.UP, Command.DOWN} or not self.contents:
                return key
            # The child may have changed this Pile's contents or focus while handling the key,
            # so the sizes are recalculated and the candidates are taken from the current focus.
            _widths, heights, size_args = self.get_rows_sizes(size, focus=True)

        for j in self._select_candidates(reverse=self._command_map[key] == Command.UP, from_edge=False):
            w = self.contents[j][0]
            self._update_pref_col_from_focus(size_args[self.focus_position])
            self.focus_position = j
            if not hasattr(w, "move_cursor_to_coords"):
                return None

            rows = heights[j]
            if self._command_map[key] == Command.UP:
                rowlist = tuple(range(rows - 1, -1, -1))
            else:  # self._command_map[key] == 'cursor down'
                rowlist = tuple(range(rows))
            for row in rowlist:
                if w.move_cursor_to_coords(size_args[j], self.pref_col, row):
                    break
            return None

        # nothing to select
        return key

    def _update_pref_col_from_focus(self, w_size: tuple[()] | tuple[int] | tuple[int, int]) -> None:
        """Update self.pref_col from the focus widget."""
        if (get_pref_col := getattr(self.focus, "get_pref_col", None)) is not None:  # noqa: SIM102
            if (pref_col := get_pref_col(w_size)) is not None:  # pylint: disable=not-callable
                self.pref_col = pref_col

    def move_cursor_to_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        col: int | Literal["left", "right", Align.LEFT, Align.RIGHT],
        row: int,
    ) -> bool:
        """Capture pref col and set new focus.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.
        """
        self.pref_col = col

        # FIXME guessing focus==True
        focus = True
        wrow = 0
        _widths, heights, size_args = self.get_rows_sizes(size, focus=focus)
        for i, (r, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents, strict=False)):  # noqa: B007
            if wrow + r > row:
                break
            wrow += r
        else:
            return False

        if not w.selectable():
            return False

        if hasattr(w, "move_cursor_to_coords") and w.move_cursor_to_coords(w_size, col, row - wrow) is False:
            return False

        # The child may have changed this Pile's contents while moving its cursor.
        if i >= len(self.contents) or self.contents[i][0] is not w:
            return False

        self.focus_position = i
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
        """Pass the event to the contained widget.

        May change focus on button 1 press.

        :raises PileError: *size* is ``()`` and the children cannot be sized as a fixed widget.

        .. deprecated:: 2.4.0
            Support for a child that does not implement ``mouse_event`` is deprecated.
            Support will be removed in version 7.0.
        """
        wrow = 0
        _widths, heights, size_args = self.get_rows_sizes(size, focus=focus)

        for i, (height, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents, strict=False)):  # noqa: B007
            if wrow + height > row:
                target_row = row - wrow
                break
            wrow += height
        else:
            return False

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
        return w.mouse_event(
            w_size,  # type: ignore[arg-type]
            event,
            button,
            col,
            target_row,
            focus and self.focus == w,
        )
