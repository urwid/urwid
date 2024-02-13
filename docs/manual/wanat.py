from __future__ import annotations

import urwid


class Pudding(urwid.Widget):
    _sizing = frozenset((urwid.FLOW,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        (maxcol,) = size
        num_pudding = maxcol // len("Pudding")
        return urwid.TextCanvas([b"Pudding" * num_pudding], maxcol=maxcol)


class BoxPudding(urwid.Widget):
    _sizing = frozenset((urwid.BOX,))

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.TextCanvas:
        (maxcol, maxrow) = size
        num_pudding = maxcol // len("Pudding")
        return urwid.TextCanvas([b"Pudding" * num_pudding] * maxrow, maxcol=maxcol)
