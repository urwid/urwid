"""BigText: a widget that renders text in a large font."""

from __future__ import annotations

import typing

from urwid.canvas import CanvasJoin, CompositeCanvas, TextCanvas
from urwid.util import decompose_tagmarkup

from .constants import Sizing
from .widget import Widget, fixed_size

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from urwid import Font
    from urwid.util import _TagMarkup


class BigText(Widget):
    """Fixed widget that renders text using a large :class:`Font`."""

    _sizing = frozenset([Sizing.FIXED])

    def __init__(self, markup: _TagMarkup, font: Font) -> None:
        """Build the widget from markup rendered with a large font.

        :param markup: same as Text widget markup
        :param font: instance of a Font class
        """
        super().__init__()
        self.text: str = ""
        self.attrib: list[tuple[Hashable, int]] = []
        self.font: Font = font
        self.set_text(markup)

    def set_text(self, markup: _TagMarkup) -> None:
        """Replace the displayed text and attributes, decomposing *markup* into them."""
        self.text, self.attrib = decompose_tagmarkup(markup)  # type: ignore[assignment]
        self._invalidate()

    def get_text(self) -> tuple[str, list[tuple[Hashable, int]]]:
        """Return (text, attributes)."""
        return self.text, self.attrib

    def set_font(self, font: Font) -> None:
        """Replace the font used to render this widget's text."""
        self.font = font
        self._invalidate()

    def pack(  # type: ignore[override]
        self,
        size: tuple[()] | None = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the ``(cols, rows)`` size needed to render this widget's text in its font."""
        rows = self.font.height
        cols = 0
        for c in self.text:
            cols += self.font.char_width(c)
        return cols, rows

    def render(
        self,
        size: tuple[()],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render this widget's text as a canvas joining each character's font glyph."""
        fixed_size(size)  # complain if parameter is wrong
        a: Hashable | None = None
        ai = ak = 0
        o = []
        rows = self.font.height
        attrib = [*self.attrib, (None, len(self.text))]
        for ch in self.text:
            if not ak:
                a, ak = attrib[ai]
                ai += 1
            ak -= 1

            if width := self.font.char_width(ch):
                c: TextCanvas | CompositeCanvas = self.font.render(ch)
                if a is not None:
                    c = CompositeCanvas(c)
                    c.fill_attr(a)
                o.append((c, None, False, width))

        if o:
            canv = CanvasJoin(o)
        else:
            canv = CompositeCanvas(TextCanvas([b""] * rows, maxcol=0, check_width=False))
        canv.set_depends([])
        return canv
