import urwid

def exit_on_q(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

class Question(urwid.Edit):
    def __init__(self):
        super(Question, self).__init__(u"What is your name?\n")

    def keypress(self, size, key):
        key = super(Question, self).keypress(size, key)
        if key == 'enter':
            fill.body = urwid.Text(u"Nice to meet you,\n"
                + self.edit_text + u".\n\nPress Q to exit.")
            return None
        return key

fill = urwid.Filler(Question())
loop = urwid.MainLoop(fill, unhandled_input=exit_on_q)
loop.run()
