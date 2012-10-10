import urwid

class SelectablePudding(urwid.Widget):
    _sizing = frozenset(['flow'])
    _selectable = True

    def __init__(self):
        self.pudding = "pudding"

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        (maxcol,) = size
        num_pudding = maxcol / len(self.pudding)
        pudding = self.pudding
        if focus:
            pudding = pudding.upper()
        return urwid.TextCanvas([pudding * num_pudding],
            maxcol=maxcol)

    def keypress(self, size, key):
        (maxcol,) = size
        if len(key) > 1:
            return key
        if key.lower() in self.pudding:
            # remove letter from pudding
            n = self.pudding.index(key.lower())
            self.pudding = self.pudding[:n] + self.pudding[n+1:]
            if not self.pudding:
                self.pudding = "pudding"
            self._invalidate()
        else:
            return key
