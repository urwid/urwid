import urwid

def exit_on_q(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

palette = [
    ('banner', '', '', '', '#ffa', '#60d'),
    ('streak', '', '', '', 'g50', '#60a'),
    ('inside', '', '', '', 'g38', '#808'),
    ('outside', '', '', '', 'g27', '#a06'),
    ('bg', '', '', '', 'g7', '#d06'),]

txt = urwid.Text(('banner', u" Hello World "), align='center')
div = urwid.Divider()
pile = urwid.Pile([
    urwid.AttrMap(div, 'outside'),
    urwid.AttrMap(div, 'inside'),
    urwid.AttrMap(txt, 'streak'),
    urwid.AttrMap(div, 'inside'),
    urwid.AttrMap(div, 'outside')])
fill = urwid.Filler(pile)
top = urwid.AttrMap(fill, 'bg')

loop = urwid.MainLoop(top, palette, unhandled_input=exit_on_q)
loop.screen.set_terminal_properties(colors=256)
loop.run()
