import urwid

def menu(title, choices):
    body = [urwid.Text(title), urwid.Divider()]
    for c in choices:
        button = urwid.Button(c)
        urwid.connect_signal(button, 'click', item_chosen, c)
        body.append(urwid.AttrMap(button, None, focus_map='reversed'))
    return urwid.ListBox(urwid.SimpleListWalker(body))

def item_chosen(self, choice):
    response = urwid.Text(u'You chose %s' % choice)
    loop.widget = urwid.Filler(response)
    # exit on the next input from user
    loop.unhandled_input = exit_program

def exit_program(key):
    raise urwid.ExitMainLoop()

choices = u'Chapman Cleese Gilliam Idle Jones Palin'.split()

loop = urwid.MainLoop(menu(u'Pythons', choices),
    palette=[('reversed', 'standout', '')])
loop.run()
