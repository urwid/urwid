from __future__ import annotations

import typing

from urwid import text_layout
from urwid.canvas import apply_text_layout
from urwid.split_repr import remove_defaults
from urwid.str_util import calc_width
from urwid.util import decompose_tagmarkup, get_encoding

from .constants import Align, Sizing, WrapMode
from .widget import Widget, WidgetError

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from typing_extensions import Literal

    from urwid.canvas import TextCanvas


class TextError(WidgetError):
    pass


class Text(Widget):
    """
    a horizontally resizeable text widget
    """

    _sizing = frozenset([Sizing.FLOW, Sizing.FIXED])

    ignore_focus = True
    _repr_content_length_max = 140

    def __init__(
        self,
        markup: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        layout: text_layout.TextLayout | None = None,
    ) -> None:
        """
        :param markup: content of text widget, one of:

            bytes or unicode
              text to be displayed

            (*display attribute*, *text markup*)
              *text markup* with *display attribute* applied to all parts
              of *text markup* with no display attribute already applied

            [*text markup*, *text markup*, ... ]
              all *text markup* in the list joined together

        :type markup: :ref:`text-markup`
        :param align: typically ``'left'``, ``'center'`` or ``'right'``
        :type align: text alignment mode
        :param wrap: typically ``'space'``, ``'any'``, ``'clip'`` or ``'ellipsis'``
        :type wrap: text wrapping mode
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance

        >>> Text(u"Hello")
        <Text fixed/flow widget 'Hello'>
        >>> t = Text(('bold', u"stuff"), 'right', 'any')
        >>> t
        <Text fixed/flow widget 'stuff' align='right' wrap='any'>
        >>> print(t.text)
        stuff
        >>> t.attrib
        [('bold', 5)]
        """
        super().__init__()
        self._cache_maxcol: int | None = None
        self.set_text(markup)
        self.set_layout(align, wrap, layout)

    def _repr_words(self) -> list[str]:
        """
        Show the text in the repr in python3 format (b prefix for byte strings) and truncate if it's too long
        """
        first = super()._repr_words()
        text = self.get_text()[0]
        rest = repr(text)
        if len(rest) > self._repr_content_length_max:
            rest = (
                rest[: self._repr_content_length_max * 2 // 3 - 3] + "..." + rest[-self._repr_content_length_max // 3 :]
            )
        return [*first, rest]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "align": self._align_mode,
            "wrap": self._wrap_mode,
        }
        return remove_defaults(attrs, Text.__init__)

    def _invalidate(self) -> None:
        self._cache_maxcol = None
        super()._invalidate()

    def set_text(self, markup: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]) -> None:
        """
        Set content of text widget.

        :param markup: see :class:`Text` for description.
        :type markup: text markup

        >>> t = Text(u"foo")
        >>> print(t.text)
        foo
        >>> t.set_text(u"bar")
        >>> print(t.text)
        bar
        >>> t.text = u"baz"  # not supported because text stores text but set_text() takes markup
        Traceback (most recent call last):
        AttributeError: can't set attribute
        """
        self._text, self._attrib = decompose_tagmarkup(markup)
        self._invalidate()

    def get_text(self) -> tuple[str | bytes, list[tuple[Hashable, int]]]:
        """
        :returns: (*text*, *display attributes*)

            *text*
              complete bytes/unicode content of text widget

            *display attributes*
              run length encoded display attributes for *text*, eg.
              ``[('attr1', 10), ('attr2', 5)]``

        >>> Text(u"Hello").get_text() # ... = u in Python 2
        (...'Hello', [])
        >>> Text(('bright', u"Headline")).get_text()
        (...'Headline', [('bright', 8)])
        >>> Text([('a', u"one"), u"two", ('b', u"three")]).get_text()
        (...'onetwothree', [('a', 3), (None, 3), ('b', 5)])
        """
        return self._text, self._attrib

    @property
    def text(self) -> str | bytes:
        """
        Read-only property returning the complete bytes/unicode content
        of this widget
        """
        return self.get_text()[0]

    @property
    def attrib(self) -> list[tuple[Hashable, int]]:
        """
        Read-only property returning the run-length encoded display
        attributes of this widget
        """
        return self.get_text()[1]

    def set_align_mode(self, mode: Literal["left", "center", "right"] | Align) -> None:
        """
        Set text alignment mode. Supported modes depend on text layout
        object in use but defaults to a :class:`StandardTextLayout` instance

        :param mode: typically ``'left'``, ``'center'`` or ``'right'``
        :type mode: text alignment mode

        >>> t = Text(u"word")
        >>> t.set_align_mode('right')
        >>> t.align
        'right'
        >>> t.render((10,)).text # ... = b in Python 3
        [...'      word']
        >>> t.align = 'center'
        >>> t.render((10,)).text
        [...'   word   ']
        >>> t.align = 'somewhere'
        Traceback (most recent call last):
        TextError: Alignment mode 'somewhere' not supported.
        """
        if not self.layout.supports_align_mode(mode):
            raise TextError(f"Alignment mode {mode!r} not supported.")
        self._align_mode = mode
        self._invalidate()

    def set_wrap_mode(self, mode: Literal["space", "any", "clip", "ellipsis"] | WrapMode) -> None:
        """
        Set text wrapping mode. Supported modes depend on text layout
        object in use but defaults to a :class:`StandardTextLayout` instance

        :param mode: typically ``'space'``, ``'any'``, ``'clip'`` or ``'ellipsis'``
        :type mode: text wrapping mode

        >>> t = Text(u"some words")
        >>> t.render((6,)).text # ... = b in Python 3
        [...'some  ', ...'words ']
        >>> t.set_wrap_mode('clip')
        >>> t.wrap
        'clip'
        >>> t.render((6,)).text
        [...'some w']
        >>> t.wrap = 'any'  # Urwid 0.9.9 or later
        >>> t.render((6,)).text
        [...'some w', ...'ords  ']
        >>> t.wrap = 'somehow'
        Traceback (most recent call last):
        TextError: Wrap mode 'somehow' not supported.
        """
        if not self.layout.supports_wrap_mode(mode):
            raise TextError(f"Wrap mode {mode!r} not supported.")
        self._wrap_mode = mode
        self._invalidate()

    def set_layout(
        self,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode,
        layout: text_layout.TextLayout | None = None,
    ) -> None:
        """
        Set the text layout object, alignment and wrapping modes at
        the same time.

        :type align: text alignment mode
        :param wrap: typically 'space', 'any', 'clip' or 'ellipsis'
        :type wrap: text wrapping mode
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance

        >>> t = Text(u"hi")
        >>> t.set_layout('right', 'clip')
        >>> t
        <Text fixed/flow widget 'hi' align='right' wrap='clip'>
        """
        if layout is None:
            layout = text_layout.default_layout
        self._layout = layout
        self.set_align_mode(align)
        self.set_wrap_mode(wrap)

    align = property(lambda self: self._align_mode, set_align_mode)
    wrap = property(lambda self: self._wrap_mode, set_wrap_mode)

    @property
    def layout(self):
        return self._layout

    def render(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        focus: bool = False,
    ) -> TextCanvas:
        """
        Render contents with wrapping and alignment.  Return canvas.

        See :meth:`Widget.render` for parameter details.

        >>> Text(u"important things").render((18,)).text
        [b'important things  ']
        >>> Text(u"important things").render((11,)).text
        [b'important  ', b'things     ']
        >>> Text("demo text").render(()).text
        [b'demo text']
        """
        text, attr = self.get_text()
        if size:
            (maxcol,) = size
        else:
            maxcol, _ = self.pack(focus=focus)

        trans = self.get_line_translation(maxcol, (text, attr))
        return apply_text_layout(text, attr, trans, maxcol)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the number of rows the rendered text requires.

        See :meth:`Widget.rows` for parameter details.

        >>> Text(u"important things").rows((18,))
        1
        >>> Text(u"important things").rows((11,))
        2
        """
        (maxcol,) = size
        return len(self.get_line_translation(maxcol))

    def get_line_translation(
        self,
        maxcol: int,
        ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None = None,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
        """
        Return layout structure used to map self.text to a canvas.
        This method is used internally, but may be useful for debugging custom layout classes.

        :param maxcol: columns available for display
        :type maxcol: int
        :param ta: ``None`` or the (*text*, *display attributes*) tuple
                   returned from :meth:`.get_text`
        :type ta: text and display attributes
        """
        if not self._cache_maxcol or self._cache_maxcol != maxcol:
            self._update_cache_translation(maxcol, ta)
        return self._cache_translation

    def _update_cache_translation(
        self,
        maxcol: int,
        ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None,
    ) -> None:
        if ta:
            text, _attr = ta
        else:
            text, _attr = self.get_text()
        self._cache_maxcol = maxcol
        self._cache_translation = self.layout.layout(text, maxcol, self._align_mode, self._wrap_mode)

    def pack(
        self,
        size: tuple[()] | tuple[int] | None = None,  # type: ignore[override]
        focus: bool = False,
    ) -> tuple[int, int]:
        """
        Return the number of screen columns and rows required for
        this Text widget to be displayed without wrapping or
        clipping, as a single element tuple.

        :param size: ``None`` or ``()`` for unlimited screen columns (like FIXED sizing)
                     or (*maxcol*,) to specify a maximum column size
        :type size: widget size
        :param focus: widget is focused on
        :type focus: bool

        >>> Text(u"important things").pack()
        (16, 1)
        >>> Text(u"important things").pack((15,))
        (9, 2)
        >>> Text(u"important things").pack((8,))
        (8, 2)
        >>> Text(u"important things").pack(())
        (16, 1)
        """
        text, attr = self.get_text()

        if size:
            (maxcol,) = size
            if not hasattr(self.layout, "pack"):
                return maxcol, self.rows(size, focus)

            trans = self.get_line_translation(maxcol, (text, attr))
            cols = self.layout.pack(maxcol, trans)
            return (cols, len(trans))

        if text:
            if isinstance(text, bytes):
                text = text.decode(get_encoding())

            return (
                max(calc_width(line, 0, len(line)) for line in text.splitlines(keepends=False)),
                text.count("\n") + 1,
            )
        return 0, 1
