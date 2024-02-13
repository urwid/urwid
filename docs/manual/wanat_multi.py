from __future__ import annotations

import urwid


class MultiPudding(urwid.Widget):
    _sizing = frozenset((urwid.FLOW, urwid.BOX))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        if len(size) == 1:
            (maxcol,) = size
            maxrow = 1
        else:
            (maxcol, maxrow) = size
        num_pudding = maxcol // len("Pudding")
        return urwid.TextCanvas([b"Pudding" * num_pudding] * maxrow, maxcol=maxcol)
