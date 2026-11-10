"""Frame: a container with a body and an optional header and footer."""

from __future__ import annotations

import typing
from collections.abc import MutableMapping
from typing import Literal

from urwid import _deprecation
from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .constants import MouseButton, Sizing, VAlign
from .container import (
    _SELECT_COMMANDS,
    SelectNavigationMixin,
)
from .filler import Filler
from .widget import (
    AbstractBoxWidget,
    AbstractFlowWidget,
    AbstractWidget,
    Widget,
    WidgetError,
    _InvalidatingAttribute,
    _select_enter_child,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from urwid.canvas import Canvas


BodyWidget = typing.TypeVar("BodyWidget", bound=AbstractBoxWidget)
HeaderWidget = typing.TypeVar("HeaderWidget", bound=AbstractFlowWidget | None)
FooterWidget = typing.TypeVar("FooterWidget", bound=AbstractFlowWidget | None)


class FrameError(WidgetError):
    """Frame related errors."""


def _check_widget_subclass(widget: AbstractWidget | None) -> None:
    if widget is None:
        return

    if not isinstance(widget, AbstractWidget):
        obj_class_path = f"{widget.__class__.__module__}.{widget.__class__.__name__}"
        _deprecation.warn(f"{obj_class_path} is not implementing Widget API.", since="2.4.0", removed_in="7.0")


def _check_min_body_rows(rows: int) -> None:
    """Reject a minimum of body rows that is not a non-negative integer.

    :raises TypeError: *rows* is not an integer.
    :raises ValueError: *rows* is negative.
    """
    if not isinstance(rows, int):
        raise TypeError(f"min_body_rows must be an integer, got {rows!r}")
    if rows < 0:
        raise ValueError(f"min_body_rows must not be negative, got {rows!r}")


def _check_trim_first(part: Literal["header", "footer"]) -> None:
    """Reject a part other than the header or the footer.

    :raises ValueError: *part* is not the string ``'header'`` or ``'footer'``.
    """
    # A tuple compares by equality and needs no hash, so an unhashable value gets the same error as any other.
    if not isinstance(part, str) or part not in ("header", "footer"):
        raise ValueError(f"trim_first must be 'header' or 'footer', got {part!r}")


class _FrameContents(
    MutableMapping[
        Literal["header", "footer", "body"],
        tuple[BodyWidget | HeaderWidget | FooterWidget, None],
    ]
):
    """Mapping view onto a Frame's `header`, `body`, and `footer` slots, as :attr:`Frame.contents` returns it."""

    __slots__ = ("__weakref__", "_frame")

    def __init__(self, frame: Frame[BodyWidget, HeaderWidget, FooterWidget]) -> None:
        """Hold the Frame the view reads and writes."""
        self._frame = frame

    def __len__(self) -> int:
        """Return the number of parts the Frame has."""
        return len(self._frame._contents_keys())

    def __getitem__(
        self,
        key: Literal["header", "footer", "body"],
    ) -> tuple[BodyWidget | HeaderWidget | FooterWidget, None]:
        """Return the ``(widget, options)`` pair for *key*.

        :raises KeyError: *key* is not one of the three frame parts, or names a part this Frame does not have.
        """
        return self._frame._contents__getitem__(key)

    def __setitem__(
        self,
        key: Literal["header", "footer", "body"],
        value: tuple[BodyWidget | HeaderWidget | FooterWidget, None],
    ) -> None:
        """Replace the ``(widget, options)`` pair for *key*.

        :raises KeyError: *key* is not one of the three frame parts.
        :raises FrameError: *value* is not a valid ``(widget, options)`` pair.
        """
        # The overloads pair each key with its own widget type; this view takes any key with any of them.
        self._frame._contents__setitem__(key, value)  # type: ignore[arg-type]

    def __delitem__(self, key: Literal["header", "footer", "body"]) -> None:
        """Remove the header or footer.

        :raises KeyError: *key* is not a removable part, or names a part this Frame does not have.
        """
        self._frame._contents__delitem__(key)  # type: ignore[arg-type]

    def __iter__(self) -> Iterator[Literal["header", "footer", "body"]]:
        """Yield the keys of the parts the Frame has, the body first."""
        yield from self._frame._contents_keys()

    def __repr__(self) -> str:
        """Return the parts and the Frame."""
        return f"<FrameContents({dict(self)}) for {self._frame}>"

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield the ``(key, (widget, options))`` items."""
        yield from self.items()


class Frame(
    Widget,
    SelectNavigationMixin[Literal["header", "footer", "body"]],
    typing.Generic[BodyWidget, HeaderWidget, FooterWidget],
):
    """Frame widget is a box widget with optional header and footer flow widgets placed above and below it.

    It also accepts a flow size, when its body does: the header, the body and the footer then take all their rows.
    It reports FLOW sizing only with :attr:`flow` set, so containers lay it out as a box widget by default.

    .. note:: The main difference between a Frame and a :class:`Pile` widget
        defined as: `Pile([('pack', header), body, ('pack', footer)])` is that
        the Frame will not automatically change focus up and down in response to keystrokes.

    Sends ``"focus changed"`` after :attr:`focus_part` changed, also when removing the header or the footer in focus
    moves the focus to the body.
    Its handlers receive the frame, the old and the new focus part.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed"]

    _selectable = True
    _sizing = frozenset([Sizing.BOX])
    #: Whether this Frame reports FLOW sizing as well, when its body reports it; see :meth:`sizing`.
    flow = _InvalidatingAttribute[bool](default=False)
    #: Rows the body takes in a box size right after the part in focus; see :meth:`frame_top_bottom`.
    min_body_rows = _InvalidatingAttribute[int](default=0, validate=_check_min_body_rows)
    #: The part that gives up its rows first, ``'header'`` or ``'footer'``, while the body is in focus.
    trim_first = _InvalidatingAttribute[Literal["header", "footer"]](default="header", validate=_check_trim_first)

    def __init__(
        self,
        body: BodyWidget,
        header: HeaderWidget | None = None,
        footer: FooterWidget | None = None,
        focus_part: Literal["header", "footer", "body"] | AbstractWidget = "body",
        *,
        select_navigation: bool = False,
        flow: bool = False,
        min_body_rows: int = 0,
        trim_first: Literal["header", "footer"] = "header",
    ) -> None:
        """Initialize a new Frame instance.

        :param body: a box widget for the body of the frame, and a flow widget as well for a flow size
        :param header: a flow widget for above the body (or None)
        :param footer: a flow widget for below the body (or None)
        :param focus_part:  'header', 'footer' or 'body'
        :param select_navigation: handle the ``'next selectable'`` and ``'prev selectable'`` commands,
            see :ref:`select-navigation`.
        :param flow: report FLOW sizing as well when the body reports it, see :attr:`flow`.
        :param min_body_rows: rows the body keeps on a short screen, see :meth:`frame_top_bottom`.
        :param trim_first: ``'header'`` or ``'footer'``, the part trimmed first while the body is in focus,
            see :meth:`frame_top_bottom`.
        :raises TypeError: *min_body_rows* is not an integer.
        :raises ValueError: *focus_part* is not one of the three frame parts.
            *min_body_rows* is negative.
            *trim_first* is not ``'header'`` or ``'footer'``.

        .. deprecated:: 2.4.0
            Passing a header, body or footer that does not implement the Widget API is deprecated.
            Support will be removed in version 7.0.
        """
        super().__init__()

        self._header = header
        self._body = body
        self._footer = footer
        if focus_part in {"header", "footer", "body"}:
            self.focus_part = focus_part
        elif focus_part == header:
            self.focus_part = "header"
        elif focus_part == footer:
            self.focus_part = "footer"
        elif focus_part == body:
            self.focus_part = "body"
        else:
            raise ValueError(f"Invalid focus part {focus_part!r}")
        self.select_navigation = select_navigation
        self.flow = flow
        self.min_body_rows = min_body_rows
        self.trim_first = trim_first

        _check_widget_subclass(header)
        _check_widget_subclass(body)
        _check_widget_subclass(footer)

    def __setstate__(self, state: typing.Any) -> None:
        """Restore the attributes from a pickle or a copy.

        Pickles of urwid 5.0.x and older store the focus part as ``focus_part``, which is restored as ``_focus_part``.

        :param state: the instance dictionary, or ``(dictionary, slots)`` for a subclass with slots.
        :raises ValueError: the state has no focus part.
            Its focus part is not ``'header'``, ``'footer'`` or ``'body'``.
            It has the focus part more than once: under both names, or in both the dictionary and the slots.
        """
        attributes, slots = state if isinstance(state, tuple) else (state, None)
        attributes = dict(attributes or {})
        slots = dict(slots or {})
        # the places a focus part can be stored: the old name, the current one, and a slot of a subclass
        stored = [
            holder.pop(name)
            for holder, name in ((attributes, "focus_part"), (attributes, "_focus_part"), (slots, "_focus_part"))
            if name in holder
        ]
        if not stored:
            raise ValueError("Frame state has no focus part")
        if len(stored) > 1:
            raise ValueError("Frame state has the focus part more than once")
        (part,) = stored
        # an exact str, so that a value which only compares equal to a part name is rejected, a str subclass included
        if type(part) is not str or part not in {"header", "footer", "body"}:  # pylint: disable=unidiomatic-typecheck
            raise ValueError(f"Frame state has an invalid focus part: {part!r}")
        vars(self).update(attributes)
        # into the slot of a subclass that has one, otherwise into the instance dictionary
        object.__setattr__(self, "_focus_part", part)
        for name, value in slots.items():
            setattr(self, name, value)

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "body": self._body,
            "header": self._header,
            "footer": self._footer,
            "focus_part": self.focus_part,
            "select_navigation": self.select_navigation,
            "flow": self.flow,
            "min_body_rows": self.min_body_rows,
            "trim_first": self.trim_first,
        }
        return remove_defaults(attrs, Frame.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield this widget's constructor arguments as `(name, value)` pairs, for `rich`'s repr protocol."""
        yield "body", self._body
        yield "header", self._header
        yield "footer", self._footer
        yield "focus_part", self.focus_part
        yield "select_navigation", self.select_navigation, False
        yield "flow", self.flow, False
        yield "min_body_rows", self.min_body_rows, 0
        yield "trim_first", self.trim_first, "header"

    def sizing(self) -> frozenset[Sizing]:
        """Return BOX, and FLOW as well when :attr:`flow` is set and the body reports FLOW."""
        # A body that does not implement the Widget API has no sizing() and is laid out as a box widget.
        if self.flow and Sizing.FLOW in getattr(self._body, "sizing", frozenset)():
            return frozenset((Sizing.BOX, Sizing.FLOW))
        return self._sizing

    def _flow_rows(self, maxcol: int, *, focus: bool) -> tuple[int, int, int]:
        """Return the rows of the header, the body and the footer at the width *maxcol*.

        A missing header or footer has 0 rows.
        """
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer
        body = typing.cast("AbstractFlowWidget", self._body)
        return (
            0 if header is None else header.rows((maxcol,), focus and self.focus_part == "header"),
            body.rows((maxcol,), focus and self.focus_part == "body"),
            0 if footer is None else footer.rows((maxcol,), focus and self.focus_part == "footer"),
        )

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the total rows of the header, the body and the footer at the width in *size*.

        It is used for a flow size, which shows every part in full.
        The body has to accept a flow size.

        >>> from urwid import ListBox, Text
        >>> Frame(ListBox([Text("one"), Text("two")]), header=Text("head"), footer=Text("foot")).rows((10,))
        4
        """
        (maxcol,) = size
        return sum(self._flow_rows(maxcol, focus=focus))

    def _layout(
        self,
        size: tuple[int, int] | tuple[int],
        *,
        focus: bool,
    ) -> tuple[int, int, tuple[int] | tuple[int, int]]:
        """Return the header rows shown, the first footer row and the size the body gets, for a box or a flow size."""
        if len(size) == 1:
            (maxcol,) = size
            hrows, brows, _frows = self._flow_rows(maxcol, focus=focus)
            return hrows, hrows + brows, (maxcol,)
        maxcol, maxrow = size
        (htrim, ftrim), _ = self.frame_top_bottom((maxcol, maxrow), focus)
        return htrim, maxrow - ftrim, (maxcol, maxrow - htrim - ftrim)

    @property
    def focus_part(self) -> Literal["header", "footer", "body"]:
        """Return which part of the frame is in focus.

        Setting it to another part redraws the frame and sends ``"focus changed"``.
        Unlike the :attr:`focus_position` setter, it does not check that the frame has that part.
        """
        return self._focus_part

    @focus_part.setter
    def focus_part(self, part: Literal["header", "footer", "body"]) -> None:
        # The previous part is absent while the constructor sets the first one,
        # or when a subclass sets one before it calls the constructor.
        # Setting the first part is not a change, so it is not reported.
        # read without a subclass __getattr__, which could supply a value the frame does not have
        try:
            old_part = object.__getattribute__(self, "_focus_part")
        except AttributeError:
            old_part = None
        self._focus_part: Literal["header", "footer", "body"] = part
        if old_part is not None and part != old_part:
            self._invalidate()
            self._emit("focus changed", old_part, part)

    @property
    def header(self) -> HeaderWidget | None:
        """Return the header widget, or None if there is no header."""
        return self._header

    @header.setter
    def header(self, header: HeaderWidget | None) -> None:
        _check_widget_subclass(header)
        self._header = header
        if header is None and self.focus_part == "header":
            self.focus_part = "body"
        self._invalidate()

    @property
    def body(self) -> BodyWidget:
        """Return the body widget."""
        return self._body

    @body.setter
    def body(self, body: BodyWidget) -> None:
        _check_widget_subclass(body)
        self._body = body
        self._invalidate()

    @property
    def footer(self) -> FooterWidget | None:
        """Return the footer widget, or None if there is no footer."""
        return self._footer

    @footer.setter
    def footer(self, footer: FooterWidget | None) -> None:
        _check_widget_subclass(footer)
        self._footer = footer
        if footer is None and self.focus_part == "footer":
            self.focus_part = "body"
        self._invalidate()

    @property
    def focus_position(self) -> Literal["header", "footer", "body"]:
        """Return which part of the frame is in focus: `'body', 'header'` or `'footer'`.

        :returns: one of 'header', 'footer' or 'body'.
        """
        return self.focus_part

    @focus_position.setter
    def focus_position(self, position: Literal["header", "footer", "body"]) -> None:
        """
        Determine which part of the frame is in focus.

        :param position: 'header', 'footer' or 'body'
        :raises IndexError: *position* is not one of the three frame parts, or names a part this Frame does not have.
        """
        if position not in {"header", "footer", "body"}:
            raise IndexError(f"Invalid position for Frame: {position}")
        if (position == "header" and self._header is None) or (position == "footer" and self._footer is None):
            raise IndexError(f"This Frame has no {position}")
        self.focus_part = position
        self._invalidate()

    @property
    def focus(self) -> BodyWidget | HeaderWidget | FooterWidget:
        """Return the child :class:`Widget` in focus: the body, header or footer widget. Read-only."""
        return {  # type: ignore[return-value]
            "header": self._header,
            "footer": self._footer,
            "body": self._body,
        }[self.focus_part]

    @property
    def contents(  # type: ignore[override]
        self,
    ) -> MutableMapping[
        Literal["header", "footer", "body"],
        tuple[BodyWidget | HeaderWidget | FooterWidget, None],
    ]:
        """Return a dict-like object similar to the following.

        ::

            {
                "body": (body_widget, None),
                "header": (header_widget, None),  # if frame has a header
                "footer": (footer_widget, None),  # if frame has a footer
            }

        This object may be used to read or update the contents of the Frame.

        The values are similar to the list-like .contents objects used
        in other containers with (:class:`Widget`, options) tuples, but are
        constrained to keys for each of the three usual parts of a Frame.
        When other keys are used a :exc:`KeyError` will be raised.

        Currently, all options are `None`, but using the :meth:`options` method
        to create the options value is recommended for forwards
        compatibility.
        """
        return _FrameContents(self)

    def _contents_keys(self) -> list[Literal["header", "footer", "body"]]:
        keys: list[Literal["header", "footer", "body"]] = ["body"]
        if self._header is not None:
            keys.append("header")
        if self._footer is not None:
            keys.append("footer")
        return keys

    @typing.overload
    def _contents__getitem__(self, key: Literal["body"]) -> tuple[BodyWidget, None]: ...

    @typing.overload
    def _contents__getitem__(self, key: Literal["header"]) -> tuple[HeaderWidget, None]: ...

    @typing.overload
    def _contents__getitem__(self, key: Literal["footer"]) -> tuple[FooterWidget, None]: ...

    def _contents__getitem__(
        self, key: Literal["body", "header", "footer"]
    ) -> tuple[BodyWidget | HeaderWidget | FooterWidget, None]:
        """
        Return the ``(widget, options)`` pair for *key*, for the container contents protocol.

        :raises KeyError: *key* is not one of the three frame parts.
        """
        if key == "body":
            return (self._body, None)
        if key == "header" and self._header is not None:
            return (self._header, None)
        if key == "footer" and self._footer is not None:
            return (self._footer, None)
        raise KeyError(f"Frame.contents has no key: {key!r}")

    @typing.overload
    def _contents__setitem__(self, key: Literal["body"], value: tuple[BodyWidget, None]) -> None: ...

    @typing.overload
    def _contents__setitem__(self, key: Literal["header"], value: tuple[HeaderWidget, None]) -> None: ...

    @typing.overload
    def _contents__setitem__(self, key: Literal["footer"], value: tuple[FooterWidget, None]) -> None: ...

    def _contents__setitem__(
        self,
        key: Literal["body", "header", "footer"],
        value: tuple[BodyWidget | HeaderWidget | FooterWidget, None],
    ) -> None:
        """
        Replace the ``(widget, options)`` pair for *key*, for the container contents protocol.

        :raises KeyError: *key* is not one of the three frame parts.
        :raises FrameError: *value* is not a ``(widget, None)`` pair.
        """
        if key not in {"body", "header", "footer"}:
            raise KeyError(f"Frame.contents has no key: {key!r}")
        try:
            value_w, value_options = value
            if value_options is not None:
                raise FrameError(f"added content invalid: {value!r}")
        except (ValueError, TypeError) as exc:
            raise FrameError(f"added content invalid: {value!r}").with_traceback(exc.__traceback__) from exc
        if key == "body":
            self.body = value_w  # type: ignore[assignment]
        elif key == "footer":
            self.footer = value_w  # type: ignore[assignment]
        else:
            self.header = value_w  # type: ignore[assignment]

    def _contents__delitem__(self, key: Literal["header", "footer"]) -> None:
        """
        Remove the header or footer, for the container contents protocol.

        :raises KeyError: *key* is not a removable part, or names a part this Frame does not have.
        """
        if key not in {"header", "footer"}:
            raise KeyError(f"Frame.contents can't remove key: {key!r}")
        if (key == "header" and self._header is None) or (key == "footer" and self._footer is None):
            raise KeyError(f"Frame.contents has no key: {key!r}")
        if key == "header":
            self.header = None
        else:
            self.footer = None

    def options(self) -> None:
        """
        There are currently no options for Frame contents.

        Return None as a placeholder for future options.
        """

    def frame_top_bottom(self, size: tuple[int, int], focus: bool) -> tuple[tuple[int, int], tuple[int, int]]:
        """
        Calculate the number of rows for the header and footer.

        The parts take rows in this order, each one at most the rows it reports, and the body also takes the rest:

        - header in focus: the header, :attr:`min_body_rows` of the body, the footer;
        - footer in focus: the footer, :attr:`min_body_rows` of the body, the header;
        - body in focus: :attr:`min_body_rows` of the body but at least 1, the part :attr:`trim_first` does not name,
          the part it names.

        With the default ``min_body_rows=0`` and ``trim_first='header'``, the part in focus is shown first,
        and with the body or the footer in focus the header is trimmed before the footer.

        >>> from urwid import Edit, ListBox, Pile, Text
        >>> frame = Frame(ListBox([Text("entry")]), header=Edit("path: "), footer=Pile([Text("flag")] * 3))
        >>> frame.frame_top_bottom((10, 4), True)
        ((0, 3), (1, 3))
        >>> frame.min_body_rows = 2
        >>> frame.trim_first = "footer"
        >>> frame.frame_top_bottom((10, 4), True)
        ((1, 1), (1, 3))

        :param size: See :meth:`Widget.render` for details
        :param focus: ``True`` if this widget is in focus
        :returns: `(head rows, foot rows),(orig head, orig foot)`
                  orig head/foot are from rows() calls.
        """
        (maxcol, maxrow) = size
        frows = hrows = 0
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer

        if header is not None:
            hrows = header.rows((maxcol,), self.focus_part == "header" and focus)

        if footer is not None:
            frows = footer.rows((maxcol,), self.focus_part == "footer" and focus)

        min_body_rows = self.min_body_rows
        match self.focus_part:
            case "header":
                htrim = min(hrows, maxrow)
                ftrim = min(frows, max(0, maxrow - htrim - min_body_rows))
            case "footer":
                ftrim = min(frows, maxrow)
                htrim = min(hrows, max(0, maxrow - ftrim - min_body_rows))
            case "body":
                # The body in focus keeps a row, so the focus stays in view.
                remaining = max(0, maxrow - max(1, min_body_rows))
                if hrows + frows <= remaining:
                    htrim, ftrim = hrows, frows
                elif self.trim_first == "header":
                    ftrim = min(frows, remaining)
                    htrim = min(hrows, remaining - ftrim)
                else:
                    htrim = min(hrows, remaining)
                    ftrim = min(frows, remaining - htrim)
            case _:
                typing.assert_never(self.focus_part)
        return (htrim, ftrim), (hrows, frows)

    def render(
        self,
        size: tuple[int, int] | tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """
        Render the Frame and return the resulting canvas.

        At a flow size every part is rendered in full.

        :raises RuntimeError: the header or footer renders a different number of rows than it reported.
        """
        if len(size) == 1:
            return self._render_flow(size[0], focus=focus)
        (maxcol, maxrow) = size
        (htrim, ftrim), (hrows, frows) = self.frame_top_bottom((maxcol, maxrow), focus)

        combinelist = []
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer

        head: Canvas | CompositeCanvas | None = None
        if header is not None and htrim and htrim < hrows:
            head = Filler(header, VAlign.TOP).render(
                (maxcol, htrim),
                focus and self.focus_part == "header",
            )
        elif header is not None and htrim:
            head = header.render(
                (maxcol,),
                focus and self.focus_part == "header",
            )
            if head.rows() != hrows:
                raise RuntimeError("rows, render mismatch")
        if head:
            combinelist.append((head, "header", self.focus_part == "header"))

        if ftrim + htrim < maxrow:
            body = self.body.render(
                (maxcol, maxrow - ftrim - htrim),
                focus and self.focus_part == "body",
            )
            combinelist.append((body, "body", self.focus_part == "body"))

        foot: Canvas | CompositeCanvas | None = None
        if footer is not None and ftrim and ftrim < frows:
            foot = Filler(footer, VAlign.BOTTOM).render(
                (maxcol, ftrim),
                focus and self.focus_part == "footer",
            )
        elif footer is not None and ftrim:
            foot = footer.render(
                (maxcol,),
                focus and self.focus_part == "footer",
            )
            if foot.rows() != frows:
                raise RuntimeError("rows, render mismatch")
        if foot:
            combinelist.append((foot, "footer", self.focus_part == "footer"))

        # A header or footer of 0 rows is not drawn, but its rows decided the layout.
        # It is listed in the canvas children, so the canvas cache drops this canvas when it changes.
        undrawn = [
            (0, 0, part.render((maxcol,)), name)
            for part, name, rows in ((header, "header", hrows), (footer, "footer", frows))
            if part is not None and not rows
        ]
        if not combinelist:
            # No part has rows: an empty combination would lose the width.
            out = CompositeCanvas(SolidCanvas(" ", maxcol, maxrow))
        else:
            out = CanvasCombine(combinelist)
        out.children.extend(undrawn)
        return out

    def _render_flow(self, maxcol: int, *, focus: bool) -> CompositeCanvas:
        """Render every part at the width *maxcol*, the header above the body and the footer below it."""
        combinelist = []
        undrawn = []
        parts: tuple[tuple[AbstractFlowWidget | None, Literal["header", "body", "footer"]], ...] = (
            (self._header, "header"),
            (typing.cast("AbstractFlowWidget", self._body), "body"),
            (self._footer, "footer"),
        )
        for part, name in parts:
            if part is None:
                continue
            canvas = part.render((maxcol,), focus and self.focus_part == name)
            if canvas.rows():
                combinelist.append((canvas, name, self.focus_part == name))
            else:
                # A part of 0 rows is not drawn, but it is listed in the canvas children,
                # so the canvas cache drops this canvas when it changes.
                undrawn.append((0, 0, canvas, name))
        out = CanvasCombine(combinelist) if combinelist else CompositeCanvas(SolidCanvas(" ", maxcol, 0))
        out.children.extend(undrawn)
        return out

    def keypress(
        self,
        size: tuple[int, int] | tuple[int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Pass keypress to widget in focus.

        With :attr:`select_navigation`, unhandled ``'next selectable'`` and ``'prev selectable'`` commands
        may cause a focus change.
        """
        if (unhandled := self._keypress_focus_part(size, key)) is None:
            return None
        if self.select_navigation and self._command_map[unhandled] in _SELECT_COMMANDS:
            return self._select_keypress_unhandled(unhandled)
        return unhandled

    def _keypress_focus_part(self, size: tuple[int, int] | tuple[int], key: str) -> str | None:
        """Pass keypress to the part in focus and return what it leaves unhandled."""
        maxcol = size[0]
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer

        if self.focus_part == "header" and header is not None:
            if not header.selectable():
                return key
            return header.keypress((maxcol,), key)
        if self.focus_part == "footer" and footer is not None:
            if not footer.selectable():
                return key
            return footer.keypress((maxcol,), key)
        if self.focus_part != "body" or not self.body.selectable():
            return key
        if len(size) == 1:
            return typing.cast("AbstractFlowWidget", self.body).keypress((maxcol,), key)
        # The body gets the rows render() gives it, so a body row on screen also gets the keys.
        (header_rows, footer_rows), _ = self.frame_top_bottom(size, focus=True)
        body_rows = size[1] - header_rows - footer_rows
        if body_rows <= 0:
            return key
        return self.body.keypress((maxcol, body_rows), key)

    def _select_candidates(
        self,
        *,
        reverse: bool,
        from_edge: bool,
    ) -> Iterator[Literal["header", "body", "footer"]]:
        """Yield the selectable parts in the traversal order.

        :param reverse: yield them from the bottom to the top.
        :param from_edge: start at the top (bottom when *reverse*) part instead of after the focus.
        """
        parts: Iterator[Literal["header", "body", "footer"]] = reversed(self) if reverse else iter(self)
        if not from_edge:
            for part in parts:
                if part == self.focus_part:
                    break
        for part in parts:
            # Iteration yields only the parts the frame has, so the widget is not None.
            if typing.cast("AbstractWidget", self._contents__getitem__(part)[0]).selectable():
                yield part

    def _select_enter_focus(self, *, reverse: bool) -> None:
        """Call the entry hook of the part in focus."""
        _select_enter_child(self.focus, reverse=reverse)

    def mouse_event(
        self,
        size: tuple[int, int] | tuple[int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass mouse event to appropriate part of frame. Focus may be changed on button 1 press."""
        maxcol = size[0]
        htrim, footer_top, body_size = self._layout(size, focus=focus)
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer

        if header is not None and row < htrim:  # within header
            focus = focus and self.focus_part == "header"
            if is_mouse_press(event) and button == MouseButton.LEFT and header.selectable():
                self.focus_position = "header"

            if not hasattr(header, "mouse_event"):
                return False
            return header.mouse_event((maxcol,), event, button, col, row, focus)

        if footer is not None and row >= footer_top:  # within footer
            focus = focus and self.focus_part == "footer"
            if is_mouse_press(event) and button == MouseButton.LEFT and footer.selectable():
                self.focus_position = "footer"

            if not hasattr(footer, "mouse_event"):
                return False
            return footer.mouse_event((maxcol,), event, button, col, row - footer_top, focus)

        # within body
        focus = focus and self.focus_part == "body"
        if is_mouse_press(event) and button == MouseButton.LEFT and self.body.selectable():
            self.focus_position = "body"

        if not hasattr(self.body, "mouse_event"):
            return False
        return self.body.mouse_event(body_size, event, button, col, row - htrim, focus)  # type: ignore[arg-type]

    def get_cursor_coords(self, size: tuple[int, int] | tuple[int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focus widget."""
        maxcol = size[0]
        hrows, footer_top, body_size = self._layout(size, focus=True)
        header: AbstractFlowWidget | None = self._header
        footer: AbstractFlowWidget | None = self._footer

        if self.focus_part == "header":
            if header is None or not header.selectable() or not hasattr(header, "get_cursor_coords"):
                return None
            row_adjust = 0
            coords = header.get_cursor_coords((maxcol,))
        elif self.focus_part == "body":
            if not self.body.selectable() or not hasattr(self.body, "get_cursor_coords"):
                return None
            row_adjust = hrows
            coords = self.body.get_cursor_coords(body_size)
        else:
            if footer is None or not footer.selectable() or not hasattr(footer, "get_cursor_coords"):
                return None
            row_adjust = footer_top
            coords = footer.get_cursor_coords((maxcol,))

        if coords is None:
            return None

        x, y = coords
        return x, y + row_adjust

    def __iter__(self) -> Iterator[Literal["header", "body", "footer"]]:
        """Return an iterator over the positions in this Frame top to bottom."""
        if self._header is not None:
            yield "header"
        yield "body"
        if self._footer is not None:
            yield "footer"

    def __reversed__(self) -> Iterator[Literal["footer", "body", "header"]]:
        """Return an iterator over the positions in this Frame bottom to top."""
        if self._footer is not None:
            yield "footer"
        yield "body"
        if self._header is not None:
            yield "header"
