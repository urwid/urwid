from __future__ import annotations

import typing

from urwid.canvas import CanvasJoin, CompositeCanvas, TextCanvas
from urwid.util import decompose_tagmarkup

from .constants import Sizing
from .widget import Widget, fixed_size

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from urwid import Font


class BigText(Widget):
    _sizing = frozenset([Sizing.FIXED])

    def __init__(self, markup, font: Font) -> None:
        """
        markup -- same as Text widget markup
        font -- instance of a Font class
        """
        super().__init__()
        self.text: str = ""
        self.attrib = []
        self.font: Font = font
        self.set_font(font)
        self.set_text(markup)

    def set_text(self, markup):
        self.text, self.attrib = decompose_tagmarkup(markup)
        self._invalidate()

    def get_text(self):
        """
        Returns (text, attributes).
        """
        return self.text, self.attrib

    def set_font(self, font: Font) -> None:
        self.font = font
        self._invalidate()

    def pack(
        self,
        size: tuple[()] | None = (),  # type: ignore[override]
        focus: bool = False,
    ) -> tuple[int, int]:
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

            else:
                # ignore invalid characters
                continue
        if o:
            canv = CanvasJoin(o)
        else:
            canv = CompositeCanvas(TextCanvas([b""] * rows, maxcol=0, check_width=False))
        canv.set_depends([])
        return canv
