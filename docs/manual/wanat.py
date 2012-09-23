import urwid

class Pudding(urwid.Widget):
    _sizing = frozenset(['flow'])

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        (maxcol,) = size
        num_pudding = maxcol / len("Pudding")
        return urwid.TextCanvas(["Pudding" * num_pudding], maxcol=maxcol)


class BoxPudding(urwid.Widget):
    _sizing = frozenset(['box'])

    def render(self, size, focus=False):
        (maxcol, maxrow) = size
        num_pudding = maxcol / len("Pudding")
        return urwid.TextCanvas(["Pudding" * num_pudding] * maxrow,
                                maxcol=maxcol)
