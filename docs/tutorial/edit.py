import urwid

def do_reply(input):
    if input != 'enter':
        return
    if fill.body == ask:
        fill.body = urwid.Text(u"Nice to meet you,\n"+
            ask.edit_text+".")
        return True
    else:
        raise urwid.ExitMainLoop()

ask = urwid.Edit(u"What is your name?\n")
fill = urwid.Filler( ask )
loop = urwid.MainLoop(fill, unhandled_input=do_reply)
loop.run()
