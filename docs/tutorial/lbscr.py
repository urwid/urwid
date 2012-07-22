import urwid

def show_all_input(keys, raw):
    """make keys pressed visible to the user"""
    show_key.set_text(u"Pressed: " + u" ".join([
        unicode(k) for k in keys]))
    return keys

def exit_on_cr(key):
    if key == 'enter':
        raise urwid.ExitMainLoop()

palette = [('header', 'white', 'black'),
           ('reveal focus', 'black', 'dark cyan', 'standout'),]

div = urwid.Divider(u"-")
content = urwid.SimpleListWalker([
    urwid.AttrMap(w, None, 'reveal focus') for w in [
        urwid.Text(u"This is a text string that is fairly long"),
        urwid.Divider(u"-"),] + [
        urwid.Text(u"Numbers %d" % i) for i in range(40)] + [
        urwid.Divider(u"-"),
        urwid.Text(u"The end."),]])
listbox = urwid.ListBox(content)
show_key = urwid.Text(u"", wrap='clip')
head = urwid.AttrMap(show_key, 'header')
top = urwid.Frame(listbox, head)
loop = urwid.MainLoop(top, palette, input_filter=show_all_input,
                      unhandled_input=exit_on_cr)
loop.run()
