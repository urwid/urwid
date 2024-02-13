from __future__ import annotations

import urwid


class CursorPudding(urwid.Widget):
    _sizing = frozenset(["flow"])
    _selectable = True

    def __init__(self):
        super().__init__()
        self.cursor_col = 0

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        (maxcol,) = size
        num_pudding = maxcol // len("Pudding")
        cursor = None
        if focus:
            cursor = self.get_cursor_coords(size)
        return urwid.TextCanvas([b"Pudding" * num_pudding], [], cursor=cursor, maxcol=maxcol)

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int]:
        (maxcol,) = size
        col = min(self.cursor_col, maxcol - 1)
        return col, 0

    def keypress(self, size: tuple[int], key: str) -> str | None:
        (maxcol,) = size
        if key == "left":
            col = self.cursor_col - 1
        elif key == "right":
            col = self.cursor_col + 1
        else:
            return key
        self.cursor_x = max(0, min(maxcol - 1, col))
        self._invalidate()
        return None
