import urwid

class SelectableText(urwid.Text):
    def selectable(self):
        return True

    def keypress(self, size, key):
        return key
