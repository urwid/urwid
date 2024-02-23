from __future__ import annotations

import enum
import typing

from urwid.canvas import CompositeCanvas, SolidCanvas

from .constants import BOX_SYMBOLS, SHADE_SYMBOLS, Sizing
from .widget import Widget


class DividerSymbols(str, enum.Enum):
    """Common symbols for divider widgets."""

    # Lines
    LIGHT_HL = BOX_SYMBOLS.LIGHT.HORIZONTAL
    LIGHT_4_DASHES = BOX_SYMBOLS.LIGHT.HORIZONTAL_4_DASHES
    LIGHT_3_DASHES = BOX_SYMBOLS.LIGHT.HORIZONTAL_3_DASHES
    LIGHT_2_DASHES = BOX_SYMBOLS.LIGHT.HORIZONTAL_2_DASHES
    HEAVY_HL = BOX_SYMBOLS.HEAVY.HORIZONTAL
    HEAVY_4_DASHES = BOX_SYMBOLS.HEAVY.HORIZONTAL_4_DASHES
    HEAVY_3_DASHES = BOX_SYMBOLS.HEAVY.HORIZONTAL_3_DASHES
    HEAVY_2_DASHES = BOX_SYMBOLS.HEAVY.HORIZONTAL_2_DASHES
    DOUBLE_HL = BOX_SYMBOLS.DOUBLE.HORIZONTAL

    # Full block
    FULL_BLOCK = SHADE_SYMBOLS.FULL_BLOCK
    DARK_SHADE = SHADE_SYMBOLS.DARK_SHADE
    MEDIUM_SHADE = SHADE_SYMBOLS.MEDIUM_SHADE
    LITE_SHADE = SHADE_SYMBOLS.LITE_SHADE


class Divider(Widget):
    """
    Horizontal divider widget
    """

    Symbols = DividerSymbols

    _sizing = frozenset([Sizing.FLOW])

    ignore_focus = True

    def __init__(
        self,
        div_char: str | bytes = " ",
        top: int = 0,
        bottom: int = 0,
    ) -> None:
        """
        :param div_char: character to repeat across line
        :type div_char: bytes or unicode

        :param top: number of blank lines above
        :type top: int

        :param bottom: number of blank lines below
        :type bottom: int

        >>> Divider()
        <Divider flow widget>
        >>> Divider(u'-')
        <Divider flow widget '-'>
        >>> Divider(u'x', 1, 2)
        <Divider flow widget 'x' bottom=2 top=1>
        """
        super().__init__()
        self.div_char = div_char
        self.top = top
        self.bottom = bottom

    def _repr_words(self) -> list[str]:
        return super()._repr_words() + [repr(self.div_char)] * (self.div_char != " ")

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = dict(super()._repr_attrs())
        if self.top:
            attrs["top"] = self.top
        if self.bottom:
            attrs["bottom"] = self.bottom
        return attrs

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the number of lines that will be rendered.

        >>> Divider().rows((10,))
        1
        >>> Divider(u'x', 1, 2).rows((10,))
        4
        """
        (_maxcol,) = size
        return self.top + 1 + self.bottom

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """
        Render the divider as a canvas and return it.

        >>> Divider().render((10,)).text # ... = b in Python 3
        [...'          ']
        >>> Divider(u'-', top=1).render((10,)).text
        [...'          ', ...'----------']
        >>> Divider(u'x', bottom=2).render((5,)).text
        [...'xxxxx', ...'     ', ...'     ']
        """
        (maxcol,) = size
        canv = CompositeCanvas(SolidCanvas(self.div_char, maxcol, 1))
        if self.top or self.bottom:
            canv.pad_trim_top_bottom(self.top, self.bottom)
        return canv
