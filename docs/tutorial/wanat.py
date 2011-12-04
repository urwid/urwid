import urwid


class Pudding(urwid.FlowWidget):

    def selectable(self):
        return False

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        (maxcol, ) = size
        num_pudding = maxcol / len("Pudding")
        return urwid.TextCanvas(["Pudding"*num_pudding], maxcol=maxcol)


class BoxPudding(urwid.BoxWidget):

    def selectable(self):
        return False

    def render(self, size, focus=False):
        (maxcol, maxrow) = size
        num_pudding = maxcol / len("Pudding")
        return urwid.TextCanvas(["Pudding"*num_pudding] * maxrow,
                                maxcol=maxcol)
