from __future__ import annotations

import typing
import warnings

from urwid.canvas import CanvasCombine, CompositeCanvas
from urwid.split_repr import remove_defaults
from urwid.util import is_mouse_press

from .constants import Sizing, VAlign
from .container import WidgetContainerMixin
from .filler import Filler
from .widget import Widget, WidgetError

if typing.TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping

    from typing_extensions import Literal


BodyWidget = typing.TypeVar("BodyWidget")
HeaderWidget = typing.TypeVar("HeaderWidget")
FooterWidget = typing.TypeVar("FooterWidget")


class FrameError(WidgetError):
    pass


def _check_widget_subclass(widget: Widget | None) -> None:
    if widget is None:
        return

    if not isinstance(widget, Widget):
        obj_class_path = f"{widget.__class__.__module__}.{widget.__class__.__name__}"
        warnings.warn(
            f"{obj_class_path} is not subclass of Widget",
            DeprecationWarning,
            stacklevel=3,
        )


class Frame(Widget, WidgetContainerMixin, typing.Generic[BodyWidget, HeaderWidget, FooterWidget]):
    """
    Frame widget is a box widget with optional header and footer
    flow widgets placed above and below the box widget.

    .. note:: The main difference between a Frame and a :class:`Pile` widget
        defined as: `Pile([('pack', header), body, ('pack', footer)])` is that
        the Frame will not automatically change focus up and down in response to keystrokes.
    """

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    def __init__(
        self,
        body: BodyWidget,
        header: HeaderWidget = None,
        footer: FooterWidget = None,
        focus_part: Literal["header", "footer", "body"] | Widget = "body",
    ):
        """
        :param body: a box widget for the body of the frame
        :type body: Widget
        :param header: a flow widget for above the body (or None)
        :type header: Widget
        :param footer: a flow widget for below the body (or None)
        :type footer: Widget
        :param focus_part:  'header', 'footer' or 'body'
        :type focus_part: str | Widget
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

        _check_widget_subclass(header)
        _check_widget_subclass(body)
        _check_widget_subclass(footer)

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "body": self._body,
            "header": self._header,
            "footer": self._footer,
            "focus_part": self.focus_part,
        }
        return remove_defaults(attrs, Frame.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        yield "body", self._body
        yield "header", self._header
        yield "footer", self._footer
        yield "focus_part", self.focus_part

    @property
    def header(self) -> HeaderWidget:
        return self._header

    @header.setter
    def header(self, header: HeaderWidget) -> None:
        _check_widget_subclass(header)
        self._header = header
        if header is None and self.focus_part == "header":
            self.focus_part = "body"
        self._invalidate()

    def get_header(self) -> HeaderWidget:
        warnings.warn(
            f"method `{self.__class__.__name__}.get_header` is deprecated, "
            f"standard property `{self.__class__.__name__}.header` should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.header

    def set_header(self, header: HeaderWidget) -> None:
        warnings.warn(
            f"method `{self.__class__.__name__}.set_header` is deprecated, "
            f"standard property `{self.__class__.__name__}.header` should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.header = header

    @property
    def body(self) -> BodyWidget:
        return self._body

    @body.setter
    def body(self, body: BodyWidget) -> None:
        _check_widget_subclass(body)
        self._body = body
        self._invalidate()

    def get_body(self) -> BodyWidget:
        warnings.warn(
            f"method `{self.__class__.__name__}.get_body` is deprecated, "
            f"standard property {self.__class__.__name__}.body should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.body

    def set_body(self, body: BodyWidget) -> None:
        warnings.warn(
            f"method `{self.__class__.__name__}.set_body` is deprecated, "
            f"standard property `{self.__class__.__name__}.body` should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.body = body

    @property
    def footer(self) -> FooterWidget:
        return self._footer

    @footer.setter
    def footer(self, footer: FooterWidget) -> None:
        _check_widget_subclass(footer)
        self._footer = footer
        if footer is None and self.focus_part == "footer":
            self.focus_part = "body"
        self._invalidate()

    def get_footer(self) -> FooterWidget:
        warnings.warn(
            f"method `{self.__class__.__name__}.get_footer` is deprecated, "
            f"standard property `{self.__class__.__name__}.footer` should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.footer

    def set_footer(self, footer: FooterWidget) -> None:
        warnings.warn(
            f"method `{self.__class__.__name__}.set_footer` is deprecated, "
            f"standard property `{self.__class__.__name__}.footer` should be used instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.footer = footer

    @property
    def focus_position(self) -> Literal["header", "footer", "body"]:
        """
        writeable property containing an indicator which part of the frame
        that is in focus: `'body', 'header'` or `'footer'`.

        :returns: one of 'header', 'footer' or 'body'.
        :rtype: str
        """
        return self.focus_part

    @focus_position.setter
    def focus_position(self, part: Literal["header", "footer", "body"]) -> None:
        """
        Determine which part of the frame is in focus.

        :param part: 'header', 'footer' or 'body'
        :type part: str
        """
        if part not in {"header", "footer", "body"}:
            raise IndexError(f"Invalid position for Frame: {part}")
        if (part == "header" and self._header is None) or (part == "footer" and self._footer is None):
            raise IndexError(f"This Frame has no {part}")
        self.focus_part = part
        self._invalidate()

    def get_focus(self) -> Literal["header", "footer", "body"]:
        """
        writeable property containing an indicator which part of the frame
        that is in focus: `'body', 'header'` or `'footer'`.

        .. note:: included for backwards compatibility. You should rather use
            the container property :attr:`.focus_position` to get this value.

        :returns: one of 'header', 'footer' or 'body'.
        :rtype: str
        """
        warnings.warn(
            "included for backwards compatibility."
            "You should rather use the container property `.focus_position` to get this value.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.focus_position

    def set_focus(self, part: Literal["header", "footer", "body"]) -> None:
        warnings.warn(
            "included for backwards compatibility."
            "You should rather use the container property `.focus_position` to set this value.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.focus_position = part

    @property
    def focus(self) -> BodyWidget | HeaderWidget | FooterWidget:
        """
        child :class:`Widget` in focus: the body, header or footer widget.
        This is a read-only property."""
        return {"header": self._header, "footer": self._footer, "body": self._body}[self.focus_part]

    def _get_focus(self) -> BodyWidget | HeaderWidget | FooterWidget:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus` is deprecated, "
            f"please use `{self.__class__.__name__}.focus` property",
            DeprecationWarning,
            stacklevel=3,
        )
        return {"header": self._header, "footer": self._footer, "body": self._body}[self.focus_part]

    @property
    def contents(
        self,
    ) -> MutableMapping[
        Literal["header", "footer", "body"],
        tuple[BodyWidget | HeaderWidget | FooterWidget, None],
    ]:
        """
        a dict-like object similar to::

            {
                'body': (body_widget, None),
                'header': (header_widget, None),  # if frame has a header
                'footer': (footer_widget, None) # if frame has a footer
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

        # noinspection PyMethodParameters
        class FrameContents(
            typing.MutableMapping[
                str,
                typing.Tuple[typing.Union[BodyWidget, HeaderWidget, FooterWidget], None],
            ]
        ):
            # pylint: disable=no-self-argument

            __slots__ = ()

            def __len__(inner_self) -> int:
                return len(inner_self.keys())

            __getitem__ = self._contents__getitem__
            __setitem__ = self._contents__setitem__
            __delitem__ = self._contents__delitem__

            def __iter__(inner_self) -> Iterator[str]:
                yield from inner_self.keys()

            def __repr__(inner_self) -> str:
                return f"<{inner_self.__class__.__name__}({dict(inner_self)}) for {self}>"

            def __rich_repr__(inner_self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
                yield from inner_self.items()

        return FrameContents()

    def _contents_keys(self) -> list[Literal["header", "footer", "body"]]:
        keys = ["body"]
        if self._header:
            keys.append("header")
        if self._footer:
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
        if key == "body":
            return (self._body, None)
        if key == "header" and self._header:
            return (self._header, None)
        if key == "footer" and self._footer:
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
        if key not in {"body", "header", "footer"}:
            raise KeyError(f"Frame.contents has no key: {key!r}")
        try:
            value_w, value_options = value
            if value_options is not None:
                raise FrameError(f"added content invalid: {value!r}")
        except (ValueError, TypeError) as exc:
            raise FrameError(f"added content invalid: {value!r}").with_traceback(exc.__traceback__) from exc
        if key == "body":
            self.body = value_w
        elif key == "footer":
            self.footer = value_w
        else:
            self.header = value_w

    def _contents__delitem__(self, key: Literal["header", "footer"]) -> None:
        if key not in {"header", "footer"}:
            raise KeyError(f"Frame.contents can't remove key: {key!r}")
        if (key == "header" and self._header is None) or (key == "footer" and self._footer is None):
            raise KeyError(f"Frame.contents has no key: {key!r}")
        if key == "header":
            self.header = None
        else:
            self.footer = None

    def _contents(self):
        warnings.warn(
            f"method `{self.__class__.__name__}._contents` is deprecated, "
            f"please use property `{self.__class__.__name__}.contents`",
            DeprecationWarning,
            stacklevel=3,
        )
        return self.contents

    def options(self) -> None:
        """
        There are currently no options for Frame contents.

        Return None as a placeholder for future options.
        """

    def frame_top_bottom(self, size: tuple[int, int], focus: bool) -> tuple[tuple[int, int], tuple[int, int]]:
        """
        Calculate the number of rows for the header and footer.

        :param size: See :meth:`Widget.render` for details
        :type size: widget size
        :param focus: ``True`` if this widget is in focus
        :type focus: bool
        :returns: `(head rows, foot rows),(orig head, orig foot)`
                  orig head/foot are from rows() calls.
        :rtype: (int, int), (int, int)
        """
        (maxcol, maxrow) = size
        frows = hrows = 0

        if self.header:
            hrows = self.header.rows((maxcol,), self.focus_part == "header" and focus)

        if self.footer:
            frows = self.footer.rows((maxcol,), self.focus_part == "footer" and focus)

        remaining = maxrow

        if self.focus_part == "footer":
            if frows >= remaining:
                return (0, remaining), (hrows, frows)

            remaining -= frows
            if hrows >= remaining:
                return (remaining, frows), (hrows, frows)

        elif self.focus_part == "header":
            if hrows >= maxrow:
                return (remaining, 0), (hrows, frows)

            remaining -= hrows
            if frows >= remaining:
                return (hrows, remaining), (hrows, frows)

        elif hrows + frows >= remaining:
            # self.focus_part == 'body'
            rless1 = max(0, remaining - 1)
            if frows >= remaining - 1:
                return (0, rless1), (hrows, frows)

            remaining -= frows
            rless1 = max(0, remaining - 1)
            return (rless1, frows), (hrows, frows)

        return (hrows, frows), (hrows, frows)

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        (maxcol, maxrow) = size
        (htrim, ftrim), (hrows, frows) = self.frame_top_bottom((maxcol, maxrow), focus)

        combinelist = []
        depends_on = []

        head = None
        if htrim and htrim < hrows:
            head = Filler(self.header, VAlign.TOP).render((maxcol, htrim), focus and self.focus_part == "header")
        elif htrim:
            head = self.header.render((maxcol,), focus and self.focus_part == "header")
            if head.rows() != hrows:
                raise RuntimeError("rows, render mismatch")
        if head:
            combinelist.append((head, "header", self.focus_part == "header"))
            depends_on.append(self.header)

        if ftrim + htrim < maxrow:
            body = self.body.render((maxcol, maxrow - ftrim - htrim), focus and self.focus_part == "body")
            combinelist.append((body, "body", self.focus_part == "body"))
            depends_on.append(self.body)

        foot = None
        if ftrim and ftrim < frows:
            foot = Filler(self.footer, VAlign.BOTTOM).render((maxcol, ftrim), focus and self.focus_part == "footer")
        elif ftrim:
            foot = self.footer.render((maxcol,), focus and self.focus_part == "footer")
            if foot.rows() != frows:
                raise RuntimeError("rows, render mismatch")
        if foot:
            combinelist.append((foot, "footer", self.focus_part == "footer"))
            depends_on.append(self.footer)

        return CanvasCombine(combinelist)

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Pass keypress to widget in focus."""
        (maxcol, maxrow) = size

        if self.focus_part == "header" and self.header is not None:
            if not self.header.selectable():
                return key
            return self.header.keypress((maxcol,), key)
        if self.focus_part == "footer" and self.footer is not None:
            if not self.footer.selectable():
                return key
            return self.footer.keypress((maxcol,), key)
        if self.focus_part != "body":
            return key
        remaining = maxrow
        if self.header is not None:
            remaining -= self.header.rows((maxcol,))
        if self.footer is not None:
            remaining -= self.footer.rows((maxcol,))
        if remaining <= 0:
            return key

        if not self.body.selectable():
            return key
        return self.body.keypress((maxcol, remaining), key)

    def mouse_event(
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """
        Pass mouse event to appropriate part of frame.
        Focus may be changed on button 1 press.
        """
        (maxcol, maxrow) = size
        (htrim, ftrim), (_hrows, _frows) = self.frame_top_bottom((maxcol, maxrow), focus)

        if row < htrim:  # within header
            focus = focus and self.focus_part == "header"
            if is_mouse_press(event) and button == 1 and self.header.selectable():
                self.focus_position = "header"
            if not hasattr(self.header, "mouse_event"):
                return False
            return self.header.mouse_event((maxcol,), event, button, col, row, focus)

        if row >= maxrow - ftrim:  # within footer
            focus = focus and self.focus_part == "footer"
            if is_mouse_press(event) and button == 1 and self.footer.selectable():
                self.focus_position = "footer"
            if not hasattr(self.footer, "mouse_event"):
                return False
            return self.footer.mouse_event((maxcol,), event, button, col, row - maxrow + ftrim, focus)

        # within body
        focus = focus and self.focus_part == "body"
        if is_mouse_press(event) and button == 1 and self.body.selectable():
            self.focus_position = "body"

        if not hasattr(self.body, "mouse_event"):
            return False
        return self.body.mouse_event((maxcol, maxrow - htrim - ftrim), event, button, col, row - htrim, focus)

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focus widget."""
        if not self.focus.selectable():
            return None
        if not hasattr(self.focus, "get_cursor_coords"):
            return None

        fp = self.focus_position
        (maxcol, maxrow) = size
        (hrows, frows), _ = self.frame_top_bottom(size, True)

        if fp == "header":
            row_adjust = 0
            coords = self.header.get_cursor_coords((maxcol,))
        elif fp == "body":
            row_adjust = hrows
            coords = self.body.get_cursor_coords((maxcol, maxrow - hrows - frows))
        else:
            row_adjust = maxrow - frows
            coords = self.footer.get_cursor_coords((maxcol,))

        if coords is None:
            return None

        x, y = coords
        return x, y + row_adjust

    def __iter__(self) -> Iterator[Literal["header", "body", "footer"]]:
        """
        Return an iterator over the positions in this Frame top to bottom.
        """
        if self._header:
            yield "header"
        yield "body"
        if self._footer:
            yield "footer"

    def __reversed__(self) -> Iterator[Literal["footer", "body", "header"]]:
        """
        Return an iterator over the positions in this Frame bottom to top.
        """
        if self._footer:
            yield "footer"
        yield "body"
        if self._header:
            yield "header"
