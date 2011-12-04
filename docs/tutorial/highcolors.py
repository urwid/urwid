import urwid

def exit_on_q(input):
    if input in ('q', 'Q'):
        raise urwid.ExitMainLoop()

palette = [
    ('banner', '', '', '', '#ffa', '#60d'),
    ('streak', '', '', '', 'g50', '#60a'),
    ('inside', '', '', '', 'g38', '#808'),
    ('outside', '', '', '', 'g27', '#a06'),
    ('bg', '', '', '', 'g7', '#d06'),]

txt = urwid.Text(('banner', u" Hello World "), align='center')
map1 = urwid.AttrMap(txt, 'streak')
pile = urwid.Pile([
    urwid.AttrMap(urwid.Divider(), 'outside'),
    urwid.AttrMap(urwid.Divider(), 'inside'),
    map1,
    urwid.AttrMap(urwid.Divider(), 'inside'),
    urwid.AttrMap(urwid.Divider(), 'outside')])
fill = urwid.Filler(pile)
map2 = urwid.AttrMap(fill, 'bg')

loop = urwid.MainLoop(map2, palette, unhandled_input=exit_on_q)
loop.screen.set_terminal_properties(colors=256)
loop.run()
