import urwid

def show_all_input(input, raw):
    show_key.set_text(u"Pressed: " + u" ".join([
        unicode(i) for i in input]))
    return input

def exit_on_cr(input):
    if input == 'enter':
        raise urwid.ExitMainLoop()

palette = [('header', 'white', 'black'),
           ('reveal focus', 'black', 'dark cyan', 'standout'),]

content = urwid.SimpleListWalker([
    urwid.AttrMap(w, None, 'reveal focus') for w in [
        urwid.Text(u"This is a text string that is fairly long"),
        urwid.Divider(u"-"),] + [
        urwid.Text(u"Short one"),
        urwid.Text(u"Another"),
        urwid.Divider(u"-"), ] * 10 + [
        urwid.Text(u"What could be after this?"),
        urwid.Text(u"The end."),]])
listbox = urwid.ListBox(content)
show_key = urwid.Text(u"", wrap='clip')
head = urwid.AttrMap(show_key, 'header')
top = urwid.Frame(listbox, head)
loop = urwid.MainLoop(top, palette, input_filter=show_all_input,
                      unhandled_input=exit_on_cr)
loop.run()
