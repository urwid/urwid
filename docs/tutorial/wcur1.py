import urwid

class CursorPudding(urwid.Widget):
    _sizing = frozenset(['flow'])
    _selectable = True

    def __init__(self):
        self.cursor_col = 0

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        (maxcol,) = size
        num_pudding = maxcol / len("Pudding")
        cursor = None
        if focus:
            cursor = self.get_cursor_coords(size)
        return urwid.TextCanvas(["Pudding" * num_pudding], [], cursor, maxcol)

    def get_cursor_coords(self, size):
        (maxcol,) = size
        col = min(self.cursor_col, maxcol - 1)
        return col, 0

    def keypress(self, size, key):
        (maxcol, ) = size
        if key == 'left':
            col = self.cursor_col - 1
        elif key == 'right':
            col = self.cursor_col + 1
        else:
            return key
        self.cursor_x = max(0, min(maxcol - 1, col))
        self._invalidate()
