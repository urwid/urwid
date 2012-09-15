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
streak = urwid.AttrMap(txt, 'streak')
div = urwid.Divider()
inside = urwid.AttrMap(div, 'inside')
outside = urwid.AttrMap(div, 'outside')
pile = urwid.Pile([outside, inside, streak, inside, outside])
fill = urwid.Filler(pile)
top = urwid.AttrMap(fill, 'bg')

loop = urwid.MainLoop(top, palette, unhandled_input=exit_on_q)
loop.screen.set_terminal_properties(colors=256)
loop.run()
