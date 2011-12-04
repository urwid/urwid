import urwid


class NewPudding(urwid.FlowWidget):

    def selectable(self):
        return False

    def rows(self, size, focus=False):
        w = self.display_widget(size, focus)
        return w.rows(size, focus)

    def render(self, size, focus=False):
        w = self.display_widget(size, focus)
        return w.render(size, focus)

    def display_widget(self, size, focus):
        (maxcol,) = size
        num_pudding = maxcol / len("Pudding")
        return urwid.Text("Pudding" * num_pudding)
