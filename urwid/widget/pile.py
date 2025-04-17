from __future__ import annotations

import typing
import warnings
from itertools import chain, repeat

from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .constants import Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin, _ContainerElementSizingFlag
from .monitored_list import MonitoredFocusList, MonitoredList
from .widget import Widget, WidgetError, WidgetWarning

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from typing_extensions import Literal


class PileError(WidgetError):
    """Pile related errors."""


class PileWarning(WidgetWarning):
    """Pile related warnings."""


class Pile(Widget, WidgetContainerMixin, WidgetContainerListContentsMixin):
    """
    A pile of widgets stacked vertically from top to bottom
    """

    def sizing(self) -> frozenset[Sizing]:
        """Sizing supported by widget.

        :return: Calculated widget sizing
        :rtype: frozenset[Sizing]

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

        box_flow_fixed = (
            _ContainerElementSizingFlag.BOX | _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED
        )
        flow_fixed = _ContainerElementSizingFlag.FLOW | _ContainerElementSizingFlag.FIXED

        for idx, (widget, (size_kind, _size_weight)) in enumerate(self.contents):
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
                    flag |= _ContainerElementSizingFlag.FLOW

            else:
                flag = _ContainerElementSizingFlag.WH_PACK
                if Sizing.FLOW in w_sizing:
                    flag |= _ContainerElementSizingFlag.FLOW
                if Sizing.FIXED in w_sizing:
                    flag |= _ContainerElementSizingFlag.FIXED

            if not flag & box_flow_fixed:
                warnings.warn(
                    f"Sizing combination of widget {idx} not supported: {size_kind.name} {'|'.join(w_sizing).upper()}",
                    PileWarning,
                    stacklevel=3,
                )
                return frozenset((Sizing.BOX, Sizing.FLOW))

            if flag & _ContainerElementSizingFlag.BOX:
                supported.add(Sizing.BOX)
                if not flag & flow_fixed:
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
            Widget
            | tuple[Literal["pack", WHSettings.PACK] | int, Widget]
            | tuple[Literal["given", WHSettings.GIVEN], int, Widget]
            | tuple[Literal["weight", WHSettings.WEIGHT], int | float, Widget]
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
            always treat *widget* as a box widget and give it *given_height* rows, where given_height is an int
        (``'pack'``, *widget*)
            allow *widget* to calculate its own height by calling its :meth:`rows` method,
            i.e. treat it as a flow widget.
        (``'weight'``, *weight*, *widget*)
            if the pile is treated as a box widget then treat widget as a box
            widget with a height based on its relative weight value, otherwise treat the same as (``'pack'``, *widget*).

        Widgets not in a tuple are the same as (``'weight'``, ``1``, *widget*)`

        .. note:: If the Pile is treated as a box widget there must be at least
            one ``'weight'`` tuple in :attr:`widget_list`.
        """
        self._selectable = False
        super().__init__()
        self._contents: MonitoredFocusList[
            Widget,
            tuple[Literal[WHSettings.PACK], None]
            | tuple[Literal[WHSettings.GIVEN], int]
            | tuple[Literal[WHSettings.WEIGHT], int | float],
        ] = MonitoredFocusList()
        self._contents.set_modified_callback(self._contents_modified)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._validate_contents_modified)

        for i, original in enumerate(widget_list):
            w = original
            if not isinstance(w, tuple):
                self.contents.append((w, (WHSettings.WEIGHT, 1)))
            elif w[0] in {Sizing.FLOW, WHSettings.PACK}:  # 'pack' used to be called 'flow'
                f, w = w
                self.contents.append((w, (WHSettings.PACK, None)))
            elif len(w) == 2 or w[0] in {Sizing.FIXED, WHSettings.GIVEN}:  # backwards compatibility
                height, w = w[-2:]
                self.contents.append((w, (WHSettings.GIVEN, height)))
            elif w[0] == WHSettings.WEIGHT:
                f, height, w = w
                self.contents.append((w, (f, height)))
            else:
                raise PileError(f"initial widget list item invalid {original!r}")
            if focus_item is None and w.selectable():
                focus_item = i

            if not isinstance(w, Widget):
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)

        if self.contents and focus_item is not None:
            self.focus = focus_item

        self.pref_col = 0

    def _repr_words(self) -> list[str]:
        if len(self.contents) > 1:
            contents_string = f"({len(self.contents)} items)"
        elif self.contents:
            contents_string = "(1 item)"
        else:
            contents_string = "()"
        return [*super()._repr_words(), contents_string]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {**super()._repr_attrs(), "focus_item": self.focus_position if len(self._contents) > 1 else None}
        return remove_defaults(attrs, Pile.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        widget_list: list[
            Widget
            | tuple[Literal[WHSettings.PACK] | int, Widget]
            | tuple[Literal[WHSettings.WEIGHT], int | float, Widget]
        ] = []

        for w_instance, (sizing, amount) in self._contents:
            if sizing == WHSettings.GIVEN:
                widget_list.append((amount, w_instance))
            elif sizing == WHSettings.PACK:
                widget_list.append((WHSettings.PACK, w_instance))
            elif sizing == WHSettings.WEIGHT:
                if amount == 1:
                    widget_list.append(w_instance)
                else:
                    widget_list.append((WHSettings.WEIGHT, amount, w_instance))

        yield "widget_list", widget_list
        yield "focus_item", self.focus_position if self._contents else None

    def __len__(self) -> int:
        return len(self._contents)

    def _contents_modified(self) -> None:
        """Recalculate whether this widget should be selectable whenever the contents has been changed."""
        self._selectable = any(w.selectable() for w, o in self.contents)
        self._invalidate()

    def _validate_contents_modified(self, slc, new_items) -> None:
        invalid_items: list[tuple[Widget, tuple[typing.Any, typing.Any]]] = []
        try:
            for item in new_items:
                _w, (t, n) = item
                if any(
                    (
                        t not in {WHSettings.PACK, WHSettings.GIVEN, WHSettings.WEIGHT},
                        (n is not None and (not isinstance(n, (int, float)) or n < 0)),
                    )
                ):
                    invalid_items.append(item)

        except (TypeError, ValueError) as exc:
            raise PileError(f"added content invalid: {exc}").with_traceback(exc.__traceback__) from exc

        if invalid_items:
            raise PileError(f"added content invalid: {invalid_items!r}")

    @property
    def widget_list(self):
        """
        A list of the widgets in this Pile

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents`.
        """
        warnings.warn(
            "only for backwards compatibility. You should use the new standard container property `contents`."
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
            "only for backwards compatibility. You should use the new standard container property `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
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
            "only for backwards compatibility. You should use the new standard container property `contents`."
            "API will be removed in version 5.0.",
            DeprecationWarning,
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
    def contents(
        self,
    ) -> MonitoredFocusList[
        Widget,
        tuple[Literal[WHSettings.PACK], None]
        | tuple[Literal[WHSettings.GIVEN], int]
        | tuple[Literal[WHSettings.WEIGHT], int | float],
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
        c: Sequence[
            Widget,
            tuple[Literal[WHSettings.PACK], None]
            | tuple[Literal[WHSettings.GIVEN], int]
            | tuple[Literal[WHSettings.WEIGHT], int | float],
        ],
    ) -> None:
        self._contents[:] = c

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
            ``'fixed'`` or a weight value (number) for ``'weight'``
        """

        if height_type == WHSettings.PACK:
            return (WHSettings.PACK, None)
        if height_type in {WHSettings.GIVEN, WHSettings.WEIGHT} and height_amount is not None:
            return (height_type, height_amount)
        raise PileError(f"invalid combination: height_type={height_type!r}, height_amount={height_amount!r}")

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

    def get_focus(self) -> Widget | None:
        """
        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        warnings.warn(
            "for backwards compatibility."
            "You may also use the new standard container property .focus to get the child widget in focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    def set_focus(self, item: Widget | int) -> None:
        warnings.warn(
            "for backwards compatibility."
            "You may also use the new standard container property .focus to get the child widget in focus."
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
        raise ValueError(f"Widget not found in Pile contents: {item!r}")

    @property
    def focus_item(self):
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container properties "
            "`focus` and `focus_position` to get the child widget in focus or modify the focus position."
            "API will be removed in version 4.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.focus

    @focus_item.setter
    def focus_item(self, new_item):
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container properties "
            "`focus` and `focus_position` to get the child widget in focus or modify the focus position."
            "API will be removed in version 4.0.",
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

    def get_pref_col(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> int | None:
        """Return the preferred column for the cursor, or None."""
        if not self.selectable():
            return None

        if not self.contents:
            return None

        _, _, size_args = self.get_rows_sizes(size, focus=self.selectable())
        self._update_pref_col_from_focus(size_args[self.focus_position])
        return self.pref_col

    def get_item_size(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        i: int,
        focus: bool,
        item_rows: list[int] | None = None,
    ) -> tuple[()] | tuple[int] | tuple[int, int]:
        """
        Return a size appropriate for passing to self.contents[i][0].render
        """
        warnings.warn(
            "get_item_size is going to be deprecated and can be removed soon."
            "This method is not used by the urwid codebase and `get_rows_sizes` is used for the similar purposes.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        _w, (f, height) = self.contents[i]
        if f == WHSettings.PACK:
            if not size:
                return ()
            return (size[0],)

        if not size:
            raise PileError(f"Element {i} using parameters {f} and do not have full size information")

        maxcol = size[0]

        if f == WHSettings.GIVEN:
            return (maxcol, height)

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
    ) -> tuple[Sequence[int], Sequence[int], Sequence[tuple[int] | tuple[()]]]:
        """Get rows widths, heights and render size parameters

        Fixed case expect widget sizes calculation with several cycles for unknown height cases.
        """
        if not self.contents:
            return (), (), ()

        widths: dict[int, int] = {}
        heights: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}

        flow: list[tuple[Widget, int, bool]] = []
        box: list[int] = []
        weighted: dict[int, list[int]] = {}
        weights: list[int] = []
        weight_max_sizes: dict[int, int] = {}

        for idx, (widget, (size_kind, size_weight)) in enumerate(self.contents):
            w_sizing = widget.sizing()
            focused = focus and self.focus == widget
            if size_kind == WHSettings.PACK:
                if Sizing.FIXED in w_sizing:
                    widths[idx], heights[idx] = widget.pack((), focused)
                    w_h_args[idx] = ()
                if Sizing.FLOW in w_sizing:
                    # re-calculate height at the end
                    flow.append((widget, idx, focused))
                if not w_sizing & {Sizing.FIXED, Sizing.FLOW}:
                    raise PileError(f"Unsupported sizing {w_sizing} for {size_kind.upper()}")

            elif size_kind == WHSettings.GIVEN:
                heights[idx] = size_weight
                if Sizing.BOX in w_sizing:
                    box.append(idx)
                else:
                    raise PileError(f"Unsupported sizing {w_sizing} for {size_kind.upper()}")

            elif size_weight <= 0:
                widths[idx] = 0
                heights[idx] = 0
                if Sizing.FLOW in w_sizing:
                    w_h_args[idx] = (0,)
                else:
                    w_sizing[idx] = (0, 0)

            elif Sizing.FIXED in w_sizing and w_sizing & {Sizing.BOX, Sizing.FLOW}:
                width, height = widget.pack((), focused)
                widths[idx] = width  # We're fitting everything in case of FIXED

                if Sizing.BOX in w_sizing:
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
            heights[idx] = widget.rows((max_width,), focused)
            w_h_args[idx] = (max_width,)

        if weight_max_sizes:
            max_weighted_coefficient = max(height / weight for weight, height in weight_max_sizes.items())

            for weight in weight_max_sizes:
                height = max(int(max_weighted_coefficient * weight + 0.5), 1)
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
    ) -> tuple[Sequence[int], Sequence[int], Sequence[tuple[int] | tuple[()]]]:
        """Get rows widths, heights and render size parameters

        Flow case is the simplest one: minimum cycles in the logic and no widgets manipulation.
        Here we can make some shortcuts
        """
        maxcol = size[0]
        if not self.contents:
            return (maxcol,), (0,), ()

        widths: Sequence[int] = (maxcol,) * len(self.contents)
        heights: list[int] = []
        w_h_args: list[tuple[int, int] | tuple[int] | tuple[()]] = []
        focus_position = self.focus_position

        for i, (w, (f, height)) in enumerate(self.contents):
            if isinstance(w, Widget):
                w_sizing = w.sizing()
            else:
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            focused = focus and i == focus_position

            if f == WHSettings.GIVEN:
                heights.append(height)
                w_h_args.append((maxcol, height))
            elif Sizing.FLOW in w_sizing:
                heights.append(w.rows((maxcol,), focus=focused))
                w_h_args.append((maxcol,))
            elif Sizing.FIXED in w_sizing and f == WHSettings.PACK:
                heights.append(w.pack((), focused)[1])
                w_h_args.append(())
            else:
                warnings.warn(
                    f"Unusual widget {i} sizing {w_sizing} for {f.upper()}). "
                    f"Assuming wrong sizing and using {Sizing.FLOW.upper()} for height calculation",
                    PileWarning,
                    stacklevel=3,
                )
                heights.append(w.rows((maxcol,), focus=focused))
                w_h_args.append((maxcol,))

        return (widths, tuple(heights), tuple(w_h_args))

    def get_rows_sizes(
        self,
        size: tuple[int, int] | tuple[int] | tuple[()],
        focus: bool = False,
    ) -> tuple[Sequence[int], Sequence[int], Sequence[tuple[int, int] | tuple[int] | tuple[()]]]:
        """Get rows widths, heights and render size parameters"""
        if not size:
            return self._get_fixed_rows_sizes(focus=focus)
        if len(size) == 1:
            return self._get_flow_rows_sizes(size, focus=focus)

        maxcol, maxrow = size
        if not self.contents:
            return (maxcol,), (maxrow,), ()

        remaining: int = maxrow

        widths: Sequence[int] = (maxcol,) * len(self.contents)
        heights: dict[int, int] = {}
        weighted: dict[int, int] = {}
        w_h_args: dict[int, tuple[int, int] | tuple[int] | tuple[()]] = {}
        focus_position = self.focus_position

        for i, (w, (f, height)) in enumerate(self.contents):
            if isinstance(w, Widget):
                w_sizing = w.sizing()
            else:
                warnings.warn(f"{w!r} is not a Widget", PileWarning, stacklevel=3)
                w_sizing = frozenset((Sizing.FLOW, Sizing.BOX))

            focused = focus and i == focus_position

            if f == WHSettings.GIVEN:
                heights[i] = height
                w_h_args[i] = (maxcol, height)
                remaining -= height
            elif f == WHSettings.PACK or len(size) == 1:
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

                item_height = w.pack(w_h_arg, focused)[1]
                heights[i] = item_height
                w_h_args[i] = w_h_arg
                remaining -= item_height
            elif height:
                weighted[i] = height
            else:
                heights[i] = 0
                w_h_args[i] = (maxcol, 0)  # zero-weighted items treated as ('given', 0)

        sum_weight = sum(weighted.values())
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
                indexes = (element for pair in zip(after[::-1], before) for element in pair)
            elif offset > 0:
                indexes = (
                    *before[:offset],
                    *(element for pair in zip(after[::-1], before[offset:]) for element in pair),
                )
            else:
                indexes = (
                    *after[-1 : offset - 1 : -1],
                    *(element for pair in zip(after[offset - 1 :: -1], before) for element in pair),
                )

            for idx in indexes:
                height, heights[idx] = heights[idx], 0
                remaining += height
                if remaining > 0:
                    break

        remaining = max(remaining, 0)

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
        """Get packed sized for widget."""
        if size:
            return super().pack(size, focus)
        widths, heights, _ = self.get_rows_sizes(size, focus)
        return (max(widths), sum(heights))

    def get_item_rows(self, size: tuple[int] | tuple[int, int], focus: bool) -> list[int]:
        """A list of the number of rows used by each widget in self.contents.

        This method is a normally used only by `get_item_size` for the BOX case..
        """
        return list(self.get_rows_sizes(size, focus)[1])

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> SolidCanvas | CompositeCanvas:
        _widths, heights, size_args = self.get_rows_sizes(size, focus)

        combinelist = []
        for i, (height, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents)):
            item_focus = self.focus == w
            canv = None
            if height > 0:
                canv = w.render(w_size, focus=focus and item_focus)

            if canv:
                combinelist.append((canv, i, item_focus))

        if not combinelist:
            return SolidCanvas(" ", size[0], (*size[1:], 0)[0])

        out = CanvasCombine(combinelist)
        if len(size) == 2 and size[1] != out.rows():
            # flow/fixed widgets rendered too large/small
            out = CompositeCanvas(out)
            out.pad_trim_top_bottom(0, size[1] - out.rows())
        return out

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focus widget."""
        if not self.selectable():
            return None
        if not hasattr(self.focus, "get_cursor_coords"):
            return None

        i = self.focus_position
        _widths, heights, size_args = self.get_rows_sizes(size, focus=True)
        if (coords := self.focus.get_cursor_coords(size_args[i])) is not None:
            x, y = coords
            if i > 0:
                y += sum(heights[:i])

            return x, y

        return None

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return sum(self.get_rows_sizes(size, focus)[1])

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the keypress to the widget in focus.

        Unhandled 'up' and 'down' keys may cause a focus change.
        """
        if not self.contents:
            return key

        i = self.focus_position
        _widths, heights, size_args = self.get_rows_sizes(size, focus=self.selectable())
        if self.selectable():
            key = self.focus.keypress(size_args[i], key)
            if self._command_map[key] not in {Command.UP, Command.DOWN}:
                return key

        if self._command_map[key] == Command.UP:
            candidates = tuple(range(i - 1, -1, -1))  # count backwards to 0
        else:  # self._command_map[key] == 'cursor down'
            candidates = tuple(range(i + 1, len(self.contents)))

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self._update_pref_col_from_focus(size_args[self.focus_position])
            self.focus_position = j
            if not hasattr(self.focus, "move_cursor_to_coords"):
                return None

            rows = heights[j]
            if self._command_map[key] == Command.UP:
                rowlist = tuple(range(rows - 1, -1, -1))
            else:  # self._command_map[key] == 'cursor down'
                rowlist = tuple(range(rows))
            for row in rowlist:
                if self.focus.move_cursor_to_coords(size_args[self.focus_position], self.pref_col, row):
                    break
            return None

        # nothing to select
        return key

    def _update_pref_col_from_focus(self, w_size: tuple[()] | tuple[int] | tuple[int, int]) -> None:
        """Update self.pref_col from the focus widget."""

        if not hasattr(self.focus, "get_pref_col"):
            return

        if (pref_col := self.focus.get_pref_col(w_size)) is not None:
            self.pref_col = pref_col

    def move_cursor_to_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        col: int,
        row: int,
    ) -> bool:
        """Capture pref col and set new focus."""
        self.pref_col = col

        # FIXME guessing focus==True
        focus = True
        wrow = 0
        _widths, heights, size_args = self.get_rows_sizes(size, focus=focus)
        for i, (r, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents)):  # noqa: B007
            if wrow + r > row:
                break
            wrow += r
        else:
            return False

        if not w.selectable():
            return False

        if hasattr(w, "move_cursor_to_coords") and w.move_cursor_to_coords(w_size, col, row - wrow) is False:
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
        """
        wrow = 0
        _widths, heights, size_args = self.get_rows_sizes(size, focus=focus)

        for i, (height, w_size, (w, _)) in enumerate(zip(heights, size_args, self.contents)):  # noqa: B007
            if wrow + height > row:
                target_row = row - wrow
                break
            wrow += height
        else:
            return False

        if is_mouse_press(event) and button == 1 and w.selectable():
            self.focus_position = i

        if not hasattr(w, "mouse_event"):
            warnings.warn(
                f"{w.__class__.__module__}.{w.__class__.__name__} is not subclass of Widget",
                DeprecationWarning,
                stacklevel=2,
            )
            return False

        return w.mouse_event(w_size, event, button, col, target_row, focus and self.focus == w)
