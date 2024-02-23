from __future__ import annotations

from urwid.canvas import SolidCanvas

from .constants import SHADE_SYMBOLS, Sizing
from .widget import Widget


class SolidFill(Widget):
    """
    A box widget that fills an area with a single character
    """

    _selectable = False
    ignore_focus = True
    _sizing = frozenset([Sizing.BOX])

    Symbols = SHADE_SYMBOLS

    def __init__(self, fill_char: str = " ") -> None:
        """
        :param fill_char: character to fill area with
        :type fill_char: bytes or unicode

        >>> SolidFill(u'8')
        <SolidFill box widget '8'>
        """
        super().__init__()
        self.fill_char = fill_char

    def _repr_words(self) -> list[str]:
        return [*super()._repr_words(), repr(self.fill_char)]

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> SolidCanvas:
        """
        Render the Fill as a canvas and return it.

        >>> SolidFill().render((4,2)).text # ... = b in Python 3
        [...'    ', ...'    ']
        >>> SolidFill('#').render((5,3)).text
        [...'#####', ...'#####', ...'#####']
        """
        maxcol, maxrow = size
        return SolidCanvas(self.fill_char, maxcol, maxrow)
