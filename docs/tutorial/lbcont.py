import urwid

class Question(urwid.Edit):
    def __init__(self):
        super(Question, self).__init__(('I say', u"What is your name?\n"))

    def keypress(self, size, key):
        key = super(Question, self).keypress(size, key)
        if key == 'enter' and not self.edit_text:
            raise urwid.ExitMainLoop()
        return key

def answer(name):
    return urwid.Text(('I say', u"Nice to meet you, " + name + "\n"))

class ConversationListBox(urwid.ListBox):
    def __init__(self):
        super(ConversationListBox, self).__init__(
            urwid.SimpleFocusListWalker([Question()]))

    def keypress(self, size, key):
        key = super(ConversationListBox, self).keypress(size, key)
        if key != 'enter' or not hasattr(self.focus, 'edit_text'):
            return key
        # replace or add response below
        pos = self.focus_position
        self.body[pos + 1:pos + 2] = [answer(self.focus.edit_text)]
        if not self.body[pos + 2:pos + 3]: self.body.append(Question())
        self.set_focus(pos + 2)

palette = [('I say', 'default,bold', 'default', 'bold'),]
loop = urwid.MainLoop(ConversationListBox(), palette)
loop.run()
