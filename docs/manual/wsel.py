from __future__ import annotations

import urwid


class SelectablePudding(urwid.Widget):
    _sizing = frozenset((urwid.FLOW,))
    _selectable = True

    def __init__(self) -> None:
        super().__init__()
        self.pudding = "pudding"

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        (maxcol,) = size
        num_pudding = maxcol // len(self.pudding)
        pudding = self.pudding
        if focus:
            pudding = pudding.upper()
        return urwid.TextCanvas([pudding.encode("utf-8") * num_pudding], maxcol=maxcol)

    def keypress(self, size: tuple[int], key: str) -> str | None:
        if len(key) > 1:
            return key

        if key.lower() in self.pudding:
            # remove letter from pudding
            n = self.pudding.index(key.lower())
            self.pudding = self.pudding[:n] + self.pudding[n + 1 :]
            if not self.pudding:
                self.pudding = "pudding"
            self._invalidate()
            return None

        return key
