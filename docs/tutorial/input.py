import urwid

def show_or_exit(input):
    if input in ('q', 'Q'):
        raise urwid.ExitMainLoop()
    txt.set_text(repr(input))

txt = urwid.Text(u"Hello World")
fill = urwid.Filler(txt, 'top')
loop = urwid.MainLoop(fill, unhandled_input=show_or_exit)
loop.run()
